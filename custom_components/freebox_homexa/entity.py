"""Support pour les fonctionnalités de base des appareils Freebox dans Home Assistant."""
# DESCRIPTION: Ce fichier définit la classe de base pour les entités Freebox Home,
#              offrant une gestion centralisée des appareils via l'API Freebox.
# OBJECTIF: Fournir une structure réutilisable pour les entités Freebox dans Home Assistant.

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import CATEGORY_TO_MODEL, DOMAIN, FreeboxHomeCategory
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

# SECTION: Classe de base pour les entités Freebox Home
class FreeboxHomeEntity(Entity):
    """Représentation de base d'une entité Freebox Home dans Home Assistant.

    Cette classe hérite de Entity et fournit des méthodes pour initialiser,
    mettre à jour et interagir avec les appareils Freebox Home via l'API.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        router: FreeboxRouter,
        node: dict[str, Any],
        sub_node: dict[str, Any] | None = None,
    ) -> None:
        """Initialise une entité Freebox Home.

        Args:
            hass: Instance de Home Assistant.
            router: Instance du routeur Freebox gérant cette entité.
            node: Données de l'appareil Freebox.
            sub_node: Données optionnelles pour les sous-appareils (facultatif).
        """
        self._hass = hass
        self._router = router
        self._node = node
        self._sub_node = sub_node
        self._id = node["id"]
        self._attr_name = node["label"].strip()
        self._device_name = self._attr_name
        self._attr_unique_id = f"{self._router.mac}-node_{self._id}"

        if sub_node is not None:
            self._attr_name += " " + sub_node["label"].strip()
            self._attr_unique_id += "-" + sub_node["name"].strip()

        self._available = True
        self._firmware = node["props"].get("FwVersion")
        self._manufacturer = "Freebox SAS"
        self._remove_signal_update: Callable[[], None] | None = None

        # Détermination du modèle en fonction de la catégorie
        self._model = CATEGORY_TO_MODEL.get(node["category"])
        if self._model is None:
            if node["type"].get("inherit") == "node::rts":
                self._manufacturer = "Somfy"
                self._model = CATEGORY_TO_MODEL[FreeboxHomeCategory.RTS]
            elif node["type"].get("inherit") == "node::ios":
                self._manufacturer = "Somfy"
                self._model = CATEGORY_TO_MODEL[FreeboxHomeCategory.IOHOME]

        # Informations sur l'appareil pour le registre
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._id)},
            manufacturer=self._manufacturer,
            model=self._model,
            name=self._device_name,
            sw_version=self._firmware,
            via_device=(DOMAIN, router.mac),
        )
        _LOGGER.debug(f"Entité {self._attr_name} initialisée pour l'appareil {self._id}")

    # SECTION: Méthodes pour interagir avec l'API Freebox
    async def set_home_endpoint_value(
        self, command_id: int | None, value: Any | None = None
    ) -> bool:
        """Définit une valeur pour un endpoint Freebox Home.

        Args:
            command_id: Identifiant de la commande à exécuter.
            value: Valeur à définir (facultatif).

        Returns:
            bool: True si la commande réussit, False sinon.
        """
        if command_id is None:
            _LOGGER.error(f"Impossible de définir une valeur via l'API pour {self._id}. La commande est None")
            return False
        try:
            await self._router.home.set_home_endpoint_value(self._id, command_id, value)
            _LOGGER.debug(f"Valeur {value} définie pour l'endpoint {command_id} sur {self._id}")
            return True
        except Exception as err:
            _LOGGER.error(f"Échec de la définition de la valeur pour {self._id}, endpoint {command_id}: {err}")
            return False

    async def get_home_endpoint_value(self, command_id: int | None) -> Any | None:
        """Récupère la valeur d'un endpoint Freebox Home.

        Args:
            command_id: Identifiant de la commande.

        Returns:
            Any | None: Valeur de l'endpoint ou None si non disponible.
        """
        if command_id is None:
            _LOGGER.error(f"Impossible de récupérer une valeur via l'API pour {self._id}. La commande est None")
            return None
        try:
            node = await self._router.home.get_home_endpoint_value(self._id, command_id)
            value = node.get("value")
            _LOGGER.debug(f"Valeur récupérée pour l'endpoint {command_id} sur {self._id}: {value}")
            return value
        except Exception as err:
            _LOGGER.error(f"Échec de la récupération de la valeur pour {self._id}, endpoint {command_id}: {err}")
            return None

    # SECTION: Méthodes utilitaires pour récupérer des valeurs
    def get_command_id(self, nodes: list, ep_type: str, name: str) -> int | None:
        """Récupère l'identifiant de commande pour un endpoint spécifique.

        Args:
            nodes: Liste des endpoints de l'appareil.
            ep_type: Type d'endpoint (ex. 'slot', 'signal').
            name: Nom de l'endpoint.

        Returns:
            int | None: Identifiant de la commande ou None si non trouvé.
        """
        node = next(
            (x for x in nodes if x["name"] == name and x["ep_type"] == ep_type), None
        )
        if not node:
            _LOGGER.warning(f"L'appareil Freebox Home n'a pas de commande pour: {name}/{ep_type}")
            return None
        return node["id"]

    def get_node_value(self, nodes: list, ep_type: str, name: str) -> Any | None:
        """Récupère la valeur d'un endpoint spécifique.

        Args:
            nodes: Liste des endpoints de l'appareil.
            ep_type: Type d'endpoint.
            name: Nom de l'endpoint.

        Returns:
            Any | None: Valeur de l'endpoint ou None si non trouvée.
        """
        node = next(
            (x for x in nodes if x["name"] == name and x["ep_type"] == ep_type), None
        )
        if node is None:
            _LOGGER.warning(f"L'appareil Freebox Home n'a pas de valeur pour: {ep_type}/{name}")
            return None
        return node.get("value", None)

    # SECTION: Gestion des mises à jour d'état
    async def async_update_signal(self) -> None:
        """Met à jour l'état et le nom de l'entité à partir des données du routeur.

        Récupère les dernières données de l'appareil et met à jour l'état dans Home Assistant.
        """
        try:
            self._node = self._router.home_devices[self._id]
            if self._sub_node is None:
                self._attr_name = self._node["label"].strip()
            else:
                self._attr_name = f"{self._node['label'].strip()} {self._sub_node['label'].strip()}"
            self.async_write_ha_state()
            _LOGGER.debug(f"Entité {self._attr_name} mise à jour avec succès")
        except KeyError:
            _LOGGER.error(f"Appareil {self._id} non trouvé dans les données du routeur")
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour de l'entité {self._attr_name}: {err}")

    # SECTION: Cycle de vie de l'entité dans Home Assistant
    async def async_added_to_hass(self) -> None:
        """Enregistre les callbacks lorsque l'entité est ajoutée à Home Assistant.

        Écoute les mises à jour du routeur pour déclencher les mises à jour d'état.
        """
        self._remove_signal_update = async_dispatcher_connect(
            self._hass,
            self._router.signal_home_device_update,
            self.async_update_signal,
        )
        _LOGGER.debug(f"Entité {self._attr_name} ajoutée à Home Assistant")

    async def async_will_remove_from_hass(self) -> None:
        """Nettoie les ressources lorsque l'entité est retirée de Home Assistant.

        Supprime le listener de mise à jour si présent.
        """
        if self._remove_signal_update is not None:
            self._remove_signal_update()
            self._remove_signal_update = None
            _LOGGER.debug(f"Entité {self._attr_name} retirée de Home Assistant")

    # SECTION: Méthodes internes
    def get_value(self, ep_type: str, name: str) -> Any | None:
        """Récupère la valeur d'un endpoint spécifique à partir des données locales.

        Args:
            ep_type: Type d'endpoint.
            name: Nom de l'endpoint.

        Returns:
            Any | None: Valeur de l'endpoint ou None si non trouvée.
        """
        node = next(
            (
                endpoint
                for endpoint in self._node["show_endpoints"]
                if endpoint["name"] == name and endpoint["ep_type"] == ep_type
            ),
            None,
        )
        if node is None:
            _LOGGER.warning(f"L'appareil Freebox Home n'a pas de valeur pour: {ep_type}/{name}")
            return None
        return node.get("value")
