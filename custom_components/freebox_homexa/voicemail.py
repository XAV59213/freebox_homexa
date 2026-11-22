"""Messagerie vocale Freebox (API ``call/voicemail/``, hors freebox-api).

Les numéros et les identifiants bruts (le nom de fichier contient le numéro)
ne sortent pas : ni journal, ni attribut d'état, ni événement, ni URL. La carte
reçoit un jeton opaque et ne demande le numéro que si elle l'affiche.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import math
import re
import secrets
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from urllib.parse import quote, urljoin

import aiohttp
from aiohttp import ClientTimeout
from freebox_api.exceptions import HttpRequestError, InsufficientPermissionsError
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .availability import FreeboxReachableMixin
from .calls_ws import contact_label, event_caller_fields, events_include_number
from .const import DOMAIN
from .errors import api_error_code, is_permission_denied, is_shutdown_error

if TYPE_CHECKING:
    from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

_MESSAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")
_SAFE_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_API_MAJOR = re.compile(r"v?(\d+)")
_VERSION_CODES = frozenset({
    "invalid_request",
    "invalid_api_version",
    "unknown_api",
    "no_such_method",
    "unknown_endpoint",
    "not_found",
    "unsupported",
    "not_supported",
})
VOICEMAIL_LIST_LIMIT = 30
NEW_VOICEMAIL_EVENT = "freebox_homexa_new_voicemail"
_LIST_PATH = "call/voicemail/"
# Après un internal_error, on réessaie vite : la Freebox met souvent 3 minutes.
VOICEMAIL_RETRY_DELAYS = (15, 30, 60)
# Plusieurs échecs de suite, environ 10 minutes, avant de rendre le capteur indisponible.
VOICEMAIL_UNAVAILABLE_AFTER = 600
# Écritures (lu, suppression) : la forme d'identifiant, pas une longue attente.
# L'URL qui se termine par « .au » renvoie souvent internal_error ou invalid_id ;
# l'audio GET marche parce qu'un segment suit l'identifiant.
_WRITE_FORMS = (
    ("literal", False, ""),
    ("slash", False, "/"),
    ("dot", True, ""),
    ("dot-slash", True, "/"),
)
_TRANSIENT_CODES = frozenset({
    "internal_error",
    "timeout",
    "network",
    "network_error",
    "TimeoutError",
    "ServerTimeoutError",
    "ClientConnectorError",
    "ClientOSError",
    "ClientError",
    "OSError",
    "ConnectionError",
})


@dataclass(frozen=True, slots=True)
class VoicemailMessage:
    """Un message. ``phone_number`` ne doit jamais apparaître dans ``repr``."""

    id: str
    country_code: str
    phone_number: str
    date: int
    read: bool
    duration: int
    contact_name: str = ""

    def __repr__(self) -> str:
        return f"VoicemailMessage(read={self.read!r}, duration={self.duration!r})"


class VoicemailTokens:
    """Jetons HMAC par entrée. Le secret reste en mémoire et n'est pas journalisé."""

    def __init__(self) -> None:
        self._secret = secrets.token_bytes(32)
        self._by_token: dict[str, str] = {}
        self._by_id: dict[str, str] = {}

    def issue(self, message_id: str) -> str:
        known = self._by_id.get(message_id)
        if known is not None:
            return known
        token = hmac.new(self._secret, message_id.encode(), hashlib.sha256).hexdigest()
        occupant = self._by_token.get(token)
        if occupant is not None and occupant != message_id:
            token = hmac.new(
                self._secret,
                f"{len(self._by_id)}:{message_id}".encode(),
                hashlib.sha256,
            ).hexdigest()
        self._by_token[token] = message_id
        self._by_id[message_id] = token
        return token

    def resolve(self, token: str) -> str | None:
        return self._by_token.get(token)


