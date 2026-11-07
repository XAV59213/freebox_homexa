"""Rappels « prévenez-moi avant le début » du guide TNT Freebox Homexa.

Adapted from cyclope205/programme-tnt-fr v3.0.8 (MIT), reminders.py.
Différences : services sous le domaine freebox_homexa, profils lus dans les
options des entrées Freebox Homexa, pas de cibles globales par défaut.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, NotRequired, TypedDict

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
if TYPE_CHECKING:
    from homeassistant.util.json import JsonArrayType

from .const import DOMAIN
from .tnt_const import (
    CONF_ANNOUNCE_VOLUME,
    CONF_MEDIA_PLAYER_TARGETS,
    CONF_NOTIFY_TARGET,
    CONF_REMINDER_PROFILES,
    CONF_TTS_ENGINE,
)

from .errors import async_action_errors

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_tnt_reminders"
SERVICE_SCHEDULE_REMINDER = "schedule_reminder"
SERVICE_CANCEL_REMINDER = "cancel_reminder"
SERVICE_GET_STATUS = "get_reminder_status"

_REMINDERS_SETUP_KEY = f"{DOMAIN}_tnt_reminders_setup"
_UNSUB_KEY = f"{DOMAIN}_tnt_reminder_unsubs"
REMINDER_SERVICES = ("schedule_reminder", "cancel_reminder", "get_reminder_status")

_REMINDER_FIELDS: dict[object, object] = {
    vol.Required("channel_name"): cv.string,
    vol.Required("program_title"): cv.string,
    vol.Required("start_time"): cv.string,
    vol.Required("minutes_before"): vol.In([5, 10, 15]),
}

# Optional on every service call: which named reminder profile (person -> their
# own notify_target/media_player_targets/tts_engine, configured in the
# integration's options) this reminder is for. Omitted or unknown -> falls
# back to the integration-wide defaults, exactly as before this field existed.
_PROFILE_FIELD: dict[object, object] = {vol.Optional("profile_name"): cv.string}

SCHEDULE_SCHEMA = type(cv.PLATFORM_SCHEMA)({**_REMINDER_FIELDS, **_PROFILE_FIELD})
CANCEL_SCHEMA = type(cv.PLATFORM_SCHEMA)({**_REMINDER_FIELDS, **_PROFILE_FIELD})
STATUS_SCHEMA = type(cv.PLATFORM_SCHEMA)(
    {
        vol.Required("channel_name"): cv.string,
        vol.Required("program_title"): cv.string,
        vol.Required("start_time"): cv.string,
        **_PROFILE_FIELD,
    }
)

class ReminderNotification(TypedDict):
    """Fields consumed by notification routing, including old stored records."""

    channel_name: str
    program_title: str
    minutes_before: int
    targets: NotRequired[list[str]]
    media_player_targets: NotRequired[list[str]]
    tts_engine: NotRequired[str | None]
    announce_volume: NotRequired[float | None]
    profile_name: NotRequired[str | None]


class Reminder(ReminderNotification):
    """The integration's persisted timer format; identifiers stay unchanged."""

    id: str
    fire_time: str


class ReminderStorage(TypedDict, total=False):
    """Version-one store. Copies retain unrelated existing root metadata."""

    reminders: list[Reminder]


