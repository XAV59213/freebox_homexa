"""Support for Freebox Player remote control."""

import logging
from typing import Any

from homeassistant.components.remote import RemoteEntity, RemoteEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_platform

from .const import DOMAIN
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

# Liste des commandes valides pour la télécommande Freebox Player
VALID_COMMANDS = {
    "red", "green", "blue", "yellow", "power", "list", "tv", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "back", "0", "swap", "info", "epg", "mail", "media", "help", "options", "pip", "vol_inc", "vol_dec",
    "ok", "up", "right", "down", "left", "prgm_inc", "prgm_dec", "mute", "home", "rec", "bwd", "prev",
    "play", "fwd", "next"
}

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Freebox remote entities from a config entry."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    
    _LOGGER.debug("Starting setup for Freebox Player remote entities")
    
    try:
        players = await router._api.player.get_players()
        _LOGGER.debug("Found %d Freebox Players: %s", len(players), players)
    except Exception as err:
        _LOGGER.error("Failed to fetch Freebox Players: %s", err)
        return
    
    entities = [FreeboxRemote(hass, router, player) for player in players]
    
    if entities:
        async_add_entities(entities, update_before_add=True)
        platform = entity_platform.async_get_current_platform()
        
        # Enregistrement du service générique 'remote'
        platform.async_register_entity_service(
            "remote",
            {
                "code": str,
                "long_press": {"type": bool, "default": False, "optional": True},
                "repeat": {"type": int, "default": 0, "optional": True},
            },
            "async_send_command",
        )
        
        # Enregistrement d'un service spécifique pour chaque commande
        for cmd in VALID_COMMANDS:
            platform.async_register_entity_service(
                cmd,
                {
                    "long_press": {"type": bool, "default": False, "optional": True},
                    "repeat": {"type": int, "default": 0, "optional": True},
                },
                lambda entity, cmd=cmd, **kwargs: entity.async_send_specific_command(cmd, **kwargs),
            )
        
        _LOGGER.debug(
            "Added %d remote entities and %d command services for %s (%s)",
            len(entities),
            len(VALID_COMMANDS),
            router.name,
            router.mac,
        )
    else:
        _LOGGER.warning("No Freebox Player entities added - no players detected")

class FreeboxRemote(FreeboxHomeEntity, RemoteEntity):
    """Representation of a Freebox Player remote."""

    _attr_supported_features = (
        RemoteEntityFeature.TURN_ON | RemoteEntityFeature.TURN_OFF
    )

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, player: dict[str, Any]
    ) -> None:
        """Initialize a Freebox remote."""
        node = {
            "id": player["id"],
            "label": player.get("name", f"Player {player['id']}"),
            "category": "player",
            "props": {},
            "show_endpoints": [],
            "type": {"endpoints": []},
            "status": "active",
        }
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{router.mac}_player_{player['id']}"
        self._player_id = player["id"]
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the Freebox Player."""
        await self.async_send_specific_command("power", long_press=False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the Freebox Player."""
        await self.async_send_specific_command("power", long_press=False)

    async def async_send_command(self, command: list[str], **kwargs: Any) -> None:
        """Send a command to the Freebox Player (generic service)."""
        commands = [kwargs.get("code")] if "code" in kwargs else command
        long_press = kwargs.get("long_press", False)
        repeat = kwargs.get("repeat", 0)
        await self._send_commands(commands, long_press, repeat)

    async def async_send_specific_command(self, command: str, **kwargs: Any) -> None:
        """Send a specific command to the Freebox Player."""
        long_press = kwargs.get("long_press", False)
        repeat = kwargs.get("repeat", 0)
        await self._send_commands([command], long_press, repeat)

    async def _send_commands(self, commands: list[str], long_press: bool, repeat: int) -> None:
        """Helper method to send commands."""
        for cmd in commands:
            if cmd not in VALID_COMMANDS:
                _LOGGER.error("Invalid command '%s' for Player %s. Valid commands: %s", cmd, self._player_id, VALID_COMMANDS)
                continue
            try:
                await self._router._api.remote.send_key(
                    code=cmd, key=cmd, long_press=long_press, repeat=repeat
                )
                _LOGGER.info("Sent command %s to Player %s (long_press=%s, repeat=%d)", cmd, self._player_id, long_press, repeat)
                if cmd == "power":
                    self._attr_is_on = not self._attr_is_on  # Mise à jour de l'état pour power
                    self.async_write_ha_state()
            except Exception as err:
                _LOGGER.error("Failed to send command %s to Player %s: %s", cmd, self._player_id, err)

    async def async_update(self) -> None:
        """Update the remote state."""
        try:
            status = await self._router._api.player.get_player_status(self._player_id)
            self._attr_is_on = status.get("power_state") == "running"
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to update Player %s status: %s", self._player_id, err)
            self._attr_is_on = None