class VoicemailEndpointError(Exception):
    """Réponse HTTP sans URL, identifiant ni numéro dans le message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def tokens_of(router: FreeboxRouter) -> VoicemailTokens:
    store = router.voicemail_tokens
    if isinstance(store, VoicemailTokens):
        return store
    store = VoicemailTokens()
    router.voicemail_tokens = store
    return store


def validated_voicemail_id(raw: object) -> str:
    """Refuse un identifiant vide, un chemin ou une chaîne inattendue."""
    if not isinstance(raw, str) or ".." in raw or _MESSAGE_ID.fullmatch(raw) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="voicemail_invalid_id",
        )
    return raw


def resolve_voicemail_token(router: FreeboxRouter, public_id: str) -> str:
    """Retrouve l'identifiant Freebox d'un jeton. Le nom de fichier ne passe pas."""
    token = validated_voicemail_id(public_id)
    raw = tokens_of(router).resolve(token)
    if raw is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="voicemail_invalid_id",
        )
    return validated_voicemail_id(raw)


def voicemail_api_path(message_id: str, suffix: str = "", *, encode_dot: bool = False) -> str:
    """Chemin ``call/voicemail/<id>``. Le point de ``.au`` reste littéral.

    ``encode_dot`` est le second essai quand la forme littérale répond 404.
    ``..``, ``/`` et tout caractère hors ``[A-Za-z0-9._-]`` sont refusés.
    """
    ident = validated_voicemail_id(message_id)
    quoted = quote(ident, safe="")
    if encode_dot:
        quoted = quoted.replace(".", "%2E")
    return f"call/voicemail/{quoted}{suffix}"


def _not_found(err: BaseException) -> bool:
    """404 HTTP ou Freebox. Un refus de droit ne change pas l'encodage du point."""
    if is_permission_denied(err):
        return False
    if isinstance(err, VoicemailEndpointError):
        return err.code == "not_found"
    code = api_error_code(err)
    if code in {"404", "not_found"}:
        return True
    status = getattr(err, "status", None)
    return status == 404 or re.search(r"\b404\b", str(err)) is not None


