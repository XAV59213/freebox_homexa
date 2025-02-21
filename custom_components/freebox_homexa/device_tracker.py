"""Support for tracking Freebox devices (Freebox v6 and Freebox mini 4K)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.device_tracker import SourceType, ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_DEVICE_NAME, DEVICE_ICONS, DOMAIN
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up device tracker entities for Freebox component."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    tracked: set[str] = set()

    @callback
    def update_router() -> None:
        """Update router devices and add new trackers."""
        add_entities(router, async_add_entities, tracked)

    entry.async_on_unload(
        async_dispatcher_connect(hass, router.signal_device_new, update_router)
    )
    update_router()


@callback
def add_entities(
    router: FreeboxRouter, async_add_entities: AddEntitiesCallback, tracked: set[str]
) -> None:
    """Add new device tracker entities from the router."""
    new_tracked = [
        FreeboxDevice(router, device)
        for mac, device in router.devices.items()
        if mac not in tracked
    ]
    if new_tracked:
        async_add_entities(new_tracked, update_before_add=True)
        tracked.update(device.mac_address for device in new_tracked)
        _LOGGER.debug(
            "Added %d new device trackers for %s (%s)",
            len(new_tracked),
            router.name,
            router.mac,
        )


class FreeboxDevice(ScannerEntity):
    """Representation of a Freebox device tracker."""

    _attr_should_poll = False
    _attr_source_type = SourceType.ROUTER

    def __init__(self, router: FreeboxRouter, device: dict[str, Any]) -> None:
        """Initialize a Freebox device tracker."""
        self._router = router
        self._mac = device["l2ident"]["id"]
        self._name = device["primary_name"].strip() or DEFAULT_DEVICE_NAME
        self._manufacturer = device.get("vendor_name", "Unknown")
        self._attr_icon = icon_for_freebox_device(device)
        self._active = False
        self._attr_unique_id = f"{router.mac}_{self._mac}"
        self._attr_extra_state_attributes: dict[str, Any] = {}

    @callback
    def async_update_state(self) -> None:
        """Update the device state from router data."""
        device = self._router.devices.get(self._mac)
        if not device:
            _LOGGER.warning("Device %s not found in router data", self._mac)
            self._active = False
            self._attr_extra_state_attributes = {}
            return

        self._active = device.get("active", False)
        if device.get("attrs") is None:  # Regular device
            last_reachable = device.get("last_time_reachable")
            last_activity = device.get("last_activity")
            self._attr_extra_state_attributes = {
                "last_time_reachable": (
                    datetime.fromtimestamp(last_reachable).isoformat()
                    if last_reachable
                    else None
                ),
                "last_time_activity": (
                    datetime.fromtimestamp(last_activity).isoformat()
                    if last_activity
                    else None
                ),
            }
        else:  # Router itself
            self._attr_extra_state_attributes = device.get("attrs", {})

    @property
    def mac_address(self) -> str:
        """Return the MAC address of the device."""
        return self._mac

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def is_connected(self) -> bool:
        """Return True if the device is connected to the network."""
        return self._active

    @property
    def manufacturer(self) -> str:
        """Return the manufacturer of the device."""
        return self._manufacturer

    @callback
    def async_on_demand_update(self) -> None:
        """Handle on-demand state update."""
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added to Home Assistant."""
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_device_update,
                self.async_on_demand_update,
            )
        )


def icon_for_freebox_device(device: dict[str, Any]) -> str:
    """Return the icon for a Freebox device based on its type."""
    return DEVICE_ICONS.get(device.get("host_type", ""), "mdi:help-network")
