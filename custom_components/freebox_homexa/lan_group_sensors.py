"""Capteur « Clients connectés » de chaque groupe de clients réseau.

Un capteur par appareil de regroupement : « Clients réseau filaires », « Clients Wi-Fi »
et chaque sous-groupe de type (« Serveurs (filaire) »…). Il est créé quand le groupe
existe et disparaît avec lui (le registre retire les entités d'un appareil supprimé).
Les répéteurs ont déjà leur capteur « Clients Wi-Fi » (wifi_ap_sensors) : pas de doublon.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .device_groups import (
    GROUP_NAMES,
    GROUP_SENSOR_UID_PART,
    LAN_GROUPS,
    LAN_TYPE_GROUPS,
    group_identifier,
    lan_client_name,
    lan_type_name,
)
from .router import FreeboxRouter
from .availability import FreeboxReachableMixin

# Noms listés dans l'attribut « appareils » (au-delà : « … +N »), pour rester loin de la
# limite de taille des attributs de Home Assistant.
MAX_LISTED = 50


def group_sensor_unique_id(router_mac: str, key: str) -> str:
    return f"{router_mac}{GROUP_SENSOR_UID_PART}{key}"


def _names(devices: list[dict[str, Any]]) -> list[str]:
    names = sorted({lan_client_name(d) for d in devices}, key=str.lower)
    if len(names) > MAX_LISTED:
        return [*names[:MAX_LISTED], f"… +{len(names) - MAX_LISTED}"]
    return names


class FreeboxLanGroupClientsSensor(FreeboxReachableMixin, SensorEntity):
    """Nombre de clients en ligne dans un groupe de clients réseau."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "lan_group_clients"
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Listes de noms : pas d'historique (base de données) pour ces attributs.
    _unrecorded_attributes = frozenset({"appareils", "hors_ligne"})

    def __init__(self, router: FreeboxRouter, key: str, tracked: set[str]) -> None:
        self._router = router
        self._key = key
        self._tracked = tracked
        self._attr_unique_id = group_sensor_unique_id(router.mac, key)
        if key in LAN_TYPE_GROUPS:
            group, lan_type = LAN_TYPE_GROUPS[key]
            name = lan_type_name(group, lan_type)
        else:
            name = GROUP_NAMES[key]
        # Même description que l'appareil de groupe créé par le routeur (déjà existant).
        self._attr_device_info = DeviceInfo(
            identifiers={group_identifier(router.mac, key)},
            manufacturer="Freebox SAS",
            name=name,
            entry_type=DeviceEntryType.SERVICE,
        )
        self._attr_native_value = 0
        self._attr_extra_state_attributes: dict[str, Any] = {}

    @callback
    def async_update_state(self) -> None:
        members = self._router.lan_group_members(self._key)
        online = [d for d in members if d.get("active")]
        offline = [d for d in members if not d.get("active")]
        self._attr_native_value = len(online)
        self._attr_extra_state_attributes = {
            "appareils": _names(online),
            "hors_ligne": _names(offline),
            "total": len(members),
        }

    @callback
    def async_on_demand_update(self) -> None:
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._router.signal_device_update, self.async_on_demand_update
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        # Groupe retiré : le capteur pourra être recréé si le groupe revient.
        self._tracked.discard(self._key)


def async_setup_lan_group_sensors(
    router: FreeboxRouter,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    tracked: set[str] = set()

    @callback
    def add_group_sensors() -> None:
        new_entities = []
        for key in list(router.group_device_ids):
            if key in tracked or (key not in LAN_GROUPS and key not in LAN_TYPE_GROUPS):
                continue
            tracked.add(key)
            new_entities.append(FreeboxLanGroupClientsSensor(router, key, tracked))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        async_dispatcher_connect(router.hass, router.signal_device_update, add_group_sensors)
    )
    add_group_sensors()
