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

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Freebox remote entities from a config entry."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    
    # Récupérer les players disponibles
    try:
        players = await router._api.player.get_players()
    except Exception as err:
        _LOGGER.error("Failed to fetch Freebox Players: %s", err)
        return
    
    entities = [FreeboxRemote(hass, router, player) for player in players]
    
    if entities:
        async_add_entities(entities, update_before_add=True)
        # Enregistrement du service 'remote'
        platform = entity_platform.async_get_current_platform()
        platform.async_register_entity_service(
            "remote",
            {
                "code": str,
            },
            "async_send_command",
        )
        _LOGGER.debug(
            "Added %d remote entities for %s (%s)",
            len(entities),
            router.name,
            router.mac,
        )

class FreeboxRemote(FreeboxHomeEntity, RemoteEntity):
    """Representation of a Freebox Player remote."""

    _attr_supported_features = (
        RemoteEntityFeature.TURN_ON | RemoteEntityFeature.TURN_OFF
    )

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, player: dict[str, Any]
    ) -> None:
        """Initialize a Freebox remote."""
        # Création d'un faux node pour compatibilité avec FreeboxHomeEntity
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
        try:
            await self._router._api.remote.send_key(
                code="power", key="power", long_press=False
            )
            self._attr_is_on = True
            self.async_write_ha_state()
            _LOGGER.info("Turned on Freebox Player %s", self._player_id)
        except Exception as err:
            _LOGGER.error("Failed to turn on Player %s: %s", self._player_id, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the Freebox Player."""
        try:
            await self._router._api.remote.send_key(
                code="power", key="power", long_press=False
            )
            self._attr_is_on = False
            self.async_write_ha_state()
            _LOGGER.info("Turned off Freebox Player %s", self._player_id)
        except Exception as err:
            _LOGGER.error("Failed to turn off Player %s: %s", self._player_id, err)

    async def async_send_command(self, command: list[str], **kwargs: Any) -> None:
        """Send a command to the Freebox Player."""
        # Si 'code' est fourni dans kwargs (via le service), utiliser cette valeur
        commands = [kwargs.get("code")] if "code" in kwargs else command
        for cmd in commands:
            try:
                await self._router._api.remote.send_key(
                    code=cmd, key=cmd, long_press=False
                )
                _LOGGER.info("Sent command %s to Player %s", cmd, self._player_id)
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
