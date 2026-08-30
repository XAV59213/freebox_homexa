"""Freebox Player (Delta / Devialet) media player."""

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
)


def _player_model(player: dict[str, Any]) -> str:
    model = player.get("device_model") or player.get("stb_type") or "player"
    if model in {"fbx7hd-delta", "stb_v7"} or "delta" in str(model).lower():
        return "Freebox Player Devialet"
    return str(model)


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

    entities = [FreeboxPlayerMediaPlayer(router, player) for player in players]
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

    def __init__(self, router: FreeboxRouter, player: dict[str, Any]) -> None:
        self._router = router
        self._player = player
        self._player_id = player["id"]
        self._attr_unique_id = f"{router.mac}_player_{self._player_id}"
        self._attr_device_info = player_device_info(router, player)
        self._attr_available = bool(player.get("reachable", True))

    async def _command(self, name: str) -> None:
        try:
            await self._router._api.player.execute_media_control_command(
                name, self._player_id
            )
        except Exception as err:
            _LOGGER.error("Commande %s échouée sur Player %s : %s", name, self._player_id, err)

    async def async_update(self) -> None:
        try:
            status = await self._router._api.player.get_player_status(self._player_id) or {}
        except Exception as err:
            _LOGGER.debug("Statut Player %s indisponible : %s", self._player_id, err)
            self._attr_available = False
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
                vol_data = await self._router._api.player.get_player_volume(self._player_id) or {}
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
        self._attr_source = status.get("app") or status.get("source")

    async def async_set_volume_level(self, volume: float) -> None:
        await self._router._api.player.update_player_volume(
            volume=int(round(volume * 100)), player_id=self._player_id
        )

    async def async_mute_volume(self, mute: bool) -> None:
        await self._router._api.player.update_player_volume(
            mute=mute, player_id=self._player_id
        )

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

    async def async_turn_on(self) -> None:
        if self.state == MediaPlayerState.OFF:
            await self._try_power()

    async def async_turn_off(self) -> None:
        if self.state != MediaPlayerState.OFF:
            await self._try_power()

    async def _try_power(self) -> None:
        try:
            await self._command("play_pause")
        except Exception:
            pass
        try:
            await self._router._api.remote.send_key(code="power", key="power")
        except Exception as err:
            _LOGGER.debug("Touche power indisponible : %s", err)