def _stamp(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    if value < 0:
        return 0
    return int(value)


def _message_identifier(raw: object) -> str | None:
    """Accepte une chaîne ou un id numérique. Un item illisible est ignoré."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        text = str(raw)
    elif isinstance(raw, float):
        if not math.isfinite(raw) or not raw.is_integer():
            return None
        text = str(int(raw))
    elif isinstance(raw, str):
        text = raw
    else:
        return None
    if not text or ".." in text or _MESSAGE_ID.fullmatch(text) is None:
        return None
    return text


def parse_voicemails(payload: object) -> list[VoicemailMessage]:
    """``GET call/voicemail/``. ``None`` est une liste vide, comme le SDK.

    Un élément illisible est ignoré. Il n'efface pas les autres messages.
    """
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("Invalid voicemail collection")
    messages: list[VoicemailMessage] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        ident = _message_identifier(item.get("id"))
        if ident is None:
            continue
        number = item.get("phone_number")
        country = item.get("country_code")
        read = item.get("read")
        phone = number if isinstance(number, str) else ""
        messages.append(
            VoicemailMessage(
                id=ident,
                country_code=country if isinstance(country, str) else "",
                phone_number=phone,
                date=_stamp(item.get("date")),
                read=read if isinstance(read, bool) else False,
                duration=_stamp(item.get("duration")),
                contact_name=contact_label(item.get("name"), phone),
            )
        )
    return messages


def messages_of(router: FreeboxRouter) -> list[VoicemailMessage]:
    return [item for item in router.voicemails if isinstance(item, VoicemailMessage)]


def _iso(stamp: int) -> str | None:
    if stamp <= 0:
        return None
    return dt_util.utc_from_timestamp(stamp).isoformat()


def public_message(
    message: VoicemailMessage, *, public_id: str, include_number: bool = False
) -> dict[str, object]:
    """Vue sans numéro ni identifiant Freebox, sauf demande explicite de la carte."""
    payload: dict[str, object] = {
        "id": public_id,
        "date": _iso(message.date),
        "duration": message.duration,
        "read": message.read,
    }
    if include_number:
        payload["phone_number"] = message.phone_number
    return payload


def public_messages(
    router: FreeboxRouter,
    messages: list[VoicemailMessage],
    *,
    include_number: bool = False,
) -> list[dict[str, object]]:
    store = tokens_of(router)
    return [
        public_message(item, public_id=store.issue(item.id), include_number=include_number)
        for item in messages
    ]


def public_summary(
    messages: list[VoicemailMessage], tokens: VoicemailTokens | None = None
) -> dict[str, object]:
    store = tokens if tokens is not None else VoicemailTokens()
    ordered = sorted(messages, key=lambda item: item.date, reverse=True)
    latest = _iso(ordered[0].date) if ordered else None
    return {
        "total": len(messages),
        "latest": latest,
        "messages": [
            public_message(item, public_id=store.issue(item.id))
            for item in ordered[:VOICEMAIL_LIST_LIMIT]
        ],
    }


def unread_count(messages: list[VoicemailMessage]) -> int:
    return sum(1 for item in messages if not item.read)


def voicemail_status(router: FreeboxRouter) -> dict[str, object]:
    """État visible. ``error`` reste posé au chargement initial, pas à chaque à-coup."""
    loading = router.voicemail_loading is True
    available = router.voicemail_available is not False
    supported = router.voicemail_supported
    has_list = bool(messages_of(router))
    cached = (
        router.voicemail_failure_since is not None
        and has_list
        and available
        and not loading
    )
    reveal_error = loading or not available or supported is False
    return {
        "available": available,
        "supported": supported is not False,
        "loading": loading,
        "cached": cached,
        "error": router.voicemail_error if reveal_error else None,
    }


def stored_error(err: BaseException) -> str:
    """Code Freebox affichable. Pas de chiffres, d'URL, d'identifiant ni de numéro."""
    if isinstance(err, VoicemailEndpointError) and _SAFE_CODE.fullmatch(err.code):
        return err.code
    status = getattr(err, "status", None)
    code = api_error_code(err)
    if code == "404" or status == 404:
        return "not_found"
    if isinstance(code, str) and _SAFE_CODE.fullmatch(code):
        return code
    name = type(err).__name__
    if _SAFE_CODE.fullmatch(name):
        return name
    return "error"


def _is_version_mismatch(err: BaseException) -> bool:
    """404, invalid_request, ou endpoint inconnu. Un refus de droit ne bascule pas."""
    if is_permission_denied(err):
        return False
    if isinstance(err, VoicemailEndpointError):
        return err.code in _VERSION_CODES
    code = api_error_code(err)
    if code in _VERSION_CODES or code == "404":
        return True
    status = getattr(err, "status", None)
    if status == 404:
        return True
    text = str(err).lower()
    if (
        "unknown endpoint" in text
        or "unknown_endpoint" in text
        or "unsupported" in text
        or "not supported" in text
    ):
        return True
    return re.search(r"\b404\b", text) is not None


def _http_status(payload: object) -> int | None:
    if isinstance(payload, (dict, list, str, bytes, bytearray)):
        return None
    status = getattr(payload, "status", None)
    if isinstance(status, bool) or not isinstance(status, int):
        return None
    return status


def _reject_status(payload: object) -> object:
    status = _http_status(payload)
    if status == 404:
        raise VoicemailEndpointError("not_found")
    if status is not None and status >= 400:
        raise VoicemailEndpointError("http_error")
    return payload


def _prefix_from_api_version(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("api version unavailable")
    raw = payload.get("api_version")
    if isinstance(raw, bool) or raw is None:
        raise ValueError("api version unavailable")
    if isinstance(raw, int):
        text = str(raw)
    elif isinstance(raw, float):
        if not math.isfinite(raw) or not raw.is_integer():
            raise ValueError("api version unavailable")
        text = str(int(raw))
    elif isinstance(raw, str):
        text = raw.strip()
    else:
        raise ValueError("api version unavailable")
    match = _API_MAJOR.match(text)
    if match is None:
        raise ValueError("api version unavailable")
    base = payload.get("api_base_url")
    if isinstance(base, str) and base.startswith("/") and ".." not in base and "://" not in base:
        root = base if base.endswith("/") else f"{base}/"
    else:
        root = "/api/"
    return f"{root}v{match.group(1)}/"


async def _json_body(response: object) -> object:
    if isinstance(response, dict):
        return response
    status = _http_status(response)
    reader = getattr(response, "json", None)
    try:
        if status is not None and status >= 400:
            raise ValueError("api version unavailable")
        if not callable(reader):
            raise ValueError("api version unavailable")
        data = reader()
        if hasattr(data, "__await__"):
            data = await data
        return data
    finally:
        release = getattr(response, "release", None)
        if callable(release):
            released = release()
            if hasattr(released, "__await__"):
                await released


async def _fetch_api_version(access: object) -> object:
    """``/api_version`` à la racine de l'hôte. ``urljoin`` avec un chemin absolu."""
    session = getattr(access, "session", None)
    base_url = getattr(access, "base_url", None)
    get = getattr(session, "get", None) if session is not None else None
    if callable(get) and isinstance(base_url, str) and base_url:
        timeout = getattr(access, "timeout", None)
        kwargs: dict[str, object] = {}
        if isinstance(timeout, int) and not isinstance(timeout, bool) and timeout > 0:
            kwargs["timeout"] = ClientTimeout(total=timeout)
        response = await get(urljoin(base_url, "/api_version"), **kwargs)
        return await _json_body(response)
    getter = getattr(access, "get", None)
    if not callable(getter):
        raise ValueError("api version unavailable")
    return await getter("/api_version")


async def _advertised_prefix(router: FreeboxRouter) -> str:
    cached = router.voicemail_advertised_prefix
    if isinstance(cached, str) and cached.startswith("/") and cached.endswith("/"):
        return cached
    prefix = _prefix_from_api_version(await _fetch_api_version(router._api.call._access))
    router.voicemail_advertised_prefix = prefix
    return prefix


def _safe_kind(err: BaseException) -> str:
    kind = type(err).__name__
    if not _SAFE_CODE.fullmatch(kind):
        return "Error"
    return kind


def _minimal_http_error(err: BaseException) -> HttpRequestError | InsufficientPermissionsError:
    """Chaîne une erreur dont le message est seulement le code, jamais le corps."""
    code = stored_error(err)
    text = f'Request failed (APIResponse: {{"error_code": "{code}"}})'
    if is_permission_denied(err):
        return InsufficientPermissionsError(text)
    return HttpRequestError(text)


async def _read_api_result(response: object) -> object:
    """Lit une réponse d'écriture. Le corps brut ne part ni dans l'exception ni au journal."""
    status = _http_status(response)
    content_type = getattr(response, "content_type", None)
    reader = getattr(response, "json", None)
    try:
        if content_type != "application/json" or not callable(reader):
            if status is not None and status >= 400:
                raise VoicemailEndpointError("http_error")
            return _reject_status(response)
        data = reader()
        if hasattr(data, "__await__"):
            data = await data
    finally:
        release = getattr(response, "release", None)
        if callable(release):
            released = release()
            if hasattr(released, "__await__"):
                await released
    if isinstance(data, dict) and data.get("success") is False:
        code = data.get("error_code")
        safe = code if isinstance(code, str) and _SAFE_CODE.fullmatch(code) else "error"
        text = f'Request failed (APIResponse: {{"error_code": "{safe}"}})'
        if safe == "insufficient_rights":
            raise InsufficientPermissionsError(text)
        raise HttpRequestError(text)
    if isinstance(data, dict) and "result" in data:
        return data.get("result")
    return data


class _NoJsonSession:
    """La session Freebox n'est pas disponible : repli sur ``access.put`` / ``delete``."""


_NO_JSON_SESSION = _NoJsonSession()


async def _invoke_json(access: object, method: str, path: str, payload: object) -> object:
    """PUT/DELETE avec ``Content-Type: application/json``. Sentinel si pas de session."""
    session = getattr(access, "session", None)
    base_url = getattr(access, "base_url", None)
    token = getattr(access, "session_token", None)
    verb = getattr(session, method, None) if session is not None else None
    if not callable(verb) or not isinstance(base_url, str) or not base_url:
        return _NO_JSON_SESSION
    if not isinstance(token, str) or not token:
        return _NO_JSON_SESSION
    headers = {"X-Fbx-App-Auth": token, "Content-Type": "application/json"}
    body = json.dumps(payload) if isinstance(payload, dict) else None
    kwargs: dict[str, object] = {"headers": headers, "data": body}
    timeout = getattr(access, "timeout", None)
    if isinstance(timeout, int) and not isinstance(timeout, bool) and timeout > 0:
        kwargs["timeout"] = ClientTimeout(total=timeout)
    response = await verb(urljoin(base_url, path), **kwargs)
    return await _read_api_result(response)


async def _invoke(access: object, method: str, path: str, payload: object) -> object:
    if method != "get":
        sent = await _invoke_json(access, method, path, payload)
        if sent is not _NO_JSON_SESSION:
            return sent
    action = getattr(access, method, None)
    if not callable(action):
        raise VoicemailEndpointError("http_error")
    if method == "get":
        result = await action(path)
    else:
        result = await action(path, payload)
    return _reject_status(result)


def _with_prefix(prefix: str, relative: str) -> str:
    if not prefix:
        return relative
    return f"{prefix}{relative}"


async def async_voicemail_exchange(
    router: FreeboxRouter, method: str, relative: str, payload: object = None
) -> object:
    """Appelle call/voicemail. Au premier 404, rejoue la version annoncée.

    ``""`` veut dire que le chemin relatif de la session (v6) a déjà répondu :
    un 404 de lecture plus tard ne change plus de version et ne conclut pas
    que la messagerie n'existe pas. Une écriture (PUT/DELETE) qui répond
    404 ou endpoint inconnu sur ce préfixe est rejouée une fois sur la
    version annoncée : la liste et l'audio existent souvent en v6, pas les
    écritures. La variante qui répond est mémorisée à part.
    """
    access = router._api.call._access
    write = method != "get"
    remembered = router.voicemail_write_prefix if write and router.voicemail_write_prefix else router.voicemail_api_prefix
    first = relative if remembered is None else _with_prefix(remembered, relative)
    try:
        result = await _invoke(access, method, first, payload)
    except Exception as err:
        if not _is_version_mismatch(err) or (remembered is not None and not write):
            raise
        if write and remembered == router.voicemail_write_prefix and router.voicemail_write_prefix:
            raise
        try:
            advertised = await _advertised_prefix(router)
            alternative = _with_prefix(advertised, relative)
            if alternative == first:
                raise err
            result = await _invoke(access, method, alternative, payload)
        except Exception as fallback_err:
            if (
                fallback_err is err
                or _is_version_mismatch(fallback_err)
                or isinstance(fallback_err, ValueError)
            ):
                raise err
            raise
        if write:
            router.voicemail_write_prefix = advertised
        else:
            router.voicemail_api_prefix = advertised
        return result
    if remembered is None and not write:
        router.voicemail_api_prefix = ""
    return result


async def async_voicemail_by_id(
    router: FreeboxRouter,
    method: str,
    ident: str,
    suffix: str = "",
    payload: object = None,
) -> object:
    """Point littéral, puis ``%2E`` si cette forme répond 404. La forme utile est mémorisée."""
    async with router.voicemail_refresh_lock:
        return await _voicemail_by_id(router, method, ident, suffix, payload)


async def _voicemail_by_id(
    router: FreeboxRouter,
    method: str,
    ident: str,
    suffix: str,
    payload: object,
) -> object:
    if "." not in ident:
        order = (False,)
    elif router.voicemail_encode_dot is True:
        order = (True, False)
    else:
        order = (False, True)
    last: BaseException | None = None
    for index, encode in enumerate(order):
        path = voicemail_api_path(ident, suffix, encode_dot=encode)
        try:
            result = await async_voicemail_exchange(router, method, path, payload)
        except Exception as err:
            last = err
            if index + 1 == len(order) or not _not_found(err):
                raise
            continue
        if "." in ident:
            router.voicemail_encode_dot = encode
        return result
    if last is not None:
        raise last
    raise VoicemailEndpointError("not_found")


def _announce(router: FreeboxRouter, messages: list[VoicemailMessage]) -> None:
    """Le premier relevé réussi sert de référence : pas d'événement au démarrage."""
    current = {item.id for item in messages}
    known = router.voicemail_seen
    router.voicemail_seen = current
    if known is None:
        return
    store = tokens_of(router)
    for item in messages:
        if item.id in known or item.read:
            continue
        router.hass.bus.async_fire(
            NEW_VOICEMAIL_EVENT,
            {
                "entry_id": router.entry_id,
                "id": store.issue(item.id),
                "duration": item.duration,
                "date": _iso(item.date),
                **event_caller_fields(
                    router.call_list if isinstance(router.call_list, list) else None,
                    number=item.phone_number,
                    stamp=item.date,
                    own_name=item.contact_name,
                    include_number=events_include_number(router),
                ),
            },
        )


def _signal(router: FreeboxRouter) -> None:
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    async_dispatcher_send(router.hass, router.signal_sensor_update)


def _mark_unsupported(router: FreeboxRouter, err: BaseException) -> None:
    """La session et la version annoncée ont répondu 404 ou endpoint inconnu."""
    code = stored_error(err)
    router.voicemail_supported = False
    router.voicemail_available = True
    router.voicemail_error = code
    router.voicemails = []
    kind = type(err).__name__
    if not _SAFE_CODE.fullmatch(kind):
        kind = "Error"
    if router.voicemail_failure_logged:
        _LOGGER.debug("Messagerie vocale non prise en charge (%s, %s)", kind, code)
    else:
        router.voicemail_failure_logged = True
        _LOGGER.info("Messagerie vocale non prise en charge (%s, %s)", kind, code)
    _signal(router)


def _unsupported(router: FreeboxRouter) -> None:
    if router.voicemail_supported is False:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="voicemail_unsupported",
        )


