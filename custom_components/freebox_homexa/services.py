"""Services de l'intégration, enregistrés une seule fois (async_setup).

Chaque appel retrouve l'entrée chargée concernée : `config_entry_id` ou `device_id`
(facultatifs) s'ils sont fournis, sinon l'unique entrée chargée.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, SERVICE_REBOOT, SERVICE_RELOAD, SERVICE_REMOTE, option_remote_code

_LOGGER = logging.getLogger(__name__)

PLAYER_PATH_TEMPLATE = "http://{host}/pub/remote_control?code={remote_code}&key={key}"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DEVICE_ID = "device_id"


def _loaded_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and getattr(entry, "runtime_data", None) is not None
    ]


def _entry_ids_from_call(hass: HomeAssistant, call: ServiceCall) -> set[str]:
    """Entrées visées explicitement par l'appel (config_entry_id / device_id)."""
    wanted: set[str] = set()
    for key in (ATTR_CONFIG_ENTRY_ID, ATTR_DEVICE_ID):
        value = call.data.get(key)
        values = value if isinstance(value, (list, tuple, set)) else [value] if value else []
        for item in values:
            if key == ATTR_CONFIG_ENTRY_ID:
                wanted.add(str(item))
                continue
            device = dr.async_get(hass).async_get(str(item))
            if device is None:
                continue
            entry_id = getattr(device, "config_entry_id", None)
            if entry_id:
                wanted.add(entry_id)
            else:  # anciennes versions de Home Assistant
                wanted.update(getattr(device, "config_entries", None) or ())
    return wanted


def async_resolve_entries(
    hass: HomeAssistant, call: ServiceCall, *, allow_many: bool = False
) -> list[ConfigEntry]:
    """Entrées chargées visées par l'appel ; erreur traduite si aucune / ambiguë."""
    loaded = _loaded_entries(hass)
    if not loaded:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_loaded_entry",
            translation_placeholders={"service": call.service},
        )
    wanted = _entry_ids_from_call(hass, call)
    if wanted:
        entries = [entry for entry in loaded if entry.entry_id in wanted]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"service": call.service},
            )
        return entries
    if len(loaded) > 1 and not allow_many:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="multiple_entries",
            translation_placeholders={"service": call.service},
        )
    return loaded


def _router(hass: HomeAssistant, entry: ConfigEntry) -> Any:
    return entry.runtime_data


async def _save_config(hass: HomeAssistant) -> None:
    data = hass.data.get(DOMAIN, {})
    store = data.get("store")
    if store is not None and "config" in data:
        await store.async_save(data["config"])


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Enregistre les services reboot / reload / remote (une seule fois)."""

    async def async_reboot(call: ServiceCall) -> None:
        for entry in async_resolve_entries(hass, call):
            await _router(hass, entry).reboot()
        await _save_config(hass)

    async def async_reload_config(call: ServiceCall) -> None:
        # Recharge aussi une entrée en échec (ex. en attente d'autorisation) : c'est
        # justement à cela que sert « reload ». Sans cible : toutes les entrées actives.
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.disabled_by is None
        ]
        wanted = _entry_ids_from_call(hass, call)
        if wanted:
            entries = [entry for entry in entries if entry.entry_id in wanted]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded" if wanted else "no_loaded_entry",
                translation_placeholders={"service": call.service},
            )
        for entry in entries:
            await hass.config_entries.async_reload(entry.entry_id)

    async def async_freebox_player_remote(call: ServiceCall) -> None:
        code_list = call.data.get("code", "")
        if not code_list:
            return
        for entry in async_resolve_entries(hass, call):
            remote_code = option_remote_code(entry)
            if not remote_code:
                _LOGGER.warning(
                    "Code télécommande Player manquant. "
                    "Paramètres → Homexa → Configurer, ou Player : Réglages → Système → Informations."
                )
                continue
            # Session aiohttp partagée de Home Assistant (pas de session créée / fermée ici).
            session = async_get_clientsession(hass)
            for code in str(code_list).split(","):
                url = PLAYER_PATH_TEMPLATE.format(
                    host=entry.data[CONF_HOST],
                    remote_code=remote_code,
                    key=code.strip(),
                )
                try:
                    async with session.get(url, ssl=False) as response:
                        if response.status != 200:
                            _LOGGER.error("Remote %s HTTP %s", code, response.status)
                except aiohttp.ClientError as err:
                    _LOGGER.error("Remote %s : %s", code, err)

    for service, handler in (
        (SERVICE_REBOOT, async_reboot),
        (SERVICE_RELOAD, async_reload_config),
        (SERVICE_REMOTE, async_freebox_player_remote),
    ):
        if not hass.services.has_service(DOMAIN, service):
            hass.services.async_register(DOMAIN, service, handler)
