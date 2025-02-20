"""Support for Freebox camera entities with streaming and motion detection."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from homeassistant.components.camera import CameraEntityFeature
from homeassistant.components.ffmpeg.camera import (
    CONF_EXTRA_ARGUMENTS,
    CONF_INPUT,
    DEFAULT_ARGUMENTS,
    FFmpegCamera,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_DETECTION, DOMAIN, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Freebox camera entities from a config entry."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    tracked: set[str] = set()

    @callback
    def update_callback() -> None:
        """Add new cameras when detected."""
        add_entities(hass, router, async_add_entities, tracked)

    router.listeners.append(
        async_dispatcher_connect(hass, router.signal_home_device_new, update_callback)
    )
    update_callback()


@callback
def add_entities(
    hass: HomeAssistant,
    router: FreeboxRouter,
    async_add_entities: AddEntitiesCallback,
    tracked: set[str],
) -> None:
    """Add new camera entities from the router."""
    new_tracked = [
        FreeboxCamera(hass, router, node)
        for nodeid, node in router.home_devices.items()
        if node["category"] == FreeboxHomeCategory.CAMERA and nodeid not in tracked
    ]
    if new_tracked:
        async_add_entities(new_tracked, update_before_add=True)
        tracked.update(node._id for node in new_tracked)
        _LOGGER.debug(
            "Added %d camera entities for %s (%s)",
            len(new_tracked),
            router.name,
            router.mac,
        )


class FreeboxCamera(FreeboxHomeEntity, FFmpegCamera):
    """Representation of a Freebox camera without TurboJPEG dependency."""

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        """Initialize a Freebox camera."""
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{self._attr_unique_id}_camera"

        # Prepare FFmpeg stream URL with encoded password
        password = node["props"]["Pass"]
        stream_url = node["props"]["Stream"].replace(password, quote(password, safe=""))
        device_info = {
            CONF_NAME: node["label"].strip(),
            CONF_INPUT: str(stream_url),
            CONF_EXTRA_ARGUMENTS: DEFAULT_ARGUMENTS,
        }
        # Désactiver les instantanés pour éviter l'utilisation de TurboJPEG
        FFmpegCamera.__init__(self, hass, device_info, still_image_url=None)

        self._attr_supported_features = (
            CameraEntityFeature.ON_OFF | CameraEntityFeature.STREAM
        )
        self._command_motion_detection = self.get_command_id(
            node["type"]["endpoints"], "slot", ATTR_DETECTION
        )
        self._attr_extra_state_attributes = {}
        self._update_node(node)

    @property
    def still_image_url(self) -> str | None:
        """Return None to disable still image generation."""
        return None

    async def async_enable_motion_detection(self) -> None:
        """Enable motion detection on the camera."""
        if self._command_motion_detection is None:
            _LOGGER.error("Motion detection not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_motion_detection, True)
            self._attr_motion_detection_enabled = True
            self.async_write_ha_state()
            _LOGGER.info("Motion detection enabled for %s", self._node_id)
        except Exception as err:
            _LOGGER.error("Failed to enable motion detection for %s: %s", self._node_id, err)

    async def async_disable_motion_detection(self) -> None:
        """Disable motion detection on the camera."""
        if self._command_motion_detection is None:
            _LOGGER.error("Motion detection not supported for %s", self._node_id)
            return
        try:
            await self.set_home_endpoint_value(self._command_motion_detection, False)
            self._attr_motion_detection_enabled = False
            self.async_write_ha_state()
            _LOGGER.info("Motion detection disabled for %s", self._node_id)
        except Exception as err:
            _LOGGER.error("Failed to disable motion detection for %s: %s", self._node_id, err)

    async def async_update_signal(self) -> None:
        """Update the camera state from the Freebox."""
        node = self._router.home_devices.get(self._id)
        if node is None:
            _LOGGER.warning("Camera node %s not found in router data", self._id)
            return
        try:
            self._update_node(node)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to update camera %s: %s", self._node_id, err)

    def _update_node(self, node: dict[str, Any]) -> None:
        """Update camera attributes from node data."""
        self._attr_name = node["label"].strip()
        self._attr_is_streaming = node["status"] == "active"

        # Update extra state attributes from signal endpoints
        for endpoint in filter(
            lambda x: x["ep_type"] == "signal", node["show_endpoints"]
        ):
            self._attr_extra_state_attributes[endpoint["name"]] = endpoint["value"]

        # Set motion detection status with default False if missing
        self._attr_motion_detection_enabled = self._attr_extra_state_attributes.get(
            ATTR_DETECTION, False
        )

    @property
    def available(self) -> bool:
        """Return True if the camera is available."""
        return self._attr_is_streaming is not None
