"""Journal d'appels servi à la carte homexa-calls-card par WebSocket.

Les noms et numéros des correspondants ne sont jamais placés dans les
attributs d'état (visibles par tous les utilisateurs, automatisations et
exports) : la carte les demande avec la commande ``freebox_homexa/calls``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import math
import re
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import ERR_INVALID_FORMAT, ERR_NOT_FOUND
from homeassistant.components.websocket_api.decorators import websocket_command
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import CONF_EVENT_INCLUDE_NUMBER, DOMAIN, option_enabled

if TYPE_CHECKING:
    from .router import FreeboxConfigEntry

CALL_LOG_MAX = 30
CALL_LOG_KEY = "calls_log"
MISSED_KEY = "missed"
MISSED_CALL_EVENT = "freebox_homexa_missed_call"
UNKNOWN_CALLER = "Inconnu"
_CALL_MATCH_SECONDS = 180
_CALL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


def _timestamp(call: Mapping[str, object]) -> float:
    """Validate the SDK's Unix timestamp before sorting or formatting it."""
    value = call.get("datetime")
    if not value:
        return 0
    if not isinstance(value, (int, float)):
        raise ValueError("Invalid call timestamp")
    return float(value)


def _call_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def contact_label(raw_name: object, number: str) -> str:
    """Nom de contact. Un libellé vide ou égal au numéro n'est pas un contact."""
    if not isinstance(raw_name, str):
        return ""
    name = raw_name.strip()
    if not name or name == number:
        return ""
    named = _digits(name)
    numbered = _digits(number)
    if named and numbered and named == numbered:
        return ""
    return name


def caller_fields(name: str, number: str, *, include_number: bool) -> dict[str, object]:
    """``caller`` est le nom, sinon le numéro si l'option l'autorise, sinon « Inconnu ».

    ``number`` est omis quand l'option est désactivée. Le numéro n'est jamais recopié dans ``name``.
    """
    contact = name.strip()
    if contact:
        caller = contact
        shown = contact
    elif include_number and number:
        caller = number
        shown = UNKNOWN_CALLER
    else:
        caller = UNKNOWN_CALLER
        shown = UNKNOWN_CALLER
    payload: dict[str, object] = {"caller": caller, "name": shown}
    if include_number and number:
        payload["number"] = number
    return payload


def events_include_number(router: object) -> bool:
    """Option d'entrée. Absente = désactivée, les événements n'emportent pas le numéro."""
    hass = getattr(router, "hass", None)
    entry_id = getattr(router, "entry_id", None)
    entries = getattr(getattr(hass, "config_entries", None), "async_get_entry", None)
    if not isinstance(entry_id, str) or not callable(entries):
        return False
    entry = entries(entry_id)
    if entry is None:
        return False
    return option_enabled(entry, CONF_EVENT_INCLUDE_NUMBER, False)


def match_caller(
    call_list: Sequence[Mapping[str, object]] | None,
    *,
    number: str,
    stamp: int,
    own_name: str,
) -> tuple[str, str]:
    """Nom et numéro : champs du message, sinon l'appel du journal au même numéro ou à la même heure."""
    own = contact_label(own_name, number)
    chosen_name = own
    chosen_number = number
    best: tuple[int, int, int] | None = None
    for call in call_list or []:
        if not isinstance(call, Mapping):
            continue
        raw_number = call.get("number")
        call_number = raw_number if isinstance(raw_number, str) else ""
        call_name = contact_label(call.get("name"), call_number)
        raw_stamp = call.get("datetime")
        delta: int | None = None
        if (
            stamp > 0
            and isinstance(raw_stamp, (int, float))
            and not isinstance(raw_stamp, bool)
            and math.isfinite(float(raw_stamp))
        ):
            delta = abs(int(raw_stamp) - stamp)
        same = bool(number and call_number and _digits(number) == _digits(call_number))
        close = delta is not None and delta <= _CALL_MATCH_SECONDS
        if not same and not (close and not number):
            continue
        rank = (0 if same else 1, delta if delta is not None else 10**9, 0 if call_name else 1)
        if best is not None and rank >= best:
            continue
        best = rank
        chosen_name = call_name or own
        if call_number and (same or not number):
            chosen_number = call_number
    return chosen_name, chosen_number


def event_caller_fields(
    call_list: Sequence[Mapping[str, object]] | None,
    *,
    number: str,
    stamp: int,
    own_name: str,
    include_number: bool,
) -> dict[str, object]:
    name, resolved = match_caller(call_list, number=number, stamp=stamp, own_name=own_name)
    return caller_fields(name, resolved, include_number=include_number)


def _call_identity(call: Mapping[str, object]) -> str | None:
    """Clé interne de dédoublonnage. Elle n'est pas mise dans l'événement."""
    raw = call.get("id")
    text = ""
    if isinstance(raw, bool):
        text = ""
    elif isinstance(raw, int):
        text = str(raw)
    elif isinstance(raw, float) and math.isfinite(raw) and raw.is_integer():
        text = str(int(raw))
    elif isinstance(raw, str):
        text = raw
    if text and ".." not in text and _CALL_ID.fullmatch(text):
        return text
    number = call.get("number") if isinstance(call.get("number"), str) else ""
    kind = call.get("type") if isinstance(call.get("type"), str) else ""
    stamp = call.get("datetime")
    if not number and not isinstance(stamp, (int, float)):
        return None
    material = f"{kind}|{stamp}|{number}".encode()
    return hashlib.sha256(material).hexdigest()


def _call_date(call: Mapping[str, object]) -> str | None:
    stamp = call.get("datetime")
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
        return None
    if not math.isfinite(float(stamp)) or stamp <= 0:
        return None
    return dt_util.utc_from_timestamp(int(stamp)).isoformat()


