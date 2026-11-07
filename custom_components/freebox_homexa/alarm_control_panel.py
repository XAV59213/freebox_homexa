"""Support for Freebox alarms."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from functools import partial

import asyncio
from typing import TYPE_CHECKING, Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
)
if TYPE_CHECKING:
    from homeassistant.components.alarm_control_panel.const import AlarmControlPanelEntityFeature, AlarmControlPanelState
else:
    from homeassistant.components.alarm_control_panel import AlarmControlPanelEntityFeature, AlarmControlPanelState

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from datetime import datetime, timedelta

from .discovery import DiscoveryCandidate, async_setup_discovery
from .const import FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .errors import async_action_errors
from .router import FreeboxConfigEntry, FreeboxRouter

# Signal endpoints that must never be exposed in Home Assistant attributes.
HIDDEN_SIGNAL_ATTRIBUTES = frozenset({"pin"})

FREEBOX_TO_STATUS = {
    "alarm1_arming": AlarmControlPanelState.ARMING,
    "alarm2_arming": AlarmControlPanelState.ARMING,
    "alarm1_armed": AlarmControlPanelState.ARMED_AWAY,
    "alarm2_armed": AlarmControlPanelState.ARMED_HOME,
    "alarm1_alert_timer": AlarmControlPanelState.TRIGGERED,
    "alarm2_alert_timer": AlarmControlPanelState.TRIGGERED,
    "alert": AlarmControlPanelState.TRIGGERED,
    "idle": AlarmControlPanelState.DISARMED,
}


# Une seule action / mise à jour à la fois vers la Freebox pour cette plateforme.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: FreeboxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up alarm panel."""
    router: FreeboxRouter = entry.runtime_data

    def candidates() -> Iterable[DiscoveryCandidate]:
        for nodeid, node in router.home_devices.items():
            if node["category"] == FreeboxHomeCategory.ALARM:
                yield str(nodeid), partial(FreeboxAlarm, hass, router, node)

    async_setup_discovery(hass, entry, router,
        [router.signal_home_device_new, router.signal_home_device_update], candidates, async_add_entities)


class FreeboxAlarm(FreeboxHomeEntity, AlarmControlPanelEntity):
    """Representation of a Freebox alarm."""

    _attr_code_arm_required = False

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        """Initialize an alarm."""
        super().__init__(hass, router, node)

        self._command_trigger = self.get_command_id(
            node["type"]["endpoints"], "slot", "trigger"
        )
        self._command_arm_away = self.get_command_id(
            node["type"]["endpoints"], "slot", "alarm1"
        )
        self._command_arm_home = self.get_command_id(
            node["type"]["endpoints"], "slot", "alarm2"
        )
        self._command_disarm = self.get_command_id(
            node["type"]["endpoints"], "slot", "off"
        )
        self._command_state = self.get_command_id(
            node["type"]["endpoints"], "signal", "state"
        )

        self._unsub_watcher: Callable[[], None] | None = None
        self._freebox_alarm_state = "idle"

        # Absent always available. Présent if the alarm2 slot exists on the panel.
        self._supported_features = AlarmControlPanelEntityFeature.ARM_AWAY
        if self._command_arm_home:
            self._supported_features |= AlarmControlPanelEntityFeature.ARM_HOME
        if self._command_trigger:
            self._supported_features |= AlarmControlPanelEntityFeature.TRIGGER

        self.update_parameters(node)

    @async_action_errors
    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        await self.async_execute_home_command(self._command_disarm)
        await asyncio.sleep(1)
        await self.async_update()

    @async_action_errors
    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command (Absent)."""
        await self.async_execute_home_command(self._command_arm_away)
        await asyncio.sleep(1)
        self._start_arming_watcher()

    @async_action_errors
    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command (Présent)."""
        await self.async_execute_home_command(self._command_arm_home)
        await asyncio.sleep(1)
        self._start_arming_watcher()

    def _start_arming_watcher(self) -> None:
        """Replace the previous watcher instead of leaking one on repeated arming."""
        if self._unsub_watcher is not None:
            self._unsub_watcher()
        self._unsub_watcher = async_track_time_interval(
            self.hass, self.async_update_during_arming, timedelta(seconds=1)
        )

    @async_action_errors
    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Send alarm trigger command."""
        await self.async_execute_home_command(self._command_trigger)

    async def async_update_during_arming(self, now: datetime | None = None) -> None:
        """Poll state during arming/alert phases."""
        state: object = await self.get_home_endpoint_value(self._command_state)
        self._freebox_alarm_state = state if isinstance(state, str) else ""
        self._attr_alarm_state = FREEBOX_TO_STATUS.get(self._freebox_alarm_state)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update state."""
        state: object = await self.get_home_endpoint_value(self._command_state)
        if isinstance(state, str) and state:
            self._freebox_alarm_state = state
            self._attr_alarm_state = FREEBOX_TO_STATUS.get(state)
            if self._freebox_alarm_state == "idle" and self._unsub_watcher is not None:
                self._unsub_watcher()
                self._unsub_watcher = None
        else:
            self._attr_alarm_state = None

    def update_parameters(self, node: Mapping[str, object]) -> None:
        """Update public metadata, never exposing the PIN signal."""
        label = node["label"]
        if not isinstance(label, str):
            raise TypeError("Alarm label must be a string")
        self._source_name = label.strip()
        endpoints = node["show_endpoints"]
        if not isinstance(endpoints, list):
            raise TypeError("Alarm endpoints must be a list")
        attributes: dict[str, object] = {}
        for endpoint in endpoints:
            if not isinstance(endpoint, Mapping):
                raise TypeError("Alarm endpoint must be a mapping")
            data: Mapping[object, object] = endpoint
            if data["ep_type"] != "signal":
                continue
            name = data["name"]
            if not isinstance(name, str):
                raise TypeError("Alarm signal name must be a string")
            if name not in HIDDEN_SIGNAL_ATTRIBUTES:
                attributes[name] = data["value"]
        self._attr_extra_state_attributes = attributes

    async def async_will_remove_from_hass(self) -> None:
        """Cleanup when entity is removed."""
        if self._unsub_watcher is not None:
            self._unsub_watcher()
            self._unsub_watcher = None
        await super().async_will_remove_from_hass()

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        """Return the list of supported features."""
        return self._supported_features
