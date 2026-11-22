"""Messagerie vocale Freebox (API ``call/voicemail/``, hors freebox-api).

Les numéros et indicatifs ne sortent pas des objets internes : ni journal, ni
attribut d'état, ni événement. La carte les demande explicitement.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import quote

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .availability import FreeboxReachableMixin
from .const import DOMAIN
from .errors import is_permission_denied, is_shutdown_error

if TYPE_CHECKING:
    from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

_MESSAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")
VOICEMAIL_LIST_LIMIT = 30
NEW_VOICEMAIL_EVENT = "freebox_homexa_new_voicemail"


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


def validated_voicemail_id(raw: object) -> str:
    """Refuse un identifiant vide, un chemin ou une chaîne inattendue."""
    if not isinstance(raw, str) or ".." in raw or _MESSAGE_ID.fullmatch(raw) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="voicemail_invalid_id",
        )
    return raw


def voicemail_api_path(message_id: str, suffix: str = "") -> str:
    """Identifiant cité. Les points du fichier sont encodés : ``quote`` les laisse."""
    quoted = quote(message_id, safe="").replace(".", "%2E")
    return f"call/voicemail/{quoted}{suffix}"


def _stamp(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if value < 0:
        return 0
    return int(value)


def parse_voicemails(payload: object) -> list[VoicemailMessage]:
    """``GET call/voicemail/``. ``None`` est une liste vide, comme le SDK."""
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("Invalid voicemail collection")
    messages: list[VoicemailMessage] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Invalid voicemail collection")
        ident = item.get("id")
        if not isinstance(ident, str) or not ident:
            raise ValueError("Invalid voicemail collection")
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


def public_message(message: VoicemailMessage, *, include_number: bool = False) -> dict[str, object]:
    """Vue sans numéro, sauf demande explicite de la carte."""
    payload: dict[str, object] = {
        "id": message.id,
        "date": _iso(message.date),
        "duration": message.duration,
        "read": message.read,
    }
    if include_number:
        payload["phone_number"] = message.phone_number
    return payload


def public_summary(messages: list[VoicemailMessage]) -> dict[str, object]:
    ordered = sorted(messages, key=lambda item: item.date, reverse=True)
    latest = _iso(ordered[0].date) if ordered else None
    return {
        "total": len(messages),
        "latest": latest,
        "messages": [public_message(item) for item in ordered[:VOICEMAIL_LIST_LIMIT]],
    }


def unread_count(messages: list[VoicemailMessage]) -> int:
    return sum(1 for item in messages if not item.read)


def _announce(router: FreeboxRouter, messages: list[VoicemailMessage]) -> None:
    """Le premier relevé réussi sert de référence : pas d'événement au démarrage."""
    current = {item.id for item in messages}
    known = router.voicemail_seen
    router.voicemail_seen = current
    if known is None:
        return
    for item in messages:
        if item.id in known or item.read:
            continue
        router.hass.bus.async_fire(
            NEW_VOICEMAIL_EVENT,
            {
                "entry_id": router.entry_id,
                "id": item.id,
                "duration": item.duration,
                "date": _iso(item.date),
            },
        )


def _signal(router: FreeboxRouter) -> None:
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    async_dispatcher_send(router.hass, router.signal_sensor_update)


async def async_refresh_voicemails(router: FreeboxRouter) -> None:
    """Relevé isolé. Un refus de droit ``calls`` rend le capteur indisponible."""
    was_available = router.voicemail_available is not False
    try:
        payload = await router._api.call._access.get("call/voicemail/")
        found = parse_voicemails(payload)
    except Exception as err:
        if router.closing and is_shutdown_error(err, router):
            return
        router.note_permission("calls", err)
        router.voicemail_available = False
        if was_available:
            _LOGGER.info("Messagerie vocale Freebox indisponible")
        return
    _announce(router, found)
    router.voicemails = found
    if was_available is False:
        _LOGGER.info("Messagerie vocale Freebox de nouveau disponible")
    router.voicemail_available = True
    # Le journal d'appels reste prioritaire : on ne lève le Repair que s'il va bien.
    if router.calls_available is not False:
        router.note_permission("calls")


async def _deny(router: FreeboxRouter, err: Exception) -> None:
    router.note_permission("calls", err)
    router.voicemail_available = False
    _signal(router)
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="voicemail_permission",
    ) from err


async def async_mark_voicemail_read(router: FreeboxRouter, message_id: str) -> None:
    ident = validated_voicemail_id(message_id)
    try:
        await router._api.call._access.put(voicemail_api_path(ident), {"read": True})
    except HomeAssistantError:
        raise
    except Exception as err:
        if is_permission_denied(err):
            await _deny(router, err)
        raise
    router.voicemails = [
        replace(item, read=True) if item.id == ident else item for item in messages_of(router)
    ]
    await async_refresh_voicemails(router)
    _signal(router)


async def async_delete_voicemail(router: FreeboxRouter, message_id: str) -> None:
    ident = validated_voicemail_id(message_id)
    try:
        await router._api.call._access.delete(voicemail_api_path(ident))
    except HomeAssistantError:
        raise
    except Exception as err:
        if is_permission_denied(err):
            await _deny(router, err)
        raise
    router.voicemails = [item for item in messages_of(router) if item.id != ident]
    await async_refresh_voicemails(router)
    _signal(router)


async def async_voicemail_audio(router: FreeboxRouter, message_id: str) -> bytes:
    ident = validated_voicemail_id(message_id)
    try:
        payload = await router._api.call._access.get(voicemail_api_path(ident, "/audio_file"))
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
    """Nombre de messages non lus. Les attributs n'ont pas de numéro."""

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
        return unread_count(messages_of(self._router))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        summary = public_summary(messages_of(self._router))
        summary["voicemail"] = True
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
