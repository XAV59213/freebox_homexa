"""Support for Freebox switch entities (WiFi and shutter/opener inversion)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from freebox_api.exceptions import InsufficientPermissionsError
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION, STORAGE_KEY, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

# WiFi switch description
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
    """Set up Freebox switch entities from a config entry."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]

    # WiFi switch
    wifi_switches = [FreeboxSwitch(router, desc) for desc in SWITCH_DESCRIPTIONS]

    # Shutter and opener inversion switches
    invert_switches = [
        FreeboxShutterInvertSwitchEntity(hass, router, node)
        for node in router.home_devices.values()
        if node["category"] in {FreeboxHomeCategory.SHUTTER, FreeboxHomeCategory.OPENER}
    ]

    entities = wifi_switches + invert_switches
    if entities:
        async_add_entities(entities, update_before_add=True)
        _LOGGER.debug(
            "Added %d switch entities for %s (%s)",
            len(entities),
            router.name,
            router.mac,
        )


class FreeboxSwitch(SwitchEntity):
    """Representation of a Freebox WiFi switch."""

    def __init__(
        self, router: FreeboxRouter, entity_description: SwitchEntityDescription
    ) -> None:
        """Initialize the WiFi switch."""
        self.entity_description = entity_description
        self._router = router
        self._attr_device_info = router.device_info
        self._attr_unique_id = f"{router.mac}_{entity_description.key}"

    async def _async_set_state(self, enabled: bool) -> None:
        """Set the WiFi state (on/off)."""
        try:
            await self._router.wifi.set_global_config({"enabled": enabled})
            _LOGGER.info(
                "WiFi %s for %s",
                "enabled" if enabled else "disabled",
                self._router.name,
            )
        except InsufficientPermissionsError:
            _LOGGER.warning(
                "Insufficient permissions to modify Freebox WiFi settings for %s. "
                "Refer to documentation for setup instructions.",
                self._router.name,
            )
            raise

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the WiFi switch on."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the WiFi switch off."""
        await self._async_set_state(False)

    async def async_update(self) -> None:
        """Update the WiFi switch state."""
        try:
            data = await self._router.wifi.get_global_config()
            self._attr_is_on = bool(data["enabled"])
        except Exception as err:
            _LOGGER.error("Failed to update WiFi state for %s: %s", self._router.name, err)
            self._attr_is_on = None


class FreeboxShutterInvertSwitchEntity(FreeboxHomeEntity, SwitchEntity):
    """Representation of a Freebox shutter/opener inversion switch."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:directions-fork"

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        """Initialize the shutter/opener inversion switch."""
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{self._attr_unique_id}_invert_switch"
        self._attr_name = "Invert Positioning"
        self._storage = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{self._attr_unique_id}")
        self._state: bool | None = None

    @property
    def translation_key(self) -> str:
        """Return the translation key for this entity."""
        return "invert_switch"

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the inversion switch on."""
        await self._storage.async_save({"state": True})
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the inversion switch off."""
        await self._storage.async_save({"state": False})
        self._state = False
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return True

    async def async_update(self) -> None:
        """Update the inversion switch state from storage."""
        try:
            data = await self._storage.async_load()
            self._state = data.get("state", False) if data else False
        except Exception as err:
            _LOGGER.error(
                "Failed to load inversion state for %s (%s): %s",
                self._attr_name,
                self._node_id,
                err,
            )
            self._state = None
