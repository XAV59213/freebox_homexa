"""Support pour les fonctionnalités de base des appareils Freebox dans Home Assistant."""
# DESCRIPTION: Ce fichier définit la classe de base pour les entités Freebox Home,
# offrant une gestion centralisée des appareils via l'API Freebox.
# OBJECTIF: Fournir une structure réutilisable pour les entités Freebox dans Home Assistant.

from __future__ import annotations
import logging
from collections.abc import Callable
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from freebox_api.exceptions import HttpRequestError
from .const import CATEGORY_TO_MODEL, DOMAIN, FreeboxHomeCategory
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)


class FreeboxHomeEntity(Entity):
    """Représentation de base d'une entité Freebox Home dans Home Assistant."""

    def __init__(
        self,
        hass: HomeAssistant,
        router: FreeboxRouter,
        node: dict[str, Any],
        sub_node: dict[str, Any] | None = None,
    ) -> None:
        """Initialise une entité Freebox Home."""
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
        self._firmware = node.get("props", {}).get("FwVersion")
        self._manufacturer = "Freebox SAS"
        self._remove_signal_update: Callable[[], None] | None = None

        # Détermination du modèle
        self._model = CATEGORY_TO_MODEL.get(node["category"])
        if self._model is None:
            if node.get("type", {}).get("inherit") == "node::rts":
                self._manufacturer = "Somfy"
                self._model = CATEGORY_TO_MODEL[FreeboxHomeCategory.RTS]
            elif node.get("type", {}).get("inherit") == "node::ios":
                self._manufacturer = "Somfy"
                self._model = CATEGORY_TO_MODEL[FreeboxHomeCategory.IOHOME]

        # Device info avec via_device corrigé (obligatoire pour HA 2025.12)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._id)},
            manufacturer=self._manufacturer,
            model=self._model,
            name=self._device_name,
            sw_version=self._firmware,
            via_device=(DOMAIN, router.mac),          # ← CORRECTION
        )

        _LOGGER.debug(f"Entité {self._attr_name} initialisée pour l'appareil {self._id}")

    # ===================================================================
    # Méthodes pour interagir avec l'API Freebox
    # ===================================================================
    async def set_home_endpoint_value(
        self, command_id: int | None, value: Any | None = None
    ) -> bool:
        """Définit une valeur pour un endpoint Freebox Home."""
        if self._id is None or command_id is None:
            _LOGGER.error("Impossible de définir une valeur via l'API. ID ou command_id manquant.")
            return False
        try:
            await self._router.home.set_home_endpoint_value(self._id, command_id, value)
            return True
        except HttpRequestError as err:
            _LOGGER.error(f"Erreur HTTP définition endpoint {command_id} sur {self._id}: {err}")
            return False
        except Exception as err:
            _LOGGER.error(f"Échec inattendu définition endpoint {command_id} sur {self._id}: {err}")
            return False

    async def get_home_endpoint_value(self, command_id: int | None) -> Any | None:
        """Récupère la valeur d'un endpoint Freebox Home."""
        if self._id is None or command_id is None:
            _LOGGER.error("Impossible de récupérer une valeur via l'API. ID ou command_id manquant.")
            return None
        try:
            node = await self._router.home.get_home_endpoint_value(self._id, command_id)
            return node.get("value")
        except HttpRequestError as err:
            _LOGGER.error(f"Erreur HTTP récupération endpoint {command_id} sur {self._id}: {err}")
            return None
        except Exception as err:
            _LOGGER.error(f"Échec inattendu récupération endpoint {command_id} sur {self._id}: {err}")
            return None

    # ===================================================================
    # Méthodes utilitaires
    # ===================================================================
    def get_command_id(self, nodes: list, ep_type: str, name: str) -> int | None:
        """Récupère l'identifiant de commande pour un endpoint spécifique."""
        node = next(
            (x for x in nodes if x.get("name") == name and x.get("ep_type") == ep_type), None
        )
        if not node:
            _LOGGER.warning(f"L'appareil Freebox Home n'a pas de commande pour: {name}/{ep_type}")
            return None
        return node.get("id")

    def get_node_value(self, nodes: list, ep_type: str, name: str) -> Any | None:
        """Récupère la valeur d'un endpoint spécifique."""
        node = next(
            (x for x in nodes if x.get("name") == name and x.get("ep_type") == ep_type), None
        )
        if node is None:
            _LOGGER.warning(f"L'appareil Freebox Home n'a pas de valeur pour: {ep_type}/{name}")
            return None
        return node.get("value")

    def get_value(self, ep_type: str, name: str) -> Any | None:
        """Récupère la valeur d'un endpoint à partir des données locales du nœud."""
        node = next(
            (
                endpoint
                for endpoint in self._node.get("show_endpoints", [])
                if endpoint.get("name") == name and endpoint.get("ep_type") == ep_type
            ),
            None,
        )
        if node is None:
            _LOGGER.warning(f"L'appareil Freebox Home n'a pas de valeur pour: {ep_type}/{name}")
            return None
        return node.get("value")

    # ===================================================================
    # Gestion des mises à jour
    # ===================================================================
    async def async_update_signal(self) -> None:
        """Met à jour l'état et le nom de l'entité à partir des données du routeur."""
        if self._id not in self._router.home_devices:
            _LOGGER.error(f"Appareil {self._id} non trouvé dans les données du routeur")
            return
        try:
            self._node = self._router.home_devices[self._id]
            if self._sub_node is None:
                self._attr_name = self._node["label"].strip()
            else:
                self._attr_name = f"{self._node['label'].strip()} {self._sub_node['label'].strip()}"
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error(f"Échec mise à jour entité {self._attr_name}: {err}")

    # ===================================================================
    # Cycle de vie de l'entité
    # ===================================================================
    async def async_added_to_hass(self) -> None:
        """Enregistre les callbacks lorsque l'entité est ajoutée à Home Assistant."""
        self._remove_signal_update = async_dispatcher_connect(
            self._hass,
            self._router.signal_home_device_update,
            self.async_update_signal,
        )
        _LOGGER.debug(f"Entité {self._attr_name} ajoutée à Home Assistant")

    async def async_will_remove_from_hass(self) -> None:
        """Nettoie les ressources lorsque l'entité est retirée."""
        if self._remove_signal_update is not None:
            self._remove_signal_update()
            self._remove_signal_update = None
            _LOGGER.debug(f"Entité {self._attr_name} retirée de Home Assistant")
