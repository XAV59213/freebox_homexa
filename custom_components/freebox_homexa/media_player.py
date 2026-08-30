"""Freebox Player (Delta / Devialet / Mini 4K) media player."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .router import FreeboxRouter

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

# url: opened via POST .../control/open
# remote: IR/network key via Freebox remote API (Mini 4K / CEC wake)
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
    if router.device_id:
        info["via_device_id"] = router.device_id
    return DeviceInfo(**info)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    try:
        players = await router._api.player.get_players() or []
    except Exception as err:
        _LOGGER.warning("Impossible de lister les Freebox Player : %s", err)
        return

    entities = [
        FreeboxPlayerMediaPlayer(router, player, entry.data.get("remote_code"))
        for player in players
    ]
    if entities:
        async_add_entities(entities, True)
        _LOGGER.info("%s Freebox Player(s) ajouté(s)", len(entities))
    else:
        _LOGGER.warning("Aucun Freebox Player détecté")


class FreeboxPlayerMediaPlayer(MediaPlayerEntity):
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
        remote_code: str | None = None,
    ) -> None:
        self._router = router
        self._player = player
        self._player_id = player["id"]
        self._remote_code = remote_code
        self._kind = _player_kind(player)
        self._api_version = _normalize_api_version(player.get("api_version"))
        self._attr_unique_id = f"{router.mac}_player_{self._player_id}"
        self._attr_device_info = player_device_info(router, player)
        self._attr_available = bool(player.get("reachable", True))
        self._attr_source = None
        if self._kind == "mini4k":
            self._attr_source_list = list(MINI_4K_SOURCES)
        else:
            self._attr_source_list = list(DEVIALET_SOURCES)

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
            try:
                await self._post("control/mediactrl", {"name": name})
            except Exception as err:
                _LOGGER.error("Commande %s échouée sur Player %s : %s", name, self._player_id, err)

    async def _send_remote(self, key: str) -> None:
        if not self._remote_code:
            return
        try:
            await self._router._api.remote.send_key(code=str(self._remote_code), key=key)
        except Exception as err:
            _LOGGER.debug("Touche remote %s indisponible : %s", key, err)

    async def async_update(self) -> None:
        status: dict[str, Any] | None = None
        last_err: Exception | None = None
        versions = [self._api_version] + [v for v in API_VERSION_FALLBACKS if v != self._api_version]
        for version in versions:
            try:
                status = await self._access.get(self._path("status/", version)) or {}
                self._api_version = version
                break
            except Exception as err:
                last_err = err
                status = None

        if status is None:
            _LOGGER.debug(
                "Statut Player %s (%s) indisponible : %s",
                self._player_id,
                self._api_version,
                last_err,
            )
            self._attr_available = bool(self._player.get("reachable"))
            return

        self._attr_available = True
        power = str(status.get("power_state") or status.get("power") or "").lower()
        playback = str(
            status.get("playback_state")
            or status.get("state")
            or status.get("playback")
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
        else:
            self._attr_state = MediaPlayerState.IDLE

        volume = status.get("volume")
        if volume is None:
            try:
                vol_data = await self._get("control/volume") or {}
                volume = vol_data.get("volume")
                if status.get("mute") is None:
                    status["mute"] = vol_data.get("mute")
            except Exception:
                volume = None
        if isinstance(volume, (int, float)):
            self._attr_volume_level = max(0.0, min(1.0, float(volume) / 100.0))

        mute = status.get("mute")
        if mute is not None:
            self._attr_is_volume_muted = bool(mute)

        title = (
            status.get("title")
            or status.get("program_name")
            or (status.get("cur_info") or {}).get("title")
        )
        self._attr_media_title = title
        current = status.get("app") or status.get("source") or status.get("uri")
        if isinstance(current, str) and current.startswith("tv:"):
            self._attr_source = "TV"
        elif isinstance(current, str) and "youtube" in current.lower():
            self._attr_source = "YouTube"
        elif isinstance(current, str) and "netflix" in current.lower():
            self._attr_source = "Netflix"
        elif current:
            self._attr_source = str(current)

    async def async_set_volume_level(self, volume: float) -> None:
        await self._put("control/volume", {"volume": int(round(volume * 100))})

    async def async_mute_volume(self, mute: bool) -> None:
        await self._put("control/volume", {"mute": mute})

    async def async_media_play(self) -> None:
        await self._command("play")

    async def async_media_pause(self) -> None:
        await self._command("pause")

    async def async_media_stop(self) -> None:
        await self._command("stop")

    async def async_media_next_track(self) -> None:
        await self._command("next")

    async def async_media_previous_track(self) -> None:
        await self._command("prev")

    async def async_select_source(self, source: str) -> None:
        spec = COMMON_SOURCES.get(source)
        if not spec:
            _LOGGER.warning("Source inconnue : %s", source)
            return
        try:
            if spec.get("url"):
                await self._post("control/open", {"url": spec["url"]})
            if spec.get("remote"):
                await self._send_remote(spec["remote"])
            self._attr_source = source
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Impossible d'ouvrir la source %s : %s", source, err)

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        payload: dict[str, Any] = {"url": media_id}
        if media_type:
            payload["type"] = media_type
        await self._post("control/open", payload)

    async def async_turn_on(self) -> None:
        if self.state == MediaPlayerState.OFF:
            await self._try_power()
            # One Touch Play : la TV bascule souvent sur l'entrée HDMI du Player (CEC).
            await self.async_select_source("HDMI (CEC)")

    async def async_turn_off(self) -> None:
        if self.state != MediaPlayerState.OFF:
            await self._try_power()

    async def _try_power(self) -> None:
        try:
            await self._command("play_pause")
        except Exception:
            pass
        await self._send_remote("power")
