"""Constantes pour l'intégration Freebox dans Home Assistant."""

from __future__ import annotations
import enum
import socket
from homeassistant.const import Platform
from homeassistant.components.alarm_control_panel import AlarmControlPanelState  # noqa: F401

DOMAIN = "freebox_homexa"
SERVICE_REBOOT = "reboot"
SERVICE_RELOAD = "reload"
SERVICE_REMOTE = "remote"
SERVICE_TV_GUIDE = "tv_guide"

VALUE_NOT_SET = -1
DEFAULT_DEVICE_NAME = "Unknown device"
REPEATER_MODEL = "F-RP01A"

APP_DESC = {
    "app_id": "hass",
    "app_name": "Home Assistant",
    "app_version": "28.8.6",
    "device_name": socket.gethostname(),
}
API_VERSION = "v6"

PLATFORMS = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.CAMERA,
    Platform.COVER,
    Platform.DEVICE_TRACKER,
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.SENSOR,
    Platform.SWITCH,
]

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

ATTR_MODEL = "model"
ATTR_DETECTION = "detection"

CONNECTION_SENSORS_KEYS = {"rate_down", "rate_up"}

DEVICE_ICONS = {
    "freebox_delta": "mdi:television-guide",
    "freebox_hd": "mdi:television-guide",
    "freebox_mini": "mdi:television-guide",
    "freebox_player": "mdi:television-guide",
    "freebox_wifi": "mdi:wifi-sync",
    "ip_camera": "mdi:cctv",
    "ip_phone": "mdi:phone-voip",
    "laptop": "mdi:laptop",
    "multimedia_device": "mdi:play-network",
    "nas": "mdi:nas",
    "networking_device": "mdi:wifi-sync",
    "printer": "mdi:printer",
    "router": "mdi:router-wireless",
    "smartphone": "mdi:cellphone",
    "tablet": "mdi:tablet",
    "television": "mdi:television",
    "vg_console": "mdi:gamepad-variant",
    "workstation": "mdi:desktop-tower-monitor",
}

class FreeboxHomeCategory(enum.StrEnum):
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
