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

# SECTION: Configuration des entités
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités de suivi des appareils pour l'intégration Freebox.

    Initialise la détection automatique des nouveaux appareils et les ajoute à Home Assistant.

    Args:
        hass: Instance de Home Assistant.
        entry: Entrée de configuration pour l'intégration Freebox.
        async_add_entities: Fonction pour ajouter des entités à Home Assistant.
    """
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    tracked: set[str] = set()

    @callback
    def update_router() -> None:
        """Met à jour les données du routeur et ajoute les nouveaux appareils détectés."""
        add_entities(router, async_add_entities, tracked)

    # Écoute les nouveaux appareils et déclenche la mise à jour
    entry.async_on_unload(
        async_dispatcher_connect(hass, router.signal_device_new, update_router)
    )
    update_router()

# SECTION: Fonction utilitaire pour ajouter des entités
@callback
def add_entities(
    router: FreeboxRouter, async_add_entities: AddEntitiesCallback, tracked: set[str]
) -> None:
    """Ajoute de nouvelles entités de suivi des appareils à partir des données du routeur.

    Args:
        router: Instance du routeur Freebox.
        async_add_entities: Fonction pour ajouter des entités.
        tracked: Ensemble des adresses MAC déjà suivies.
    """
    new_tracked = []

    for mac, device in router.devices.items():
        if mac in tracked:
            continue
        new_tracked.append(FreeboxDevice(router, device))
        tracked.add(mac)
        _LOGGER.debug(f"Appareil {device.get('primary_name', 'Inconnu')} ({mac}) ajouté pour le suivi")

    if new_tracked:
        async_add_entities(new_tracked, True)

# SECTION: Classe de l'entité de suivi des appareils
class FreeboxDevice(ScannerEntity):
    """Représentation d'un appareil Freebox dans Home Assistant.

    Suit la présence de l'appareil sur le réseau et fournit des attributs comme la dernière activité.
    """

    _attr_should_poll = False  # Pas de polling manuel ; mises à jour via signaux

    def __init__(self, router: FreeboxRouter, device: dict[str, Any]) -> None:
        """Initialise un appareil Freebox pour le suivi.

        Args:
            router: Routeur Freebox gérant cette entité.
            device: Données de l'appareil fournies par la Freebox.
        """
        self._router = router
        self._name = device["primary_name"].strip() or DEFAULT_DEVICE_NAME
        self._mac = device["l2ident"]["id"]
        self._manufacturer = device.get("vendor_name", "Inconnu")
        self._attr_icon = icon_for_freebox_device(device)
        self._active = False
        self._attr_extra_state_attributes: dict[str, Any] = {}
        _LOGGER.debug(f"Appareil {self._name} ({self._mac}) initialisé pour le suivi")

    @callback
    def async_update_state(self) -> None:
        """Met à jour l'état de l'appareil à partir des données du routeur.

        Récupère les informations mises à jour et ajuste les attributs en conséquence.
        """
        device = self._router.devices.get(self._mac)
        if not device:
            _LOGGER.warning(f"Appareil {self._mac} non trouvé dans les données du routeur")
            self._active = False
            self._attr_extra_state_attributes = {}
            return

        self._active = device.get("active", False)

        if device.get("attrs") is None:
            # Appareil standard
            last_reachable = device.get("last_time_reachable")
            last_activity = device.get("last_activity")
            self._attr_extra_state_attributes = {
                "last_time_reachable": (
                    datetime.fromtimestamp(last_reachable).isoformat() if last_reachable else None
                ),
                "last_time_activity": (
                    datetime.fromtimestamp(last_activity).isoformat() if last_activity else None
                ),
            }
        else:
            # Routeur lui-même
            self._attr_extra_state_attributes = device.get("attrs", {})
        _LOGGER.debug(f"Mise à jour de l'appareil {self._name}: actif={self._active}")

    @property
    def mac_address(self) -> str:
        """Retourne l'adresse MAC de l'appareil."""
        return self._mac

    @property
    def name(self) -> str:
        """Retourne le nom de l'appareil."""
        return self._name

    @property
    def is_connected(self) -> bool:
        """Retourne si l'appareil est connecté au réseau."""
        return self._active

    @callback
    def async_on_demand_update(self) -> None:
        """Met à jour l'état de l'appareil à la demande et écrit dans Home Assistant."""
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Enregistre les callbacks lorsque l'entité est ajoutée à Home Assistant."""
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_device_update,
                self.async_on_demand_update,
            )
        )
        _LOGGER.debug(f"Appareil {self._name} ajouté à Home Assistant")

# SECTION: Fonction utilitaire pour les icônes
def icon_for_freebox_device(device: dict[str, Any]) -> str:
    """Retourne une icône basée sur le type de l'appareil."""
    return DEVICE_ICONS.get(device.get("host_type", ""), "mdi:help-network")
