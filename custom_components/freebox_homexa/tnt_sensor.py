"""Capteurs TNT embarqués dans Freebox Homexa (attributs attendus par la carte)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .tnt_const import TNT_CHANNELS
from .tnt_coordinator import ProgrammeTntFrCoordinator


class HomexaTntSensor(CoordinatorEntity[ProgrammeTntFrCoordinator], SensorEntity):
    _attr_icon = "mdi:television-classic"
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: ProgrammeTntFrCoordinator,
        device_info: DeviceInfo,
        channel_id: str,
        unique_prefix: str,
    ) -> None:
        super().__init__(coordinator)
        self._channel_id = channel_id
        self._attr_unique_id = f"{unique_prefix}_tnt_{channel_id}"
        self._attr_name = TNT_CHANNELS.get(channel_id, channel_id)
        self._attr_device_info = device_info

    @property
    def _data(self) -> dict:
        return self.coordinator.data.get(self._channel_id, {}) if self.coordinator.data else {}

    @property
    def native_value(self) -> str | None:
        current = self._data.get("current")
        return current.get("title") if current else None

    @property
    def entity_picture(self) -> str | None:
        return self._data.get("channel_icon")

    @property
    def extra_state_attributes(self) -> dict:
        data = self._data
        return {
            "channel_id": self._channel_id,
            "channel_name": data.get("channel_name"),
            "channel_icon": data.get("channel_icon"),
            "current": data.get("current"),
            "prime_time": data.get("prime_time"),
            "second_part": data.get("second_part"),
        }
