"""Freebox Player (Delta / Devialet / Mini 4K) media player."""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, URL_BASE, option_remote_code
from .availability import FreeboxReachableMixin
from .player_diagnostics import cache_player_schema
from .player_remote import async_schedule_player_api_retry, async_send_player_keys, filter_ready_players
from .router import FreeboxConfigEntry, FreeboxRouter
from .tv_guide import tnt_artwork_url

from .errors import async_action_errors

_LOGGER = logging.getLogger(__name__)

PLAYER_FEATURES = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY_MEDIA
)

COMMON_SOURCES: dict[str, dict[str, str]] = {
    "TV": {"url": "tv:", "remote": "tv"},
    "HDMI (CEC)": {"url": "tv:", "remote": "tv"},
    "YouTube": {"url": "https://www.youtube.com"},
    "Netflix": {"url": "https://www.netflix.com"},
    "Navigateur": {"url": "https://www.google.com"},
}

MINI_4K_SOURCES = ["TV", "HDMI (CEC)", "YouTube", "Navigateur"]
DEVIALET_SOURCES = ["TV", "HDMI (CEC)", "YouTube", "Netflix", "Navigateur"]

MINI_4K_MODELS = {"fbx6lc", "freebox_mini", "mini4k", "mini_4k", "stb_mini"}
DEVIALET_MODELS = {"fbx7hd-delta", "stb_v7", "fbx7hd-one"}
API_VERSION_FALLBACKS = ("v6", "v8", "v7", "v5")

# Icônes carrées embarquées dans frontend/ (servies via URL_BASE, sans hotlink).
# youtube.png 256x256 (source brands.home-assistant.io/youtube/icon.png).
# netflix.png 1024x1024 (source Wikimedia Commons Netflix-new-icon.png).
# L'artwork TNT reste prioritaire en live TV.
APP_ARTWORK_URLS = {
    "YouTube": f"{URL_BASE}/youtube.png",
    "Netflix": f"{URL_BASE}/netflix.png",
}
APP_ICONS = {
    "YouTube": "mdi:youtube",
    "Netflix": "mdi:netflix",
}


def _normalize_api_version(raw: Any) -> str:
    text = str(raw or "6").strip().lower()
    if text.startswith("v"):
        text = text[1:]
    major = text.split(".")[0] or "6"
    return f"v{major}"


def _player_kind(player: dict[str, Any]) -> str:
    model = str(player.get("device_model") or player.get("stb_type") or "").lower()
    name = str(player.get("device_name") or player.get("name") or "").lower()
    if model in DEVIALET_MODELS or "delta" in model or "devialet" in name:
        return "devialet"
    if model in MINI_4K_MODELS or "mini" in model or "mini 4k" in name or "mini4k" in name:
        return "mini4k"
    if "pop" in model or "pop" in name:
        return "pop"
    return "player"


def _player_model(player: dict[str, Any]) -> str:
    kind = _player_kind(player)
    if kind == "devialet":
        return "Freebox Player Devialet"
    if kind == "mini4k":
        return "Freebox Mini 4K"
    if kind == "pop":
        return "Freebox Player Pop"
    return player.get("device_model") or player.get("stb_type") or "Freebox Player"


def player_device_info(router: FreeboxRouter, player: dict[str, Any]) -> DeviceInfo:
    player_id = player["id"]
    name = player.get("device_name") or player.get("name") or f"Freebox Player {player_id}"
    info: dict[str, Any] = {
        "identifiers": {(DOMAIN, f"player_{player_id}")},
        "manufacturer": "Freebox SAS",
        "model": _player_model(player),
        "name": name,
    }
    if player.get("mac"):
        info["connections"] = {("mac", player["mac"])}
    # Service de premier niveau : pas de via_device (retiré par le nettoyage différé).
    router.player_identifiers.add(f"player_{player_id}")
    return DeviceInfo(**info)


# Une seule action / mise à jour à la fois vers la Freebox pour cette plateforme.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: FreeboxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxRouter = entry.runtime_data
    try:
        players = await router._api.player.get_players() or []
    except Exception as err:
        _LOGGER.warning("Impossible de lister les Freebox Player : %s", err)
        return

    valid_players, skipped = filter_ready_players(
        players, logger=_LOGGER, context="media_player"
    )
    if skipped:
        await async_schedule_player_api_retry(hass, entry, router)

    entities = [FreeboxPlayerMediaPlayer(router, player, entry) for player in valid_players]
    if entities:
        async_add_entities(entities, True)
        _LOGGER.info("%s Freebox Player(s) ajouté(s)", len(entities))
    elif not players:
        _LOGGER.warning("Aucun Freebox Player détecté")
    else:
        _LOGGER.warning(
            "Aucun Freebox Player contrôlable via l'API Freebox OS "
            "(%s détecté(s), tous sans API locale)",
            len(players),
        )