def _note_failure(router: FreeboxRouter, err: BaseException) -> None:
    code = stored_error(err)
    router.voicemail_error = code
    kind = type(err).__name__
    if not _SAFE_CODE.fullmatch(kind):
        kind = "Error"
    if router.voicemail_failure_logged:
        _LOGGER.debug("Messagerie vocale Freebox indisponible (%s, %s)", kind, code)
        return
    router.voicemail_failure_logged = True
    _LOGGER.warning("Messagerie vocale Freebox indisponible (%s, %s)", kind, code)


def _is_transient(err: BaseException) -> bool:
    """internal_error, délai ou réseau. Un 404 ou un refus de droit ne l'est pas."""
    if is_permission_denied(err) or _is_version_mismatch(err):
        return False
    if isinstance(err, (TimeoutError, aiohttp.ClientError, OSError)):
        return True
    code = stored_error(err)
    if code in _TRANSIENT_CODES:
        return True
    name = type(err).__name__.lower()
    return "timeout" in name or "network" in name


def cancel_voicemail_retry(router: FreeboxRouter) -> None:
    unsub = router.voicemail_retry_unsub
    router.voicemail_retry_unsub = None
    if callable(unsub):
        unsub()
    mark = getattr(router, "voicemail_mark_unsub", None)
    router.voicemail_mark_unsub = None
    if callable(mark):
        mark()


