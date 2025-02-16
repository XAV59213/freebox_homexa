"""Support for Freebox covers."""
import logging
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.cover import CoverEntity, CoverDeviceClass, CoverState
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter
from homeassistant.helpers.entity_registry import async_get

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxHomeEntity = hass.data[DOMAIN][entry.unique_id]
    entities = []

    for nodeid, node in router.home_devices.items():
        if node["category"] == FreeboxHomeCategory.BASIC_SHUTTER:
            entities.append(FreeboxBasicShutter(hass, router, node))
        elif node["category"] in [FreeboxHomeCategory.SHUTTER, FreeboxHomeCategory.OPENER]:
            entities.append(FreeboxShutter(hass, router, node))

    async_add_entities(entities, True)

class FreeboxBasicShutter(FreeboxHomeEntity, CoverEntity):
    def __init__(self, hass, router, node) -> None:
        """Initialize a Cover"""
        super().__init__(hass, router, node)
        self._command_up = self.get_command_id(node['show_endpoints'], "slot", "up")
        self._command_stop = self.get_command_id(node['show_endpoints'], "slot", "stop")
        self._command_down = self.get_command_id(node['show_endpoints'], "slot", "down")
        self._command_state = self.get_command_id(node['show_endpoints'], "signal", "state")
        self._state = self.get_node_value(node['show_endpoints'], "signal", "state")

    @property
    def device_class(self) -> str:
        return CoverDeviceClass.SHUTTER

    @property
    def current_cover_position(self):
        return None

    @property
    def current_cover_tilt_position(self):
        return None

    @property
    def is_closed(self):
        return self._state == CoverState.CLOSED

    async def async_open_cover(self, **kwargs):
        await self.set_home_endpoint_value(self._command_up, {"value": None})
        self._state = CoverState.OPEN
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs):
        await self.set_home_endpoint_value(self._command_down, {"value": None})
        self._state = CoverState.CLOSED
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs):
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        self._state = None
        self.async_write_ha_state()

    async def async_update(self):
        self._state = await self.get_home_endpoint_value(self._command_state)
        self.async_write_ha_state()

class FreeboxShutter(FreeboxHomeEntity, CoverEntity):
    def __init__(self, hass, router, node) -> None:
        """Initialize a Cover"""
        super().__init__(hass, router, node)
        self._command_position = self.get_command_id(node['show_endpoints'], "slot", "position_set")
        self._command_stop = self.get_command_id(node['show_endpoints'], "slot", "stop")
        self._current_cover_position = self.get_corrected_state(self.get_value("signal", "position_set"))
        self._state = None
        entity_registry = async_get(hass)
        self._invert_entity_id = next(
            (entity.entity_id for entity in entity_registry.entities.values()
             if entity.unique_id == self._attr_unique_id + "_InvertSwitch"),
            None
        )

    def get_invert_status(self):
        state = self.hass.states.get(self._invert_entity_id) if self._invert_entity_id else None
        return state and state.state == "on"

    def get_corrected_state(self, value):
        return 100 - value if value is not None and self.get_invert_status() else value

    @property
    def device_class(self) -> str:
        return CoverDeviceClass.GARAGE if "garage" in self._attr_name.lower() else CoverDeviceClass.SHUTTER

    @property
    def current_cover_position(self):
        return self._current_cover_position

    @property
    def current_cover_tilt_position(self):
        return None

    @property
    def is_closed(self):
        return self._current_cover_position == 0

    async def async_set_cover_position(self, **kwargs):
        position = kwargs.get("position", 0)
        await self.set_home_endpoint_value(self._command_position, {"value": self.get_corrected_state(position)})
        self._current_cover_position = self.get_corrected_state(position)
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs):
        await self.set_home_endpoint_value(self._command_position, {"value": 0})
        self._current_cover_position = 0
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs):
        await self.set_home_endpoint_value(self._command_position, {"value": 100})
        self._current_cover_position = 100
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs):
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self):
        self._current_cover_position = self.get_corrected_state(self.get_value("signal", "position_set"))
        self.async_write_ha_state()

