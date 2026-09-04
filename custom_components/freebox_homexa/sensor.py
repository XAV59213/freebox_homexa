from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfDataRate,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DEFAULT_DEVICE_NAME, DOMAIN
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter
from .tnt_const import DEFAULT_CHANNELS
from .tnt_sensor import HomexaTntSensor
from .wifi_ap_sensors import async_setup_wifi_ap_sensors

_LOGGER = logging.getLogger(__name__)

CONNECTION_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="rate_down",
        name="Vitesse de téléchargement Freebox",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        icon="mdi:download-network",
    ),
    SensorEntityDescription(
        key="rate_up",
        name="Vitesse de téléversement Freebox",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        icon="mdi:upload-network",
    ),
    SensorEntityDescription(
        key="ipv4",
        name="IP Externe Freebox",
        icon="mdi:ip-network",
    ),
    SensorEntityDescription(
        key="uptime",
        name="Temps de fonctionnement Freebox",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement="s",
        icon="mdi:clock-outline",
    ),
)

CALL_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="missed", name="Appels manqués Freebox", icon="mdi:phone-missed"),
)

DISK_PARTITION_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="partition_free_space",
        name="espace libre",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:harddisk",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    entities: list[SensorEntity] = []

    entities.extend(
        FreeboxSensor(
            router,
            SensorEntityDescription(
                key=sensor_name,
                name=f"Freebox {sensor_name}",
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
            ),
        )
        for sensor_name in router.sensors_temperature
    )
    entities.extend(FreeboxSensor(router, description) for description in CONNECTION_SENSORS)
    entities.extend(FreeboxCallSensor(router, description) for description in CALL_SENSORS)
    entities.extend(
        FreeboxDiskSensor(router, disk, partition, description)
        for disk in router.disks.values()
        for partition in disk["partitions"].values()
        for description in DISK_PARTITION_SENSORS
    )
    for node in router.home_devices.values():
        for endpoint in node["show_endpoints"]:
            if (
                endpoint["name"] == "battery"
                and endpoint["ep_type"] == "signal"
                and endpoint.get("value") is not None
            ):
                entities.append(FreeboxBatterySensor(hass, router, node, endpoint))

    coordinator = hass.data[DOMAIN].get("tnt_coordinator")
    if coordinator is not None:
        channels = list(coordinator.data or DEFAULT_CHANNELS)
        entities.extend(
            HomexaTntSensor(coordinator, channel_id, router.mac) for channel_id in channels
        )

    if entities:
        async_add_entities(entities, True)

    tracked_wifi: set[str] = set()

    @callback
    def add_wifi_signal_sensors() -> None:
        new_sensors: list[FreeboxWifiSignalSensor] = []
        for mac, device in router.devices.items():
            if mac in tracked_wifi:
                continue
            if device.get("attrs") is not None:
                continue
            wifi = device.get("wifi") or {}
            if "wifi_signal_dbm" not in wifi and wifi.get("connectivity") != "wifi":
                continue
            new_sensors.append(FreeboxWifiSignalSensor(router, device))
            tracked_wifi.add(mac)
        if new_sensors:
            async_add_entities(new_sensors, True)
            _LOGGER.info("%s capteur(s) RSSI Wi-Fi ajouté(s)", len(new_sensors))

    entry.async_on_unload(
        async_dispatcher_connect(hass, router.signal_device_new, add_wifi_signal_sensors)
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, router.signal_device_update, add_wifi_signal_sensors)
    )
    add_wifi_signal_sensors()
    async_setup_wifi_ap_sensors(router, entry, async_add_entities)


class FreeboxSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, router: FreeboxRouter, description: SensorEntityDescription) -> None:
        self.entity_description = description
        self._router = router
        self._attr_unique_id = f"{router.mac} {description.name}"
        self._attr_device_info = router.device_info

    @callback
    def async_update_state(self) -> None:
        if self.entity_description.key in ["ipv4"]:
            state = self._router._attrs.get("IPv4")
        elif self.entity_description.key == "uptime":
            state = self._router.sensors_connection.get("uptime")
        else:
            state = self._router.sensors.get(self.entity_description.key)
        if state is None:
            self._attr_native_value = None
        elif self.native_unit_of_measurement == UnitOfDataRate.KILOBYTES_PER_SECOND:
            self._attr_native_value = round(state / 8000, 2)
        else:
            self._attr_native_value = state

    @callback
    def async_on_demand_update(self) -> None:
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._router.signal_sensor_update, self.async_on_demand_update
            )
        )


class FreeboxCallSensor(FreeboxSensor):
    def __init__(self, router: FreeboxRouter, description: SensorEntityDescription) -> None:
        super().__init__(router, description)
        self._call_list_for_type: list[dict[str, Any]] = []

    @callback
    def async_update_state(self) -> None:
        self._call_list_for_type = [
            call
            for call in self._router.call_list or []
            if call.get("new", False) and self.entity_description.key == call.get("type")
        ]
        self._attr_native_value = len(self._call_list_for_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            dt_util.utc_from_timestamp(call["datetime"]).isoformat(): call["name"]
            for call in self._call_list_for_type
        }


class FreeboxDiskSensor(FreeboxSensor):
    def __init__(self, router, disk, partition, description) -> None:
        super().__init__(router, description)
        self._disk_id = disk["id"]
        self._partition_id = partition["id"]
        self._attr_name = f"{partition['label']} {description.name}"
        self._attr_unique_id = f"{router.mac} {description.key} {disk['id']} {partition['id']}"
        device_info = {
            "identifiers": {(DOMAIN, disk["id"])},
            "model": disk["model"],
            "name": f"Disque {disk['id']}",
            "sw_version": disk["firmware"],
        }
        if router.device_id:
            device_info["via_device_id"] = router.device_id
        self._attr_device_info = DeviceInfo(**device_info)

    @callback
    def async_update_state(self) -> None:
        disk = self._router.disks.get(self._disk_id)
        if disk is None:
            self._attr_native_value = None
            return
        partition = disk["partitions"].get(self._partition_id)
        if partition is None:
            self._attr_native_value = None
            return
        total_bytes = partition.get("total_bytes")
        free_bytes = partition.get("free_bytes")
        if total_bytes is None or total_bytes <= 0:
            self._attr_native_value = 0
        elif free_bytes is None:
            self._attr_native_value = None
        else:
            self._attr_native_value = round((free_bytes / total_bytes) * 100, 2)


class FreeboxBatterySensor(FreeboxHomeEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> int | None:
        return self.get_value("signal", "battery")


class FreeboxWifiSignalSensor(SensorEntity):
    """Force du signal Wi-Fi (RSSI) d'un client vu par la Freebox."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Signal Wi-Fi"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:wifi-strength-2"

    def __init__(self, router: FreeboxRouter, device: dict[str, Any]) -> None:
        self._router = router
        self._mac = device["l2ident"]["id"]
        name = (device.get("primary_name") or "").strip() or DEFAULT_DEVICE_NAME
        device_info: dict[str, Any] = {
            "connections": {(CONNECTION_NETWORK_MAC, self._mac)},
            "manufacturer": device.get("vendor_name") or "Inconnu",
            "name": name,
        }
        if router.device_id:
            device_info["via_device_id"] = router.device_id
        self._attr_device_info = DeviceInfo(**device_info)
        self._attr_unique_id = f"{router.mac}_{self._mac}_wifi_signal"
        self._attr_extra_state_attributes: dict[str, Any] = {}
        self._attr_native_value = None

    @callback
    def async_update_state(self) -> None:
        device = self._router.devices.get(self._mac)
        if not device:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            self._attr_available = False
            return
        wifi = device.get("wifi") or {}
        self._attr_available = True
        self._attr_native_value = wifi.get("wifi_signal_dbm")
        self._attr_extra_state_attributes = {
            key: value
            for key, value in wifi.items()
            if key != "wifi_signal_dbm"
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
