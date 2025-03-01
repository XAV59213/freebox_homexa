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
        _LOGGER.debug(f"Volet basique {self._attr_name} initialisé")

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
        _LOGGER.info(f"Volet {self._attr_name} ouvert")

    async def async_close_cover(self, **kwargs) -> None:
        """Ferme le volet."""
        if self._command_down is None:
            _LOGGER.error(f"Commande de fermeture non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_down, {"value": None})
        self._state = CoverState.CLOSED
        _LOGGER.info(f"Volet {self._attr_name} fermé")

    async def async_stop_cover(self, **kwargs) -> None:
        """Arrête le volet."""
        if self._command_stop is None:
            _LOGGER.error(f"Commande d'arrêt non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        self._state = None
        _LOGGER.info(f"Volet {self._attr_name} arrêté")

    async def async_update(self) -> None:
        """Met à jour l'état du volet."""
        if self._command_state is None:
            _LOGGER.error(f"Commande d'état non disponible pour {self._attr_unique_id}")
            self._state = None
            return
        try:
            self._state = await self.get_home_endpoint_value(self._command_state)
            _LOGGER.debug(f"État du volet {self._attr_name} mis à jour: {self._state}")
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour de l'état pour {self._attr_unique_id}: {err}")
            self._state = None

    def convert_state(self, state: Any) -> str | None:
        """Convertit l'état brut en état Home Assistant."""
        if state:
            return CoverState.CLOSED
        elif state is not None:
            return CoverState.OPEN
        return None

class FreeboxShutter(FreeboxHomeEntity, CoverEntity):
    """Représentation d'un volet Freebox avec position."""
    _attr_should_poll = True
    _attr_scan_interval = SCAN_INTERVAL

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        """Initialise un volet Freebox avec position."""
        super().__init__(hass, router, node)
        self._command_position = self.get_command_id(node['show_endpoints'], "slot", "position_set")
        self._command_stop = self.get_command_id(node['show_endpoints'], "slot", "stop")
        self._current_cover_position = self.get_value("signal", "position_set")
        self._state = None
        self._invert_entity_id = None

        entity_registry = async_get(hass)
        unique_id_invert = f"{router.mac}_home_{self._node_id}_invert_switch"
        for entity in entity_registry.entities.values():
            if entity.unique_id == unique_id_invert:
                self._invert_entity_id = entity.entity_id
                _LOGGER.debug(f"Entité invert_switch trouvée pour {self._attr_name}: {self._invert_entity_id}")
                break
        else:
            _LOGGER.warning(f"Entité invert_switch non trouvée pour {self._attr_name} avec ID {unique_id_invert}")

    def _get_corrected_position(self, position: int) -> int:
        """Retourne la position corrigée si l'inversion est activée."""
        if self._invert_entity_id:
            invert_state = self.hass.states.get(self._invert_entity_id)
            if invert_state and invert_state.state == "on":
                corrected = 100 - position
                _LOGGER.debug(f"Inversion activée pour {self._attr_name}, position {position} corrigée à {corrected}")
                return corrected
        return position

    @property
    def device_class(self) -> str:
        """Retourne la classe de l'appareil (volet ou garage)."""
        if "garage" in self._attr_name.lower():
            return CoverDeviceClass.GARAGE
        return CoverDeviceClass.SHUTTER

    @property
    def current_cover_position(self) -> int | None:
        """Retourne la position actuelle du volet (0-100)."""
        return self._current_cover_position

    @property
    def current_cover_tilt_position(self) -> None:
        """Inclinaison non supportée."""
        return None

    @property
    def is_closed(self) -> bool:
        """Retourne si le volet est fermé."""
        if self._current_cover_position is None:
            return False
        corrected_position = self._get_corrected_position(self._current_cover_position)
        return corrected_position == 100

    async def async_set_cover_position(self, position: int, **kwargs) -> None:
        """Définit la position du volet."""
        corrected_position = self._get_corrected_position(position)
        if self._command_position is None:
            _LOGGER.error(f"Commande de position non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_position, {"value": corrected_position})
        self._current_cover_position = position
        _LOGGER.info(f"Position du volet {self._attr_name} définie à {position} (corrigée à {corrected_position})")

    async def async_open_cover(self, **kwargs) -> None:
        """Ouvre complètement le volet (position 0)."""
        await self.async_set_cover_position(0)

    async def async_close_cover(self, **kwargs) -> None:
        """Ferme complètement le volet (position 100)."""
        await self.async_set_cover_position(100)

    async def async_stop_cover(self, **kwargs) -> None:
        """Arrête le volet."""
        if self._command_stop is None:
            _LOGGER.error(f"Commande d'arrêt non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        await self.async_update()
        _LOGGER.info(f"Volet {self._attr_name} arrêté")

    async def async_update(self) -> None:
        """Met à jour la position actuelle du volet."""
        try:
            position = self.get_value("signal", "position_set")
            self._current_cover_position = position
            _LOGGER.debug(f"Position du volet {self._attr_name} mise à jour: {self._current_cover_position}")
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour de la position pour {self._attr_unique_id}: {err}")
            self._current_cover_position = None
