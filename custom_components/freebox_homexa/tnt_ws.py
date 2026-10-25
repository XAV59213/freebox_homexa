"""WebSocket API du guide TNT (adapted from cyclope205/programme-tnt-fr, MIT).

Seules les commandes de l'espace de noms freebox_homexa (freebox_homexa/tnt_*)
sont enregistrées ; elles sont utilisées par la carte homexa-tnt-card.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .tnt_const import CHANNEL_ORDER, CONF_REMINDER_PROFILES, TNT_CARD_VERSION

HOMEXA_DOMAIN = "freebox_homexa"


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
