"""Support pour les appareils Freebox Home (détecteurs, volets, etc.)."""
# DESCRIPTION: Classe de base pour les entités Freebox Home dans Home Assistant
# OBJECTIF: Fournir une structure commune pour gérer les appareils Freebox Home

import logging
from typing import Dict, Optional
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, VALUE_NOT_SET, DUMMY
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

# SECTION: Classe de base pour les entités Freebox
class FreeboxBaseClass(Entity):
    """Classe de base pour toutes les entités Freebox Home dans Home Assistant."""
    
    def __init__(self, hass, router: FreeboxRouter, node: Dict[str, any], sub_node=None) -> None:
        """Initialise une entité Freebox Home.

        Args:
            hass: Instance de Home Assistant.
            router: Routeur Freebox gérant cette entité.
            node: Données de l'appareil Freebox.
            sub_node: Données optionnelles pour les sous-appareils (facultatif).
        """
        _LOGGER.debug(f"Initialisation de l'entité pour le nœud: {node}")
        self._hass = hass
        self._router = router
        self._id = node["id"]
        self._name = node["label"].strip()
        self._device_name = node["label"].strip()
        self._unique_id = f"{self._router.mac}-node_{self._id}"
        self._is_device = True

        if sub_node is not None:
            self._name = sub_node["label"].strip()
            self._unique_id += "-" + sub_node["name"].strip()
            # self._is_device = False  # Commenté, possiblement inutilisé

        self._available = True
        self._firmware = node['props'].get('FwVersion', None)
        self._manufacturer = "Free SAS"
        self._model = ""
        
        # Attribution du modèle en fonction de la catégorie
        if node["category"] == "pir":
            self._model = "F-HAPIR01A"
        elif node["category"] == "camera":
            self._model = "F-HACAM01A"
        elif node["category"] == "dws":
            self._model = "F-HADWS01A"
        elif node["category"] == "kfb":
            self._model = "F-HAKFB01A"
            self._is_device = True
        elif node["category"] == "alarm":
            self._model = "F-MSEC07A"
        elif node["type"].get("inherit", None) == "node::rts":
            self._manufacturer = "Somfy"
            self._model = "RTS"
        elif node["type"].get("inherit", None) == "node::ios":
            self._manufacturer = "Somfy"
            self._model = "IOcontrol"

    @property
    def unique_id(self) -> str:
        """Retourne l'identifiant unique de l'entité."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Retourne le nom de l'entité."""
        return self._name

    @property
    def available(self) -> bool:
        """Retourne True si l'entité est disponible."""
        return self._available

    @property
    def device_info(self) -> Optional[Dict[str, any]]:
        """Retourne les informations sur l'appareil.

        Returns:
            Un dictionnaire avec les détails de l'appareil ou None si ce n'est pas un appareil principal.
        """
        if not self._is_device:
            return None
        return {
            "identifiers": {(DOMAIN, self._id)},
            "name": self._device_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "sw_version": self._firmware,
        }

    # SECTION: Méthodes pour interagir avec l'API Freebox Home
    async def set_home_endpoint_value(self, command_id, value) -> bool:
        """Définit une valeur pour un endpoint Freebox Home.

        Args:
            command_id: Identifiant de la commande.
            value: Valeur à définir.

        Returns:
            True si la commande a réussi, False sinon.
        """
        if self._id >= 1000 and DUMMY:
            _LOGGER.debug(f"Appareil fictif {self._id}: SET ignoré")
            return True
        if command_id == VALUE_NOT_SET:
            _LOGGER.error(f"Impossible de définir une valeur via l'API pour {self._id}. La commande est VALUE_NOT_SET")
            return False
        await self._router._api.home.set_home_endpoint_value(self._id, command_id, value)
        _LOGGER.debug(f"Valeur {value} définie pour l'endpoint {command_id} sur {self._id}")
        return True

    async def get_home_endpoint_value(self, command_id):
        """Récupère la valeur d'un endpoint Freebox Home.

        Args:
            command_id: Identifiant de la commande.

        Returns:
            La valeur de l'endpoint ou VALUE_NOT_SET si non disponible.
        """
        if self._id >= 1000 and DUMMY:
            _LOGGER.debug(f"Appareil fictif {self._id}: GET retourne VALUE_NOT_SET")
            return VALUE_NOT_SET
        if command_id == VALUE_NOT_SET:
            _LOGGER.error(f"Impossible de récupérer une valeur via l'API pour {self._id}. La commande est VALUE_NOT_SET")
            return VALUE_NOT_SET
        node = await self._router._api.home.get_home_endpoint_value(self._id, command_id)
        value = node.get("value", VALUE_NOT_SET)
        _LOGGER.debug(f"Valeur récupérée pour l'endpoint {command_id} sur {self._id}: {value}")
        return value

    def get_command_id(self, nodes, ep_type, name):
        """Récupère l'identifiant de commande pour un endpoint spécifique.

        Args:
            nodes: Liste des endpoints.
            ep_type: Type d'endpoint (ex. 'slot', 'signal').
            name: Nom de l'endpoint.

        Returns:
            L'identifiant de commande ou VALUE_NOT_SET si non trouvé.
        """
        node = next(filter(lambda x: (x["name"] == name and x["ep_type"] == ep_type), nodes), None)
        if node is None:
            _LOGGER.warning(f"L'appareil Freebox Home n'a pas de commande pour: {ep_type}/{name}")
            return VALUE_NOT_SET
        return node["id"]

    def get_node_value(self, nodes, ep_type, name):
        """Récupère la valeur d'un endpoint spécifique.

        Args:
            nodes: Liste des endpoints.
            ep_type: Type d'endpoint.
            name: Nom de l'endpoint.

        Returns:
            La valeur de l'endpoint ou VALUE_NOT_SET si non trouvée.
        """
        node = next(filter(lambda x: (x["name"] == name and x["ep_type"] == ep_type), nodes), None)
        if node is None:
            _LOGGER.warning(f"L'appareil Freebox Home n'a pas de valeur pour: {ep_type}/{name}")
            return VALUE_NOT_SET
        return node.get("value", VALUE_NOT_SET)
