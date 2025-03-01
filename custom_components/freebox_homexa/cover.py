"""Support pour les volets Freebox dans Home Assistant."""
# DESCRIPTION: Gestion des volets (covers) Freebox, incluant les volets basiques et les volets avec position.
# OBJECTIF: Permettre le contrôle des volets (ouverture, fermeture, arrêt) et la gestion de leur position.

import logging
import json
from homeassistant.util import slugify
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.cover import CoverEntity, CoverDeviceClass
from homeassistant.helpers.entity_registry import async_get
from .const import DOMAIN, DUMMY, VALUE_NOT_SET
from .base_class import FreeboxBaseClass

from homeassistant.const import (
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPEN,
    STATE_OPENING,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Configure les entités de volets Freebox."""
    router = hass.data[DOMAIN][entry.unique_id]
    entities = []

    for nodeId, node in router.nodes.items():
        if node["category"] == "basic_shutter":
            entities.append(FreeboxBasicShutter(hass, router, node))
        elif node["category"] == "shutter":
            entities.append(FreeboxShutter(hass, router, node))
        elif node["category"] == "opener":
            entities.append(FreeboxShutter(hass, router, node))

    async_add_entities(entities, True)

class FreeboxBasicShutter(FreeboxBaseClass, CoverEntity):
    """Représentation d'un volet basique Freebox (sans position)."""

    def __init__(self, hass, router, node) -> None:
        """Initialise un volet basique Freebox."""
        super().__init__(hass, router, node)
        self._command_up = self.get_command_id(node['show_endpoints'], "slot", "up")
        self._command_stop = self.get_command_id(node['show_endpoints'], "slot", "stop")
        self._command_down = self.get_command_id(node['show_endpoints'], "slot", "down")
        self._command_state = self.get_command_id(node['show_endpoints'], "signal", "state")
        self._state = self.get_node_value(node['show_endpoints'], "signal", "state")

    @property
    def device_class(self) -> str:
        """Retourne la classe de l'appareil (volet)."""
        return CoverDeviceClass.SHUTTER

    @property
    def current_cover_position(self):
        """Position non supportée pour les volets basiques."""
        return None

    @property
    def current_cover_tilt_position(self):
        """Inclinaison non supportée."""
        return None

    @property
    def is_closed(self):
        """Retourne si le volet est fermé."""
        if self._state == STATE_OPEN:
            return False
        if self._state == STATE_CLOSED:
            return True
        return None

    async def async_open_cover(self, **kwargs):
        """Ouvre le volet."""
        if self._command_up is None:
            _LOGGER.error(f"Commande d'ouverture non disponible pour {self.unique_id}")
            return
        await self.set_home_endpoint_value(self._command_up, {"value": None})
        self._state = STATE_OPEN
        _LOGGER.info(f"Volet {self._name} ouvert")

    async def async_close_cover(self, **kwargs):
        """Ferme le volet."""
        if self._command_down is None:
            _LOGGER.error(f"Commande de fermeture non disponible pour {self.unique_id}")
            return
        await self.set_home_endpoint_value(self._command_down, {"value": None})
        self._state = STATE_CLOSED
        _LOGGER.info(f"Volet {self._name} fermé")

    async def async_stop_cover(self, **kwargs):
        """Arrête le volet."""
        if self._command_stop is None:
            _LOGGER.error(f"Commande d'arrêt non disponible pour {self.unique_id}")
            return
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        self._state = None
        _LOGGER.info(f"Volet {self._name} arrêté")

    async def async_update(self):
        """Met à jour l'état du volet."""
        node = self._router.nodes[self._id]
        self._name = node["label"].strip()
        if self._command_state is None:
            _LOGGER.error(f"Commande d'état non disponible pour {self.unique_id}")
            self._state = None
            return
        try:
            state_value = await self.get_home_endpoint_value(self._command_state)
            self._state = self.convert_state(state_value)
            _LOGGER.debug(f"État du volet {self._name} mis à jour: {self._state}")
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour de l'état pour {self.unique_id}: {err}")
            self._state = None

    def convert_state(self, state):
        """Convertit l'état brut en état Home Assistant."""
        if state:
            return STATE_CLOSED
        elif state is not None:
            return STATE_OPEN
        return None

class FreeboxShutter(FreeboxBaseClass, CoverEntity):
    """Représentation d'un volet Freebox avec position."""

    def __init__(self, hass, router, node) -> None:
        """Initialise un volet Freebox avec position."""
        super().__init__(hass, router, node)
        self._command_position = self.get_command_id(node['type']['endpoints'], "slot", "position_set")
        self._command_up = self.get_command_id(node['type']['endpoints'], "slot", "position_set")
        self._command_down = self.get_command_id(node['type']['endpoints'], "slot", "position_set")
        self._command_stop = self.get_command_id(node['show_endpoints'], "slot", "stop")
        self._command_toggle = self.get_command_id(node['show_endpoints'], "slot", "toggle")
        self._command_state = self.get_command_id(node['type']['endpoints'], "signal", "position_set")
        self._current_state = self.get_node_value(node['show_endpoints'], "signal", "state")

        # Recherche de l'entité "invert switch"
        self._invert_entity_id = None
        entity_registry = async_get(hass)
        unique_id_invert = f"{self.unique_id}_InvertSwitch"
        for entity in entity_registry.entities.values():
            if entity.unique_id == unique_id_invert:
                self._invert_entity_id = entity.entity_id
                _LOGGER.debug(f"Entité invert_switch trouvée pour {self._name}: {self._invert_entity_id}")
                break
        else:
            _LOGGER.warning(f"Entité invert_switch non trouvée pour {self._name} avec ID {unique_id_invert}")

    def get_invert_status(self):
        """Vérifie si l'inversion est activée via l'entité switch associée."""
        if self._invert_entity_id is None:
            return False
        state = self.hass.states.get(self._invert_entity_id)
        if state is None:
            return False
        return state.state == "on"

    def get_corrected_state(self, value):
        """Corrige la position en fonction de l'état d'inversion."""
        if value is None:
            return None
        if self.get_invert_status():
            corrected = 100 - value
            if DUMMY:
                _LOGGER.error(f"Value converted from {value} to {corrected}")
            _LOGGER.debug(f"Inversion activée: position {value} corrigée à {corrected}")
            return corrected
        if DUMMY:
            _LOGGER.error(f"Value {value}")
        return value

    @property
    def device_class(self) -> str:
        """Retourne la classe de l'appareil (volet ou garage)."""
        if "garage" in self._name.lower():
            return CoverDeviceClass.GARAGE
        return CoverDeviceClass.SHUTTER

    @property
    def current_cover_position(self):
        """Retourne la position actuelle du volet (0-100)."""
        return self._current_state

    @property
    def current_cover_tilt_position(self):
        """Inclinaison non supportée."""
        return None

    @property
    def is_closed(self):
        """Retourne si le volet est fermé."""
        return self._current_state == 0

    async def async_set_cover_position(self, position, **kwargs):
        """Définit la position du volet."""
        if self._command_position is None:
            _LOGGER.error(f"Commande de position non disponible pour {self.unique_id}")
            return
        corrected_position = self.get_corrected_state(position)
        await self.set_home_endpoint_value(self._command_position, {"value": corrected_position})
        self._current_state = position
        _LOGGER.info(f"Position du volet {self._name} définie à {position} (corrigée à {corrected_position})")

    async def async_open_cover(self, **kwargs):
        """Ouvre complètement le volet (position 100 ou 0 selon inversion)."""
        if self._command_up is None:
            _LOGGER.error(f"Commande d'ouverture non disponible pour {self.unique_id}")
            return
        if self.get_invert_status():
            await self.set_home_endpoint_value(self._command_up, {"value": 0})
            self._current_state = 0
        else:
            await self.set_home_endpoint_value(self._command_up, {"value": 100})
            self._current_state = 100
        _LOGGER.info(f"Volet {self._name} ouvert")

    async def async_close_cover(self, **kwargs):
        """Ferme complètement le volet (position 0 ou 100 selon inversion)."""
        if self._command_down is None:
            _LOGGER.error(f"Commande de fermeture non disponible pour {self.unique_id}")
            return
        if self.get_invert_status():
            await self.set_home_endpoint_value(self._command_down, {"value": 100})
            self._current_state = 100
        else:
            await self.set_home_endpoint_value(self._command_down, {"value": 0})
            self._current_state = 0
        _LOGGER.info(f"Volet {self._name} fermé")

    async def async_stop_cover(self, **kwargs):
        """Arrête le volet."""
        if self._command_stop is None:
            _LOGGER.error(f"Commande d'arrêt non disponible pour {self.unique_id}")
            return
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        self._current_state = 50  # Position intermédiaire par défaut
        _LOGGER.info(f"Volet {self._name} arrêté")

    async def async_update(self):
        """Met à jour la position actuelle du volet."""
        node = self._router.nodes[self._id]
        self._name = node["label"].strip()
        if self._command_state is None:
            _LOGGER.error(f"Commande d'état non disponible pour {self.unique_id}")
            self._current_state = None
            return
        try:
            state_value = await self.get_home_endpoint_value(self._command_state)
            self._current_state = self.get_corrected_state(state_value)
            if self._id >= 1000 and DUMMY:
                _LOGGER.error(f"Current state: {self._current_state} Freebox: {state_value}")
            _LOGGER.debug(f"Position du volet {self._name} mise à jour: {self._current_state}")
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour de la position pour {self.unique_id}: {err}")
            self._current_state = None
