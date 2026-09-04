"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K) dans Home Assistant."""

from __future__ import annotations
from datetime import datetime
from typing import Any
import logging

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_DEVICE_NAME, DEVICE_ICONS, DOMAIN
from .router import FreeboxRouter, is_freebox_repeater

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    tracked: set[str] = set()

    @callback
    def update_router() -> None:
        add_entities(router, async_add_entities, tracked)

    entry.async_on_unload(
        async_dispatcher_connect(hass, router.signal_device_new, update_router)
    )
    update_router()


@callback
def add_entities(
    router: FreeboxRouter, async_add_entities: AddEntitiesCallback, tracked: set[str]
) -> None:
    new_tracked = []

    for mac, device in router.devices.items():
        if mac in tracked:
            continue
        new_tracked.append(FreeboxDevice(router, device))
        tracked.add(mac)

    if new_tracked:
        async_add_entities(new_tracked, True)


class FreeboxDevice(ScannerEntity):
    """Représentation d'un appareil Freebox dans Home Assistant."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, router: FreeboxRouter, device: dict[str, Any]) -> None:
        self._router = router
        self._name = device["primary_name"].strip() or DEFAULT_DEVICE_NAME
        self._mac = device["l2ident"]["id"]
        self._manufacturer = device.get("vendor_name", "Inconnu")
        self._attr_icon = icon_for_freebox_device(device)
        self._active = False
        self._attr_extra_state_attributes: dict[str, Any] = {}
        self._attr_device_info = self._build_device_info(device)

    def _build_device_info(self, device: dict[str, Any]) -> DeviceInfo:
        if device.get("attrs") is not None:
            return self._router.device_info

        if is_freebox_repeater(device, self._router.mac):
            return DeviceInfo(
                identifiers={(DOMAIN, f"repeater_{self._mac}")},
                connections={(CONNECTION_NETWORK_MAC, self._mac)},
                manufacturer=device.get("vendor_name") or "Freebox SAS",
                model=device.get("model") or "F-RP01A",
                name=self._name,
                via_device=(DOMAIN, self._router.mac),
            )

        parent = device.get("wifi_parent") or {}
        identifier = parent.get("identifier") or self._router.mac
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self._mac)},
            manufacturer=self._manufacturer,
            name=self._name,
            via_device=(DOMAIN, identifier),
        )

    @callback
    def async_update_state(self) -> None:
        device = self._router.devices.get(self._mac)
        if not device:
            self._active = False
            self._attr_extra_state_attributes = {}
            return

        self._active = device.get("active", False)
        self._attr_device_info = self._build_device_info(device)

        if device.get("attrs") is None:
            last_reachable = device.get("last_time_reachable")
            last_activity = device.get("last_activity")
            attributes: dict[str, Any] = {
                "last_time_reachable": (
                    datetime.fromtimestamp(last_reachable).isoformat() if last_reachable else None
                ),
                "last_time_activity": (
                    datetime.fromtimestamp(last_activity).isoformat() if last_activity else None
                ),
            }
            attributes.update(device.get("wifi") or {})
            parent = device.get("wifi_parent") or {}
            if parent.get("name"):
                attributes["connecte_sur"] = parent["name"]
                attributes["ap_kind"] = parent.get("kind")
            self._attr_extra_state_attributes = attributes
        else:
            self._attr_extra_state_attributes = device.get("attrs", {})

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_connected(self) -> bool:
        return self._active

    @callback
    def async_on_demand_update(self) -> None:
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_device_update,
                self.async_on_demand_update,
            )
        )


def icon_for_freebox_device(device: dict[str, Any]) -> str:
    return DEVICE_ICONS.get(device.get("host_type", ""), "mdi:help-network")
