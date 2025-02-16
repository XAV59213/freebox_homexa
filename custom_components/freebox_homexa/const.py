
"""Freebox component constants."""

from __future__ import annotations

import enum
import socket

from homeassistant.const import Platform

DOMAIN = "freebox_homexa"
SERVICE_REBOOT = "reboot"

#default Value
VALUE_NOT_SET = -1

APP_DESC = {
    "app_id": "hass",
    "app_name": "Home Assistant",
    "app_version": "0.106",
    "device_name": socket.gethostname(),
}
API_VERSION = "v6"

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

DEFAULT_DEVICE_NAME = "Unknown device"

# to store the cookie
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
#cover
ATTR_MODEL = "model"

CONNECTION_SENSORS_KEYS = {"rate_down", "rate_up"}

# Icons
DEVICE_ICONS = {
    "freebox_delta": "mdi:television-guide",
    "freebox_hd": "mdi:television-guide",
    "freebox_mini": "mdi:television-guide",
    "freebox_player": "mdi:television-guide",
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

ATTR_DETECTION = "detection"


# Home
class FreeboxHomeCategory(enum.StrEnum):
    """Freebox Home categories."""

    ALARM = "alarm"
    CAMERA = "camera"
    DWS = "dws"
    IOHOME = "iohome"
    KFB = "kfb"
    OPENER = "opener"
    PIR = "pir"
    RTS = "rts"
    BASIC_SHUTTER = "basic_shutter"
    SHUTTER = "shutter"

    """Freebox Home categories affichage HA """
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
    FreeboxHomeCategory.OPENER: "Ouvrant,Porte",
    
}

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

