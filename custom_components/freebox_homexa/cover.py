"""Support pour les volets Freebox dans Home Assistant."""
# DESCRIPTION: Gestion des volets (covers) Freebox, incluant les volets basiques et les volets avec position.
# OBJECTIF: Permettre le contrôle des volets (ouverture, fermeture, arrêt) et la gestion de leur position.

import logging
import json
from typing import Any
from homeassistant.util import slugify
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

# SECTION: Configuration des entités
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités de volets Freebox.

    Crée et ajoute les entités pour les volets basiques et les volets avec position.

    Args:
        hass: Instance de Home Assistant.
        entry: Entrée de configuration pour l'intégration Freebox.
        async_add_entities: Fonction pour ajouter des entités à Home Assistant.
    """
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    entities = []

    for nodeid, node in router.home_devices.items():
        if node["category"] == FreeboxHomeCategory.BASIC_SHUTTER:
            entities.append(FreeboxBasicShutter(hass, router, node))
        elif node["category"] == FreeboxHomeCategory.SHUTTER:
            entities.append(FreeboxShutter(hass, router, node))
        elif node["category"] == FreeboxHomeCategory.OPENER:
            entities.append(FreeboxShutter(hass, router, node))

    if entities:
        async_add_entities(entities, update_before_add=True)
        _LOGGER.debug(f"{len(entities)} entités de volets ajoutées pour {router.name}")

# SECTION: Classe pour les volets basiques
class FreeboxBasicShutter(FreeboxHomeEntity, CoverEntity):
    """Représentation d'un volet basique Freebox (sans position).

    Permet seulement d'ouvrir, fermer ou arrêter le volet.
    """

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        """Initialise un volet basique Freebox.

        Args:
            hass: Instance de Home Assistant.
            router: Routeur Freebox gérant cette entité.
            node: Données du volet Freebox.
        """
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
        """Retourne si le volet est fermé.

        Returns:
            bool | None: True si fermé, False si ouvert, None si inconnu.
        """
        if self._state == CoverState.OPEN:
            return False
        if self._state == CoverState.CLOSED:
            return True
        return None

    async def async_open_cover(self, **kwargs) -> None:
        """Ouvre le volet.

        Envoie la commande d'ouverture via l'API Freebox.
        """
        if self._command_up is None:
            _LOGGER.error(f"Commande d'ouverture non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_up, {"value": None})
        self._state = CoverState.OPEN
        _LOGGER.info(f"Volet {self._attr_name} ouvert")

    async def async_close_cover(self, **kwargs) -> None:
        """Ferme le volet.

        Envoie la commande de fermeture via l'API Freebox.
        """
        if self._command_down is None:
            _LOGGER.error(f"Commande de fermeture non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_down, {"value": None})
        self._state = CoverState.CLOSED
        _LOGGER.info(f"Volet {self._attr_name} fermé")

    async def async_stop_cover(self, **kwargs) -> None:
        """Arrête le volet.

        Envoie la commande d'arrêt via l'API Freebox.
        """
        if self._command_stop is None:
            _LOGGER.error(f"Commande d'arrêt non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        self._state = None
        _LOGGER.info(f"Volet {self._attr_name} arrêté")

    async def async_update(self) -> None:
        """Met à jour l'état du volet.

        Récupère l'état actuel via l'API Freebox.
        """
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
        """Convertit l'état brut en état Home Assistant.

        Args:
            state: État brut de l'API.

        Returns:
            str | None: État converti ou None si inconnu.
        """
        if state:
            return CoverState.CLOSED
        elif state is not None:
            return CoverState.OPEN
        return None

# SECTION: Classe pour les volets avec position
class FreeboxShutter(FreeboxHomeEntity, CoverEntity):
    """Représentation d'un volet Freebox avec position.

    Permet de contrôler la position précise du volet.
    """

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        """Initialise un volet Freebox avec position.

        Args:
            hass: Instance de Home Assistant.
            router: Routeur Freebox gérant cette entité.
            node: Données du volet Freebox.
        """
        super().__init__(hass, router, node)
        self._command_position = self.get_command_id(node['show_endpoints'], "slot", "position_set")
        self._command_stop = self.get_command_id(node['show_endpoints'], "slot", "stop")
        self._current_cover_position = self.get_value("signal", "position_set")
        self._state = None
        self._invert_entity_id = None
        entity_registry = async_get(hass)
        for entity in entity_registry.entities.values():
            if entity.unique_id == f"{self._attr_unique_id}_InvertSwitch":
                self._invert_entity_id = entity.entity_id
                break
        _LOGGER.debug(f"Volet avec position {self._attr_name} initialisé")

    def get_invert_status(self) -> bool:
        """Vérifie si l'inversion est activée via l'entité switch associée.

        Returns:
            bool: True si inversion activée, False sinon.
        """
        if self._invert_entity_id is None:
            return False
        state = self._hass.states.get(self._invert_entity_id)
        if state is None:
            return False
        return state.state == "on"

    def get_corrected_state(self, value: Any) -> Any:
        """Corrige la position en fonction de l'état d'inversion.

        Args:
            value: Position brute.

        Returns:
            Any: Position corrigée ou None si invalide.
        """
        if value is None:
            return None
        if self.get_invert_status():
            return 100 - value
        return value

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
        """Retourne si le volet est fermé.

        Returns:
            bool: True si position à 0, False sinon.
        """
        return self._current_cover_position == 0

    async def async_set_cover_position(self, position: int, **kwargs) -> None:
        """Définit la position du volet.

        Args:
            position: Position cible (0-100).
        """
        corrected_position = self.get_corrected_state(position)
        if self._command_position is None:
            _LOGGER.error(f"Commande de position non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_position, {"value": corrected_position})
        self._current_cover_position = corrected_position
        _LOGGER.info(f"Position du volet {self._attr_name} définie à {corrected_position}")

    async def async_open_cover(self, **kwargs) -> None:
        """Ouvre complètement le volet (position 0)."""
        if self._command_position is None:
            _LOGGER.error(f"Commande d'ouverture non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_position, {"value": 0})
        self._current_cover_position = 0
        _LOGGER.info(f"Volet {self._attr_name} ouvert")

    async def async_close_cover(self, **kwargs) -> None:
        """Ferme complètement le volet (position 100)."""
        if self._command_position is None:
            _LOGGER.error(f"Commande de fermeture non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_position, {"value": 100})
        self._current_cover_position = 100
        _LOGGER.info(f"Volet {self._attr_name} fermé")

    async def async_stop_cover(self, **kwargs) -> None:
        """Arrête le volet.

        Envoie la commande d'arrêt et met à jour la position.
        """
        if self._command_stop is None:
            _LOGGER.error(f"Commande d'arrêt non disponible pour {self._attr_unique_id}")
            return
        await self.set_home_endpoint_value(self._command_stop, {"value": None})
        await self.async_update()
        _LOGGER.info(f"Volet {self._attr_name} arrêté")

    async def async_update(self) -> None:
        """Met à jour la position actuelle du volet.

        Récupère la position via l'API et applique la correction d'inversion si nécessaire.
        """
        try:
            position = self.get_value("signal", "position_set")
            self._current_cover_position = self.get_corrected_state(position)
            _LOGGER.debug(f"Position du volet {self._attr_name} mise à jour: {self._current_cover_position}")
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour de la position pour {self._attr_unique_id}: {err}")
            self._current_cover_position = None
