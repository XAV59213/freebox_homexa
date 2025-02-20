"""Constants for the Freebox Homexa integration."""

from __future__ import annotations

import enum
import socket

from homeassistant.const import Platform

# General constants
DOMAIN = "freebox_homexa"
SERVICE_REBOOT = "reboot"
VALUE_NOT_SET = -1  # Default value when a sensor or attribute is not set

# Freebox API application description
APP_DESC = {
    "app_id": "hass",
    "app_name": "Home Assistant",
    "app_version": "25.2.17",  # Matches integration version from manifest.json
    "device_name": socket.gethostname(),
}
API_VERSION = "v6"

# Supported Home Assistant platforms
PLATFORMS = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.COVER,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Default device name when unknown
DEFAULT_DEVICE_NAME = "Unknown device"

# Storage configuration for token persistence
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

# Device attributes
ATTR_MODEL = "model"  # Model name of the device
ATTR_DETECTION = "detection"  # Detection state for sensors

# Connection sensor keys (download/upload rates in bytes/s)
CONNECTION_SENSORS_KEYS: set[str] = {"rate_down", "rate_up"}

# Device type to Material Design Icon mapping
DEVICE_ICONS = {
    "freebox_delta": "mdi:television-guide",
    "freebox_hd": "mdi:television-classic",
    "freebox_mini": "mdi:television-box",
    "freebox_player": "mdi:play-box",
    "ip_camera": "mdi:cctv",
    "ip_phone": "mdi:phone-voip",
    "laptop": "mdi:laptop",
    "multimedia_device": "mdi:play-network",
    "nas": "mdi:nas",
    "networking_device": "mdi:network",
    "printer": "mdi:printer",
    "router": "mdi:router-wireless",
    "smartphone": "mdi:cellphone",
    "tablet": "mdi:tablet",
    "television": "mdi:television",
    "vg_console": "mdi:gamepad-variant",
    "workstation": "mdi:desktop-tower-monitor",
}

# Freebox Home categories and mappings
class FreeboxHomeCategory(enum.StrEnum):
    """Categories of Freebox Home devices."""

    ALARM = "alarm"
    CAMERA = "camera"
    DWS = "dws"  # Door/Window Sensor
    IOHOME = "iohome"
    KFB = "kfb"  # Keyfob (remote control)
    OPENER = "opener"
    PIR = "pir"  # Passive Infrared (motion sensor)
    RTS = "rts"  # Roller Shutter
    BASIC_SHUTTER = "basic_shutter"
    SHUTTER = "shutter"

# Mapping of Freebox Home categories to model names for display in Home Assistant
CATEGORY_TO_MODEL = {
    FreeboxHomeCategory.PIR: "F-HAPIR01A",
    FreeboxHomeCategory.CAMERA: "F-HACAM01A",
    FreeboxHomeCategory.DWS: "F-HADWS01A",
    FreeboxHomeCategory.KFB: "F-HAKFB01A",
    FreeboxHomeCategory.ALARM: "F-MSEC07A",
    FreeboxHomeCategory.RTS: "RTS",
    FreeboxHomeCategory.IOHOME: "IOHome",
    FreeboxHomeCategory.SHUTTER: "Volet roulant",
    FreeboxHomeCategory.BASIC_SHUTTER: "Volet roulant basic",
    FreeboxHomeCategory.OPENER: "Ouvrant, Porte",
}

# Categories compatible with Home Assistant entities
HOME_COMPATIBLE_CATEGORIES = [
    FreeboxHomeCategory.ALARM,
    FreeboxHomeCategory.CAMERA,
    FreeboxHomeCategory.DWS,
    FreeboxHomeCategory.IOHOME,
    FreeboxHomeCategory.KFB,
    FreeboxHomeCategory.PIR,
    FreeboxHomeCategory.RTS,
    FreeboxHomeCategory.OPENER,
    FreeboxHomeCategory.SHUTTER,
    FreeboxHomeCategory.BASIC_SHUTTER,
]
