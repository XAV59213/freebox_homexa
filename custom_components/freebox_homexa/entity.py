"""Support pour les fonctionnalités de base des appareils Freebox dans Home Assistant."""

from __future__ import annotations
import asyncio
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

        self._model = CATEGORY_TO_MODEL.get(node["category"])
        if self._model is None:
            if node.get("type", {}).get("inherit") == "node::rts":
                self._manufacturer = "Somfy"
                self._model = CATEGORY_TO_MODEL[FreeboxHomeCategory.RTS]
            elif node.get("type", {}).get("inherit") == "node::ios":
                self._manufacturer = "Somfy"
                self._model = CATEGORY_TO_MODEL[FreeboxHomeCategory.IOHOME]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._id)},
            manufacturer=self._manufacturer,
            model=self._model,
            name=self._device_name,
            sw_version=self._firmware,
            via_device=(DOMAIN, router.mac),
        )

    # ===================================================================
    # Méthodes API avec gestion du timeout (correction principale)
    # ===================================================================
    async def set_home_endpoint_value(
        self, command_id: int | None, value: Any | None = None
    ) -> bool:
        if self._id is None or command_id is None:
            return False
        try:
            await asyncio.wait_for(
                self._router.home.set_home_endpoint_value(self._id, command_id, value),
                timeout=10.0,
            )
            return True
        except asyncio.TimeoutError:
            _LOGGER.warning(f"Timeout lors de la commande sur l'appareil {self._id}")
            return False
        except Exception as err:
            _LOGGER.error(f"Erreur lors de la commande sur l'appareil {self._id}: {err}")
            return False

    async def get_home_endpoint_value(self, command_id: int | None) -> Any | None:
        """Récupère la valeur d'un endpoint avec timeout et gestion d'erreur."""
        if self._id is None or command_id is None:
            return None
        try:
            node = await asyncio.wait_for(
                self._router.home.get_home_endpoint_value(self._id, command_id),
                timeout=8.0,          # Timeout raisonnable
            )
            return node.get("value")
        except asyncio.TimeoutError:
            _LOGGER.debug(f"Timeout sur la lecture de l'endpoint {command_id} (appareil {self._id})")
            return None
        except HttpRequestError as err:
            _LOGGER.debug(f"Erreur HTTP sur endpoint {command_id} (appareil {self._id}): {err}")
            return None
        except Exception as err:
            _LOGGER.warning(f"Erreur inattendue sur endpoint {command_id} (appareil {self._id}): {err}")
            return None

    # ===================================================================
    # Méthodes utilitaires (inchangées)
    # ===================================================================
    def get_command_id(self, nodes: list, ep_type: str, name: str) -> int | None:
        node = next(
            (x for x in nodes if x.get("name") == name and x.get("ep_type") == ep_type), None
        )
        if not node:
            _LOGGER.warning(f"Commande manquante : {name}/{ep_type}")
            return None
        return node.get("id")

    def get_node_value(self, nodes: list, ep_type: str, name: str) -> Any | None:
        node = next(
            (x for x in nodes if x.get("name") == name and x.get("ep_type") == ep_type), None
        )
        if node is None:
            return None
        return node.get("value")

    def get_value(self, ep_type: str, name: str) -> Any | None:
        node = next(
            (
                endpoint
                for endpoint in self._node.get("show_endpoints", [])
                if endpoint.get("name") == name and endpoint.get("ep_type") == ep_type
            ),
            None,
        )
        if node is None:
            return None
        return node.get("value")

    # ===================================================================
    # Mise à jour signal
    # ===================================================================
    async def async_update_signal(self) -> None:
        if self._id not in self._router.home_devices:
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
    # Cycle de vie
    # ===================================================================
    async def async_added_to_hass(self) -> None:
        self._remove_signal_update = async_dispatcher_connect(
            self._hass,
            self._router.signal_home_device_update,
            self.async_update_signal,
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_signal_update is not None:
            self._remove_signal_update()
            self._remove_signal_update = None
