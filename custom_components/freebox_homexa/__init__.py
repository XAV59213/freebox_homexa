"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K)."""
# DESCRIPTION: Fichier d'initialisation principal pour l'intégration Freebox dans Home Assistant
# OBJECTIF: Configurer l'intégration Freebox, gérer les mises à jour périodiques, les services et la fermeture propre

from pathlib import Path
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
from homeassistant.util import slugify
from freebox_api.exceptions import AuthorizationError, HttpRequestError
import aiohttp
import homeassistant.helpers.device_registry as dr

from .const import DOMAIN, PLATFORMS, SERVICE_REBOOT, SERVICE_RELOAD, SERVICE_REMOTE
from .router import FreeboxRouter, get_api

SCAN_INTERVAL = timedelta(seconds=40)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"
PLAYER_PATH_TEMPLATE = "http://{host}/pub/remote_control?code={remote_code}&key={key}"
_RESERVED_DATA_KEYS = {"config", "store"}

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


def _router_keys(hass: HomeAssistant) -> list[str]:
    """Return stored router keys for this domain."""
    return [key for key in hass.data.get(DOMAIN, {}) if key not in _RESERVED_DATA_KEYS]


def token_file_path(hass: HomeAssistant, host: str) -> Path:
    """Return the on-disk Freebox token path used by freebox_api."""
    return Path(hass.config.path(".storage", "freebox_homexa")) / f"{slugify(host)}.conf"


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

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, 80)

    if not token_file_path(hass, host).exists():
        raise ConfigEntryAuthFailed(
            "Token Freebox introuvable. Rouvre l'intégration et appuie sur la flèche droite de la Freebox."
        )

    api = await get_api(hass, host)

    try:
        await api.open(host, port)
        _LOGGER.debug("Connexion établie avec la Freebox à %s (port=%s)", host, port)
    except AuthorizationError as err:
        _LOGGER.error("Autorisation Freebox refusée ou expirée pour %s: %s", host, err)
        raise ConfigEntryAuthFailed(
            "Autorisation Freebox expirée. Appuie sur la flèche droite du Server pour réautoriser Home Assistant."
        ) from err
    except HttpRequestError as err:
        _LOGGER.error("Erreur lors de la connexion à la Freebox %s: %s", host, err)
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

    async def async_reload_config(call: ServiceCall) -> None:
        """Recharge la configuration et redécouvre les appareils Freebox Home."""
        _LOGGER.info("Rechargement de la configuration Freebox Homexa demandé.")
        await hass.config_entries.async_reload(entry.entry_id)

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
            for code in code_list.split(","):
                url = PLAYER_PATH_TEMPLATE.format(
                    host=entry.data[CONF_HOST],
                    remote_code=entry.data["remote_code"],
                    key=code.strip(),
                )
                try:
                    async with session.get(url, ssl=False) as response:
                        if response.status != 200:
                            _LOGGER.error(
                                "Échec de l'envoi de la commande '%s' : HTTP %s",
                                code,
                                response.status,
                            )
                        else:
                            _LOGGER.debug(
                                "Commande '%s' envoyée avec succès au Freebox Player.",
                                code,
                            )
                except aiohttp.ClientError as err:
                    _LOGGER.error("Erreur lors de l'envoi de la commande '%s' : %s", code, err)

    if not hass.services.has_service(DOMAIN, SERVICE_REBOOT):
        hass.services.async_register(DOMAIN, SERVICE_REBOOT, async_reboot)
    if not hass.services.has_service(DOMAIN, SERVICE_RELOAD):
        hass.services.async_register(DOMAIN, SERVICE_RELOAD, async_reload_config)
    if not hass.services.has_service(DOMAIN, SERVICE_REMOTE):
        hass.services.async_register(DOMAIN, SERVICE_REMOTE, async_freebox_player_remote)

    _LOGGER.info("L'intégration Freebox a été configurée avec succès.")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and enable the HA Reload button."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        _LOGGER.error("Impossible de décharger les plateformes Freebox Homexa")
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

    _LOGGER.info("Entrée Freebox Homexa déchargée, prête à être rechargée")
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry after options or manual reload."""
    await hass.config_entries.async_reload(entry.entry_id)
