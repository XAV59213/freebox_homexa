"""Support pour les appareils Freebox Home (détecteurs, volets, etc.)."""
import logging
from typing import Dict, Optional
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, VALUE_NOT_SET, DUMMY
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

class FreeboxBaseClass(Entity):
    """Classe de base pour toutes les entités Freebox Home."""

    def __init__(self, hass, router: FreeboxRouter, node: Dict[str, any], sub_node=None) -> None:
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
    def device_info(self) -> Optional[Dict[str, any]]:
        """Device info avec via_device corrigé (obligatoire pour HA 2025.12)."""
        if not self._is_device:
            return None
        return {
            "identifiers": {(DOMAIN, self._id)},
            "name": self._device_name,
            "manufacturer": self._manufacturer,
            "model": self._model,
            "sw_version": self._firmware,
            "via_device": (DOMAIN, self._router.mac),   # ← Correction principale
        }

    # === Méthodes API (inchangées) ===
    async def set_home_endpoint_value(self, command_id, value) -> bool:
        if self._id >= 1000 and DUMMY:
            return True
        if command_id == VALUE_NOT_SET:
            return False
        await self._router._api.home.set_home_endpoint_value(self._id, command_id, value)
        return True

    async def get_home_endpoint_value(self, command_id):
        if self._id >= 1000 and DUMMY:
            return VALUE_NOT_SET
        if command_id == VALUE_NOT_SET:
            return VALUE_NOT_SET
        node = await self._router._api.home.get_home_endpoint_value(self._id, command_id)
        return node.get("value", VALUE_NOT_SET)

    def get_command_id(self, nodes, ep_type, name):
        node = next((x for x in nodes if x.get("name") == name and x.get("ep_type") == ep_type), None)
        return node["id"] if node else VALUE_NOT_SET

    def get_node_value(self, nodes, ep_type, name):
        node = next((x for x in nodes if x.get("name") == name and x.get("ep_type") == ep_type), None)
        return node.get("value", VALUE_NOT_SET) if node else VALUE_NOT_SET
