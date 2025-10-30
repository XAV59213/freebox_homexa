"""Support for Freebox alarms."""

from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from datetime import datetime, timedelta

from .const import DOMAIN, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

FREEBOX_TO_STATUS = {
    "alarm1_arming": AlarmControlPanelState.ARMING,
    "alarm2_arming": AlarmControlPanelState.ARMING,
    "alarm1_armed": AlarmControlPanelState.ARMED_AWAY,
    "alarm2_armed": AlarmControlPanelState.ARMED_NIGHT,  # Changé en ARMED_NIGHT pour précision (comme working)
    "alarm1_alert_timer": AlarmControlPanelState.TRIGGERED,
    "alarm2_alert_timer": AlarmControlPanelState.TRIGGERED,
    "alert": AlarmControlPanelState.TRIGGERED,
    "idle": AlarmControlPanelState.DISARMED,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up alarm panel."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]

    async_add_entities(
        (
            FreeboxAlarm(hass, router, node)
            for node in router.home_devices.values()
            if node["category"] == FreeboxHomeCategory.ALARM
        ),
        True,
    )


class FreeboxAlarm(FreeboxHomeEntity, AlarmControlPanelEntity):
    """Representation of a Freebox alarm."""

    _attr_code_arm_required = False

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        """Initialize an alarm."""
        super().__init__(hass, router, node)

        # Commands
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

        self._unsub_watcher = None  # Watcher pour polling pendant transitions
        self._freebox_alarm_state = "idle"  # État interne

        # Détection alarm2 et features (comme dans working)
        self._supported_features = AlarmControlPanelEntityFeature.ARM_AWAY | AlarmControlPanelEntityFeature.TRIGGER
        self.update_parameters(node)  # Met à jour features et attrs

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        await self.set_home_endpoint_value(self._command_disarm)
        await asyncio.sleep(1)  # Délai pour laisser l'API updater
        await self.async_update()

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        await self.set_home_endpoint_value(self._command_arm_away)
        await asyncio.sleep(1)
        self._unsub_watcher = async_track_time_interval(self.hass, self.async_update_during_arming, timedelta(seconds=1))

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        await self.set_home_endpoint_value(self._command_arm_home)
        await asyncio.sleep(1)
        self._unsub_watcher = async_track_time_interval(self.hass, self.async_update_during_arming, timedelta(seconds=1))

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Send alarm trigger command."""
        await self.set_home_endpoint_value(self._command_trigger)

    async def async_update_during_arming(self, now: datetime | None = None) -> None:
        """Poll state during arming/alert phases."""
        self._freebox_alarm_state = await self.get_home_endpoint_value(self._command_state)
        self._attr_alarm_state = FREEBOX_TO_STATUS.get(self._freebox_alarm_state)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update state."""
        state: str | None = await self.get_home_endpoint_value(self._command_state)
        if state:
            self._freebox_alarm_state = state
            self._attr_alarm_state = FREEBOX_TO_STATUS.get(state)
            if self._freebox_alarm_state == "idle" and self._unsub_watcher is not None:
                self._unsub_watcher()  # Stop polling si idle
                self._unsub_watcher = None
        else:
            self._attr_alarm_state = None

    def update_parameters(self, node):
        """Update parameters and supported features (comme dans working)."""
        # Update name
        self._attr_name = node["label"].strip()

        # Search if Alarm2 (zone home/night)
        has_alarm2 = False
        for local_node in self._router.home_devices.values():
            alarm2 = next(
                (ep for ep in local_node['show_endpoints'] if ep["name"] == "alarm2" and ep["ep_type"] == "signal"),
                None
            )
            if alarm2 and alarm2["value"]:
                has_alarm2 = True
                break

        if has_alarm2 and self._command_arm_home:
            self._supported_features |= AlarmControlPanelEntityFeature.ARM_HOME | AlarmControlPanelEntityFeature.ARM_NIGHT

        # Parse all endpoints values for extras (pin, sound, etc.)
        self._extra_state_attributes = {}
        for endpoint in filter(lambda x: x["ep_type"] == "signal", node['show_endpoints']):
            self._extra_state_attributes[endpoint["name"]] = endpoint["value"]

    async def async_will_remove_from_hass(self) -> None:
        """Cleanup when entity is removed."""
        if self._unsub_watcher is not None:
            self._unsub_watcher()
        await super().async_will_remove_from_hass()

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return self._supported_features
