"""Support pour les volets Freebox dans Home Assistant."""
# DESCRIPTION: Gestion des volets (covers) Freebox, incluant les volets basiques et les volets avec position.
# OBJECTIF: Permettre le contrôle des volets (ouverture, fermeture, arrêt) et la gestion de leur position.

import logging
from typing import Any
from datetime import timedelta
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.cover import CoverEntity, CoverDeviceClass, CoverState
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get
from .const import DOMAIN, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités de volets Freebox."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    entities = []

    for nodeid, node in router.home_devices.items():
        if node["category"] == FreeboxHomeCategory.BASIC_SHUTTER:
            entities.append(FreeboxBasicShutter(hass, router, node))
        elif node["category"] in {FreeboxHomeCategory.SHUTTER, FreeboxHomeCategory.OPENER}:
            entities.append(FreeboxShutter(hass, router, node))

    if entities:
        async_add_entities(entities, update_before_add=True)
        _LOGGER.debug(f"{len(entities)} entités de volets ajoutées pour {router.name}")

class FreeboxBasicShutter(FreeboxHomeEntity, CoverEntity):
    """Représentation d'un volet basique Freebox (sans position)."""
    _attr_should_poll = True
    _attr_scan_interval = SCAN_INTERVAL

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        """Initialise un volet basique Freebox."""
        super().__init__(hass, router, node)
        self._command_up = self.get_command_id(node['show_endpoints'], "slot", "up")
        self._command_stop = self.get_command_id(node['show_endpoints'], "slot", "stop")
        self._command_down = self.get_command_id(node['show_endpoints'], "slot", "down")
        self._command_state = self.get_command_id(node['show_endpoints'], "signal", "state")
        self._state = self.get_node_value(node['show_endpoints'], "signal", "state")
        self._color = self._determine_color()
        self._icon = self._determine_icon()
        _LOGGER.debug(f"Volet basique {self._attr_name} initialisé")

    def _determine_color(self):
        """Détermine la couleur en fonction de l'état du volet."""
        if self.is_closed:
            return "red"  # Rouge pour volet fermé
        elif self.current_cover_position == 100:
            return "green"  # Vert pour volet complètement ouvert
        else:
            return "orange"  # Orange pour état intermédiaire

    def _determine_icon(self):
        """Détermine l'icône en fonction de l'état du volet."""
        if self.is_closed:
            return "mdi:window-shutter"  # Icône volet fermé
        elif self.current_cover_position == 100:
            return "mdi:window-shutter-open"  # Icône volet ouvert
        else:
            return "mdi:window-shutter-alert"  # Icône pour position intermédiaire

    @property
    def device_class(self) -> str:
        """Retourne la classe de l'appareil (volet)."""
        return CoverDeviceClass.SHUTTER

    @property
    def current_cover_position(self) -> None:
        """Position non supportée pour les volets basiques."""
        return None

    @property
    def current_cover_tilt_position(self) -> None:
        """Inclinaison non supportée."""
        return None

    @property
    def is_closed(self) -> bool | None:
        """Retourne si le volet est fermé."""
        if self._state == CoverState.OPEN:
            return False
        if self._state == CoverState.CLOSED:
            return True
        return None

    async def async_open_cover(self, **kwargs) -> None:
        """Ouvre le volet."""
        if self._command_up is None:
            _LOGGER.error(f"Commande d'ouverture non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_up, {"value": None})
        self._state = CoverState.OPEN
        self._color = self._determine_color()
        self._icon = self._determine_icon()
        _LOGGER.info(f"Volet {self._attr_name} ouvert")

    async def async_close_cover(self, **kwargs) -> None:
        """Ferme le volet."""
        if self._command_down is None:
            _LOGGER.error(f"Commande de fermeture non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_down, {"value": None})
        self._state = CoverState.CLOSED
        self._color = self._determine_color()
        self._icon = self._determine_icon()
        _LOGGER.info(f"Volet {self._attr_name} fermé")

    @property
    def color(self):
        """Retourne la couleur actuelle du volet."""
        return self._color

    @property
    def icon(self):
        """Retourne l'icône actuelle du volet."""
        return self._icon
