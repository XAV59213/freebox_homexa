"""Capteurs de synthèse Wi-Fi : répéteurs, box et clients."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, REPEATER_MODEL
from .router import FreeboxRouter


def _ap_device_info(router: FreeboxRouter, access_point: dict[str, Any]) -> DeviceInfo:
    if access_point.get("kind") == "gateway":
        return router.device_info
    mac = access_point.get("mac") or access_point.get("id")
    device_info: dict[str, Any] = {
        "identifiers": {(DOMAIN, f"repeater_{mac}")},
        "connections": {(CONNECTION_NETWORK_MAC, mac)},
        "manufacturer": access_point.get("vendor_name") or "Freebox SAS",
        "model": access_point.get("model") or REPEATER_MODEL,
        "name": access_point.get("name") or f"Répéteur Wi-Fi {str(mac)[-5:]}",
        "via_device": (DOMAIN, router.mac),
    }
    return DeviceInfo(**device_info)


def _client_label(access_point: dict[str, Any]) -> str:
    names = [str(name) for name in (access_point.get("client_names") or []) if name]
    return ", ".join(names) if names else "Aucun"


class FreeboxRepeaterCountSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Répéteurs Wi-Fi"
    _attr_icon = "mdi:wifi-sync"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, router: FreeboxRouter) -> None:
        self._router = router
        self._attr_unique_id = f"{router.mac}_wifi_repeater_count"
        self._attr_device_info = router.device_info
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {}

    @callback
    def async_update_state(self) -> None:
        repeaters = list(self._router.repeaters.values())
        self._attr_native_value = len(repeaters)
        self._attr_extra_state_attributes = {
            "points_acces": len(self._router.wifi_aps),
            "repeteurs": [item.get("name") for item in repeaters],
            "etats": {item.get("name"): item.get("state") for item in repeaters},
            "clients_par_repeteur": {
                item.get("name"): item.get("client_names") or [] for item in repeaters
            },
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


class FreeboxWifiClientCountSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Clients Wi-Fi"
    _attr_icon = "mdi:account-multiple"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, router: FreeboxRouter, ap_id: str) -> None:
        self._router = router
        self._ap_id = ap_id
        access_point = router.wifi_aps.get(ap_id) or {}
        kind = access_point.get("kind")
        if ap_id == "gateway" or kind == "gateway":
            self._attr_name = "Clients Wi-Fi box"
            self._attr_unique_id = f"{router.mac}_wifi_clients_gateway"
        else:
            mac = access_point.get("mac") or ap_id
            self._attr_unique_id = f"{router.mac}_wifi_clients_{mac}"
        self._attr_device_info = _ap_device_info(router, access_point or {"kind": "gateway"})
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {}

    @callback
    def async_update_state(self) -> None:
        access_point = self._router.wifi_aps.get(self._ap_id) or {}
        self._attr_native_value = access_point.get("client_count", 0)
        self._attr_extra_state_attributes = {
            "etat": access_point.get("state"),
            "type": access_point.get("kind"),
            "appareils": access_point.get("client_names") or [],
            "detail_appareils": access_point.get("clients") or [],
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


class FreeboxWifiClientListSensor(SensorEntity):
    """Liste nominative des clients d'un AP, visible dans l'état du capteur."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Appareils connectés"
    _attr_icon = "mdi:devices"

    def __init__(self, router: FreeboxRouter, ap_id: str) -> None:
        self._router = router
        self._ap_id = ap_id
        access_point = router.wifi_aps.get(ap_id) or {}
        kind = access_point.get("kind")
        if ap_id == "gateway" or kind == "gateway":
            self._attr_name = "Appareils sur le Wi-Fi box"
            self._attr_unique_id = f"{router.mac}_wifi_client_list_gateway"
        else:
            mac = access_point.get("mac") or ap_id
            self._attr_unique_id = f"{router.mac}_wifi_client_list_{mac}"
        self._attr_device_info = _ap_device_info(router, access_point or {"kind": "gateway"})
        self._attr_native_value = "Aucun"
        self._attr_extra_state_attributes = {}

    @callback
    def async_update_state(self) -> None:
        access_point = self._router.wifi_aps.get(self._ap_id) or {}
        self._attr_native_value = _client_label(access_point)
        self._attr_extra_state_attributes = {
            "nombre": access_point.get("client_count", 0),
            "etat": access_point.get("state"),
            "detail_appareils": access_point.get("clients") or [],
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


class FreeboxWifiTotalClientSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Clients Wi-Fi total"
    _attr_icon = "mdi:wifi"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, router: FreeboxRouter) -> None:
        self._router = router
        self._attr_unique_id = f"{router.mac}_wifi_clients_total"
        self._attr_device_info = router.device_info
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {}

    @callback
    def async_update_state(self) -> None:
        per_ap = {
            item.get("name"): item.get("client_names") or []
            for item in self._router.wifi_aps.values()
        }
        self._attr_native_value = sum(len(names) for names in per_ap.values())
        self._attr_extra_state_attributes = {
            "par_point_acces": per_ap,
            "repeteurs": len(self._router.repeaters),
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


def async_setup_wifi_ap_sensors(
    router: FreeboxRouter,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [FreeboxRepeaterCountSensor(router), FreeboxWifiTotalClientSensor(router)],
        True,
    )
    tracked: set[str] = set()

    @callback
    def add_ap_client_sensors() -> None:
        new_entities: list[Entity] = []
        for ap_id in router.wifi_aps:
            if ap_id in tracked:
                continue
            new_entities.append(FreeboxWifiClientCountSensor(router, ap_id))
            new_entities.append(FreeboxWifiClientListSensor(router, ap_id))
            tracked.add(ap_id)
        if new_entities:
            async_add_entities(new_entities, True)

    entry.async_on_unload(
        async_dispatcher_connect(router.hass, router.signal_device_new, add_ap_client_sensors)
    )
    entry.async_on_unload(
        async_dispatcher_connect(router.hass, router.signal_device_update, add_ap_client_sensors)
    )
    add_ap_client_sensors()
