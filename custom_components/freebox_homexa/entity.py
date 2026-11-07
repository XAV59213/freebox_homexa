"""Support pour les fonctionnalités de base des appareils Freebox dans Home Assistant."""

from __future__ import annotations
import asyncio
import logging
from collections.abc import Callable, Sequence, Mapping
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo, async_get as async_get_device_registry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from freebox_api.exceptions import HttpRequestError
from .const import CATEGORY_TO_MODEL, DOMAIN, FreeboxHomeCategory
from .device_groups import GROUP_HOME, group_identifier, home_node_group, home_node_name, suggested_area
from .availability import home_node_reachable, router_reachable
from .errors import is_shutdown_error, poll_log_level
from .router import FreeboxRouter
from .registry_compat import as_version, get_device_by_identifier

_LOGGER = logging.getLogger(__name__)


def _home_endpoint_payload(value: Any | None) -> dict[str, Any]:
    """Build the JSON body expected by Freebox Home PUT /home/endpoints."""
    if isinstance(value, dict) and "value" in value:
        return value
    return {"value": value}


class FreeboxHomeEntity(Entity):
    """Représentation de base d'une entité Freebox Home dans Home Assistant."""

    _attr_has_entity_name = True
    _home_entity_name: str | None = None
    _home_use_device_class_name = False

    @property
    def name(self) -> str | None:
        """Keep device labels out of relative names, without altering legacy IDs."""
        if (getattr(self, "translation_key", None) or self._home_use_device_class_name) and getattr(self, "platform_data", None) is not None:
            translated = super().name
            if isinstance(translated, str):
                return translated
        if self._home_entity_name is not None:
            return self._home_entity_name
        if self._sub_node is not None:
            return str(self._sub_node["label"]).strip()
        if self._node.get("category") == FreeboxHomeCategory.ALARM:
            # Alarm entities share the Home group device, not a dedicated node.
            return self._source_name
        return self._home_entity_name

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
        self._source_name = (node.get("label") or "").strip()
        self._device_name = self._source_name
        self._attr_unique_id = f"{self._router.mac}-node_{self._id}"

        if sub_node is not None:
            self._source_name += " " + sub_node["label"].strip()
            self._attr_unique_id += "-" + sub_node["name"].strip()

        self._available = True
        self._failed_read_endpoints: set[int] = set()
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

        if not (node.get("label") or "").strip() or self._device_name.lower() == "unknown device":
            self._device_name = home_node_name(node, self._model)
            self._source_name = self._device_name + (
                " " + sub_node["label"].strip() if sub_node is not None else ""
            )

        device_info: DeviceInfo = {
            "identifiers": {(DOMAIN, self._id)},
            "manufacturer": self._manufacturer,
            "model": self._model,
            "name": self._device_name,
            "sw_version": as_version(self._firmware),
        }
        if node.get("category") == FreeboxHomeCategory.ALARM:
            # Le module d'alarme porte ses entités sur l'appareil de groupe
            # « Maison connectée et alarme » (plus d'appareil séparé ni de groupe vide).
            self._attr_device_info = self._alarm_group_device_info(hass, router)
            return
        area = suggested_area(self._device_name)
        if area:
            device_info["suggested_area"] = area
        parent_id = router.parent_for(f"node:{self._id}", self._device_name, home_node_group(node))
        if parent_id:
            device_info["via_device_id"] = parent_id
        self._attr_device_info = device_info

    def _alarm_group_device_info(self, hass: HomeAssistant, router: FreeboxRouter) -> DeviceInfo:
        """DeviceInfo du groupe « Maison connectée et alarme » ; retire l'ancien appareil alarme."""
        router.used_groups.add(GROUP_HOME)
        router.group_device_id(GROUP_HOME)  # crée l'appareil « Freebox Maison connectée »
        # L'ancien appareil séparé est retiré par le nettoyage différé, une fois
        # les entités déplacées (le retirer ici supprimerait leurs entrées du registre).
        router.merged_node_ids.add(self._id)
        return DeviceInfo(
            identifiers={group_identifier(router.mac, GROUP_HOME)},
            manufacturer=self._manufacturer,
            model=self._model,
            sw_version=as_version(self._firmware),
        )

    async def set_home_endpoint_value(
        self, command_id: int | None, value: Any | None = None, *, log_errors: bool = True
    ) -> bool:
        if self._id is None or command_id is None:
            return False
        payload = _home_endpoint_payload(value)
        try:
            await asyncio.wait_for(
                self._router.home.set_home_endpoint_value(self._id, command_id, payload),
                timeout=10.0,
            )
            return True
        except asyncio.TimeoutError:
            if log_errors:
                _LOGGER.warning("Timeout lors de la commande sur l'appareil %s", self._id)
            return False
        except Exception as err:  # noqa: BLE001
            if is_shutdown_error(err, self._router):
                if log_errors:
                    _LOGGER.debug("Commande sur l'appareil %s ignorée (rechargement) : %s", self._id, err)
                return False
            if log_errors:
                _LOGGER.error("Erreur lors de la commande sur l'appareil %s : %s", self._id, err)
            return False

    async def async_execute_home_command(
        self, command_id: int | None, value: Any | None = None
    ) -> None:
        """Require acknowledgement before updating camera/cover optimistic state.

        Keep the historical boolean helper for its other existing callers.
        No raw SDK error, URL or command payload is exposed in the UI message,
        nor logged again before HA reports the raised exception.
        """
        if not await self.set_home_endpoint_value(command_id, value, log_errors=False):
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            )

    async def get_home_endpoint_value(self, command_id: int | None) -> Any | None:
        """Récupère la valeur d'un endpoint avec timeout et gestion d'erreur."""
        if self._id is None or command_id is None:
            return None
        try:
            node = await self._router.async_read(
                lambda: asyncio.wait_for(
                    self._router.home.get_home_endpoint_value(self._id, command_id),
                    timeout=8.0,
                )
            )
            if not isinstance(node, dict) or "value" not in node:
                raise ValueError("Invalid Home endpoint response")
            self._router.note_source(("home_endpoint", self._id, command_id), True, "Lecture Home")
            self._failed_read_endpoints.discard(command_id)
            return node["value"]
        except Exception as err:  # SDK/transport failures are not an explicit unknown value.
            self._router.note_source(("home_endpoint", self._id, command_id), False, "Lecture Home")
            self._failed_read_endpoints.add(command_id)
            if self._router.closing and is_shutdown_error(err, self._router):
                return None
            _LOGGER.debug("Lecture Home indisponible (%s)", type(err).__name__)
            return None

    def get_command_id(self, nodes: Sequence[Mapping[str, object]], ep_type: str, name: str) -> int | None:
        node = next(
            (x for x in nodes if x.get("name") == name and x.get("ep_type") == ep_type), None
        )
        if not node:
            _LOGGER.warning("Commande manquante : %s/%s", name, ep_type)
            return None
        command_id = node.get("id")
        return command_id if isinstance(command_id, int) and not isinstance(command_id, bool) else None

    def get_node_value(self, nodes: Sequence[Mapping[str, object]], ep_type: str, name: str) -> Any | None:
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

    @property
    def available(self) -> bool:
        """Indisponible si la Freebox est injoignable ou si elle signale le nœud « unreachable »."""
        if self._failed_read_endpoints:
            return False
        if not router_reachable(self._router):
            return False
        if getattr(self._router, "home_available", True) is False:
            return False
        if (getattr(self._router, "home_snapshot_known", False) is True
                and self._id not in self._router.home_devices):
            return False
        if not home_node_reachable(self._node):
            return False
        return super().available

    async def async_update_signal(self) -> None:
        if self._id not in self._router.home_devices:
            self.async_write_ha_state()
            return
        try:
            self._node = self._router.home_devices[self._id]
            if self._sub_node is None:
                self._source_name = self._node["label"].strip()
            else:
                self._source_name = f"{self._node['label'].strip()} {self._sub_node['label'].strip()}"
            if self._node.get("category") != FreeboxHomeCategory.ALARM:
                # Update the device's source name, retaining name_by_user and IDs.
                device_name = (self._node.get("label") or "").strip() or home_node_name(self._node, self._model)
                registry = async_get_device_registry(self._hass)
                device = get_device_by_identifier(registry, (DOMAIN, self._id), self._router.entry_id)
                if device is not None and device.name != device_name:
                    registry.async_update_device(device.id, name=device_name)
            self._attr_available = True
            self._router.note_source(("home_metadata", self._id), True, "Métadonnées Home")
            self.async_write_ha_state()
        except Exception as err:  # noqa: BLE001
            if is_shutdown_error(err, self._router):
                _LOGGER.debug("Mise à jour de %s interrompue (rechargement) : %s", self._source_name, err)
                return
            self._attr_available = False
            self._router.note_source(("home_metadata", self._id), False, "Métadonnées Home")
            _LOGGER.debug("Mise à jour Home impossible (%s)", type(err).__name__)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_signal_update = async_dispatcher_connect(
            self._hass,
            self._router.signal_home_device_update,
            self.async_update_signal,
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_signal_update is not None:
            self._remove_signal_update()
            self._remove_signal_update = None
        await super().async_will_remove_from_hass()
