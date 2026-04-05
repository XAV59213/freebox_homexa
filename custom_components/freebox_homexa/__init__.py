"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K)."""
import logging
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
import aiohttp
import homeassistant.helpers.device_registry as dr
from .const import DOMAIN, PLATFORMS, SERVICE_REBOOT
from .router import FreeboxRouter, get_api

SCAN_INTERVAL = timedelta(seconds=40)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"
PLAYER_PATH_TEMPLATE = "http://{host}/pub/remote_control?code={remote_code}&key={key}"

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Freebox Homexa from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load() or {}
    hass.data[DOMAIN]["config"] = stored_data
    hass.data[DOMAIN]["store"] = store

    async def save_data():
        await store.async_save(hass.data[DOMAIN]["config"])

    api = await get_api(hass, entry.data[CONF_HOST])
    try:
        await api.open(entry.data[CONF_HOST], entry.data.get("port", 80))
    except HttpRequestError as err:
        _LOGGER.error(f"Erreur de connexion à la Freebox: {err}")
        raise ConfigEntryNotReady from err

    freebox_config = await api.system.get_config()

    # === CRÉATION ROBUSTE DU DEVICE PARENT (HUB) ===
    device_registry = dr.async_get(hass)
    hub_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, freebox_config["mac"])},
        connections={(dr.CONNECTION_NETWORK_MAC, freebox_config["mac"])},
        manufacturer="Freebox SAS",
        name="Freebox Server",
        model=freebox_config["model_info"]["pretty_name"],
        sw_version=freebox_config["firmware_version"],
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    hass.data[DOMAIN]["hub_device_info"] = hub_device
    # ===============================================

    router = FreeboxRouter(hass, entry, api, freebox_config)
    await router.update_all()

    entry.async_on_unload(
        async_track_time_interval(hass, router.update_all, SCAN_INTERVAL)
    )
    hass.data[DOMAIN][entry.unique_id] = router

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Services existants (reboot, remote, etc.)
    # ... (le reste du code reste identique à ta version actuelle)

    _LOGGER.info("L'intégration Freebox Homexa a été configurée avec succès.")
    return True