def _schedule_voicemail_retry(router: FreeboxRouter) -> None:
    """15 s, puis 30 s, puis 60 s. Un minuteur déjà posé n'est pas remplacé."""
    if router.closing or router.voicemail_retry_unsub is not None:
        return
    index = router.voicemail_retry_index
    if index < 0:
        index = 0
    delay = VOICEMAIL_RETRY_DELAYS[min(index, len(VOICEMAIL_RETRY_DELAYS) - 1)]
    router.voicemail_retry_index = index + 1

    async def _run(_now: object) -> None:
        router.voicemail_retry_unsub = None
        if router.closing:
            return
        await async_refresh_voicemails(router, force=True)

    router.voicemail_retry_unsub = async_call_later(router.hass, delay, _run)


def request_voicemail_refresh(router: object) -> None:
    """Relit la messagerie tout de suite, par exemple après un appel manqué."""
    from .router import FreeboxRouter

    if not isinstance(router, FreeboxRouter):
        return
    if router.closing or router.voicemail_supported is not True:
        return
    router.hass.async_create_task(async_refresh_voicemails(router, force=True))


def _snapshot(router: FreeboxRouter) -> tuple[object, ...]:
    return (
        router.voicemail_available,
        router.voicemail_supported,
        router.voicemail_loading,
        router.voicemail_error,
        router.voicemail_stale,
        tuple((item.id, item.read, item.date) for item in messages_of(router)),
    )


