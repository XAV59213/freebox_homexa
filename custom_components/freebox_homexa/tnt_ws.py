"""WebSocket API du guide TNT (adapted from cyclope205/programme-tnt-fr, MIT).

Seules les commandes de l'espace de noms freebox_homexa (freebox_homexa/tnt_*)
sont enregistrées ; elles sont utilisées par la carte homexa-tnt-card.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import websocket_command
from homeassistant.core import HomeAssistant, callback

from .tnt_coordinator import ProgrammeTntFrCoordinator
from .tnt_const import CHANNEL_ORDER, CONF_REMINDER_PROFILES, TNT_CARD_VERSION

HOMEXA_DOMAIN = "freebox_homexa"


def _homexa_coordinators(hass: HomeAssistant) -> list[ProgrammeTntFrCoordinator]:
    return [
        coordinator
        for coordinator in hass.data.get(HOMEXA_DOMAIN, {}).get("tnt_coordinators", {}).values()
        if isinstance(coordinator, ProgrammeTntFrCoordinator)
    ]


@callback
def async_register_homexa_websocket_api(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_homexa_programmes)
    websocket_api.async_register_command(hass, websocket_homexa_reminder_profiles)
    websocket_api.async_register_command(hass, websocket_homexa_version)


@websocket_command(
    {
        "type": "freebox_homexa/tnt_programmes",
        "channels": [str],
        "date": str,
    }
)
@callback
def websocket_homexa_programmes(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, object]
) -> None:
    message_id = _message_id(msg)
    channels = msg.get("channels")
    date = msg.get("date")
    # Plain keys support both public HA validator engines. Required payload
    # checks stay inside ActiveConnection's invalid_format exception boundary.
    if not isinstance(channels, list) or not all(isinstance(c, str) for c in channels):
        raise vol.Invalid("Expected channel list", path=["channels"])
    if date is not None and not isinstance(date, str):
        raise vol.Invalid("Expected date string", path=["date"])
    programmes: dict[str, list[dict[str, object]]] = {}
    for coordinator in _homexa_coordinators(hass):
        for channel_id in channels:
            if channel_id in programmes:
                continue
            day_progs = coordinator.get_programmes_for_day(channel_id, date)
            if day_progs is not None:
                programmes[channel_id] = day_progs
    connection.send_result(message_id, {"programmes": programmes})


@websocket_command({"type": "freebox_homexa/tnt_reminder_profiles"})
@callback
def websocket_homexa_reminder_profiles(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, object]
) -> None:
    message_id = _message_id(msg)
    names: list[str] = []
    for entry in hass.config_entries.async_entries(HOMEXA_DOMAIN):
        for profile in entry.options.get(CONF_REMINDER_PROFILES, []):
            name = profile.get("name") if isinstance(profile, dict) else None
            if isinstance(name, str) and name and name not in names:
                names.append(name)
    connection.send_result(message_id, {"profiles": names})


@websocket_command({"type": "freebox_homexa/tnt_version"})
@callback
def websocket_homexa_version(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, object]
) -> None:
    connection.send_result(
        _message_id(msg), {"version": TNT_CARD_VERSION, "channel_order": CHANNEL_ORDER}
    )


def _message_id(msg: dict[str, object]) -> int:
    """Narrow the public envelope, including direct handler calls."""
    message_id = msg["id"]
    if not isinstance(message_id, int):
        raise vol.Invalid("Invalid message id", path=["id"])
    return message_id
