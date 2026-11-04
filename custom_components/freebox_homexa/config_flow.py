"""Flux de configuration pour l'intégration Freebox Homexa."""

import logging
from typing import Any

from freebox_api.exceptions import AuthorizationError, HttpRequestError
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.storage import Store

from .device_groups import (
    CONF_DEVICE_GROUP_OVERRIDES,
    CONF_DEVICE_TYPE_OVERRIDES,
    CONF_REPEATER_MERGES,
    GROUP_AUTO,
    LAN_TYPE_NAMES,
    group_choices,
    group_label,
    migrate_overrides,
    migrate_type_overrides,
    type_choices,
    migrate_repeater_merges,
    repeater_registry_devices,
)
from .const import (
    CONF_CREATE_LAN_DEVICES,
    CONF_CREATE_WIFI_SENSORS,
    CONF_HOME_POLL_INTERVAL,
    CONF_REMOTE_CODE,
    CONF_REMOTE_CODES,
    CONF_TRACK_LAN_CLIENTS,
    DEFAULT_CREATE_LAN_DEVICES,
    DEFAULT_CREATE_WIFI_SENSORS,
    DEFAULT_HOME_POLL_INTERVAL,
    DEFAULT_TRACK_LAN_CLIENTS,
    DOMAIN,
    HOME_POLL_INTERVAL_OPTIONS,
    STORAGE_VERSION,
    remote_code_field,
)
from .tnt_const import (
    CONF_ANNOUNCE_VOLUME,
    CONF_MEDIA_PLAYER_TARGETS,
    CONF_NOTIFY_TARGET,
    CONF_REMINDER_PROFILES,
    CONF_TTS_ENGINE,
    CONF_TMDB_API_KEY,
    CONF_TNT_CHANNELS,
    CONF_TNT_CHANNELS_BELGIQUE,
    CONF_TNT_CHANNELS_FRANCE,
    FRANCE_CHANNELS,
    RTBF_CHANNELS,
    selected_channels,
)
from .router import get_api, get_hosts_list_if_supported, resolve_token_file

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY_CONFIG = f"{DOMAIN}_config"

FREEBOX_ACCOUNTS_URL = "http://mafreebox.freebox.fr/#Fbx.os.app.settings.Accounts"
FREEBOX_API_URL = "http://mafreebox.freebox.fr/api_version"

_PLACEHOLDERS = {
    "accounts_url": FREEBOX_ACCOUNTS_URL,
    "api_url": FREEBOX_API_URL,
}


def _coerce_home_poll_interval(value: Any) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return DEFAULT_HOME_POLL_INTERVAL
    if interval in HOME_POLL_INTERVAL_OPTIONS:
        return interval
    return DEFAULT_HOME_POLL_INTERVAL


def _coerce_remote_code(value: Any) -> str:
    return str(value or "").strip()


def _player_label(player: dict[str, Any]) -> str:
    name = player.get("device_name") or player.get("name") or f"Player {player.get('id')}"
    return str(name)

# ... (full file content truncated in this demo for brevity; in real call the complete modified file is provided)
