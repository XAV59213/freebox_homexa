"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K) dans Home Assistant."""

from __future__ import annotations
from datetime import datetime
from typing import Any
import logging

from homeassistant.components.device_tracker.entity import ScannerEntity
from .availability import FreeboxReachableMixin
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CREATE_LAN_DEVICES,
    CONF_TRACK_LAN_CLIENTS,
    DEFAULT_CREATE_LAN_DEVICES,
    DEFAULT_TRACK_LAN_CLIENTS,
    DEVICE_ICONS,
    option_enabled,
)
from .device_groups import client_device_is_protected, lan_client_name
from .registry_compat import (
    foreign_device_with_connection,
    get_device_by_connection,
    update_entity_device,
)
from .router import FreeboxConfigEntry, FreeboxRouter, is_freebox_repeater, normalize_mac

_LOGGER = logging.getLogger(__name__)


def _is_lan_client(device: dict[str, Any], router_mac: str) -> bool:
    """True pour un hôte LAN (pas le Server, pas un répéteur)."""
    if device.get("attrs") is not None:
        return False
    return not is_freebox_repeater(device, router_mac)


# Entités mises à jour par le relevé central du routeur (dispatcher) : pas de limite.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: FreeboxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxRouter = entry.runtime_data
    tracked: set[str] = set()
    track_lan = option_enabled(entry, CONF_TRACK_LAN_CLIENTS, DEFAULT_TRACK_LAN_CLIENTS)
    create_devices = option_enabled(
        entry, CONF_CREATE_LAN_DEVICES, DEFAULT_CREATE_LAN_DEVICES
    )
    router.create_lan_devices = create_devices

    @callback
    def update_router() -> None:
        add_entities(router, async_add_entities, tracked, track_lan, create_devices)

    entry.async_on_unload(
        async_dispatcher_connect(hass, router.signal_device_new, update_router)
    )
    update_router()


@callback
def add_entities(
    router: FreeboxRouter,
    async_add_entities: AddEntitiesCallback,
    tracked: set[str],
    track_lan: bool,
    create_devices: bool,
) -> None:
    if router.closing:
        return
    new_tracked = []

    for mac, device in router.devices.items():
        if mac in tracked:
            continue
        if not track_lan and _is_lan_client(device, router.mac):
            continue
        new_tracked.append(FreeboxDevice(router, device, create_devices))
        tracked.add(mac)

    if new_tracked:
        async_add_entities(new_tracked, True)