def _publish(router: FreeboxRouter, before: tuple[object, ...]) -> None:
    """N'écrit l'état que si la partie visible a changé."""
    if _snapshot(router) != before:
        _signal(router)


def _note_transient(router: FreeboxRouter, err: BaseException) -> None:
    """Panne passagère. L'état visible ne bouge qu'au démarrage ou après 10 minutes.

    Tant qu'une liste existe et que les échecs durent moins d'environ 10 minutes,
    on ne pose ni ``voicemail_error`` ni ``voicemail_stale`` : chaque bascule
    réécrivait le capteur, la carte rappelait ``call/voicemail/``, et la Freebox
    répondait encore ``internal_error``. Le journal de ces à-coups reste en debug.
    """
    now = time.monotonic()
    if router.voicemail_failure_since is None:
        router.voicemail_failure_since = now
    code = stored_error(err)
    kind = _safe_kind(err)
    elapsed = now - router.voicemail_failure_since
    past = elapsed >= VOICEMAIL_UNAVAILABLE_AFTER
    has_list = bool(messages_of(router))
    known = router.voicemail_supported is True or has_list
    _LOGGER.debug(
        "Messagerie vocale Freebox momentanément indisponible (%s, %s)", kind, code
    )
    before = _snapshot(router)
    if not past:
        if not known and (
            router.voicemail_loading is not True or router.voicemail_error != code
        ):
            router.voicemail_loading = True
            router.voicemail_error = code
            router.voicemail_available = True
            router.voicemail_stale = False
            _publish(router, before)
        _schedule_voicemail_retry(router)
        return
    router.voicemail_loading = False
    router.voicemail_error = code
    router.voicemail_stale = has_list
    became_unavailable = router.voicemail_available is not False
    router.voicemail_available = False
    if became_unavailable or not router.voicemail_outage_logged:
        router.voicemail_outage_logged = True
        _LOGGER.warning("Messagerie vocale Freebox indisponible (%s, %s)", kind, code)
    _publish(router, before)
    _schedule_voicemail_retry(router)


def _keep_snapshot(router: FreeboxRouter, err: BaseException) -> None:
    """Une panne qui n'est pas un accès réseau garde la liste, sans relance rapide."""
    code = stored_error(err)
    router.voicemail_error = code
    router.voicemail_stale = True
    kind = type(err).__name__
    if not _SAFE_CODE.fullmatch(kind):
        kind = "Error"
    if router.voicemail_failure_logged:
        _LOGGER.debug("Messagerie vocale Freebox momentanément indisponible (%s, %s)", kind, code)
    else:
        router.voicemail_failure_logged = True
        _LOGGER.warning(
            "Messagerie vocale Freebox momentanément indisponible (%s, %s)", kind, code
        )
    _signal(router)


def _list_due(router: FreeboxRouter) -> bool:
    """N'empile pas un relevé sur une relance déjà posée après un échec.

    Un succès n'impose pas d'attente : le poll (40 s) et un second relevé
    restent possibles. Seule une série d'échecs espace les essais.
    """
    if router.voicemail_retry_unsub is not None:
        return False
    if router.voicemail_failure_since is None:
        return True
    last = router.voicemail_last_attempt
    if last is None:
        return True
    index = router.voicemail_retry_index - 1
    if index < 0:
        index = 0
    wait = VOICEMAIL_RETRY_DELAYS[min(index, len(VOICEMAIL_RETRY_DELAYS) - 1)]
    return time.monotonic() - last >= wait


