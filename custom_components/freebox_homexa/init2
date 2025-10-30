"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K)."""
# DESCRIPTION: Fichier d'initialisation principal pour l'intégration Freebox dans Home Assistant
# OBJECTIF: Configurer l'intégration Freebox, gérer les mises à jour périodiques, les services et la fermeture propre

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
import homeassistant.helpers.device_registry as dr  # Ajout pour le registre des devices

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
    """Set up Freebox Homexa from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load()
    if stored_data is None:
        _LOGGER.info("Aucune configuration Freebox existante trouvée. Création d'une nouvelle configuration.")
        stored_data = {}

    hass.data[DOMAIN]["config"] = stored_data
    hass.data[DOMAIN]["store"] = store

    async def save_data():
        """Sauvegarde les données de configuration avant l'arrêt de Home Assistant."""
        _LOGGER.debug("Sauvegarde des données de configuration Freebox en cours...")
        await store.async_save(hass.data[DOMAIN]["config"])
        _LOGGER.info("Données de configuration Freebox sauvegardées avec succès.")

    api = await get_api(hass, entry.data[CONF_HOST])
    try:
        await api.open(entry.data[CONF_HOST], entry.data.get("port", 80))
        _LOGGER.debug(f"Connexion établie avec la Freebox à {entry.data[CONF_HOST]}.")
    except HttpRequestError as err:
        _LOGGER.error(f"Erreur lors de la connexion à la Freebox {entry.data[CONF_HOST]}: {err}")
        raise ConfigEntryNotReady from err

    freebox_config = await api.system.get_config()

    # Création explicite du device parent (hub Freebox) pour éviter l'erreur via_device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, freebox_config["mac"])},
        connections={(dr.CONNECTION_NETWORK_MAC, freebox_config["mac"])},
        manufacturer="Freebox SAS",
        name="Freebox Server",
        model=freebox_config["model_info"]["pretty_name"],
        sw_version=freebox_config["firmware_version"],
    )

    router = FreeboxRouter(hass, entry, api, freebox_config)
    await router.update_all()

    entry.async_on_unload(
        async_track_time_interval(hass, router.update_all, SCAN_INTERVAL)
    )

    hass.data[DOMAIN][entry.unique_id] = router
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_reboot(call: ServiceCall) -> None:
        """Gère le service de redémarrage de la Freebox."""
        _LOGGER.warning(
            "Le service 'freebox.reboot' est déprécié et remplacé par une entité bouton dédiée ; "
            "veuillez utiliser cette entité pour redémarrer la Freebox."
        )
        await router.reboot()
        await save_data()
        _LOGGER.info("Redémarrage de la Freebox effectué avec succès.")

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, async_reboot)

    async def async_close_connection(event: Event) -> None:
        """Ferme la connexion à la Freebox lors de l'arrêt de Home Assistant."""
        _LOGGER.debug("Fermeture de la connexion à la Freebox en cours...")
        await router.close()
        await save_data()
        _LOGGER.info("Connexion Freebox fermée proprement.")

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    async def async_freebox_player_remote(call: ServiceCall) -> None:
        """Gère le contrôle à distance du Freebox Player."""
        code_list = call.data.get("code", "")
        if not code_list:
            _LOGGER.warning("Aucun code fourni pour la télécommande du Freebox Player.")
            return

        async with aiohttp.ClientSession() as session:
            for code in code_list.split(','):
                url = PLAYER_PATH_TEMPLATE.format(
                    host=entry.data[CONF_HOST],
                    remote_code=entry.data["remote_code"],
                    key=code.strip()
                )
                try:
                    async with session.get(url, ssl=False) as response:
                        if response.status != 200:
                            _LOGGER.error(f"Échec de l'envoi de la commande '{code}' : HTTP {response.status}")
                        else:
                            _LOGGER.debug(f"Commande '{code}' envoyée avec succès au Freebox Player.")
                except aiohttp.ClientError as err:
                    _LOGGER.error(f"Erreur lors de l'envoi de la commande '{code}' : {err}")

    hass.services.async_register(DOMAIN, "remote", async_freebox_player_remote)
    _LOGGER.info("L'intégration Freebox a été configurée avec succès.")
    return True
