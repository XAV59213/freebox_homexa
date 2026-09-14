"""Constantes pour l'intégration Freebox dans Home Assistant."""

from __future__ import annotations
import enum
from typing import Any
from homeassistant.const import Platform
from homeassistant.components.alarm_control_panel import AlarmControlPanelState  # noqa: F401
from homeassistant.config_entries import ConfigEntry

DOMAIN = "freebox_homexa"
SERVICE_REBOOT = "reboot"
SERVICE_RELOAD = "reload"
SERVICE_REMOTE = "remote"
SERVICE_TV_GUIDE = "tv_guide"

VALUE_NOT_SET = -1
DEFAULT_DEVICE_NAME = "Unknown device"
REPEATER_MODEL = "F-RP01A"

# Options (Paramètres → Intégration → Configurer)
CONF_TRACK_LAN_CLIENTS = "track_lan_clients"
CONF_CREATE_WIFI_SENSORS = "create_wifi_sensors"
CONF_CREATE_LAN_DEVICES = "create_lan_devices"
CONF_HOME_POLL_INTERVAL = "home_poll_interval"
CONF_REMOTE_CODE = "remote_code"
CONF_REMOTE_CODES = "remote_codes"

DEFAULT_TRACK_LAN_CLIENTS = True
DEFAULT_CREATE_WIFI_SENSORS = True
DEFAULT_CREATE_LAN_DEVICES = True
DEFAULT_HOME_POLL_INTERVAL = 15
HOME_POLL_INTERVAL_OPTIONS = [5, 10, 15, 20, 25, 30]

# Must stay stable. freebox-api requests a new pairing if this dict differs
# from the saved token file (app_version / hostname used to change every restart).
APP_DESC = {
    "app_id": "hass",
    "app_name": "Home Assistant",
    "app_version": "28.8",
    "device_name": "Home Assistant",
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


def option_enabled(entry: ConfigEntry, key: str, default: bool = True) -> bool:
    """Lit une option booléenne de la config entry."""
    return bool(entry.options.get(key, default))


def option_home_poll_interval(entry: ConfigEntry) -> int:
    """Intervalle du poll Home (PIR, contacts, alarme, volets), en secondes."""
    try:
        value = int(entry.options.get(CONF_HOME_POLL_INTERVAL, DEFAULT_HOME_POLL_INTERVAL))
    except (TypeError, ValueError):
        return DEFAULT_HOME_POLL_INTERVAL
    if value in HOME_POLL_INTERVAL_OPTIONS:
        return value
    return DEFAULT_HOME_POLL_INTERVAL


def _clean_remote_code(raw: Any) -> str | None:
    if raw is None:
        return None
    code = str(raw).strip()
    return code or None


def remote_code_field(player_id: Any) -> str:
    """Clé d'option pour le code d'un Player."""
    return f"{CONF_REMOTE_CODE}_{player_id}"


def option_remote_code(entry: ConfigEntry, player_id: Any | None = None) -> str | None:
    """Code télécommande réseau : d'abord celui du Player, sinon le code commun."""
    if player_id is not None:
        codes = entry.options.get(CONF_REMOTE_CODES)
        if isinstance(codes, dict):
            found = _clean_remote_code(codes.get(str(player_id)) or codes.get(player_id))
            if found:
                return found
        found = _clean_remote_code(entry.options.get(remote_code_field(player_id)))
        if found:
            return found
    found = _clean_remote_code(entry.options.get(CONF_REMOTE_CODE))
    if found:
        return found
    return _clean_remote_code(entry.data.get(CONF_REMOTE_CODE))
