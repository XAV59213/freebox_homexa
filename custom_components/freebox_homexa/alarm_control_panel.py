"""Support for Freebox alarm control panels."""

from typing import Any

import logging

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

# Mapping of Freebox alarm states to Home Assistant states
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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Freebox alarm control panel entities from a config entry."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]

    entities = [
        FreeboxAlarm(hass, router, node)
        for node in router.home_devices.values()
        if node["category"] == FreeboxHomeCategory.ALARM
    ]
    if entities:
        async_add_entities(entities, update_before_add=True)
        _LOGGER.debug(
            "Added %d alarm control panels for %s (%s)",
            len(entities),
            router.name,
            router.mac,
        )


class FreeboxAlarm(FreeboxHomeEntity, AlarmControlPanelEntity):
    """Representation of a Freebox alarm control panel."""

    _attr_code_arm_required = False

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        """Initialize a Freebox alarm control panel."""
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{self._attr_unique_id}_alarm"

        # Command IDs for alarm actions
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

        # Define supported features based on available commands
        self._attr_supported_features = (
            (AlarmControlPanelEntityFeature.ARM_AWAY if self._command_arm_away else 0)
            | (AlarmControlPanelEntityFeature.ARM_HOME if self._command_arm_home else 0)
            | (AlarmControlPanelEntityFeature.TRIGGER if self._command_trigger else 0)
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send the disarm command to the Freebox alarm."""
        if self._command_disarm is None:
            _LOGGER.error("Disarm command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_disarm)
            _LOGGER.info("Alarm disarmed for %s", self._node_id)
        except Exception as err:
            _LOGGER.error("Failed to disarm alarm %s: %s", self._node_id, err)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send the arm away command to the Freebox alarm."""
        if self._command_arm_away is None:
            _LOGGER.error("Arm away command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_arm_away)
            _LOGGER.info("Alarm armed away for %s", self._node_id)
        except Exception as err:
            _LOGGER.error("Failed to arm away alarm %s: %s", self._node_id, err)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send the arm home command to the Freebox alarm."""
        if self._command_arm_home is None:
            _LOGGER.error("Arm home command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_arm_home)
            _LOGGER.info("Alarm armed home for %s", self._node_id)
        except Exception as err:
            _LOGGER.error("Failed to arm home alarm %s: %s", self._node_id, err)

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Send the trigger command to the Freebox alarm."""
        if self._command_trigger is None:
            _LOGGER.error("Trigger command not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_trigger)
            _LOGGER.info("Alarm triggered for %s", self._node_id)
        except Exception as err:
            _LOGGER.error("Failed to trigger alarm %s: %s", self._node_id, err)

    async def async_update(self) -> None:
        """Update the alarm state from the Freebox."""
        if self._command_state is None:
            _LOGGER.error("State command not available for %s", self._node_id)
            self._attr_alarm_state = None
            return
        try:
            state: str | None = await self.get_home_endpoint_value(self._command_state)
            self._attr_alarm_state = FREEBOX_TO_STATUS.get(
                state, AlarmControlPanelState.DISARMED
            )
        except Exception as err:
            _LOGGER.error("Failed to update alarm state for %s: %s", self._node_id, err)
            self._attr_alarm_state = None