def _profile_targets(value: object) -> list[str]:
    """Accept both historical singleton targets and current multiple selectors."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_reminder_profile")


def _reminder_id(
    channel_name: str,
    program_title: str,
    start_time: str,
    minutes_before: int,
    profile_name: str | None = None,
) -> str:
    """Deterministic id derived from the identifying fields.

    Lets the card cancel a reminder using the same data it scheduled it
    with, without needing the server to hand back a generated id. The
    profile name is part of the id so that two profiles (e.g. two people
    in two rooms) scheduling a reminder for the very same program and
    delay don't collide into a single stored reminder.
    """
    raw = f"{channel_name}|{program_title}|{start_time}|{minutes_before}|{profile_name or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

async def async_setup_reminders(hass: HomeAssistant) -> None:
    """Register the reminder services and restore pending reminders.

    Safe to call multiple times (e.g. multiple config entry reloads) - only
    does real work once per HA run. Never raises: a failure here must not
    block the rest of the integration's setup.
    """
    if hass.data.get(_REMINDERS_SETUP_KEY):
        return
    hass.data[_REMINDERS_SETUP_KEY] = True
    hass.data.setdefault(_UNSUB_KEY, {})

    store: Store[ReminderStorage] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    manager = _ReminderManager(hass, store)

    hass.services.async_register(
        DOMAIN, SERVICE_SCHEDULE_REMINDER, manager.async_handle_schedule, schema=SCHEDULE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL_REMINDER, manager.async_handle_cancel, schema=CANCEL_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_STATUS,
        manager.async_handle_status,
        schema=STATUS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    try:
        await manager.async_restore_pending()
    except Exception:  # noqa: BLE001
        _LOGGER.error(
            "Restauration des rappels TNT non entièrement confirmée ; vérifiez le "
            "stockage et le statut des rappels. Les minuteurs déjà restaurés sont conservés."
        )

class _ReminderManager:
    def __init__(self, hass: HomeAssistant, store: Store[ReminderStorage]) -> None:
        self._hass = hass
        self._store = store
        self._storage_lock = asyncio.Lock()

    def _resolve_notify_targets(self) -> list[str]:
        """Pas de cibles globales dans Homexa : tout passe par les profils."""
        return []

    def _resolve_tts_engine(self) -> str | None:
        return None

    def _find_profile(self, profile_name: str | None) -> dict[str, object] | None:
        """Named reminder profile matching profile_name, if configured and found."""
        profiles: list[dict[str, object]] = []
        for entry in self._hass.config_entries.async_entries(DOMAIN):
            saved = entry.options.get(CONF_REMINDER_PROFILES, [])
            if not isinstance(saved, list):
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_reminder_profile")
            for raw_profile in saved:
                if not isinstance(raw_profile, dict) or not isinstance(raw_profile.get("name"), str):
                    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_reminder_profile")
                profile: dict[str, object] = {}
                for key, value in raw_profile.items():
                    if not isinstance(key, str):
                        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_reminder_profile")
                    profile[key] = value
                profiles.append(profile)
        if not profile_name:
            # Sans nom : le profil unique s'il n'y en a qu'un.
            return profiles[0] if len(profiles) == 1 else None
        return next((p for p in profiles if p.get("name") == profile_name), None)

    def _resolve_targets(
        self, profile_name: str | None
    ) -> tuple[list[str], list[str], str | None, float | None]:
        """(notify targets, media_player targets, tts engine) for this reminder.

        Uses the named profile's own devices when profile_name matches a
        configured profile; otherwise falls back to the integration-wide
        defaults, exactly like before profiles existed.
        """
        profile = self._find_profile(profile_name)
        if profile is not None:
            raw_targets = _profile_targets(profile.get(CONF_NOTIFY_TARGET))
            targets = [
                slug[len("notify.") :] if slug.startswith("notify.") else slug
                for slug in raw_targets
            ]
            media_targets = _profile_targets(profile.get(CONF_MEDIA_PLAYER_TARGETS))
            tts_engine = profile.get(CONF_TTS_ENGINE)
            volume = profile.get(CONF_ANNOUNCE_VOLUME)
            if tts_engine is not None and not isinstance(tts_engine, str):
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_reminder_profile")
            if volume is not None and not isinstance(volume, (int, float)):
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_reminder_profile")
            return (
                targets,
                media_targets,
                tts_engine,
                volume,
            )
        return ([], [], None, None)

    @async_action_errors
    async def async_handle_schedule(self, call: ServiceCall) -> None:
        channel_name = call.data["channel_name"]
        program_title = call.data["program_title"]
        start_time_raw = call.data["start_time"]
        minutes_before = call.data["minutes_before"]
        profile_name = call.data.get("profile_name")

        targets, media_player_targets, tts_engine, announce_volume = (
            self._resolve_targets(profile_name)
        )
        if not tts_engine:
            # Un media_player sans moteur TTS reste utilisable si
            # c'est un appareil Alexa (route via notify.alexa_media_*
            # dans _async_notify, qui ne necessite aucun tts_engine) -
            # ne vider que les cibles qui en ont reellement besoin.
            media_player_targets = [
                player
                for player in media_player_targets
                if self._alexa_notify_slug(player)
            ]
        if not targets and not media_player_targets:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_reminder_profile",
            )

        start_time = dt_util.parse_datetime(start_time_raw)
        if start_time is None or start_time.tzinfo is None or start_time.utcoffset() is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_start_time",
            )

        fire_time = start_time - timedelta(minutes=minutes_before)
        if fire_time <= dt_util.now():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="reminder_too_late",
            )

        reminder_id = _reminder_id(
            channel_name, program_title, start_time_raw, minutes_before, profile_name
        )
        reminder: Reminder = {
            "id": reminder_id,
            "channel_name": channel_name,
            "program_title": program_title,
            "minutes_before": minutes_before,
            "profile_name": profile_name,
            "fire_time": fire_time.isoformat(),
            "targets": targets,
            "media_player_targets": media_player_targets,
            "tts_engine": tts_engine,
            "announce_volume": announce_volume,
        }
        await self._async_save(reminder)
        self._schedule(reminder)

    @async_action_errors
    async def async_handle_cancel(self, call: ServiceCall) -> None:
        reminder_id = _reminder_id(
            call.data["channel_name"],
            call.data["program_title"],
            call.data["start_time"],
            call.data["minutes_before"],
            call.data.get("profile_name"),
        )
        # If persistence fails, keep the existing timer rather than cancelling a
        # reminder which will reappear after restart despite a reported failure.
        await self._async_remove(reminder_id)
        unsub_map = self._hass.data.setdefault(_UNSUB_KEY, {})
        unsub = unsub_map.pop(reminder_id, None)
        if unsub:
            unsub()

    @async_action_errors
    async def async_handle_status(self, call: ServiceCall) -> ServiceResponse:
        channel_name = call.data["channel_name"]
        program_title = call.data["program_title"]
        start_time = call.data["start_time"]
        profile_name = call.data.get("profile_name")
        async with self._storage_lock:
            data = await self._store.async_load() or {"reminders": []}
        existing_ids = {r["id"] for r in data.get("reminders", [])}
        active_ids = self._hass.data.get(_UNSUB_KEY, {})
        queried = {_reminder_id(channel_name, program_title, start_time, minutes, profile_name)
                   for minutes in (5, 10, 15)}
        if any((rid in existing_ids) != (rid in active_ids) for rid in queried):
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="reminder_state_unconfirmed"
            )
        scheduled: JsonArrayType = [
            minutes
            for minutes in (5, 10, 15)
            if _reminder_id(channel_name, program_title, start_time, minutes, profile_name)
            in existing_ids
        ]
        return {"scheduled_minutes": scheduled}

    async def async_restore_pending(self) -> None:
        async with self._storage_lock:
            data = await self._store.async_load()
            if not data:
                return
            now = dt_util.now()
            kept = []
            for reminder in data.get("reminders", []):
                fire_time = dt_util.parse_datetime(reminder.get("fire_time", ""))
                if fire_time is None or fire_time <= now:
                    continue
                kept.append(reminder)
                self._schedule(reminder)
            if len(kept) != len(data.get("reminders", [])):
                snapshot = data.copy()
                snapshot["reminders"] = kept
                await self._async_store_checked(snapshot)

    def _schedule(self, reminder: Reminder) -> None:
        fire_time = dt_util.parse_datetime(reminder["fire_time"])

        if fire_time is None or fire_time.tzinfo is None or fire_time.utcoffset() is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_start_time")

        async def _fire(_now: datetime) -> None:
            self._hass.data.setdefault(_UNSUB_KEY, {}).pop(reminder["id"], None)
            await self._async_remove(reminder["id"])
            await self._async_notify(reminder)

        unsub = async_track_point_in_time(self._hass, _fire, fire_time)
        timers = self._hass.data.setdefault(_UNSUB_KEY, {})
        previous = timers.get(reminder["id"])
        if previous is not None:
            previous()
        timers[reminder["id"]] = unsub

    def _alexa_notify_slug(self, entity_id: str) -> str | None:
        """notify.alexa_media_<slug> service name for this entity, if any.

        Alexa Media Player registers both a media_player entity and a
        notify.alexa_media_<slug> service using the same device slug. So
        if someone picks their Echo from the "media player" field (the
        obvious, expected place - it IS a media player after all), we
        still route it through Alexa's own voice via the notify service
        instead of tts.speak, which needs a publicly reachable URL for a
        generated audio file - something most home installs (Tailscale-
        only external_url, no Nabu Casa Cloud) can't offer Amazon's
        servers. This makes the intuitive choice work, instead of only
        the "appareil a notifier" field.
        """
        registry = er.async_get(self._hass)
        entry = registry.async_get(entity_id)
        if entry is None or entry.platform != "alexa_media":
            return None
        slug = "alexa_media_" + entity_id.split(".", 1)[1]
        if self._hass.services.has_service("notify", slug):
            return slug
        return None

    async def _async_notify(self, reminder: ReminderNotification) -> None:
        targets = reminder.get("targets") or self._resolve_notify_targets()
        media_player_targets_early = reminder.get("media_player_targets") or []
        if not targets and not media_player_targets_early:
            _LOGGER.warning(
                "Rappel pour %s ignore : aucun appareil de notification "
                "configure dans les options de Freebox Homexa (Configurer → Profils de rappel)",
                reminder["program_title"],
            )
            return
        message = (
            f"{reminder['program_title']} commence dans "
            f"{reminder['minutes_before']} min sur {reminder['channel_name']}"
        )
        for slug in targets:
            try:
                service_data: dict[str, object] = {"title": "Guide TNT Freebox Homexa", "message": message}
                if slug.startswith("alexa_media"):
                    # Ask Alexa to speak the message in its own voice
                    # instead of posting a silent notification to the
                    # Alexa app - avoids needing a publicly reachable
                    # URL for a generated audio file (see _notify_options
                    # docstring in config_flow.py for the full reasoning).
                    service_data["data"] = {"type": "tts"}
                await self._hass.services.async_call(
                    "notify",
                    slug,
                    service_data,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Echec de l'envoi du rappel pour %s via notify.%s",
                    reminder["program_title"],
                    slug,
                )

        media_player_targets = reminder.get("media_player_targets") or []
        tts_engine = reminder.get("tts_engine") or self._resolve_tts_engine()
        announce_volume = reminder.get("announce_volume")
        for player in media_player_targets:
            previous_volume = None
            if announce_volume is not None:
                state = self._hass.states.get(player)
                if state is not None:
                    previous_volume = state.attributes.get("volume_level")
                try:
                    await self._hass.services.async_call(
                        "media_player",
                        "volume_set",
                        {"volume_level": announce_volume},
                        target={"entity_id": player},
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.exception(
                        "Echec du reglage du volume d'annonce pour %s",
                        player,
                    )
            alexa_slug = self._alexa_notify_slug(player)
            if alexa_slug:
                try:
                    await self._hass.services.async_call(
                        "notify",
                        alexa_slug,
                        {
                            "title": "Guide TNT Freebox Homexa",
                            "message": message,
                            "data": {"type": "tts"},
                        },
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.exception(
                        "Echec de l'annonce vocale Alexa du rappel pour %s sur %s",
                        reminder["program_title"],
                        player,
                    )
                await self._restore_announce_volume(player, previous_volume, message)
                continue
            if not tts_engine:
                _LOGGER.warning(
                    "Pas de moteur TTS configure pour annoncer le rappel de %s sur %s",
                    reminder["program_title"],
                    player,
                )
                await self._restore_announce_volume(player, previous_volume, message)
                continue
            try:
                await self._hass.services.async_call(
                    "tts",
                    "speak",
                    {"media_player_entity_id": player, "message": message},
                    target={"entity_id": tts_engine},
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Echec de l'annonce vocale du rappel pour %s sur %s",
                    reminder["program_title"],
                    player,
                )
            await self._restore_announce_volume(player, previous_volume, message)

    async def _restore_announce_volume(
        self, player: str, previous_volume: float | None, message: str
    ) -> None:
        """Attend approximativement la fin de l'annonce puis restaure le volume."""
        if previous_volume is None:
            return
        words = max(1, len(message.split()))
        delay = min(30.0, max(2.5, words / 2.5 + 1.5))
        await asyncio.sleep(delay)
        try:
            await self._hass.services.async_call(
                "media_player",
                "volume_set",
                {"volume_level": previous_volume},
                target={"entity_id": player},
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Echec de la restauration du volume pour %s",
                player,
            )

    async def _async_store_checked(self, data: ReminderStorage) -> None:
        # HA Store logs and swallows WriteError. A normal return alone is NOT a
        # persistence acknowledgement. Verify using only its public API.
        try:
            await self._store.async_save(data)
            persisted = await self._store.async_load()
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="reminder_storage_failed"
            ) from err
        if persisted != data:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="reminder_storage_failed"
            )

    async def _async_save(self, reminder: Reminder) -> None:
        async with self._storage_lock:
            data = (await self._store.async_load() or {"reminders": []}).copy()
            reminders = [r for r in data.get("reminders", []) if r["id"] != reminder["id"]]
            reminders.append(reminder)
            data["reminders"] = reminders
            await self._async_store_checked(data)

    async def _async_remove(self, reminder_id: str) -> None:
        async with self._storage_lock:
            data = (await self._store.async_load() or {"reminders": []}).copy()
            data["reminders"] = [r for r in data.get("reminders", []) if r["id"] != reminder_id]
            await self._async_store_checked(data)


def async_unload_reminders(hass: HomeAssistant) -> None:
    """Annule les rappels planifiés en mémoire et retire les services (dernière entrée déchargée).

    Les rappels restent enregistrés et seront reprogrammés au prochain chargement.
    """
    if not hass.data.pop(_REMINDERS_SETUP_KEY, None):
        return
    for unsub in hass.data.pop(_UNSUB_KEY, {}).values():
        unsub()
    for service in REMINDER_SERVICES:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
