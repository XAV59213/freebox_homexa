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
    """Configure les entités de capteurs pour la Freebox.

    Initialise les capteurs pour la température, la connexion, les appels, les disques et la batterie.

    Args:
        hass: Instance de Home Assistant.
        entry: Entrée de configuration pour l'intégration Freebox.
        async_add_entities: Fonction pour ajouter des entités à Home Assistant.
    """
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
    """Représentation de base d'un capteur Freebox.

    Gère les capteurs de données système et réseau.
    """
    _attr_should_poll = False  # Pas de polling manuel, mises à jour via signaux

    def __init__(
        self, router: FreeboxRouter, description: SensorEntityDescription
    ) -> None:
        """Initialise un capteur Freebox.

        Args:
            router: Routeur Freebox associé.
            description: Description du capteur.
        """
        self.entity_description = description
        self._router = router
        self._attr_unique_id = f"{router.mac} {description.name}"
        self._attr_device_info = router.device_info
        _LOGGER.debug(f"Capteur {description.name} initialisé")

    @callback
    def async_update_state(self) -> None:
        """Met à jour l'état du capteur.

        Ajuste la valeur selon l'unité (ex. conversion des débits en Ko/s).
        """
        state = self._router.sensors.get(self.entity_description.key)
        if state is None:
            _LOGGER.warning(f"Donnée manquante pour {self.entity_description.name}")
            self._attr_native_value = None
        elif self.native_unit_of_measurement == UnitOfDataRate.KILOBYTES_PER_SECOND:
            # Conversion de bits/s en Ko/s (1 Ko = 1000 octets, 1 octet = 8 bits)
            self._attr_native_value = round(state / 8000, 2)
        else:
            self._attr_native_value = state
        _LOGGER.debug(f"Capteur {self.entity_description.name} mis à jour: {self._attr_native_value}")

    @callback
    def async_on_demand_update(self) -> None:
        """Met à jour l'état à la demande et écrit dans Home Assistant."""
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Ajoute le capteur à Home Assistant et enregistre les mises à jour."""
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
        """Initialise un capteur d'appels.

        Args:
            router: Routeur Freebox.
            description: Description du capteur.
        """
        super().__init__(router, description)
        self._call_list_for_type: list[dict[str, Any]] = []

    @callback
    def async_update_state(self) -> None:
        """Met à jour le nombre d'appels pour le type spécifié."""
        self._call_list_for_type = [
            call for call in self._router.call_list or []
            if call.get("new", False) and self.entity_description.key == call.get("type")
        ]
        self._attr_native_value = len(self._call_list_for_type)
        _LOGGER.debug(f"{self.entity_description.name}: {self._attr_native_value} appel(s)")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Retourne les attributs supplémentaires des appels.

        Returns:
            dict: Liste des appels avec timestamp et nom.
        """
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
        """Initialise un capteur de disque.

        Args:
            router: Routeur Freebox.
            disk: Données du disque.
            partition: Données de la partition.
            description: Description du capteur.
        """
        super().__init__(router, description)
        self._disk_id = disk["id"]
        self._partition_id = partition["id"]
        self._attr_name = f"{partition['label']} {description.name}"
        self._attr_unique_id = f"{router.mac} {description.key} {disk['id']} {partition['id']}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, disk["id"])},
            model=disk["model"],
            name=f"Disque {disk['id']}",
            sw_version=disk["firmware"],
            via_device=(DOMAIN, router.mac),
        )
        _LOGGER.debug(f"Capteur de disque {self._attr_name} initialisé")

    @callback
    def async_update_state(self) -> None:
        """Met à jour l'espace libre sur la partition."""
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

        # Logs pour déboguer les valeurs
        _LOGGER.debug(f"Total bytes pour {self._attr_name}: {total_bytes}")
        _LOGGER.debug(f"Free bytes pour {self._attr_name}: {free_bytes}")

        if total_bytes is None or total_bytes <= 0:
            _LOGGER.warning(f"Taille totale indisponible ou invalide pour {self._attr_name}")
            self._attr_native_value = None
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
        """Retourne le niveau de batterie.

        Returns:
            int | None: Pourcentage de batterie ou None si indisponible.
        """
        value = self.get_value("signal", "battery")
        if value is not None:
            _LOGGER.debug(f"Batterie {self._attr_name}: {value}%")
        else:
            _LOGGER.warning(f"Valeur de batterie indisponible pour {self._attr_name}")
        return value
