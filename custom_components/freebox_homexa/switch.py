"""Support for Freebox Delta, Revolution and Mini 4K."""

from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Any
import os

from pathlib import Path
from freebox_api.exceptions import InsufficientPermissionsError
from homeassistant.util import slugify
from homeassistant.core import callback
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.storage import Store

from .const import DOMAIN ,STORAGE_VERSION, STORAGE_KEY
from .router import FreeboxRouter
from .entity import FreeboxHomeEntity
#from .base_class import FreeboxBaseClass

_LOGGER = logging.getLogger(__name__)


SWITCH_DESCRIPTIONS = [
    SwitchEntityDescription(
        key="wifi",
        name="Freebox WiFi",
        entity_category=EntityCategory.CONFIG,
    )
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the switch."""
    
    router: FreeboxHomeEntity = hass.data[DOMAIN][entry.unique_id]
    entities = []

    for nodeid, node in router.home_devices.items():
        if node["category"]=="shutter":
            entities.append(FreeboxShutterInvertSwitchEntity(hass, router, node))
        elif node["category"]=="opener":
            entities.append(FreeboxShutterInvertSwitchEntity(hass, router, node))
    
    for entity_description in SWITCH_DESCRIPTIONS:
        entities.append(FreeboxSwitch(router, entity_description))
        #_LOGGER.error("wifi: " + str(entity_description)) 
    
    async_add_entities(entities, True)


class FreeboxSwitch(SwitchEntity):
    """Representation of a freebox switch."""

    def __init__(
        self, router: FreeboxRouter, entity_description: SwitchEntityDescription
    ) -> None:
        """Initialize the switch."""
        self.entity_description = entity_description
        self._router = router
        self._attr_device_info = router.device_info
        self._attr_unique_id = f"{router.mac} {entity_description.name}"

    async def _async_set_state(self, enabled: bool) -> None:
        """Turn the switch on or off."""
        try:
            await self._router.wifi.set_global_config({"enabled": enabled})
        except InsufficientPermissionsError:
            _LOGGER.warning(
                "Home Assistant does not have permissions to modify the Freebox"
                " settings. Please refer to documentation"
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set_state(False)

    async def async_update(self) -> None:
        """Get the state and update it."""
        data = await self._router.wifi.get_global_config()
        self._attr_is_on = bool(data["enabled"])
        
        
#class FreeboxShutterInvertSwitchEntity(FreeboxBaseClass, SwitchEntity):
class FreeboxShutterInvertSwitchEntity(FreeboxHomeEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, hass, router, node):
        super().__init__(hass, router, node)

        self._attr_unique_id = self._attr_unique_id + '_InvertSwitch'
        self._attr_icon = "mdi:directions-fork"
        self._name = "Inversion Positionnement"

        self._state = False
        freebox_path = Store(hass, STORAGE_VERSION, STORAGE_KEY).path
        self._path = Path(f"{freebox_path}/{slugify(self._attr_unique_id)}.conf")
        


    @property
    def translation_key(self):
        return "invert_switch"

    @property
    def is_on(self) -> bool | None:
        """Return True if entity is on."""
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._hass.async_add_executor_job(self._path.write_text, '1')
        self._state = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hass.async_add_executor_job(self._path.write_text, '0')
        self._state = False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    async def async_update(self) -> None:
        try:
            value = await self._hass.async_add_executor_job(self._path.read_text)
            if( value == "1"):
                self._state = True
            else:
                self._state = False
        except OSError as e:
            pass