class FreeboxPlayerMediaPlayer(FreeboxReachableMixin, MediaPlayerEntity):
    """Contrôle du Freebox Player via l'API Player Freebox OS."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_supported_features = PLAYER_FEATURES
    _attr_has_entity_name = True
    _attr_name = None
    _attr_volume_step = 0.05

    def __init__(
        self,
        router: FreeboxRouter,
        player: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        self._router = router
        self._entry = entry
        self._player = player
        self._player_id = player["id"]
        self._kind = _player_kind(player)
        self._api_version = _normalize_api_version(player.get("api_version"))
        self._attr_unique_id = f"{router.mac}_player_{self._player_id}"
        self._attr_device_info = player_device_info(router, player)
        self._attr_available = bool(player.get("reachable", True))
        self._attr_source = None
        self._channel_number = None
        if self._kind == "mini4k":
            self._attr_source_list = list(MINI_4K_SOURCES)
        else:
            self._attr_source_list = list(DEVIALET_SOURCES)

    @property
    def _remote_code(self) -> str | None:
        return option_remote_code(self._entry, self._player_id)

    def _path(self, suffix: str, version: str | None = None) -> str:
        return f"player/{self._player_id}/api/{version or self._api_version}/{suffix}"

    @property
    def _access(self):
        return self._router._api.player._access

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "player_id": self._player_id,
            "api_version": self._api_version,
            "player_model": _player_model(self._player),
            "channel_number": self._channel_number,
            "hdmi_note": "HDMI (CEC) réveille la TV sur la sortie du Player, ce n'est pas une entrée HDMI de la TV.",
        }

    async def _get(self, suffix: str) -> Any:
        return await self._access.get(self._path(suffix))

    async def _put(self, suffix: str, data: dict[str, Any]) -> Any:
        return await self._access.put(self._path(suffix), data)

    async def _post(self, suffix: str, data: dict[str, Any]) -> Any:
        return await self._access.post(self._path(suffix), data)

    async def _command(self, name: str) -> None:
        try:
            await self._post("control/mediactrl", {"cmd": name})
        except Exception:
            # Preserve the established firmware compatibility fallback, but let its
            # failure reach the user-facing error boundary instead of false success.
            await self._post("control/mediactrl", {"name": name})

    def _require_remote_code(self) -> str:
        code = self._remote_code
        if not code:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="remote_code_missing",
                translation_placeholders={"player": str(self._player_id)},
            )
        return str(code)

    async def _send_remote(self, key: str) -> None:
        failures = await async_send_player_keys(self._router, self._require_remote_code(), [key])
        if failures:
            raise failures[0][1]

    async def async_update(self) -> None:
        status: dict[str, Any] | None = None
        last_err: Exception | None = None
        versions = [self._api_version] + [v for v in API_VERSION_FALLBACKS if v != self._api_version]
        for version in versions:
            try:
                status = await self._router.async_read(lambda: self._access.get(self._path("status/", version)))
                if not isinstance(status, dict):
                    raise ValueError("Invalid Player status")
                self._api_version = version
                break
            except Exception as err:
                last_err = err
                status = None

        if status is None:
            cache_player_schema(self._router, self._player_id, None, "unavailable")
            _LOGGER.debug(
                "Statut Player %s (%s) indisponible : %s",
                self._player_id,
                self._api_version,
                last_err,
            )
            # A previously confirmed standby remains controllable through the
            # existing Server remote channel, but never infer off on first contact.
            self._attr_available = (self._attr_state == MediaPlayerState.OFF
                                    and self._remote_code is not None)
            self._router.player_status_available[str(self._player_id)] = self._attr_available
            async_dispatcher_send(self._router.hass, self._router.signal_device_update)
            return

        cache_player_schema(self._router, self._player_id, status, "received")
        self._attr_available = status.get("reachable") is not False
        # Devialet : champs observés dans /player/{id}/api/{version}/status/.
        # Les formats plats restent prioritaires pour les autres firmwares.
        def as_dict(value: Any) -> dict[str, Any]:
            return value if isinstance(value, dict) else {}

        foreground = as_dict(status.get("foreground_app"))
        context = as_dict(foreground.get("context"))
        channel = as_dict(context.get("channel"))
        nested_state = as_dict(as_dict(status.get("player")).get("state"))
        power = str(status.get("power_state") or status.get("power") or "").lower()
        playback = str(
            status.get("playback_state")
            or status.get("state")
            or status.get("playback")
            or nested_state.get("playback_state")
            or ""
        ).lower()

        if power in {"standby", "stopped", "off"}:
            self._attr_state = MediaPlayerState.OFF
        elif playback in {"playing", "play"}:
            self._attr_state = MediaPlayerState.PLAYING
        elif playback in {"paused", "pause"}:
            self._attr_state = MediaPlayerState.PAUSED
        elif power in {"running", "on"}:
            self._attr_state = MediaPlayerState.ON
        elif playback in {"stopped", "stop", "idle"}:
            self._attr_state = MediaPlayerState.IDLE
        else:
            self._attr_state = None

        if self._attr_state == MediaPlayerState.OFF and self._remote_code is not None:
            self._attr_available = True
        self._router.player_status_available[str(self._player_id)] = self._attr_available
        async_dispatcher_send(self._router.hass, self._router.signal_device_update)

        volume = status.get("volume")
        if volume is None:
            try:
                vol_data = await self._get("control/volume") or {}
                volume = vol_data.get("volume")
                if status.get("mute") is None:
                    status["mute"] = vol_data.get("mute")
            except Exception:
                volume = None
        self._attr_volume_level = None
        if (
            isinstance(volume, (int, float))
            and not isinstance(volume, bool)
            and math.isfinite(volume)
        ):
            self._attr_volume_level = max(0.0, min(1.0, float(volume) / 100.0))

        mute = status.get("mute")
        self._attr_is_volume_muted = (
            bool(mute) if isinstance(mute, (bool, int)) and mute in (0, 1) else None
        )

        title = (
            status.get("title")
            or status.get("program_name")
            or as_dict(status.get("cur_info")).get("title")
        )
        channel_name = channel.get("channelName")
        self._attr_media_channel = channel_name if isinstance(channel_name, str) else None
        number = channel.get("channelNumber")
        self._channel_number = (
            number if isinstance(number, (int, str)) and not isinstance(number, bool) else None
        )
        # Une chaîne n'est pas un titre d'émission : simple repli d'affichage.
        self._attr_media_title = title or self._attr_media_channel
        current = (
            status.get("app") or status.get("source") or status.get("uri")
            or foreground.get("cur_url") or foreground.get("package")
        )
        self._attr_source = None
        self._attr_media_image_url = None
        self._attr_icon = None
        if self._attr_state == MediaPlayerState.OFF:
            self._attr_media_title = None
            self._attr_media_channel = None
            self._channel_number = None
            return
        if isinstance(current, str) and (
            current.startswith("tv:") or current == "fr.freebox.tv"
        ):
            self._attr_source = "TV"
        elif isinstance(current, str) and "youtube" in current.lower():
            self._attr_source = "YouTube"
        elif isinstance(current, str) and "netflix" in current.lower():
            self._attr_source = "Netflix"
        elif current:
            self._attr_source = str(current)
        # Repli UX uniquement : nom de l'application déjà reconnue, jamais un
        # titre de vidéo inventé. La chaîne TV (ex. BFM TV) reste prioritaire.
        if not self._attr_media_title and self._attr_source in {"YouTube", "Netflix"}:
            self._attr_media_title = self._attr_source
        # Artwork : TNT prioritaire en TV ; sinon logos publics YouTube/Netflix
        # (pas de miniature de vidéo inventée).
        if self._attr_source == "TV":
            hass = getattr(self, "hass", None)
            if hass is not None:
                self._attr_media_image_url = tnt_artwork_url(
                    hass,
                    channel_name=self._attr_media_channel,
                    channel_number=self._channel_number,
                )
        elif self._attr_source in APP_ARTWORK_URLS:
            self._attr_media_image_url = APP_ARTWORK_URLS[self._attr_source]
            self._attr_icon = APP_ICONS[self._attr_source]

    @async_action_errors
    async def async_set_volume_level(self, volume: float) -> None:
        if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not math.isfinite(volume) or not 0 <= volume <= 1:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_action_value"
            )
        await self._put("control/volume", {"volume": int(round(volume * 100))})

    @async_action_errors
    async def async_mute_volume(self, mute: bool) -> None:
        if not isinstance(mute, bool):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_action_value"
            )
        await self._put("control/volume", {"mute": mute})

    @async_action_errors
    async def async_media_play(self) -> None:
        await self._command("play")

    @async_action_errors
    async def async_media_pause(self) -> None:
        await self._command("pause")

    @async_action_errors
    async def async_media_stop(self) -> None:
        await self._command("stop")

    @async_action_errors
    async def async_media_next_track(self) -> None:
        await self._command("next")

    @async_action_errors
    async def async_media_previous_track(self) -> None:
        await self._command("prev")

    @async_action_errors
    async def async_select_source(self, source: str) -> None:
        spec = COMMON_SOURCES.get(source)
        if not spec:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_source"
            )
        if spec.get("url"):
            await self._post("control/open", {"url": spec["url"]})
        if spec.get("remote"):
            await self._send_remote(spec["remote"])
        self._attr_source = source
        self.async_write_ha_state()

    @async_action_errors
    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        payload: dict[str, Any] = {"url": media_id}
        if media_type:
            payload["type"] = media_type
        await self._post("control/open", payload)

    @async_action_errors
    async def async_turn_on(self) -> None:
        if self.state == MediaPlayerState.OFF:
            await self._try_power()
            await self.async_select_source("HDMI (CEC)")

    @async_action_errors
    async def async_turn_off(self) -> None:
        if self.state != MediaPlayerState.OFF:
            await self._try_power()

    async def _try_power(self) -> None:
        # Validate before any preliminary media command can have a side effect.
        self._require_remote_code()
        try:
            await self._command("play_pause")
        except Exception:
            pass
        await self._send_remote("power")
