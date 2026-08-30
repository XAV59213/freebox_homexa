# custom_components/freebox_homexa/sensor.py
"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K) dans Home Assistant."""
# DESCRIPTION: Ce fichier définit des capteurs pour surveiller différents aspects de la Freebox, tels que la vitesse de connexion,
#              les appels manqués, l'espace disque disponible et le niveau de batterie des appareils domestiques.
# OBJECTIF: Intégrer des capteurs dans Home Assistant pour fournir des informations en temps réel sur la Freebox.

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

# SECTION: Définitions des capteurs
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
    SensorEntityDescription(
        key="missed",
        name="Appels manqués Freebox",
        icon="mdi:phone-missed",
    ),
)

DISK_PARTITION_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="partition_free_space",
        name="espace libre",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:harddisk",
    ),
)

# SECTION: Configuration des entités
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités de capteurs pour la Freebox."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    entities: list[SensorEntity] = []

    # Capteurs de température
    _LOGGER.debug(
        f"{router.name} - {router.mac} - {len(router.sensors_temperature)} capteur(s) de température"
    )
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

    # Capteurs de connexion
    entities.extend(FreeboxSensor(router, description) for description in CONNECTION_SENSORS)

    # Capteurs d'appels
    entities.extend(FreeboxCallSensor(router, description) for description in CALL_SENSORS)

    # Capteurs de disques
    _LOGGER.debug(f"{router.name} - {router.mac} - {len(router.disks)} disque(s)")
    entities.extend(
        FreeboxDiskSensor(router, disk, partition, description)
        for disk in router.disks.values()
        for partition in disk["partitions"].values()
        for description in DISK_PARTITION_SENSORS
    )

    # Capteurs de batterie
    for node in router.home_devices.values():
        for endpoint in node["show_endpoints"]:
            if (
                endpoint["name"] == "battery"
                and endpoint["ep_type"] == "signal"
                and endpoint.get("value") is not None
            ):
                entities.append(FreeboxBatterySensor(hass, router, node, endpoint))

    if entities:
        async_add_entities(entities, True)
        _LOGGER.debug(f"{len(entities)} entités ajoutées pour {router.name}")

# SECTION: Classe de capteur générique
class FreeboxSensor(SensorEntity):
    """Représentation de base d'un capteur Freebox."""
    _attr_should_poll = False

    def __init__(
        self, router: FreeboxRouter, description: SensorEntityDescription
    ) -> None:
        self.entity_description = description
        self._router = router
        self._attr_unique_id = f"{router.mac} {description.name}"
        self._attr_device_info = router.device_info
        _LOGGER.debug(f"Capteur {description.name} initialisé")

    @callback
    def async_update_state(self) -> None:
        if self.entity_description.key in ["ipv4"]:
            state = self._router._attrs.get("IPv4")
        elif self.entity_description.key == "uptime":
            state = self._router.sensors_connection.get("uptime")
        else:
            state = self._router.sensors.get(self.entity_description.key)
        if state is None:
            _LOGGER.warning(f"Donnée manquante pour {self.entity_description.name}")
            self._attr_native_value = None
        elif self.native_unit_of_measurement == UnitOfDataRate.KILOBYTES_PER_SECOND:
            self._attr_native_value = round(state / 8000, 2)
        else:
            self._attr_native_value = state
        _LOGGER.debug(f"Capteur {self.entity_description.name} mis à jour: {self._attr_native_value}")

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
        _LOGGER.debug(f"Capteur {self.entity_description.name} ajouté à Home Assistant")

# SECTION: Classe pour les capteurs d'appels
class FreeboxCallSensor(FreeboxSensor):
    """Représentation d'un capteur d'appels Freebox (ex. appels manqués)."""

    def __init__(
        self, router: FreeboxRouter, description: SensorEntityDescription
    ) -> None:
        super().__init__(router, description)
        self._call_list_for_type: list[dict[str, Any]] = []

    @callback
    def async_update_state(self) -> None:
        self._call_list_for_type = [
            call for call in self._router.call_list or []
            if call.get("new", False) and self.entity_description.key == call.get("type")
        ]
        self._attr_native_value = len(self._call_list_for_type)
        _LOGGER.debug(f"{self.entity_description.name}: {self._attr_native_value} appel(s)")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            dt_util.utc_from_timestamp(call["datetime"]).isoformat(): call["name"]
            for call in self._call_list_for_type
        }

# SECTION: Classe pour les capteurs de disques
class FreeboxDiskSensor(FreeboxSensor):
    """Représentation d'un capteur de disque Freebox (ex. espace libre)."""

    def __init__(
        self,
        router: FreeboxRouter,
        disk: dict[str, Any],
        partition: dict[str, Any],
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(router, description)
        self._disk_id = disk["id"]
        self._partition_id = partition["id"]
        self._attr_name = f"{partition['label']} {description.name}"
        self._attr_unique_id = f"{router.mac} {description.key} {disk['id']} {partition['id']}"
        device_info: dict[str, Any] = {
            "identifiers": {(DOMAIN, disk["id"])},
            "model": disk["model"],
            "name": f"Disque {disk['id']}",
            "sw_version": disk["firmware"],
        }
        if router.device_id:
            device_info["via_device_id"] = router.device_id
        self._attr_device_info = DeviceInfo(**device_info)
        _LOGGER.debug(f"Capteur de disque {self._attr_name} initialisé")

    @callback
    def async_update_state(self) -> None:
        disk = self._router.disks.get(self._disk_id)
        if disk is None:
            _LOGGER.warning(f"Disque {self._disk_id} non trouvé pour {self._attr_name}")
            self._attr_native_value = None
            return
        partition = disk["partitions"].get(self._partition_id)
        if partition is None:
            _LOGGER.warning(f"Partition {self._partition_id} non trouvée pour {self._attr_name}")
            self._attr_native_value = None
            return

        total_bytes = partition.get("total_bytes")
        free_bytes = partition.get("free_bytes")

        _LOGGER.debug(f"Total bytes pour {self._attr_name}: {total_bytes}")
        _LOGGER.debug(f"Free bytes pour {self._attr_name}: {free_bytes}")

        if total_bytes is None or total_bytes <= 0:
            self._attr_native_value = 0
        elif free_bytes is None:
            _LOGGER.warning(f"Espace libre indisponible pour {self._attr_name}")
            self._attr_native_value = None
        else:
            self._attr_native_value = round((free_bytes / total_bytes) * 100, 2)
            _LOGGER.debug(f"{self._attr_name}: {self._attr_native_value}% libre")

# SECTION: Classe pour les capteurs de batterie
class FreeboxBatterySensor(FreeboxHomeEntity, SensorEntity):
    """Représentation d'un capteur de batterie pour les appareils Freebox."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> int | None:
        value = self.get_value("signal", "battery")
        if value is not None:
            _LOGGER.debug(f"Batterie {self._attr_name}: {value}%")
        else:
            _LOGGER.warning(f"Valeur de batterie indisponible pour {self._attr_name}")
        return value
