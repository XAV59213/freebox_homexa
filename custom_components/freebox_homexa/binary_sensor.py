"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, REPEATER_MODEL, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

RAID_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="raid_degraded",
        name="degradé",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités de capteurs binaires Freebox."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]

    binary_entities: list[BinarySensorEntity] = [
        FreeboxRaidDegradedSensor(router, raid, description)
        for raid in router.raids.values()
        for description in RAID_SENSORS
    ]

    for node in router.home_devices.values():
        if node["category"] == FreeboxHomeCategory.PIR:
            binary_entities.append(FreeboxPirSensor(hass, router, node))
        elif node["category"] == FreeboxHomeCategory.DWS:
            binary_entities.append(FreeboxDwsSensor(hass, router, node))

        binary_entities.extend(
            FreeboxCoverSensor(hass, router, node)
            for endpoint in node["show_endpoints"]
            if (
                endpoint["name"] == "cover"
                and endpoint["ep_type"] == "signal"
                and endpoint.get("value") is not None
            )
        )

    tracked_repeaters: set[str] = set()

    @callback
    def add_repeaters() -> None:
        new_repeaters: list[FreeboxRepeaterSensor] = []
        for mac, device in router.repeaters.items():
            if mac in tracked_repeaters:
                continue
            new_repeaters.append(FreeboxRepeaterSensor(router, device))
            tracked_repeaters.add(mac)
        if new_repeaters:
            async_add_entities(new_repeaters, True)
            _LOGGER.info("%s répéteur(s) Wi-Fi ajouté(s)", len(new_repeaters))

    entry.async_on_unload(
        async_dispatcher_connect(hass, router.signal_device_new, add_repeaters)
    )
    add_repeaters()

    if binary_entities:
        async_add_entities(binary_entities, True)


class FreeboxHomeBinarySensor(FreeboxHomeEntity, BinarySensorEntity):
    """Représentation de base d'un capteur binaire Freebox Home."""
    _sensor_name = "trigger"

    def __init__(
        self,
        hass: HomeAssistant,
        router: FreeboxRouter,
        node: dict[str, Any],
        sub_node: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(hass, router, node, sub_node)
        self._node_id = node.get("id")
        if self._node_id is None:
            _LOGGER.error("L'appareil Freebox n'a pas d'ID valide")
            raise ValueError("L'appareil Freebox n'a pas d'ID valide")
        self._command_id = self.get_command_id(
            node["type"]["endpoints"], "signal", self._sensor_name
        )
        self._attr_is_on = self._edit_state(self.get_value("signal", self._sensor_name))

    async def async_update_signal(self) -> None:
        try:
            value = await self.get_home_endpoint_value(self._command_id)
            self._attr_is_on = self._edit_state(value)
            await super().async_update_signal()
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour du capteur {self._node_id}: {err}")
            self._attr_is_on = None

    def _edit_state(self, state: bool | None) -> bool | None:
        if state is None:
            return None
        if self._sensor_name == "trigger":
            return not state
        return state


class FreeboxPirSensor(FreeboxHomeBinarySensor):
    _attr_device_class = BinarySensorDeviceClass.MOTION


class FreeboxDwsSensor(FreeboxHomeBinarySensor):
    _attr_device_class = BinarySensorDeviceClass.DOOR


class FreeboxCoverSensor(FreeboxHomeBinarySensor):
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _sensor_name = "cover"

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        self._node_id = node.get("id")
        if self._node_id is None:
            raise ValueError("L'appareil Freebox n'a pas d'ID valide")
        cover_node = next(
            (
                ep
                for ep in node["type"]["endpoints"]
                if ep["name"] == self._sensor_name and ep["ep_type"] == "signal"
            ),
            None,
        )
        super().__init__(hass, router, node, cover_node)


class FreeboxRepeaterSensor(BinarySensorEntity):
    """Répéteur Wi-Fi Free (F-RP01A) : en ligne + nombre de clients."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "En ligne"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:wifi-sync"

    def __init__(self, router: FreeboxRouter, device: dict[str, Any]) -> None:
        self._router = router
        self._mac = device["l2ident"]["id"]
        name = (device.get("primary_name") or "").strip() or f"Répéteur Wi-Fi {self._mac[-5:]}"
        device_info: dict[str, Any] = {
            "identifiers": {(DOMAIN, f"repeater_{self._mac}")},
            "connections": {(CONNECTION_NETWORK_MAC, self._mac)},
            "manufacturer": device.get("vendor_name") or "Freebox SAS",
            "model": device.get("model") or REPEATER_MODEL,
            "name": name,
        }
        if router.device_id:
            device_info["via_device_id"] = router.device_id
        self._attr_device_info = DeviceInfo(**device_info)
        self._attr_unique_id = f"{router.mac}_repeater_{self._mac}"
        self._attr_is_on = bool(device.get("active"))
        self._attr_extra_state_attributes = {
            "mac": self._mac,
            "clients": device.get("client_count", 0),
            "host_type": device.get("host_type"),
        }

    @callback
    def async_update_state(self) -> None:
        device = self._router.repeaters.get(self._mac) or self._router.devices.get(self._mac)
        if device is None:
            self._attr_is_on = False
            self._attr_extra_state_attributes = {"mac": self._mac, "clients": 0}
            return
        self._attr_is_on = bool(device.get("active"))
        self._attr_extra_state_attributes = {
            "mac": self._mac,
            "clients": device.get("client_count", 0),
            "host_type": device.get("host_type"),
        }

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


class FreeboxRaidDegradedSensor(BinarySensorEntity):
    """Représentation d'un capteur RAID dégradé Freebox."""
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        router: FreeboxRouter,
        raid: dict[str, Any],
        description: BinarySensorEntityDescription,
    ) -> None:
        self.entity_description = description
        self._router = router
        self._attr_device_info = router.device_info
        self._raid = raid
        self._attr_name = f"Array RAID {raid['id']} {description.name}"
        self._attr_unique_id = f"{router.mac}_{description.key}_{raid['name']}_{raid['id']}"

    @callback
    def async_update_state(self) -> None:
        self._raid = self._router.raids.get(self._raid["id"])
        if self._raid is None:
            self._attr_is_on = None
        else:
            self._attr_is_on = self._raid.get("degraded", False)

    @property
    def is_on(self) -> bool | None:
        return self._attr_is_on

    @callback
    def async_on_demand_update(self) -> None:
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_sensor_update,
                self.async_on_demand_update,
            )
        )
