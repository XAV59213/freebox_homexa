"""Support pour l'intégration Freebox Homexa."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, PLATFORMS
from .router import FreeboxRouter, get_api

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=120)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configuration de l'entrée Freebox Homexa."""
    hass.data.setdefault(DOMAIN, {})

    try:
        port = entry.data.get("port", 80)
        api = await get_api(hass, entry.data["host"], port)

        router = FreeboxRouter(hass, entry, api)
        await router.async_update()

        # Mise à jour périodique
        entry.async_on_unload(
            async_track_time_interval(hass, router.async_update, SCAN_INTERVAL)
        )

        hass.data[DOMAIN][entry.entry_id] = router

        # Chargement des plateformes
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        _LOGGER.info("Freebox Homexa configurée avec succès pour %s", entry.data["host"])
        return True

    except Exception as err:
        _LOGGER.error("Erreur lors de la configuration de Freebox Homexa : %s", err)
        raise ConfigEntryNotReady from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Déchargement de l'entrée."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