def announce_missed_calls(router: object) -> None:
    """Un événement par nouvel appel manqué. Le premier relevé réussi ne notifie pas."""
    calls = getattr(router, "call_list", None)
    missed: list[tuple[str, Mapping[str, object]]] = []
    if isinstance(calls, list):
        for call in calls:
            if not isinstance(call, Mapping) or call.get("type") != MISSED_KEY:
                continue
            ident = _call_identity(call)
            if ident is None:
                continue
            missed.append((ident, call))
    current = {ident for ident, _call in missed}
    known = getattr(router, "missed_call_seen", None)
    setattr(router, "missed_call_seen", current)
    if not isinstance(known, set):
        return
    include = events_include_number(router)
    hass = getattr(router, "hass", None)
    fire = getattr(getattr(hass, "bus", None), "async_fire", None)
    if not callable(fire):
        return
    entry_id = getattr(router, "entry_id", "")
    for ident, call in missed:
        if ident in known:
            continue
        raw_number = call.get("number")
        number = raw_number if isinstance(raw_number, str) else ""
        payload: dict[str, object] = {
            "entry_id": entry_id if isinstance(entry_id, str) else "",
            "date": _call_date(call),
        }
        payload.update(
            caller_fields(contact_label(call.get("name"), number), number, include_number=include)
        )
        fire(MISSED_CALL_EVENT, payload)


def format_calls(
    call_list: Sequence[Mapping[str, object]] | None,
    limit: int = CALL_LOG_MAX,
    *,
    include_number: bool = False,
) -> list[dict[str, object]]:
    """Derniers appels, du plus récent au plus ancien (format de la carte).

    Le numéro n'est jamais recopié dans le nom. Il n'est envoyé que si la carte
    demande ``include_number``.
    """
    calls = sorted(
        (c for c in call_list or [] if isinstance(c, dict)),
        key=_timestamp,
        reverse=True,
    )[:limit]
    rows: list[dict[str, object]] = []
    for call in calls:
        number = _call_text(call.get("number"))
        name = _call_text(call.get("name")).strip()
        if not name or name == number:
            name = "Inconnu"
        rows.append(
            {
                "name": name,
                "number": number if include_number else "",
                "type": call.get("type") or "",
                "datetime": dt_util.utc_from_timestamp(_timestamp(call)).isoformat()
                if call.get("datetime")
                else None,
                "duration": call.get("duration") or 0,
                "new": bool(call.get("new", False)),
            }
        )
    return rows


@callback
def async_register_calls_websocket_api(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_homexa_calls)


def _loaded_entries(hass: HomeAssistant) -> list[FreeboxConfigEntry]:
    return [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if getattr(e, "runtime_data", None) is not None
    ]


@websocket_command(
    {
        "type": "freebox_homexa/calls",
        "entity_id": str,
        "limit": vol.All(int, vol.Range(min=1, max=CALL_LOG_MAX)),
        vol.Optional("include_number"): bool,
    }
)
@callback
def websocket_homexa_calls(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, object]
) -> None:
    """Liste des appels pour le capteur d'appels Freebox Homexa demandé.

    Réservé aux utilisateurs authentifiés (comme les commandes TNT) qui ont le
    droit de lire l'entité capteur visée.
    """
    message_id = msg["id"]
    entity_id = msg.get("entity_id")
    limit = msg.get("limit", CALL_LOG_MAX)
    if not isinstance(message_id, int):
        raise vol.Invalid("Invalid message id", path=["id"])
    if entity_id is not None and not isinstance(entity_id, str):
        raise vol.Invalid("Invalid entity id", path=["entity_id"])
    if not isinstance(limit, int) or not 1 <= limit <= CALL_LOG_MAX:
        raise vol.Invalid("Invalid call limit", path=["limit"])
    include_number = msg.get("include_number", False)
    if not isinstance(include_number, bool):
        include_number = False
    entries = _loaded_entries(hass)
    entry = None
    only_missed = False
    if entity_id:
        reg_entry = er.async_get(hass).async_get(entity_id)
        if reg_entry is None or reg_entry.platform != DOMAIN or reg_entry.domain != "sensor":
            connection.send_error(message_id, ERR_NOT_FOUND, "Capteur d'appels Freebox Homexa introuvable")
            return
        from homeassistant.auth.permissions.const import POLICY_READ

        if not connection.user.permissions.check_entity(entity_id, POLICY_READ):
            raise Unauthorized(entity_id=entity_id)
        unique_id = str(reg_entry.unique_id or "")
        if unique_id.endswith("Derniers appels Freebox"):
            only_missed = False
        elif unique_id.endswith("Appels manqués Freebox"):
            only_missed = True
        else:
            connection.send_error(message_id, ERR_INVALID_FORMAT, "Ce capteur n'est pas un capteur d'appels")
            return
        entry = next((e for e in entries if e.entry_id == reg_entry.config_entry_id), None)
    elif len(entries) == 1:
        entry = entries[0]
        if not connection.user.is_admin:
            # Sans entité précisée : réservé aux administrateurs.
            raise Unauthorized()
    if entry is None:
        connection.send_error(message_id, ERR_NOT_FOUND, "Aucune Freebox Homexa chargée pour ce capteur")
        return
    call_list = entry.runtime_data.call_list or []
    if only_missed:
        call_list = [c for c in call_list if c.get("type") == MISSED_KEY and c.get("new", False)]
    connection.send_result(
        message_id, {"calls": format_calls(call_list, limit, include_number=include_number)}
    )
