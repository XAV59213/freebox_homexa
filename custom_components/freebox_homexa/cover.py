"""Support for Freebox covers."""
import logging
import json
from typing import Any
from homeassistant.util import slugify
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
        if node["category"]==FreeboxHomeCategory.BASIC_SHUTTER:
            entities.append(FreeboxBasicShutter(hass, router, node))
            
        elif node["category"]==FreeboxHomeCategory.SHUTTER:
            entities.append(FreeboxShutter(hass, router, node))
            
        elif node["category"]==FreeboxHomeCategory.OPENER:
            entities.append(FreeboxShutter(hass, router, node))

    async_add_entities(entities, True)



class FreeboxBasicShutter(FreeboxHomeEntity,CoverEntity):

    def __init__(self, hass, router, node) -> None:
        """Initialize a Cover"""
        super().__init__(hass, router, node)
        self._command_up    = self.get_command_id(node['show_endpoints'], "slot", "up")
        self._command_stop  = self.get_command_id(node['show_endpoints'], "slot", "stop")
        self._command_down  = self.get_command_id(node['show_endpoints'], "slot", "down")
        self._command_state = self.get_command_id(node['show_endpoints'], "signal", "state")
        self._state         = self.get_node_value(node['show_endpoints'], "signal", "state")

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
        """Return if the cover is closed or not."""
        if(self._state == CoverState.OPEN):
            return False
        if(self._state == CoverState.CLOSED):
            return True
        return None

    async def async_open_cover(self, **kwargs):
        """Open cover."""
        await self.set_home_endpoint_value(self._command_up, {"value": None})
        self._state = CoverState.OPEN

    async def async_close_cover(self, **kwargs):
        """Close cover."""
        await self.set_home_endpoint_value(self._command_down, {"value": None})
        self._state = CoverState.CLOSED

    async def async_stop_cover(self, **kwargs):
        """Stop cover."""
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        self._state = None

    async def async_update(self):
        """Get the state & name and update it."""
        self._state = await self.get_home_endpoint_value(self._command_state)
        

    def convert_state(self, state):
        if( state ): 
            return CoverState.CLOSED
        elif( state is not None):
            return CoverState.OPEN
        else:
            return None

class FreeboxShutter(FreeboxHomeEntity, CoverEntity):
       
    def __init__(self, hass, router, node) -> None:
        """Initialize a Cover"""
        
        super().__init__(hass, router, node)
        
        self._command_position = self.get_command_id(node['show_endpoints'], "slot", "position_set")
        self._command_stop  = self.get_command_id(node['show_endpoints'], "slot", "stop")
        self._current_cover_position = self.get_value( "signal", "position_set")
        self._state = None

        # Go over all entities to find the switch
        self._invert_entity_id = None
        entity_registry = async_get(hass)
        for entity in entity_registry.entities.values():
            if (entity.unique_id == self._attr_unique_id + "_InvertSwitch"):
                self._invert_entity_id = entity.entity_id


    def get_invert_status(self):
        if(self._invert_entity_id == None):
            return False
        state = self._hass.states.get(self._invert_entity_id)
        if( state == None ):
            return False
        if( state.state == "on" ):
            return True
        return False

    def get_corrected_state(self, value):
        if( value == None ):
            return value
        if( self.get_invert_status() ):
            return 100 - value
        return value

    @property
    def device_class(self) -> str:
        if("garage" in self._attr_name.lower()):
            return CoverDeviceClass.GARAGE
        return CoverDeviceClass.SHUTTER

    @property
    def current_cover_position(self):
        return self._current_cover_position

    @property
    def current_cover_tilt_position(self):
        return None
        
    @property
    def is_closed(self):
        '''Return if the cover is closed or not.'''
        if(self._current_cover_position == 0):
            return True
        return False

    async def async_set_cover_position(self, position, **kwargs):
        """Set cover position."""
        await self.set_home_endpoint_value(self._command_position, {"value": self.get_corrected_state(position)})
        self._current_cover_position = self.get_corrected_state(position)


    async def async_open_cover(self, **kwargs):
        """Open cover."""
        await self.set_home_endpoint_value(self._command_position, {"value": 0})
        #self.state=CoverState.OPEN
        self._current_cover_position = 0


    async def async_close_cover(self, **kwargs):
        """Close cover."""
        await self.set_home_endpoint_value(self._command_position, {"value": 100})
        #self.state=CoverState.CLOSED
        self._current_cover_position = 100

    async def async_stop_cover(self, **kwargs):
        """Stop cover."""
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        self.async_update()

    async def async_update(self):
        """Get the state & name and update it."""
        self._current_cover_position = self.get_corrected_state(self.get_value( "signal", "position_set"))
