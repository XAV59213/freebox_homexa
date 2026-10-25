"""Support pour les interrupteurs Freebox Delta, Revolution et Mini 4K dans Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from freebox_api.exceptions import InsufficientPermissionsError

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DOMAIN
from .errors import is_shutdown_error
from .router import FreeboxRouter
from .entity import FreeboxHomeEntity

_LOGGER = logging.getLogger(__name__)


@dataclass
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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités interrupteurs pour la Freebox."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    entities = []

    for nodeid, node in router.home_devices.items():
        if node["category"] in {"shutter", "opener"}:
            entities.append(FreeboxShutterInvertSwitchEntity(hass, router, node))

    for entity_description in SWITCH_DESCRIPTIONS:
        entities.append(FreeboxSwitch(router, entity_description))

    async_add_entities(entities, True)
    _LOGGER.debug("%s entités interrupteurs ajoutées pour %s", len(entities), router.name)


class FreeboxSwitch(SwitchEntity):
    """Interrupteur WiFi de la Freebox."""

    def __init__(
        self, router: FreeboxRouter, entity_description: FreeboxSwitchEntityDescription
    ) -> None:
        self.entity_description = entity_description
        self._router = router
        self._attr_device_info = router.device_info
        self._attr_unique_id = f"{router.mac} {entity_description.name}"

    async def _async_set_state(self, enabled: bool) -> None:
        try:
            await self._router.wifi.set_global_config({"enabled": enabled})
            _LOGGER.info("WiFi %s pour %s", 'activé' if enabled else 'désactivé', self._router.name)
        except InsufficientPermissionsError:
            _LOGGER.warning("Home Assistant n'a pas les permissions WiFi.")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set_state(False)

    async def async_update(self) -> None:
        try:
            data = await self._router.wifi.get_global_config()
            self._attr_is_on = bool(data["enabled"])
        except Exception as err:  # noqa: BLE001
            if is_shutdown_error(err, self._router):
                _LOGGER.debug("État du Wi-Fi non lu (rechargement) : %s", err)
                return
            _LOGGER.error("Échec de la mise à jour du WiFi : %s", err)
            self._attr_is_on = None


class FreeboxShutterInvertSwitchEntity(FreeboxHomeEntity, SwitchEntity):
    """Interrupteur d'inversion pour les volets."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:directions-fork"
    _attr_name = "Inversion Positionnement"

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{self._attr_unique_id}_InvertSwitch"
        storage_dir = Path(hass.config.path(".storage", "freebox_homexa"))
        self._path = storage_dir / f"{slugify(self._attr_unique_id)}.conf"
        self._state: bool = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self.hass.async_add_executor_job(self._load_state)

    @property
    def translation_key(self) -> str:
        return "invert_switch"

    @property
    def is_on(self) -> bool | None:
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._write, "1")
        self._state = True
        self.async_write_ha_state()
        _LOGGER.info("Inversion activée pour %s", self._attr_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._write, "0")
        self._state = False
        self.async_write_ha_state()
        _LOGGER.info("Inversion désactivée pour %s", self._attr_name)

    @property
    def available(self) -> bool:
        return True

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
            _LOGGER.error("Erreur lecture inversion %s: %s", self._attr_name, err)
            self._state = False
