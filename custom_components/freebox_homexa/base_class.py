"""Support pour les appareils Freebox Home (détecteurs, volets, etc.)."""
from __future__ import annotations
import logging
from typing import NotRequired, TypedDict
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, VALUE_NOT_SET, DUMMY
from .router import FreeboxRouter
from .registry_compat import as_version
from .sdk_contracts import HomeEndpoints

_LOGGER = logging.getLogger(__name__)

class LegacyHomeNode(TypedDict):
    id: int
    label: str
    category: str
    props: NotRequired[dict[str, object]]
    type: NotRequired[dict[str, object]]


class LegacyHomeSubNode(TypedDict):
    label: str
    name: str


class LegacyHomeEndpoint(TypedDict):
    id: int
    name: str
    ep_type: str
    value: NotRequired[object]


class FreeboxBaseClass(Entity):
    """Classe de base pour toutes les entités Freebox Home."""

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: LegacyHomeNode, sub_node: LegacyHomeSubNode | None = None) -> None:
        _LOGGER.debug("Initialisation de l'entité Home legacy")
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

        self._available = True
        self._firmware = node.get('props', {}).get('FwVersion')
        self._manufacturer = "Free SAS"
        self._model = ""

        # Attribution du modèle selon la catégorie
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
        elif node.get("type", {}).get("inherit") == "node::rts":
            self._manufacturer = "Somfy"
            self._model = "RTS"
        elif node.get("type", {}).get("inherit") == "node::ios":
            self._manufacturer = "Somfy"
            self._model = "IOcontrol"

    @property
    def device_info(self) -> DeviceInfo | None:
        """DeviceInfo HA. Cette classe n'est pas une plateforme active."""
        if not self._is_device:
            return None
        info: DeviceInfo = {
            "identifiers": {(DOMAIN, str(self._id))},
            "name": self._device_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "sw_version": as_version(self._firmware),
        }
        parent = self._router.device_id
        if isinstance(parent, str):
            info["via_device_id"] = parent
        return info

    # === Méthodes API (inchangées) ===
    async def set_home_endpoint_value(self, command_id: int, value: dict[str, object]) -> bool:
        if self._id >= 1000 and DUMMY:
            return True
        if command_id == VALUE_NOT_SET:
            return False
        home: HomeEndpoints = self._router._api.home
        await home.set_home_endpoint_value(self._id, command_id, value)
        return True

    async def get_home_endpoint_value(self, command_id: int) -> object:
        if self._id >= 1000 and DUMMY:
            return VALUE_NOT_SET
        if command_id == VALUE_NOT_SET:
            return VALUE_NOT_SET
        home: HomeEndpoints = self._router._api.home
        node = await home.get_home_endpoint_value(self._id, command_id)
        if not isinstance(node, dict):
            raise ValueError("Invalid Home endpoint response")
        return node.get("value", VALUE_NOT_SET)

    def get_command_id(self, nodes: list[LegacyHomeEndpoint], ep_type: str, name: str) -> int:
        node = next((x for x in nodes if x.get("name") == name and x.get("ep_type") == ep_type), None)
        return node["id"] if node else VALUE_NOT_SET

    def get_node_value(self, nodes: list[LegacyHomeEndpoint], ep_type: str, name: str) -> object:
        node = next((x for x in nodes if x.get("name") == name and x.get("ep_type") == ep_type), None)
        return node.get("value", VALUE_NOT_SET) if node else VALUE_NOT_SET