async def async_refresh_voicemails(router: FreeboxRouter, *, force: bool = False) -> None:
    """Relevé isolé. Un refus de droit ``calls`` rend le capteur indisponible.

    Un 404, ``invalid_request`` ou endpoint inconnu, au premier essai et sur la
    version annoncée, veut dire que la Freebox n'a pas de messagerie.
    Après un relevé réussi, une panne passagère garde les messages.
    ``force`` est réservé au minuteur de relance : le poll, la carte et un
    appel manqué n'ajoutent pas une requête si une relance est déjà posée
    ou si le dernier essai a moins de 15 s.
    """
    if not force and not _list_due(router):
        return
    async with router.voicemail_refresh_lock:
        if not force and not _list_due(router):
            return
        await _refresh_voicemails(router)


async def _refresh_voicemails(router: FreeboxRouter) -> None:
    if router.voicemail_supported is False:
        router.voicemail_available = True
        router.voicemail_loading = False
        return
    before = _snapshot(router)
    was_down = router.voicemail_available is False
    was_loading = router.voicemail_loading is True
    had_failure = router.voicemail_failure_since is not None
    router.voicemail_last_attempt = time.monotonic()
    try:
        payload = await async_voicemail_exchange(router, "get", _LIST_PATH)
        if payload is None and router.voicemail_supported is True and messages_of(router):
            return
        found = parse_voicemails(payload)
    except Exception as err:
        if router.closing and is_shutdown_error(err, router):
            return
        if is_permission_denied(err):
            router.note_permission("calls", err)
            router.voicemail_available = False
            router.voicemail_loading = False
            _note_failure(router, err)
            _publish(router, before)
            return
        if _is_transient(err):
            _note_transient(router, err)
            return
        if router.voicemail_supported is True:
            _keep_snapshot(router, err)
            return
        if _is_version_mismatch(err):
            _mark_unsupported(router, err)
            return
        router.note_permission("calls", err)
        router.voicemail_available = False
        router.voicemail_loading = False
        _note_failure(router, err)
        _publish(router, before)
        return
    _announce(router, found)
    router.voicemails = found
    if was_down:
        _LOGGER.warning("Messagerie vocale Freebox de nouveau disponible")
    elif was_loading:
        _LOGGER.info("Messagerie vocale Freebox de nouveau disponible")
    elif had_failure:
        _LOGGER.debug("Messagerie vocale Freebox de nouveau disponible")
    router.voicemail_supported = True
    router.voicemail_available = True
    router.voicemail_loading = False
    router.voicemail_stale = False
    router.voicemail_failure_since = None
    router.voicemail_retry_index = 0
    router.voicemail_error = None
    router.voicemail_failure_logged = False
    router.voicemail_outage_logged = False
    cancel_voicemail_retry(router)
    # Le journal d'appels reste prioritaire : on ne lève le Repair que s'il va bien.
    if router.calls_available is not False:
        router.note_permission("calls")
    _publish(router, before)


async def _deny(router: FreeboxRouter, err: Exception) -> None:
    router.note_permission("calls", err)
    router.voicemail_available = False
    _note_failure(router, err)
    _signal(router)
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="voicemail_permission",
    ) from err


def _http_status_label(err: BaseException) -> str:
    status = getattr(err, "status", None)
    if isinstance(status, bool) or not isinstance(status, int):
        return "-"
    return str(status)


def _log_write(action: str, form: str, err: BaseException) -> None:
    """Méthode, forme d'identifiant, statut HTTP et code. Jamais le chemin réel."""
    _LOGGER.warning(
        "Écriture messagerie %s call/voicemail/{id} forme=%s statut=%s code=%s",
        action,
        form,
        _http_status_label(err),
        stored_error(err),
    )


def _try_another_write_form(err: BaseException) -> bool:
    """internal_error et invalid_id dépendent de la forme de l'identifiant."""
    if is_permission_denied(err):
        return False
    code = stored_error(err)
    return code in {"internal_error", "invalid_id", "invalid_request", "not_found"} or _is_transient(err)


def _write_error(err: BaseException) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="voicemail_write_failed",
        translation_placeholders={"code": stored_error(err)},
    )


