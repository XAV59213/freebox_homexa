"""Programme TNT FR support inside Freebox Homexa (data only, no card rewrite)."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .tnt_const import DEFAULT_CHANNELS, DOMAIN as TNT_DOMAIN
from .tnt_coordinator import ProgrammeTntFrCoordinator
from .tnt_ws import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)

_WS_KEY = "freebox_homexa_tnt_ws"


async def async_setup_bundled_tnt(hass: HomeAssistant) -> ProgrammeTntFrCoordinator | None:
    """Set up TNT data under Homexa namespace. Do not touch other integrations' cards."""
    if hass.config_entries.async_entries(TNT_DOMAIN):
        _LOGGER.info("Programme TNT FR est déjà installé, bundle Homexa ignoré")
        return None

    if not hass.data.get(_WS_KEY):
        async_register_websocket_api(hass)
        hass.data[_WS_KEY] = True

    coordinator = ProgrammeTntFrCoordinator(hass, DEFAULT_CHANNELS)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Guide TNT XMLTV indisponible pour le moment : %s", err)

    # Keep under freebox_homexa namespace, not programme_tnt_fr domain
    hass.data.setdefault("freebox_homexa", {})["tnt"] = coordinator
    return coordinator
