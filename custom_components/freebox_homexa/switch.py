"""Support pour les interrupteurs Freebox Delta, Revolution et Mini 4K dans Home Assistant."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from freebox_api.exceptions import InsufficientPermissionsError

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .const import DOMAIN, STORAGE_VERSION, STORAGE_KEY
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

    # Interrupteurs d'inversion pour les volets
    for nodeid, node in router.home_devices.items():
        if node["category"] in {"shutter", "opener"}:
            entities.append(FreeboxShutterInvertSwitchEntity(hass, router, node))

    # Interrupteur WiFi
    for entity_description in SWITCH_DESCRIPTIONS:
        entities.append(FreeboxSwitch(router, entity_description))

    async_add_entities(entities, True)
    _LOGGER.debug(f"{len(entities)} entités interrupteurs ajoutées pour {router.name}")


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
            _LOGGER.info(f"WiFi {'activé' if enabled else 'désactivé'} pour {self._router.name}")
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
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour du WiFi: {err}")
            self._attr_is_on = None


class FreeboxShutterInvertSwitchEntity(FreeboxHomeEntity, SwitchEntity):
    """Interrupteur d'inversion pour les volets (utilise le même dossier sécurisé)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:directions-fork"
    _attr_name = "Inversion Positionnement"

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{self._attr_unique_id}_InvertSwitch"

        # Utilise le même dossier sécurisé que router.py
        storage_dir = hass.config.path(".storage", "freebox_homexa")
        Path(storage_dir).mkdir(parents=True, exist_ok=True)

        self._path = Path(storage_dir) / f"{slugify(self._attr_unique_id)}.conf"
        self._load_state()

    @property
    def translation_key(self) -> str:
        return "invert_switch"

    @property
    def is_on(self) -> bool | None:
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._path.write_text, "1")
        self._state = True
        self.async_write_ha_state()
        _LOGGER.info(f"Inversion activée pour {self._attr_name}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._path.write_text, "0")
        self._state = False
        self.async_write_ha_state()
        _LOGGER.info(f"Inversion désactivée pour {self._attr_name}")

    @property
    def available(self) -> bool:
        return True

    async def async_update(self) -> None:
        self._load_state()

    def _load_state(self) -> None:
        try:
            if self._path.exists():
                self._state = self._path.read_text().strip() == "1"
            else:
                self._state = False
        except OSError as err:
            _LOGGER.error(f"Erreur lecture inversion {self._attr_name}: {err}")
            self._state = False
