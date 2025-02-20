"""Support for Freebox sensors (connection, calls, disk, and battery)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfDataRate, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

# Connection speed sensors (download/upload rates)
CONNECTION_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="rate_down",
        name="Freebox Download Speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        icon="mdi:download-network",
    ),
    SensorEntityDescription(
        key="rate_up",
        name="Freebox Upload Speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        icon="mdi:upload-network",
    ),
)

# Call-related sensors
CALL_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="missed",
        name="Freebox Missed Calls",
        icon="mdi:phone-missed",
    ),
)

# Disk partition sensors
DISK_PARTITION_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="partition_free_space",
        name="Free Space",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:harddisk",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Freebox sensor entities from a config entry."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]

    # Temperature sensors
    temp_sensors = [
        FreeboxSensor(
            router,
            SensorEntityDescription(
                key=name,
                name=f"Freebox {name}",
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
            ),
        )
        for name in router.sensors_temperature
    ]
    _LOGGER.debug(
        "Adding %d temperature sensors for %s (%s)",
        len(temp_sensors),
        router.name,
        router.mac,
    )

    # Connection speed sensors
    conn_sensors = [FreeboxSensor(router, desc) for desc in CONNECTION_SENSORS]

    # Call sensors
    call_sensors = [FreeboxCallSensor(router, desc) for desc in CALL_SENSORS]

    # Disk partition sensors
    disk_sensors = [
        FreeboxDiskSensor(router, disk, partition, desc)
        for disk in router.disks.values()
        for partition in disk["partitions"].values()
        for desc in DISK_PARTITION_SENSORS
    ]
    _LOGGER.debug(
        "Adding %d disk sensors for %d disks on %s (%s)",
        len(disk_sensors),
        len(router.disks),
        router.name,
        router.mac,
    )

    # Battery sensors for Freebox Home devices
    battery_sensors = [
        FreeboxBatterySensor(hass, router, node, endpoint)
        for node in router.home_devices.values()
        for endpoint in node["show_endpoints"]
        if endpoint["name"] == "battery"
        and endpoint["ep_type"] == "signal"
        and endpoint.get("value") is not None
    ]

    # Add all entities
    all_entities = temp_sensors + conn_sensors + call_sensors + disk_sensors + battery_sensors
    if all_entities:
        async_add_entities(all_entities, update_before_add=True)


class FreeboxSensor(SensorEntity):
    """Base representation of a Freebox sensor."""

    _attr_should_poll = False

    def __init__(
        self, router: FreeboxRouter, description: SensorEntityDescription
    ) -> None:
        """Initialize a Freebox sensor."""
        self.entity_description = description
        self._router = router
        self._attr_unique_id = f"{router.mac} {description.name}"
        self._attr_device_info = router.device_info

    @callback
    def async_update_state(self) -> None:
        """Update the sensor state from router data."""
        state = self._router.sensors.get(self.entity_description.key)
        if state is None:
            self._attr_native_value = None
            return

        if self.native_unit_of_measurement == UnitOfDataRate.KILOBYTES_PER_SECOND:
            self._attr_native_value = round(state / 1000, 2)  # Convert bytes/s to KB/s
        else:
            self._attr_native_value = state

    @callback
    def async_on_demand_update(self) -> None:
        """Handle on-demand state update."""
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_sensor_update,
                self.async_on_demand_update,
            )
        )


class FreeboxCallSensor(FreeboxSensor):
    """Representation of a Freebox call sensor (e.g., missed calls)."""

    def __init__(
        self, router: FreeboxRouter, description: SensorEntityDescription
    ) -> None:
        """Initialize a Freebox call sensor."""
        super().__init__(router, description)
        self._call_list_for_type: list[dict[str, Any]] = []

    @callback
    def async_update_state(self) -> None:
        """Update the call sensor state."""
        self._call_list_for_type = [
            call
            for call in self._router.call_list or []
            if call["new"] and self.entity_description.key == call["type"]
        ]
        self._attr_native_value = len(self._call_list_for_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes for call sensors."""
        return {
            dt_util.utc_from_timestamp(call["datetime"]).isoformat(): call["name"]
            for call in self._call_list_for_type
        }


class FreeboxDiskSensor(FreeboxSensor):
    """Representation of a Freebox disk partition sensor."""

    def __init__(
        self,
        router: FreeboxRouter,
        disk: dict[str, Any],
        partition: dict[str, Any],
        description: SensorEntityDescription,
    ) -> None:
        """Initialize a Freebox disk sensor."""
        super().__init__(router, description)
        self._disk_id = disk["id"]
        self._partition_id = partition["id"]
        self._attr_name = f"{partition['label']} {description.name}"
        self._attr_unique_id = f"{router.mac} {description.key} {disk['id']} {partition['id']}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, disk["id"])},
            model=disk["model"],
            name=f"Disk {disk['id']}",
            sw_version=disk["firmware"],
            via_device=(DOMAIN, router.mac),
        )

    @callback
    def async_update_state(self) -> None:
        """Update the disk sensor state."""
        disk = self._router.disks.get(self._disk_id, {})
        partition = disk.get("partitions", {}).get(self._partition_id, {})
        total_bytes = partition.get("total_bytes", 0)
        if total_bytes > 0:
            self._attr_native_value = round(partition["free_bytes"] * 100 / total_bytes, 2)
        else:
            self._attr_native_value = None


class FreeboxBatterySensor(FreeboxHomeEntity, SensorEntity):
    """Representation of a Freebox Home battery sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> int | None:
        """Return the current battery level."""
        return self.get_value("signal", "battery")
