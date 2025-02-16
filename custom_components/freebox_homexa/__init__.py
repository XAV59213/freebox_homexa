"""Support for Freebox devices (Freebox v6 and Freebox mini 4K)."""

from datetime import timedelta
import logging
from functools import partial
from freebox_api.exceptions import HttpRequestError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DOMAIN, PLATFORMS, SERVICE_REBOOT
from .router import FreeboxRouter, get_api

SCAN_INTERVAL = timedelta(seconds=40)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Freebox entry."""
    
    hass.data.setdefault(DOMAIN, {})

    # Initialiser le stockage persistant
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load()

    if stored_data is None:
        _LOGGER.info("No existing Freebox_HomeXa configuration found. Creating a new one.")
        stored_data = {}

    hass.data[DOMAIN]["config"] = stored_data
    hass.data[DOMAIN]["store"] = store

    # Connexion à l'API Freebox
    api = await get_api(hass, entry.data[CONF_HOST])
    try:
        await api.open(entry.data[CONF_HOST], entry.data[CONF_PORT])
    except HttpRequestError as err:
        raise ConfigEntryNotReady from err

    freebox_config = await api.system.get_config()

    router = FreeboxRouter(hass, entry, api, freebox_config)
    await router.update_all()
    entry.async_on_unload(
        async_track_time_interval(hass, router.update_all, SCAN_INTERVAL)
    )

    hass.data[DOMAIN][entry.unique_id] = router

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Services
    async def async_reboot(call: ServiceCall) -> None:
        """Handle reboot service call."""
        _LOGGER.warning(
            "The 'freebox.reboot' service is deprecated and "
            "replaced by a dedicated reboot button entity; please "
            "use that entity to reboot the Freebox instead"
        )
        await router.reboot()

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, async_reboot)

    async def async_close_connection(event: Event) -> None:
        """Close Freebox connection on HA Stop."""
        await router.close()
        await save_data()

    async def save_data():
        """Sauvegarde des données de configuration avant l'arrêt."""
        _LOGGER.info("Saving Freebox_HomeXa configuration data...")
        await store.async_save(hass.data[DOMAIN]["config"])

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        router: FreeboxRouter = hass.data[DOMAIN].pop(entry.unique_id)
        await router.close()
        hass.services.async_remove(DOMAIN, SERVICE_REBOOT)

        # Sauvegarde des données avant de supprimer l'intégration
        if DOMAIN in hass.data and "store" in hass.data[DOMAIN]:
            await hass.data[DOMAIN]["store"].async_save(hass.data[DOMAIN]["config"])

    return unload_ok
