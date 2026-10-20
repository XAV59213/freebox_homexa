"""Capteurs TNT, adapted from cyclope205/programme-tnt-fr (MIT)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from typing import Any

from .const import DOMAIN
from .device_groups import GROUP_TV
from .tnt_const import ALL_CHANNELS
from .tnt_coordinator import ProgrammeTntFrCoordinator

TNT_DEVICE_INFO = DeviceInfo(
    # Identifiant propre à Homexa : (programme_tnt_fr, programme_tnt_fr) est
    # celui de l'intégration séparée et fusionnerait les deux appareils.
    identifiers={(DOMAIN, "programme_tnt_fr")},
    name="Programme TNT FR",
    manufacturer="xmltvfr.fr",
    model="Guide TNT",
    entry_type=DeviceEntryType.SERVICE,
    configuration_url="https://xmltvfr.fr/",
)


class HomexaTntSensor(CoordinatorEntity[ProgrammeTntFrCoordinator], SensorEntity):
    _attr_icon = "mdi:television-classic"
    _attr_has_entity_name = False
    _attr_device_info = TNT_DEVICE_INFO

    def __init__(
        self,
        coordinator: ProgrammeTntFrCoordinator,
        channel_id: str,
        unique_prefix: str,
        router: Any = None,
    ) -> None:
        super().__init__(coordinator)
        if router is not None:
            parent_id = router.parent_for("programme_tnt_fr", "Programme TNT FR", GROUP_TV)
            if parent_id:
                self._attr_device_info = DeviceInfo(
                    **TNT_DEVICE_INFO, via_device_id=parent_id
                )
        self._channel_id = channel_id
        self._attr_unique_id = f"{unique_prefix}_tnt_{channel_id}"
        self._attr_name = ALL_CHANNELS.get(channel_id, channel_id)

    @property
    def _data(self) -> dict:
        return self.coordinator.data.get(self._channel_id, {}) if self.coordinator.data else {}

    @property
    def native_value(self) -> str | None:
        current = self._data.get("current")
        return current.get("title") if isinstance(current, dict) else None

    @property
    def entity_picture(self) -> str | None:
        return self._data.get("channel_icon") or (self._data.get("current") or {}).get("icon")

    @property
    def extra_state_attributes(self) -> dict:
        data = self._data
        return {
            "channel_id": self._channel_id,
            "channel_name": data.get("channel_name") or self._attr_name,
            "channel_icon": data.get("channel_icon"),
            "homexa_tnt": True,
            "current": data.get("current"),
            "next": data.get("next"),
            "prime_time": data.get("prime_time"),
            "second_part": data.get("second_part"),
        }
