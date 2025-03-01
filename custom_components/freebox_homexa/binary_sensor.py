"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K)."""
# DESCRIPTION: Gestion des capteurs binaires pour les appareils Freebox dans Home Assistant
# OBJECTIF: Détecter des états tels que mouvement, ouverture de porte, état RAID dégradé, etc.

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

    _LOGGER.debug(f"{router.name} - {router.mac} - {len(router.raids)} raid(s)")

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
        """Initialise un capteur binaire Freebox."""
        super().__init__(hass, router, node, sub_node)
        self._node_id = node.get("id")
        if self._node_id is None:
            _LOGGER.error("L'appareil Freebox n'a pas d'ID valide")
            raise ValueError("L'appareil Freebox n'a pas d'ID valide")
        self._command_id = self.get_command_id(
            node["type"]["endpoints"], "signal", self._sensor_name
        )
        self._attr_is_on = self._edit_state(self.get_value("signal", self._sensor_name))
        _LOGGER.debug(f"Capteur binaire initialisé pour {self._node_id}: état={self._attr_is_on}")

    async def async_update_signal(self) -> None:
        """Met à jour l'état du capteur."""
        try:
            value = await self.get_home_endpoint_value(self._command_id)
            self._attr_is_on = self._edit_state(value)
            _LOGGER.debug(f"Mise à jour du capteur {self._node_id}: état={self._attr_is_on}")
            await super().async_update_signal()
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour du capteur {self._node_id}: {err}")
            self._attr_is_on = None

    def _edit_state(self, state: bool | None) -> bool | None:
        """Ajuste l'état en fonction du type de capteur."""
        if state is None:
            return None
        if self._sensor_name == "trigger":
            return not state
        return state

class FreeboxPirSensor(FreeboxHomeBinarySensor):
    """Représentation d'un capteur de mouvement Freebox (PIR)."""
    _attr_device_class = BinarySensorDeviceClass.MOTION

class FreeboxDwsSensor(FreeboxHomeBinarySensor):
    """Représentation d'un capteur d'ouverture de porte Freebox (DWS)."""
    _attr_device_class = BinarySensorDeviceClass.DOOR

class FreeboxCoverSensor(FreeboxHomeBinarySensor):
    """Représentation d'un capteur de couverture pour certains appareils Freebox."""
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _sensor_name = "cover"

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        """Initialise un capteur de couverture pour un appareil Freebox."""
        self._node_id = node.get("id")
        if self._node_id is None:
            _LOGGER.error("L'appareil Freebox n'a pas d'ID valide pour le capteur de couverture")
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
        _LOGGER.debug(f"Capteur de couverture initialisé pour {self._node_id}")

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
        """Initialise un capteur RAID dégradé."""
        self.entity_description = description
        self._router = router
        self._attr_device_info = router.device_info
        self._raid = raid
        self._attr_name = f"Array RAID {raid['id']} {description.name}"
        self._attr_unique_id = f"{router.mac}_{description.key}_{raid['name']}_{raid['id']}"
        _LOGGER.debug(f"Capteur RAID initialisé pour {self._attr_name}")

    @callback
    def async_update_state(self) -> None:
        """Met à jour l'état du capteur RAID à partir des données du routeur."""
        self._raid = self._router.raids.get(self._raid["id"])
        if self._raid is None:
            _LOGGER.warning(f"RAID {self._raid['id']} non trouvé dans les données du routeur")
            self._attr_is_on = None
        else:
            self._attr_is_on = self._raid.get("degraded", False)
            _LOGGER.debug(f"Mise à jour du capteur RAID {self._raid['id']}: état={self._attr_is_on}")

    @property
    def is_on(self) -> bool | None:
        """Retourne True si le RAID est dégradé."""
        return self._attr_is_on

    @callback
    def async_on_demand_update(self) -> None:
        """Met à jour l'état à la demande et écrit l'état dans Home Assistant."""
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Enregistre les callbacks lors de l'ajout de l'entité à Home Assistant."""
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_sensor_update,
                self.async_on_demand_update,
            )
        )
        _LOGGER.debug(f"Capteur RAID {self._raid['id']} ajouté à Home Assistant")
