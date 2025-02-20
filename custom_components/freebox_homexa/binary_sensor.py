"""Support for Freebox binary sensors (RAID, motion, door, and cover states)."""

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
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

# RAID diagnostic sensors
RAID_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="raid_degraded",
        name="Degraded",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Freebox binary sensor entities from a config entry."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]

    # RAID degraded sensors
    raid_sensors = [
        FreeboxRaidDegradedSensor(router, raid, desc)
        for raid in router.raids.values()
        for desc in RAID_SENSORS
    ]
    _LOGGER.debug(
        "Adding %d RAID sensors for %s (%s)",
        len(raid_sensors),
        router.name,
        router.mac,
    )

    # Freebox Home binary sensors (PIR, DWS, Cover)
    home_sensors = []
    for node in router.home_devices.values():
        category = node["category"]
        if category == FreeboxHomeCategory.PIR:
            home_sensors.append(FreeboxPirSensor(hass, router, node))
        elif category == FreeboxHomeCategory.DWS:
            home_sensors.append(FreeboxDwsSensor(hass, router, node))

        home_sensors.extend(
            FreeboxCoverSensor(hass, router, node)
            for endpoint in node["show_endpoints"]
            if endpoint["name"] == "cover"
            and endpoint["ep_type"] == "signal"
            and endpoint.get("value") is not None
        )

    _LOGGER.debug(
        "Adding %d Freebox Home binary sensors for %s (%s)",
        len(home_sensors),
        router.name,
        router.mac,
    )

    # Add all entities
    all_entities = raid_sensors + home_sensors
    if all_entities:
        async_add_entities(all_entities, update_before_add=True)


class FreeboxHomeBinarySensor(FreeboxHomeEntity, BinarySensorEntity):
    """Base representation of a Freebox Home binary sensor."""

    _sensor_name = "trigger"

    def __init__(
        self,
        hass: HomeAssistant,
        router: FreeboxRouter,
        node: dict[str, Any],
        sub_node: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a Freebox Home binary sensor."""
        super().__init__(hass, router, node, sub_node)
        self._command_id = self.get_command_id(
            node["type"]["endpoints"], "signal", self._sensor_name
        )
        self._attr_is_on = self._edit_state(self.get_value("signal", self._sensor_name))

    async def async_update_signal(self) -> None:
        """Update the sensor state from Freebox Home endpoint."""
        try:
            value = await self.get_home_endpoint_value(self._command_id)
            self._attr_is_on = self._edit_state(value)
        except Exception as err:
            _LOGGER.error(
                "Failed to update %s sensor for %s (%s): %s",
                self._sensor_name,
                self._router.name,
                self._node_id,
                err,
            )
            self._attr_is_on = None
        await super().async_update_signal()

    def _edit_state(self, state: bool | None) -> bool | None:
        """Adjust the sensor state based on its type."""
        if state is None:
            return None
        return not state if self._sensor_name == "trigger" else state


class FreeboxPirSensor(FreeboxHomeBinarySensor):
    """Representation of a Freebox motion sensor (PIR)."""

    _attr_device_class = BinarySensorDeviceClass.MOTION


class FreeboxDwsSensor(FreeboxHomeBinarySensor):
    """Representation of a Freebox door/window sensor (DWS)."""

    _attr_device_class = BinarySensorDeviceClass.DOOR


class FreeboxCoverSensor(FreeboxHomeBinarySensor):
    """Representation of a Freebox cover sensor (safety cover state)."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _sensor_name = "cover"

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        """Initialize a cover sensor for a Freebox Home device."""
        cover_node = next(
            (
                ep
                for ep in node["type"]["endpoints"]
                if ep["name"] == self._sensor_name and ep["ep_type"] == "signal"
            ),
            None,
        )
        super().__init__(hass, router, node, cover_node)


class FreeboxRaidDegradedSensor(BinarySensorEntity):
    """Representation of a Freebox RAID degraded sensor."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        router: FreeboxRouter,
        raid: dict[str, Any],
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize a Freebox RAID degraded sensor."""
        self.entity_description = description
        self._router = router
        self._raid_id = raid["id"]
        self._attr_device_info = router.device_info
        self._attr_name = f"Freebox RAID {raid['id']} {description.name}"
        self._attr_unique_id = f"{router.mac}_{description.key}_{raid['id']}"

    @callback
    def async_update_state(self) -> None:
        """Update the RAID sensor state."""
        raid = self._router.raids.get(self._raid_id)
        if raid is None:
            _LOGGER.warning("RAID %s not found for %s", self._raid_id, self._router.name)
            self._attr_is_on = None
        else:
            self._attr_is_on = raid.get("degraded", False)

    @property
    def is_on(self) -> bool | None:
        """Return True if the RAID is degraded."""
        return self._attr_is_on

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
