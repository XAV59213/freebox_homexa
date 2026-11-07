"""Capteurs TNT, adapted from cyclope205/programme-tnt-fr (MIT)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .router import FreeboxRouter

from .const import DOMAIN
from .tnt_const import ALL_CHANNELS, freebox_channel_number
from .tnt_coordinator import ProgrammeTntFrCoordinator

TNT_DEVICE_INFO = DeviceInfo(
    # Identifiant propre à Homexa : (programme_tnt_fr, programme_tnt_fr) est
    # celui de l'intégration séparée et fusionnerait les deux appareils.
    identifiers={(DOMAIN, "programme_tnt_fr")},
    name="TNT",
    manufacturer="xmltvfr.fr",
    model="Guide TV et Programme TNT FR",
    entry_type=DeviceEntryType.SERVICE,
    configuration_url="https://xmltvfr.fr/",
)


class HomexaTntSensor(CoordinatorEntity[ProgrammeTntFrCoordinator], SensorEntity):
    _attr_translation_key = "tnt_channel"
    _attr_has_entity_name = True
    _attr_device_info = TNT_DEVICE_INFO

    def __init__(
        self,
        coordinator: ProgrammeTntFrCoordinator,
        channel_id: str,
        unique_prefix: str,
        router: FreeboxRouter | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._channel_id = channel_id
        self._attr_unique_id = f"{unique_prefix}_tnt_{channel_id}"
        self._source_channel_name = ALL_CHANNELS.get(channel_id, channel_id)
        self._attr_translation_placeholders = {"channel": self._source_channel_name}

    @property
    def _data(self) -> dict[str, object]:
        return self.coordinator.data.get(self._channel_id, {}) if self.coordinator.data else {}

    @property
    def native_value(self) -> str | None:
        current = self._data.get("current")
        title = current.get("title") if isinstance(current, dict) else None
        return title if isinstance(title, str) else None

    @property
    def entity_picture(self) -> str | None:
        icon = self._data.get("channel_icon")
        if isinstance(icon, str) and icon:
            return icon
        current = self._data.get("current")
        icon = current.get("icon") if isinstance(current, dict) else None
        return icon if isinstance(icon, str) else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self._data
        attrs: dict[str, object] = {
            "channel_id": self._channel_id,
            "channel_name": data.get("channel_name") or self._source_channel_name,
            "channel_icon": data.get("channel_icon"),
            "homexa_tnt": True,
            "current": data.get("current"),
            "next": data.get("next"),
            "prime_time": data.get("prime_time"),
            "second_part": data.get("second_part"),
        }
        number = freebox_channel_number(self._channel_id)
        if number is not None:
            attrs["channel_number"] = number
        return attrs
