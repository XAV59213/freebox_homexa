"""Base support for Freebox Home entities."""

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


class FreeboxHomeEntity(Entity):
    """Base representation of a Freebox Home entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        router: FreeboxRouter,
        node: dict[str, Any],
        sub_node: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a Freebox Home entity.

        Args:
            hass: The Home Assistant instance.
            router: The Freebox router managing this entity.
            node: The Freebox Home node data.
            sub_node: Optional sub-node data for composite entities.
        """
        self._hass = hass
        self._router = router
        self._node = node
        self._sub_node = sub_node
        self._node_id = node["id"]
        self._attr_name = node["label"].strip()
        self._device_name = self._attr_name
        self._attr_unique_id = f"{router.mac}_home_{self._node_id}"

        if sub_node:
            self._attr_name += " " + sub_node["label"].strip()
            self._attr_unique_id += f"_{sub_node['name'].strip()}"

        self._firmware = node["props"].get("FwVersion")
        self._manufacturer = "Freebox SAS"
        self._model = CATEGORY_TO_MODEL.get(node["category"])
        self._dispatcher_remover: Callable[[], None] | None = None

        # Custom manufacturer and model for Somfy devices
        if self._model is None:
            node_type = node["type"]
            if node_type.get("inherit") == "node::rts":
                self._manufacturer = "Somfy"
                self._model = CATEGORY_TO_MODEL[FreeboxHomeCategory.RTS]
            elif node_type.get("inherit") == "node::ios":
                self._manufacturer = "Somfy"
                self._model = CATEGORY_TO_MODEL[FreeboxHomeCategory.IOHOME]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._node_id)},
            manufacturer=self._manufacturer,
            model=self._model,
            name=self._device_name,
            sw_version=self._firmware,
            via_device=(DOMAIN, router.mac),
        )

    async def async_update_signal(self) -> None:
        """Update the entity state and name from the Freebox."""
        node = self._router.home_devices.get(self._node_id)
        if not node:
            _LOGGER.warning("Node %s not found in router data", self._node_id)
            return
        self._node = node
        if self._sub_node:
            self._attr_name = f"{node['label'].strip()} {self._sub_node['label'].strip()}"
        else:
            self._attr_name = node["label"].strip()
        self.async_write_ha_state()

    async def set_home_endpoint_value(
        self, command_id: int | None, value: Any | None = None
    ) -> bool:
        """Set a value for a Freebox Home endpoint.

        Args:
            command_id: The ID of the command endpoint.
            value: The value to set (optional).

        Returns:
            bool: True if the value was set successfully, False otherwise.
        """
        if command_id is None:
            _LOGGER.error("Cannot set value: command ID is None for %s", self._node_id)
            return False
        try:
            await self._router.home.set_home_endpoint_value(self._node_id, command_id, value)
            _LOGGER.debug("Set value %s for endpoint %d on %s", value, command_id, self._node_id)
            return True
        except Exception as err:
            _LOGGER.error("Failed to set value for %s, endpoint %d: %s", self._node_id, command_id, err)
            return False

    async def get_home_endpoint_value(self, command_id: int | None) -> Any | None:
        """Get a value from a Freebox Home endpoint.

        Args:
            command_id: The ID of the signal endpoint.

        Returns:
            The value of the endpoint, or None if unavailable.
        """
        if command_id is None:
            _LOGGER.error("Cannot get value: command ID is None for %s", self._node_id)
            return None
        try:
            node = await self._router.home.get_home_endpoint_value(self._node_id, command_id)
            value = node.get("value")
            _LOGGER.debug("Got value %s for endpoint %d on %s", value, command_id, self._node_id)
            return value
        except Exception as err:
            _LOGGER.error("Failed to get value for %s, endpoint %d: %s", self._node_id, command_id, err)
            return None

    def get_command_id(self, nodes: list[dict[str, Any]], ep_type: str, name: str) -> int | None:
        """Get the command ID for a specific endpoint.

        Args:
            nodes: List of endpoint dictionaries.
            ep_type: The endpoint type (e.g., 'slot', 'signal').
            name: The endpoint name (e.g., 'trigger', 'state').

        Returns:
            The command ID, or None if not found.
        """
        for node in nodes:
            if node["name"] == name and node["ep_type"] == ep_type:
                return node["id"]
        _LOGGER.warning("No command found for %s/%s on %s", name, ep_type, self._node_id)
        return None

    def get_value(self, ep_type: str, name: str) -> Any | None:
        """Get the value of a specific endpoint from the current node.

        Args:
            ep_type: The endpoint type (e.g., 'slot', 'signal').
            name: The endpoint name (e.g., 'trigger', 'state').

        Returns:
            The endpoint value, or None if not found.
        """
        for endpoint in self._node["show_endpoints"]:
            if endpoint["name"] == name and endpoint["ep_type"] == ep_type:
                return endpoint.get("value")
        _LOGGER.warning("No value found for %s/%s on %s", ep_type, name, self._node_id)
        return None

    async def async_added_to_hass(self) -> None:
        """Register callbacks when the entity is added to Home Assistant."""
        self._dispatcher_remover = async_dispatcher_connect(
            self._hass,
            self._router.signal_home_device_update,
            self.async_update_signal,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when the entity is removed from Home Assistant."""
        if self._dispatcher_remover:
            self._dispatcher_remover()
            self._dispatcher_remover = None

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self._node.get("status") == "active"