async def _write_voicemail(
    router: FreeboxRouter,
    method: str,
    ident: str,
    payload: object = None,
) -> None:
    """PUT/DELETE. Essaie la barre finale et le point encodé si l'id est refusé.

    Le corps et le chemin ne sont pas journalisés : l'identifiant contient le numéro.
    """
    last: BaseException | None = None
    async with router.voicemail_refresh_lock:
        for form, encode, suffix in _WRITE_FORMS:
            path = voicemail_api_path(ident, suffix, encode_dot=encode)
            try:
                await async_voicemail_exchange(router, method, path, payload)
            except HomeAssistantError:
                raise
            except Exception as err:
                last = err
                _log_write(method, form, err)
                if is_permission_denied(err):
                    await _deny(router, err)
                if _try_another_write_form(err):
                    continue
                raise _write_error(err) from _minimal_http_error(err)
            if encode:
                router.voicemail_encode_dot = True
            return
    if last is not None:
        raise _write_error(last) from _minimal_http_error(last)


def schedule_mark_read_retry(router: FreeboxRouter, message_id: str) -> None:
    """Relance le marquage lu sans faire échouer une lecture déjà commencée."""

    async def _run(_now: object) -> None:
        if router.closing:
            return
        try:
            await async_mark_voicemail_read(router, message_id)
        except Exception as err:
            _LOGGER.warning(
                "Marquage lu reporté toujours en échec (%s, %s)",
                _safe_kind(err),
                stored_error(err) if not isinstance(err, HomeAssistantError) else (
                    err.translation_key or "error"
                ),
            )

    previous = getattr(router, "voicemail_mark_unsub", None)
    if callable(previous):
        previous()
    router.voicemail_mark_unsub = async_call_later(
        router.hass, VOICEMAIL_RETRY_DELAYS[0], _run
    )


async def async_mark_voicemail_read(router: FreeboxRouter, message_id: str) -> None:
    _unsupported(router)
    ident = resolve_voicemail_token(router, message_id)
    await _write_voicemail(router, "put", ident, {"read": True})
    before = _snapshot(router)
    router.voicemails = [
        replace(item, read=True) if item.id == ident else item for item in messages_of(router)
    ]
    _publish(router, before)
    await async_refresh_voicemails(router, force=True)


async def async_delete_voicemail(router: FreeboxRouter, message_id: str) -> None:
    _unsupported(router)
    ident = resolve_voicemail_token(router, message_id)
    await _write_voicemail(router, "delete", ident)
    before = _snapshot(router)
    router.voicemails = [item for item in messages_of(router) if item.id != ident]
    _publish(router, before)
    await async_refresh_voicemails(router, force=True)


async def async_voicemail_audio(router: FreeboxRouter, message_id: str) -> bytes:
    _unsupported(router)
    ident = resolve_voicemail_token(router, message_id)
    try:
        payload = await async_voicemail_by_id(router, "get", ident, "/audio_file")
    except HomeAssistantError:
        raise
    except Exception as err:
        if is_permission_denied(err):
            await _deny(router, err)
        raise
    return await _audio_bytes(payload)


async def _audio_bytes(payload: object) -> bytes:
    """``_access.get`` renvoie la réponse brute quand le type n'est pas JSON."""
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    read = getattr(payload, "read", None)
    if not callable(read):
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_audio"
        )
    body = await read()
    release = getattr(payload, "release", None)
    if callable(release):
        released = release()
        if hasattr(released, "__await__"):
            await released
    if isinstance(body, str):
        return body.encode()
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    raise HomeAssistantError(
        translation_domain=DOMAIN, translation_key="voicemail_audio"
    )


class FreeboxVoicemailSensor(FreeboxReachableMixin, SensorEntity):
    """Nombre de messages non lus. Les attributs n'ont ni numéro ni identifiant brut."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "voicemail_unread"

    def __init__(self, router: FreeboxRouter) -> None:
        self._router = router
        self._attr_unique_id = f"{router.mac} Messages vocaux non lus"
        self._attr_device_info = router.device_info

    @property
    def available(self) -> bool:
        return super().available and self._router.voicemail_available is not False

    @property
    def native_value(self) -> int | None:
        if not self.available:
            return None
        if self._router.voicemail_supported is False:
            return 0
        return unread_count(messages_of(self._router))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        summary = public_summary(messages_of(self._router), tokens_of(self._router))
        summary["voicemail"] = True
        summary["voicemail_available"] = self._router.voicemail_available is not False
        summary["voicemail_supported"] = self._router.voicemail_supported
        summary["voicemail_error"] = self._router.voicemail_error
        summary["voicemail_stale"] = self._router.voicemail_stale is True
        summary["voicemail_loading"] = self._router.voicemail_loading is True
        return summary

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._router.signal_sensor_update, self._refresh
            )
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()


def async_setup_voicemail_sensor(
    router: FreeboxRouter, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([FreeboxVoicemailSensor(router)], True)