class FreeboxDevice(FreeboxReachableMixin, ScannerEntity):
    """Représentation d'un appareil Freebox dans Home Assistant."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self, router: FreeboxRouter, device: dict[str, Any], create_lan_devices: bool
    ) -> None:
        self._router = router
        self._create_lan_devices = create_lan_devices
        mac: object = device["l2ident"]["id"]
        if not isinstance(mac, str):
            raise ValueError("Invalid LAN MAC identifier")
        self._mac = mac
        self._name = lan_client_name(device)
        self._manufacturer = device.get("vendor_name", "Inconnu")
        kind = device.get("host_type", "")
        self._attr_translation_key = f"device_{kind if kind in DEVICE_ICONS else 'unknown'}"
        self._attr_unique_id = f"{router.mac}_{self._mac}"
        self._active = False
        self._attr_extra_state_attributes: dict[str, Any] = {}
        # HA nomme l'appareil du suivi avec ce libellé quand il en crée un (sinon la MAC).
        self._attr_hostname = self._name
        self._norm_mac = normalize_mac(self._mac)
        self._lan_client = router._is_lan_client(device)
        # Attribut, pas la propriété : sur HA 2026.10 device_info est final et vaut
        # None, donc rien ne change. Sur 2026.11, sans device_info, HA crée un
        # appareil par MAC et peut recharger l'entrée en boucle.
        self._assign_device_info(device)

    def _assign_device_info(self, device: dict[str, Any]) -> None:
        """Décrit l'appareil du suivi (Server, répéteur, client, ou aucun)."""
        if not self._lan_client:
            if self._router.is_repeater_host(device):
                model = device.get("model")
                manufacturer = device.get("vendor_name")
                self._attr_device_info = self._router.repeater_device_info(
                    self._mac,
                    self._name,
                    model if isinstance(model, str) else None,
                    manufacturer if isinstance(manufacturer, str) else None,
                )
                return
            self._attr_device_info = self._router.device_info
            return
        # Même connexion que ensure_lan_client_device : un seul appareil.
        connection = (CONNECTION_NETWORK_MAC, self._mac.lower())
        if self._create_lan_devices:
            self._attr_device_info = DeviceInfo(connections={connection})
            return
        registry = dr.async_get(self._router.hass)
        entry_id = self._router.entry_id
        # Option décochée : la MAC seulement si une autre intégration a déjà
        # l'appareil (comportement 2026.10), ou si l'appareil Homexa doit rester
        # (renommé, placé, désactivé, partagé). Sinon DeviceInfo vide : aucun
        # appareil créé.
        if foreign_device_with_connection(registry, connection, entry_id) is not None:
            self._attr_device_info = DeviceInfo(connections={connection})
            return
        existing = get_device_by_connection(registry, connection, entry_id)
        if existing is not None and client_device_is_protected(
            self._router.hass, existing, entry_id
        ):
            self._attr_device_info = DeviceInfo(connections={connection})
            return
        self._attr_device_info = DeviceInfo()

    @callback
    def _async_link_device(self) -> None:
        """Range le client si l'option est active, sans déplacer l'entité pour rien.

        Le device_info porte déjà la connexion MAC : Home Assistant rattache le
        suivi au même appareil. Le déplacement ne sert qu'à HA 2026.10, où
        device_info reste None. On ne retire pas une entité d'un appareil
        désactivé : disabled_by repasserait à vide et l'entrée se rechargerait.
        """
        if (
            not self._create_lan_devices
            or not self._lan_client
            or self.registry_entry is None
            or self.hass is None
        ):
            return
        device_id = self._router.lan_device_ids.get(self._norm_mac)
        if device_id is None:
            device_id = self._router.ensure_lan_client_device(self._mac)
        if not device_id:
            return
        if update_entity_device(self.hass, self.entity_id, device_id):
            self.registry_entry = er.async_get(self.hass).async_get(self.entity_id)

    @property
    def available(self) -> bool:
        return (super().available and
                (self._mac == self._router.mac or self._router.lan_available))

    @callback
    def async_update_state(self) -> None:
        device = self._router.devices.get(self._mac)
        if not device:
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
            parent = device.get("wifi_parent") or {}
            if parent.get("name"):
                attributes["connecte_sur"] = parent["name"]
                attributes["ap_kind"] = parent.get("kind")
            self._attr_extra_state_attributes = attributes
        else:
            self._attr_extra_state_attributes = device.get("attrs", {})

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def name(self) -> str | None:
        # ScannerEntity can be unattached, or linked to a device owned by another
        # integration. Use that device's name only when it is actually linked.
        if self.registry_entry is not None and self.registry_entry.device_id:
            return None
        return self._name

    @property
    def is_connected(self) -> bool:
        return self._active

    @callback
    def async_on_demand_update(self) -> None:
        self.async_update_state()
        self._async_link_device()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        if self._lan_client:
            # Entité active : son client reçoit un appareil (pas pour une entité désactivée).
            self._router.tracked_lan_macs.add(self._norm_mac)
            self._async_link_device()
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_device_update,
                self.async_on_demand_update,
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        self._router.tracked_lan_macs.discard(self._norm_mac)


def icon_for_freebox_device(device: dict[str, Any]) -> str:
    return DEVICE_ICONS.get(device.get("host_type", ""), "mdi:help-network")
