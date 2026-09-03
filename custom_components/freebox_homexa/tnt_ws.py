"""WebSocket API for the Programme TNT FR Guide TV card."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .tnt_const import CONF_REMINDER_PROFILES, DOMAIN


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_get_programmes)
    websocket_api.async_register_command(hass, websocket_get_reminder_profiles)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "programme_tnt_fr/programmes",
        vol.Required("channels"): [str],
        vol.Optional("date"): str,
    }
)
@callback
def websocket_get_programmes(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    channels = msg["channels"]
    date_str = msg.get("date")
    programmes: dict[str, list[dict]] = {}
    for coordinator in hass.data.get(DOMAIN, {}).values():
        get_day = getattr(coordinator, "get_programmes_for_day", None)
        if get_day is None:
            continue
        for channel_id in channels:
            if channel_id in programmes:
                continue
            day_progs = get_day(channel_id, date_str)
            if day_progs is not None:
                programmes[channel_id] = day_progs
    connection.send_result(msg["id"], {"programmes": programmes})


@websocket_api.websocket_command({vol.Required("type"): "programme_tnt_fr/reminder_profiles"})
@callback
def websocket_get_reminder_profiles(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    names: list[str] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        for profile in entry.options.get(CONF_REMINDER_PROFILES, []):
            name = profile.get("name")
            if name and name not in names:
                names.append(name)
    connection.send_result(msg["id"], {"profiles": names})
