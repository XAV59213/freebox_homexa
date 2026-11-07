"""Support pour les interrupteurs Freebox Delta, Revolution et Mini 4K dans Home Assistant."""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial

import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .discovery import DiscoveryCandidate, async_setup_discovery
from .errors import is_shutdown_error, poll_log_level
from .router import FreeboxConfigEntry, FreeboxRouter
from .sdk_contracts import WifiActions
from .entity import FreeboxHomeEntity
from .availability import FreeboxReachableMixin

from .errors import async_action_errors

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FreeboxSwitchEntityDescription(SwitchEntityDescription):
    """Description des entités interrupteurs Freebox."""
    pass


SWITCH_DESCRIPTIONS = [
    FreeboxSwitchEntityDescription(
        key="wifi",
        name="Freebox WiFi",
        entity_category=EntityCategory.CONFIG,
    )
]


# Une seule action / mise à jour à la fois vers la Freebox pour cette plateforme.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: FreeboxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités interrupteurs pour la Freebox."""
    router: FreeboxRouter = entry.runtime_data
    async_add_entities([FreeboxSwitch(router, description) for description in SWITCH_DESCRIPTIONS], True)

    def candidates() -> Iterable[DiscoveryCandidate]:
        for nodeid, node in router.home_devices.items():
            if node["category"] in {"shutter", "opener"}:
                yield str(nodeid), partial(FreeboxShutterInvertSwitchEntity, hass, router, node)

    async_setup_discovery(hass, entry, router,
        [router.signal_home_device_new, router.signal_home_device_update], candidates, async_add_entities)


class FreeboxSwitch(FreeboxReachableMixin, SwitchEntity):
    """Interrupteur WiFi de la Freebox."""

    _attr_has_entity_name = True

    def __init__(
        self, router: FreeboxRouter, entity_description: FreeboxSwitchEntityDescription
    ) -> None:
        self.entity_description = entity_description
        self._router = router
        self._attr_device_info = router.device_info
        self._attr_unique_id = f"{router.mac} {entity_description.name}"
        self._attr_translation_key = "wifi"

    async def _async_set_state(self, enabled: bool) -> None:
        wifi: WifiActions = self._router.wifi
        await wifi.set_global_config({"enabled": enabled})
        _LOGGER.info("WiFi %s pour %s", 'activé' if enabled else 'désactivé', self._router.name)

    @property
    def name(self) -> str | None:
        if getattr(self, "platform_data", None) is None:
            name = self.entity_description.name
            return name.removeprefix("Freebox ") if isinstance(name, str) else None
        translated = super().name
        return translated if isinstance(translated, str) else None

    @async_action_errors
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set_state(True)

    @async_action_errors
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set_state(False)

    async def async_update(self) -> None:
        try:
            data = await self._router.async_read(self._router.wifi.get_global_config)
            if not isinstance(data, dict):
                raise ValueError("Invalid Wi-Fi response")
            enabled = data.get("enabled")
            self._attr_is_on = enabled if isinstance(enabled, bool) else None
            self._attr_available = True
            self._router.note_source("wifi_switch", True, "Interrupteur Wi-Fi")
        except Exception as err:  # noqa: BLE001
            if is_shutdown_error(err, self._router):
                _LOGGER.debug("État du Wi-Fi non lu (rechargement) : %s", err)
                return
            self._router.note_source("wifi_switch", False, "Interrupteur Wi-Fi")
            _LOGGER.debug("Lecture Wi-Fi impossible (%s)", type(err).__name__)
            self._attr_is_on = None
            self._attr_available = False


class FreeboxShutterInvertSwitchEntity(FreeboxHomeEntity, SwitchEntity):
    """Interrupteur d'inversion pour les volets."""

    _attr_has_entity_name = True
    _home_entity_name = "Inversion Positionnement"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{self._attr_unique_id}_InvertSwitch"
        storage_dir = Path(hass.config.path(".storage", "freebox_homexa"))
        self._path = storage_dir / f"{slugify(self._attr_unique_id)}.conf"
        self._state: bool | None = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self.hass.async_add_executor_job(self._load_state)

    @property
    def translation_key(self) -> str:
        return "invert_switch"

    @property
    def is_on(self) -> bool | None:
        return self._state

    @async_action_errors
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._write, "1")
        self._state = True
        self.async_write_ha_state()
        _LOGGER.info("Inversion activée pour %s", self._source_name)

    @async_action_errors
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._write, "0")
        self._state = False
        self.async_write_ha_state()
        _LOGGER.info("Inversion désactivée pour %s", self._source_name)

    @property
    def available(self) -> bool:
        # This setting is local: router reachability is irrelevant, disk errors are not.
        return self._state is not None

    async def async_update(self) -> None:
        await self.hass.async_add_executor_job(self._load_state)

    def _write(self, content: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(content)

    def _load_state(self) -> None:
        try:
            if self._path.exists():
                self._state = self._path.read_text().strip() == "1"
            else:
                self._state = False
        except OSError as err:
            _LOGGER.error("Erreur lecture inversion %s: %s", self._source_name, err)
            self._state = None
