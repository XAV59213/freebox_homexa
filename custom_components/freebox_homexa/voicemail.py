"""Messagerie vocale Freebox (API ``call/voicemail/``, hors freebox-api).

Les numéros et les identifiants bruts (le nom de fichier contient le numéro)
ne sortent pas : ni journal, ni attribut d'état, ni événement, ni URL. La carte
reçoit un jeton opaque et ne demande le numéro que si elle l'affiche.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import hmac
import logging
import math
import re
import secrets
from typing import TYPE_CHECKING
from urllib.parse import quote, urljoin

from aiohttp import ClientTimeout
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .availability import FreeboxReachableMixin
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


@dataclass(frozen=True, slots=True)
class VoicemailMessage:
    """Un message. ``phone_number`` ne doit jamais apparaître dans ``repr``."""

    id: str
    country_code: str
    phone_number: str
    date: int
    read: bool
    duration: int

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


def voicemail_api_path(message_id: str, suffix: str = "") -> str:
    """Identifiant cité. Les points du fichier sont encodés : ``quote`` les laisse."""
    quoted = quote(message_id, safe="").replace(".", "%2E")
    return f"call/voicemail/{quoted}{suffix}"


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
        messages.append(
            VoicemailMessage(
                id=ident,
                country_code=country if isinstance(country, str) else "",
                phone_number=number if isinstance(number, str) else "",
                date=_stamp(item.get("date")),
                read=read if isinstance(read, bool) else False,
                duration=_stamp(item.get("duration")),
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


async def _invoke(access: object, method: str, path: str, payload: object) -> object:
    action = getattr(access, method, None)
    if not callable(action):
        raise VoicemailEndpointError("http_error")
    if method == "get":
        result = await action(path)
    else:
        result = await action(path, payload)
    return _reject_status(result)


async def async_voicemail_exchange(
    router: FreeboxRouter, method: str, relative: str, payload: object = None
) -> object:
    """Appelle call/voicemail. Sur 404 ou endpoint inconnu, rejoue la version annoncée.

    La variante qui répond est mémorisée pour la liste, PUT, DELETE et l'audio.
    """
    access = router._api.call._access
    remembered = router.voicemail_api_prefix
    first = relative if not remembered else f"{remembered}{relative}"
    try:
        result = await _invoke(access, method, first, payload)
    except Exception as err:
        if not _is_version_mismatch(err):
            raise
        try:
            if remembered:
                alternative = relative
                chosen = ""
            else:
                advertised = await _advertised_prefix(router)
                alternative = f"{advertised}{relative}"
                chosen = advertised
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
        router.voicemail_api_prefix = chosen
        return result
    if remembered is None:
        router.voicemail_api_prefix = ""
    return result


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


async def async_refresh_voicemails(router: FreeboxRouter) -> None:
    """Relevé isolé. Un refus de droit ``calls`` rend le capteur indisponible.

    Un 404, ``invalid_request`` ou endpoint inconnu, y compris après un essai de
    la version d'API annoncée, veut dire que la Freebox n'a pas de messagerie.
    Le capteur reste disponible.
    """
    if router.voicemail_supported is False:
        router.voicemail_available = True
        return
    was_available = router.voicemail_available is not False
    try:
        payload = await async_voicemail_exchange(router, "get", _LIST_PATH)
        found = parse_voicemails(payload)
    except Exception as err:
        if router.closing and is_shutdown_error(err, router):
            return
        if _is_version_mismatch(err):
            _mark_unsupported(router, err)
            return
        router.note_permission("calls", err)
        router.voicemail_available = False
        _note_failure(router, err)
        _signal(router)
        return
    _announce(router, found)
    router.voicemails = found
    if was_available is False:
        _LOGGER.info("Messagerie vocale Freebox de nouveau disponible")
    router.voicemail_supported = True
    router.voicemail_available = True
    router.voicemail_error = None
    router.voicemail_failure_logged = False
    # Le journal d'appels reste prioritaire : on ne lève le Repair que s'il va bien.
    if router.calls_available is not False:
        router.note_permission("calls")
    _signal(router)


async def _deny(router: FreeboxRouter, err: Exception) -> None:
    router.note_permission("calls", err)
    router.voicemail_available = False
    _note_failure(router, err)
    _signal(router)
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="voicemail_permission",
    ) from err


async def async_mark_voicemail_read(router: FreeboxRouter, message_id: str) -> None:
    _unsupported(router)
    ident = resolve_voicemail_token(router, message_id)
    try:
        await async_voicemail_exchange(
            router, "put", voicemail_api_path(ident), {"read": True}
        )
    except HomeAssistantError:
        raise
    except Exception as err:
        if _is_version_mismatch(err):
            _mark_unsupported(router, err)
            _unsupported(router)
        if is_permission_denied(err):
            await _deny(router, err)
        raise
    router.voicemails = [
        replace(item, read=True) if item.id == ident else item for item in messages_of(router)
    ]
    await async_refresh_voicemails(router)
    _signal(router)


async def async_delete_voicemail(router: FreeboxRouter, message_id: str) -> None:
    _unsupported(router)
    ident = resolve_voicemail_token(router, message_id)
    try:
        await async_voicemail_exchange(router, "delete", voicemail_api_path(ident))
    except HomeAssistantError:
        raise
    except Exception as err:
        if _is_version_mismatch(err):
            _mark_unsupported(router, err)
            _unsupported(router)
        if is_permission_denied(err):
            await _deny(router, err)
        raise
    router.voicemails = [item for item in messages_of(router) if item.id != ident]
    await async_refresh_voicemails(router)
    _signal(router)


async def async_voicemail_audio(router: FreeboxRouter, message_id: str) -> bytes:
    _unsupported(router)
    ident = resolve_voicemail_token(router, message_id)
    try:
        payload = await async_voicemail_exchange(
            router, "get", voicemail_api_path(ident, "/audio_file")
        )
    except HomeAssistantError:
        raise
    except Exception as err:
        if _is_version_mismatch(err):
            _mark_unsupported(router, err)
            _unsupported(router)
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
