"""WebSocket API du guide TNT (adapted from cyclope205/programme-tnt-fr, MIT).

- programme_tnt_fr/* : compatibilité, seulement si l'intégration séparée est absente.
- freebox_homexa/tnt_* : utilisées par la carte homexa-tnt-card, toujours enregistrées.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .tnt_const import (
    CHANNEL_ORDER,
    CONF_REMINDER_PROFILES,
    DOMAIN,
    TNT_CARD_VERSION,
)

HOMEXA_DOMAIN = "freebox_homexa"


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
    sources = list(hass.data.get(DOMAIN, {}).values())
    sources.extend(
        hass.data.get("freebox_homexa", {}).get("tnt_coordinators", {}).values()
    )
    for coordinator in sources:
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
    entries = [
        *hass.config_entries.async_entries("freebox_homexa"),
        *hass.config_entries.async_entries(DOMAIN),
    ]
    for entry in entries:
        for profile in entry.options.get(CONF_REMINDER_PROFILES, []):
            name = profile.get("name")
            if name and name not in names:
                names.append(name)
    connection.send_result(msg["id"], {"profiles": names})


# --- Commandes propres à Homexa, pour la carte homexa-tnt-card ---


def _homexa_coordinators(hass: HomeAssistant) -> list:
    return list(hass.data.get(HOMEXA_DOMAIN, {}).get("tnt_coordinators", {}).values())


@callback
def async_register_homexa_websocket_api(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_homexa_programmes)
    websocket_api.async_register_command(hass, websocket_homexa_reminder_profiles)
    websocket_api.async_register_command(hass, websocket_homexa_version)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "freebox_homexa/tnt_programmes",
        vol.Required("channels"): [str],
        vol.Optional("date"): str,
    }
)
@callback
def websocket_homexa_programmes(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    programmes: dict[str, list[dict]] = {}
    for coordinator in _homexa_coordinators(hass):
        for channel_id in msg["channels"]:
            if channel_id in programmes:
                continue
            day_progs = coordinator.get_programmes_for_day(channel_id, msg.get("date"))
            if day_progs is not None:
                programmes[channel_id] = day_progs
    connection.send_result(msg["id"], {"programmes": programmes})


@websocket_api.websocket_command({vol.Required("type"): "freebox_homexa/tnt_reminder_profiles"})
@callback
def websocket_homexa_reminder_profiles(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    names: list[str] = []
    for entry in hass.config_entries.async_entries(HOMEXA_DOMAIN):
        for profile in entry.options.get(CONF_REMINDER_PROFILES, []):
            name = profile.get("name")
            if name and name not in names:
                names.append(name)
    connection.send_result(msg["id"], {"profiles": names})


@websocket_api.websocket_command({vol.Required("type"): "freebox_homexa/tnt_version"})
@callback
def websocket_homexa_version(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    connection.send_result(
        msg["id"], {"version": TNT_CARD_VERSION, "channel_order": CHANNEL_ORDER}
    )
