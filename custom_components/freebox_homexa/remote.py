"""Support for Freebox Player remote control."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.remote import RemoteEntity, RemoteEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .media_player import player_device_info
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

VALID_COMMANDS = {
    "red", "green", "blue", "yellow", "power", "list", "tv", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "back", "0", "swap", "info", "epg", "mail", "media", "help", "options", "pip", "vol_inc", "vol_dec",
    "ok", "up", "right", "down", "left", "prgm_inc", "prgm_dec", "mute", "home", "rec", "bwd", "prev",
    "play", "fwd", "next"
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    try:
        players = await router._api.player.get_players() or []
    except Exception as err:
        _LOGGER.warning("Impossible de lister les Freebox Player : %s", err)
        return

    entities = [FreeboxRemote(router, player, entry) for player in players]
    if entities:
        async_add_entities(entities, True)


class FreeboxRemote(RemoteEntity):
    """Télécommande du Freebox Player."""

    # RemoteEntityFeature only exposes LEARN_COMMAND / DELETE_COMMAND / ACTIVITY.
    # Power is provided by ToggleEntity (async_turn_on / async_turn_off).
    _attr_supported_features = RemoteEntityFeature(0)
    _attr_has_entity_name = True
    _attr_name = "Télécommande"

    def __init__(
        self, router: FreeboxRouter, player: dict[str, Any], entry: ConfigEntry
    ) -> None:
        self._router = router
        self._player_id = player["id"]
        self._remote_code = entry.data.get("remote_code")
        self._attr_unique_id = f"{router.mac}_player_{self._player_id}_remote"
        self._attr_device_info = player_device_info(router, player)
        self._attr_is_on = bool(player.get("reachable"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_commands(["power"], False, 0)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_commands(["power"], False, 0)

    async def async_send_command(self, command: list[str], **kwargs: Any) -> None:
        commands = [kwargs["code"]] if kwargs.get("code") else command
        await self._send_commands(
            [str(c) for c in commands if c],
            bool(kwargs.get("long_press", False)),
            int(kwargs.get("repeat", 0) or 0),
        )

    async def _send_commands(self, commands: list[str], long_press: bool, repeat: int) -> None:
        if not self._remote_code:
            _LOGGER.warning(
                "Code télécommande réseau manquant. Sur le Player : Réglages > Système > Informations."
            )
            return
        for cmd in commands:
            if cmd not in VALID_COMMANDS:
                _LOGGER.error("Commande invalide '%s'", cmd)
                continue
            try:
                await self._router._api.remote.send_key(
                    code=str(self._remote_code),
                    key=cmd,
                    long_press=long_press,
                    repeat=repeat,
                )
            except Exception as err:
                _LOGGER.error("Échec commande %s Player %s : %s", cmd, self._player_id, err)

    async def async_update(self) -> None:
        try:
            status = await self._router._api.player.get_player_status(self._player_id) or {}
            power = str(status.get("power_state") or "").lower()
            self._attr_is_on = power in {"running", "on"} or bool(status)
        except Exception:
            self._attr_is_on = None
