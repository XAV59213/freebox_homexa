import logging
import requests
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from freebox_api.exceptions import HttpRequestError

from .const import DOMAIN, PLATFORMS, SERVICE_REBOOT
from .router import FreeboxRouter, get_api

SCAN_INTERVAL = timedelta(seconds=40)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"

PLAYER_PATH_TEMPLATE = "http://{host}/pub/remote_control?code={remote_code}&key={key}"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required("remote_code"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

REMOTE_SCHEMA = vol.Schema(
    {
        vol.Optional("code"): cv.string
    }
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Freebox entry."""
    
    hass.data.setdefault(DOMAIN, {})

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load()
    if stored_data is None:
        _LOGGER.info("No existing Freebox_HomeXa configuration found. Creating a new one.")
        stored_data = {}
    
    hass.data[DOMAIN]["config"] = stored_data
    hass.data[DOMAIN]["store"] = store

    async def save_data():
        """Sauvegarde des données de configuration avant l'arrêt."""
        _LOGGER.info("Saving Freebox_HomeXa configuration data...")
        await store.async_save(hass.data[DOMAIN]["config"])
    
    api = await get_api(hass, entry.data[CONF_HOST])
    try:
        await api.open(entry.data[CONF_HOST], entry.data.get("port", 80))
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

    async def async_reboot(call: ServiceCall) -> None:
        """Handle reboot service call."""
        _LOGGER.warning(
            "The 'freebox.reboot' service is deprecated and "
            "replaced by a dedicated reboot button entity; please "
            "use that entity to reboot the Freebox instead"
        )
        await router.reboot()
        await save_data()

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, async_reboot)

    async def async_close_connection(event: Event) -> None:
        """Close Freebox connection on HA Stop."""
        await router.close()
        await save_data()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    async def async_freebox_player_remote(call):
        """Handle Freebox Player remote control."""
        code_list = call.data.get("code", "")
        if not code_list:
            _LOGGER.warning("No code provided for Freebox Player remote control.")
            return

        for code in code_list.split(','):
            url = PLAYER_PATH_TEMPLATE.format(host=entry.data[CONF_HOST], remote_code=entry.data["remote_code"], key=code.strip())
            try:
                response = await hass.async_add_executor_job(requests.get, url, {'verify': False})
                if response.status_code != 200:
                    _LOGGER.error("Failed to send command %s: HTTP %s", code, response.status_code)
            except requests.RequestException as err:
                _LOGGER.error("Error sending command %s: %s", code, err)

    hass.services.async_register(DOMAIN, "remote", async_freebox_player_remote)
    _LOGGER.info("Freebox Player component has been set up successfully.")
    return True
