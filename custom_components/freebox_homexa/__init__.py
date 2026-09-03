"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K)."""

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from freebox_api.exceptions import AuthorizationError, HttpRequestError
import aiohttp
import homeassistant.helpers.device_registry as dr

from .const import DOMAIN, PLATFORMS, SERVICE_REBOOT, SERVICE_RELOAD, SERVICE_REMOTE
from .router import FreeboxRouter, get_api
from .tnt_setup import async_setup_bundled_tnt

SCAN_INTERVAL = timedelta(seconds=40)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"
PLAYER_PATH_TEMPLATE = "http://{host}/pub/remote_control?code={remote_code}&key={key}"
_RESERVED_DATA_KEYS = {"config", "store", "tnt_coordinator"}

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

_LOGGER = logging.getLogger(__name__)


def _router_keys(hass: HomeAssistant) -> list[str]:
    return [key for key in hass.data.get(DOMAIN, {}) if key not in _RESERVED_DATA_KEYS]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load()
    if stored_data is None:
        _LOGGER.info("Aucune configuration Freebox stockée, démarrage avec un cache vide")
        stored_data = {}

    hass.data[DOMAIN]["config"] = stored_data
    hass.data[DOMAIN]["store"] = store

    async def save_data():
        await store.async_save(hass.data[DOMAIN]["config"])

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, 80)
    api = await get_api(hass, host)

    try:
        await api.open(host, port)
        _LOGGER.debug("Connexion Freebox établie %s:%s", host, port)
    except AuthorizationError as err:
        message = str(err).lower()
        if "timed out" in message:
            _LOGGER.warning("Autorisation Freebox en attente pour %s : %s", host, err)
            raise ConfigEntryNotReady(
                "En attente de la flèche droite sur la Freebox (token déjà enregistré conservé)"
            ) from err
        _LOGGER.error("Autorisation Freebox refusée pour %s: %s", host, err)
        raise ConfigEntryAuthFailed(
            "Autorisation Freebox refusée ou révoquée. Réautorise depuis Freebox OS."
        ) from err
    except HttpRequestError as err:
        _LOGGER.error("Erreur réseau Freebox %s: %s", host, err)
        raise ConfigEntryNotReady from err

    freebox_config = await api.system.get_config()

    device_registry = dr.async_get(hass)
    parent_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, freebox_config["mac"])},
        connections={(dr.CONNECTION_NETWORK_MAC, freebox_config["mac"])},
        manufacturer="Freebox SAS",
        name="Freebox Server",
        model=freebox_config["model_info"]["pretty_name"],
        sw_version=freebox_config["firmware_version"],
    )

    router = FreeboxRouter(hass, entry, api, freebox_config)
    router.device_id = parent_device.id
    await router.update_all()

    entry.async_on_unload(async_track_time_interval(hass, router.update_all, SCAN_INTERVAL))

    hass.data[DOMAIN][entry.unique_id] = router
    try:
        hass.data[DOMAIN]["tnt_coordinator"] = await async_setup_bundled_tnt(hass)
    except Exception:
        _LOGGER.exception("Guide TNT embarqué indisponible")
        hass.data[DOMAIN]["tnt_coordinator"] = None

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_reboot(call: ServiceCall) -> None:
        await router.reboot()
        await save_data()

    async def async_reload_config(call: ServiceCall) -> None:
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_close_connection(event: Event) -> None:
        await router.close()
        await save_data()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    async def async_freebox_player_remote(call: ServiceCall) -> None:
        code_list = call.data.get("code", "")
        if not code_list:
            return
        async with aiohttp.ClientSession() as session:
            for code in code_list.split(","):
                url = PLAYER_PATH_TEMPLATE.format(
                    host=entry.data[CONF_HOST],
                    remote_code=entry.data["remote_code"],
                    key=code.strip(),
                )
                try:
                    async with session.get(url, ssl=False) as response:
                        if response.status != 200:
                            _LOGGER.error("Remote %s HTTP %s", code, response.status)
                except aiohttp.ClientError as err:
                    _LOGGER.error("Remote %s : %s", code, err)

    if not hass.services.has_service(DOMAIN, SERVICE_REBOOT):
        hass.services.async_register(DOMAIN, SERVICE_REBOOT, async_reboot)
    if not hass.services.has_service(DOMAIN, SERVICE_RELOAD):
        hass.services.async_register(DOMAIN, SERVICE_RELOAD, async_reload_config)
    if not hass.services.has_service(DOMAIN, SERVICE_REMOTE):
        hass.services.async_register(DOMAIN, SERVICE_REMOTE, async_freebox_player_remote)

    _LOGGER.info("Freebox Homexa prêt")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    router = hass.data[DOMAIN].pop(entry.unique_id, None)
    if router is not None:
        await router.close()
    store = hass.data[DOMAIN].get("store")
    if store is not None and "config" in hass.data[DOMAIN]:
        await store.async_save(hass.data[DOMAIN]["config"])
    if not _router_keys(hass):
        for service in (SERVICE_REBOOT, SERVICE_RELOAD, SERVICE_REMOTE):
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
