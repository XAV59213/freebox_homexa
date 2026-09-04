"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K) dans Home Assistant."""
# DESCRIPTION: Gestion du suivi des appareils connectés au réseau Freebox
# OBJECTIF: Surveiller la présence des appareils sur le réseau Freebox et fournir leur état dans Home Assistant

from __future__ import annotations
from datetime import datetime
from typing import Any
import logging

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_DEVICE_NAME, DEVICE_ICONS, DOMAIN
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités de suivi des appareils pour l'intégration Freebox."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    tracked: set[str] = set()

    @callback
    def update_router() -> None:
        """Met à jour les données du routeur et ajoute les nouveaux appareils détectés."""
        add_entities(router, async_add_entities, tracked)

    entry.async_on_unload(
        async_dispatcher_connect(hass, router.signal_device_new, update_router)
    )
    update_router()


@callback
def add_entities(
    router: FreeboxRouter, async_add_entities: AddEntitiesCallback, tracked: set[str]
) -> None:
    """Ajoute de nouvelles entités de suivi des appareils à partir des données du routeur."""
    new_tracked = []

    for mac, device in router.devices.items():
        if mac in tracked:
            continue
        new_tracked.append(FreeboxDevice(router, device))
        tracked.add(mac)
        _LOGGER.debug(
            "Appareil %s (%s) ajouté pour le suivi",
            device.get("primary_name", "Inconnu"),
            mac,
        )

    if new_tracked:
        async_add_entities(new_tracked, True)


class FreeboxDevice(ScannerEntity):
    """Représentation d'un appareil Freebox dans Home Assistant."""

    _attr_should_poll = False

    def __init__(self, router: FreeboxRouter, device: dict[str, Any]) -> None:
        self._router = router
        self._name = device["primary_name"].strip() or DEFAULT_DEVICE_NAME
        self._mac = device["l2ident"]["id"]
        self._manufacturer = device.get("vendor_name", "Inconnu")
        self._attr_icon = icon_for_freebox_device(device)
        self._active = False
        self._attr_extra_state_attributes: dict[str, Any] = {}
        _LOGGER.debug("Appareil %s (%s) initialisé pour le suivi", self._name, self._mac)

    @callback
    def async_update_state(self) -> None:
        device = self._router.devices.get(self._mac)
        if not device:
            _LOGGER.warning("Appareil %s non trouvé dans les données du routeur", self._mac)
            self._active = False
            self._attr_extra_state_attributes = {}
            return

        self._active = device.get("active", False)

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
            self._attr_extra_state_attributes = attributes
        else:
            self._attr_extra_state_attributes = device.get("attrs", {})
        _LOGGER.debug("Mise à jour de l'appareil %s: actif=%s", self._name, self._active)

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
        _LOGGER.debug("Appareil %s ajouté à Home Assistant", self._name)


def icon_for_freebox_device(device: dict[str, Any]) -> str:
    """Retourne une icône basée sur le type de l'appareil."""
    return DEVICE_ICONS.get(device.get("host_type", ""), "mdi:help-network")
