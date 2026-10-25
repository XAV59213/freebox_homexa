"""Programme TNT FR support inside Freebox Homexa (data only, no card rewrite).

Adapted from cyclope205/programme-tnt-fr (MIT).
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .tnt_const import CONF_TMDB_API_KEY, selected_channels
from .tnt_coordinator import ProgrammeTntFrCoordinator
from .tnt_ws import async_register_homexa_websocket_api

_LOGGER = logging.getLogger(__name__)

_HOMEXA_WS_KEY = "freebox_homexa_tnt_homexa_ws"
# hass.data[freebox_homexa][TNT_COORDINATORS_KEY][entry_id] -> coordinator
TNT_COORDINATORS_KEY = "tnt_coordinators"


async def async_setup_bundled_tnt(
    hass: HomeAssistant, entry: ConfigEntry
) -> ProgrammeTntFrCoordinator | None:
    """Crée le coordinateur TNT de cette entrée selon les chaînes choisies dans les options."""
    if not hass.data.get(_HOMEXA_WS_KEY):
        async_register_homexa_websocket_api(hass)
        hass.data[_HOMEXA_WS_KEY] = True

    channels = selected_channels(entry.options)
    tmdb_api_key = (entry.options.get(CONF_TMDB_API_KEY) or "").strip() or None
    coordinator = ProgrammeTntFrCoordinator(hass, channels, tmdb_api_key)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Guide TNT XMLTV indisponible pour le moment : %s", err)

    hass.data.setdefault("freebox_homexa", {}).setdefault(TNT_COORDINATORS_KEY, {})[
        entry.entry_id
    ] = coordinator
    return coordinator


def async_unload_bundled_tnt(hass: HomeAssistant, entry: ConfigEntry) -> None:
    hass.data.get("freebox_homexa", {}).get(TNT_COORDINATORS_KEY, {}).pop(
        entry.entry_id, None
    )
