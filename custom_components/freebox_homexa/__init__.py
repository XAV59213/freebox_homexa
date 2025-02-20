"""Support for Freebox devices (Freebox v6 and Freebox mini 4K)."""

from datetime import timedelta
import logging
import os

from freebox_api.exceptions import HttpRequestError, AuthorizationError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, PLATFORMS, SERVICE_REBOOT, SCAN_INTERVAL
from .router import FreeboxRouter, get_api

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Freebox entry in Home Assistant."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    # Initialize Freebox API
    api = await get_api(hass, host)
    try:
        # Check if token exists and is valid
        token_file = api.token_file
        if not os.path.exists(token_file):
            _LOGGER.error("No token file found at %s. Re-authentication required.", token_file)
            raise ConfigEntryNotReady("Missing authentication token. Please reconfigure the integration.")
        
        await api.open(host, port)
    except AuthorizationError as err:
        _LOGGER.error("Authorization timed out for %s:%s - %s", host, port, err)
        raise ConfigEntryNotReady("Authorization timed out. Please re-authenticate via the config flow.") from err
    except HttpRequestError as err:
        _LOGGER.error("Failed to connect to Freebox at %s:%s - %s", host, port, err)
        raise ConfigEntryNotReady(f"Connection failed: {err}") from err

    # Fetch Freebox configuration
    try:
        freebox_config = await api.system.get_config()
    except HttpRequestError as err:
        await api.close()
        _LOGGER.error("Failed to fetch Freebox config from %s:%s - %s", host, port, err)
        raise ConfigEntryNotReady(f"Config fetch failed: {err}") from err

    # Set up router and update data
    router = FreeboxRouter(hass, entry, api, freebox_config)
    try:
        await router.update_all()
    except Exception as err:
        await router.close()
        _LOGGER.error("Initial update failed for %s:%s - %s", host, port, err)
        raise ConfigEntryNotReady(f"Initial update failed: {err}") from err

    # Periodic updates
    entry.async_on_unload(
        async_track_time_interval(hass, router.update_all, SCAN_INTERVAL)
    )

    # Store router instance
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.unique_id] = router

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register reboot service (deprecated)
    async def async_reboot(call: ServiceCall) -> None:
        """Handle the reboot service call (deprecated)."""
        _LOGGER.warning(
            "The 'freebox.reboot' service is deprecated; use the reboot button entity instead."
        )
        await router.reboot()

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, async_reboot)

    async def async_close_connection(event: Event) -> None:
        """Close the Freebox connection when Home Assistant stops."""
        try:
            await router.close()
        except Exception as err:
            _LOGGER.warning("Error closing connection for %s:%s - %s", host, port, err)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    _LOGGER.info("Successfully set up Freebox integration for %s:%s", host, port)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Freebox config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        router: FreeboxRouter = hass.data[DOMAIN].pop(entry.unique_id)
        try:
            await router.close()
        except Exception as err:
            _LOGGER.warning("Error closing connection during unload for %s:%s - %s", host, port, err)
        hass.services.async_remove(DOMAIN, SERVICE_REBOOT)
        _LOGGER.info("Successfully unloaded Freebox integration for %s:%s", host, port)

    return unload_ok
