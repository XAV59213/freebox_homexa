"""Support for Freebox cover entities (shutters and openers)."""

from typing import Any

import logging

from homeassistant.components.cover import (
    CoverEntity,
    CoverDeviceClass,
    CoverEntityFeature,
    ATTR_POSITION,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get

from .const import DOMAIN, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Freebox cover entities from a config entry."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]

    entities = [
        FreeboxBasicShutter(hass, router, node)
        if node["category"] == FreeboxHomeCategory.BASIC_SHUTTER
        else FreeboxShutter(hass, router, node)
        for node in router.home_devices.values()
        if node["category"]
        in {FreeboxHomeCategory.BASIC_SHUTTER, FreeboxHomeCategory.SHUTTER, FreeboxHomeCategory.OPENER}
    ]

    if entities:
        async_add_entities(entities, update_before_add=True)
        _LOGGER.debug(
            "Added %d cover entities for %s (%s)",
            len(entities),
            router.name,
            router.mac,
        )


class FreeboxBasicShutter(FreeboxHomeEntity, CoverEntity):
    """Representation of a basic Freebox shutter (up/stop/down only)."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        """Initialize a basic Freebox shutter."""
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{self._attr_unique_id}_basic_shutter"
        self._command_up = self.get_command_id(node["show_endpoints"], "slot", "up")
        self._command_stop = self.get_command_id(node["show_endpoints"], "slot", "stop")
        self._command_down = self.get_command_id(node["show_endpoints"], "slot", "down")
        self._command_state = self.get_command_id(node["show_endpoints"], "signal", "state")
        self._state: bool | None = None  # True = closed, False = open, None = unknown

    @property
    def device_class(self) -> str:
        """Return the device class of the cover."""
        return CoverDeviceClass.SHUTTER

    @property
    def current_cover_position(self) -> int | None:
        """Return the current cover position (not supported)."""
        return None

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return the current tilt position (not supported)."""
        return None

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed or not."""
        return self._state

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if self._command_up is None:
            _LOGGER.error("Open command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_up, {"value": None})
            self._state = False
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to open cover %s: %s", self._node_id, err)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        if self._command_down is None:
            _LOGGER.error("Close command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_down, {"value": None})
            self._state = True
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to close cover %s: %s", self._node_id, err)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        if self._command_stop is None:
            _LOGGER.error("Stop command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_stop, {"value": None})
            self._state = None
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to stop cover %s: %s", self._node_id, err)

    async def async_update(self) -> None:
        """Update the cover state from the Freebox."""
        if self._command_state is None:
            _LOGGER.error("State command not available for %s", self._node_id)
            self._state = None
            return
        try:
            state = await self.get_home_endpoint_value(self._command_state)
            self._state = self._convert_state(state)
        except Exception as err:
            _LOGGER.error("Failed to update cover state for %s: %s", self._node_id, err)
            self._state = None

    def _convert_state(self, state: Any) -> bool | None:
        """Convert Freebox state to HA closed state."""
        if state is True:
            return True  # Closed
        elif state is False:
            return False  # Open
        return None  # Unknown


class FreeboxShutter(FreeboxHomeEntity, CoverEntity):
    """Representation of a Freebox shutter with position control."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        """Initialize a Freebox shutter with position control."""
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{self._attr_unique_id}_shutter"
        self._command_position = self.get_command_id(node["show_endpoints"], "slot", "position_set")
        self._command_stop = self.get_command_id(node["show_endpoints"], "slot", "stop")
        self._current_cover_position: int | None = None
        self._invert_entity_id: str | None = None
        self._entity_registry = async_get(hass)
        self._find_invert_switch()

    def _find_invert_switch(self) -> None:
        """Find the associated inversion switch entity."""
        for entity in self._entity_registry.entities.values():
            if entity.unique_id == f"{self._router.mac}_home_{self._node_id}_invert_switch":
                self._invert_entity_id = entity.entity_id
                break

    def _get_invert_status(self) -> bool:
        """Return the inversion status from the associated switch."""
        if not self._invert_entity_id:
            return False
        state = self._hass.states.get(self._invert_entity_id)
        return state is not None and state.state == "on"

    def _get_corrected_position(self, value: int | None) -> int | None:
        """Correct the position based on inversion status."""
        if value is None:
            return None
        return 100 - value if self._get_invert_status() else value

    @property
    def device_class(self) -> str:
        """Return the device class of the cover."""
        return (
            CoverDeviceClass.GARAGE
            if "garage" in self._attr_name.lower()
            else CoverDeviceClass.SHUTTER
        )

    @property
    def current_cover_position(self) -> int | None:
        """Return the current cover position."""
        return self._current_cover_position

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return the current tilt position (not supported)."""
        return None

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed or not."""
        if self._current_cover_position is None:
            return None
        return self._current_cover_position == 0

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover position."""
        if self._command_position is None:
            _LOGGER.error("Set position command not supported for %s", self._node_id)
            return
        position = kwargs.get(ATTR_POSITION)
        if position is not None:
            try:
                corrected_position = self._get_corrected_position(position)
                await self.set_home_endpoint_value(self._command_position, {"value": corrected_position})
                self._current_cover_position = corrected_position
                self.async_write_ha_state()
            except Exception as err:
                _LOGGER.error("Failed to set position for %s: %s", self._node_id, err)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if self._command_position is None:
            _LOGGER.error("Open command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_position, {"value": self._get_corrected_position(100)})
            self._current_cover_position = self._get_corrected_position(100)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to open cover %s: %s", self._node_id, err)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        if self._command_position is None:
            _LOGGER.error("Close command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_position, {"value": self._get_corrected_position(0)})
            self._current_cover_position = self._get_corrected_position(0)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to close cover %s: %s", self._node_id, err)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        if self._command_stop is None:
            _LOGGER.error("Stop command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_stop, {"value": None})
            await self.async_update()
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to stop cover %s: %s", self._node_id, err)

    async def async_update(self) -> None:
        """Update the cover position from the Freebox."""
        try:
            position = self.get_value("signal", "position_set")
            self._current_cover_position = self._get_corrected_position(position)
        except Exception as err:
            _LOGGER.error("Failed to update cover position for %s: %s", self._node_id, err)
            self._current_cover_position = None
