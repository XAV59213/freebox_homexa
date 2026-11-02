"""Journal d'appels servi à la carte homexa-calls-card par WebSocket.

Les noms et numéros des correspondants ne sont jamais placés dans les
attributs d'état (visibles par tous les utilisateurs, automatisations et
exports) : la carte les demande avec la commande ``freebox_homexa/calls``.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN

CALL_LOG_MAX = 30
CALL_LOG_KEY = "calls_log"
MISSED_KEY = "missed"


def format_calls(call_list: list[dict[str, Any]] | None, limit: int = CALL_LOG_MAX) -> list[dict[str, Any]]:
    """Derniers appels, du plus récent au plus ancien (format de la carte)."""
    calls = sorted(
        (c for c in call_list or [] if isinstance(c, dict)),
        key=lambda c: c.get("datetime") or 0,
        reverse=True,
    )[:limit]
    return [
        {
            "name": c.get("name") or c.get("number") or "Inconnu",
            "number": c.get("number") or "",
            "type": c.get("type") or "",
            "datetime": dt_util.utc_from_timestamp(c["datetime"]).isoformat()
            if c.get("datetime")
            else None,
            "duration": c.get("duration") or 0,
            "new": bool(c.get("new", False)),
        }
        for c in calls
    ]


@callback
def async_register_calls_websocket_api(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_homexa_calls)


def _loaded_entries(hass: HomeAssistant) -> list[Any]:
    return [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if getattr(e, "runtime_data", None) is not None
    ]


@websocket_api.websocket_command(
    {
        vol.Required("type"): "freebox_homexa/calls",
        vol.Optional("entity_id"): str,
        vol.Optional("limit", default=CALL_LOG_MAX): vol.All(int, vol.Range(min=1, max=CALL_LOG_MAX)),
    }
)
@callback
def websocket_homexa_calls(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Liste des appels pour le capteur d'appels Freebox Homexa demandé.

    Réservé aux utilisateurs authentifiés (comme les commandes TNT) qui ont le
    droit de lire l'entité capteur visée.
    """
    entity_id = msg.get("entity_id")
    entries = _loaded_entries(hass)
    entry = None
    only_missed = False
    if entity_id:
        reg_entry = er.async_get(hass).async_get(entity_id)
        if reg_entry is None or reg_entry.platform != DOMAIN or reg_entry.domain != "sensor":
            connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Capteur d'appels Freebox Homexa introuvable")
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
            connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, "Ce capteur n'est pas un capteur d'appels")
            return
        entry = next((e for e in entries if e.entry_id == reg_entry.config_entry_id), None)
    elif len(entries) == 1:
        entry = entries[0]
        if not connection.user.is_admin:
            # Sans entité précisée : réservé aux administrateurs.
            raise Unauthorized()
    if entry is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Aucune Freebox Homexa chargée pour ce capteur")
        return
    call_list = entry.runtime_data.call_list or []
    if only_missed:
        call_list = [c for c in call_list if c.get("type") == MISSED_KEY and c.get("new", False)]
    connection.send_result(msg["id"], {"calls": format_calls(call_list, msg["limit"])})
