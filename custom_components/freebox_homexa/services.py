"""Services de l'intégration, enregistrés une seule fois (async_setup).

Chaque appel retrouve l'entrée chargée concernée : `config_entry_id` ou `device_id`
(facultatifs) s'ils sont fournis, sinon l'unique entrée chargée.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, SERVICE_REBOOT, SERVICE_RELOAD, SERVICE_REMOTE
from .player_remote import (
    VALID_COMMANDS,
    async_send_player_keys,
    parse_keys,
    player_id_from_identifiers,
    resolve_remote_code,
)

_LOGGER = logging.getLogger(__name__)

ATTR_PLAYER_ID = "player_id"
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


def _player_id_from_call(hass: HomeAssistant, call: ServiceCall) -> int | None:
    """Player visé : `player_id`, sinon un `device_id` d'appareil Player Homexa."""
    raw = call.data.get(ATTR_PLAYER_ID)
    if raw not in (None, ""):
        try:
            return int(raw)
        except (TypeError, ValueError) as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="remote_invalid_player",
                translation_placeholders={"player": str(raw)},
            ) from err
    value = call.data.get(ATTR_DEVICE_ID)
    values = value if isinstance(value, (list, tuple, set)) else [value] if value else []
    for item in values:
        device = dr.async_get(hass).async_get(str(item))
        if device is not None:
            found = player_id_from_identifiers(getattr(device, "identifiers", None))
            if found is not None:
                return found
    return None


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
        """Touches de télécommande vers le Freebox Player (même chemin que l'entité).

        Cible facultative : `player_id`, ou `device_id` d'un appareil Player Homexa.
        """
        keys = parse_keys(call.data.get("code", ""))
        if not keys:
            return
        invalid = [key for key in keys if key not in VALID_COMMANDS]
        if invalid:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="remote_invalid_key",
                translation_placeholders={"key": ", ".join(invalid)},
            )
        player_id = _player_id_from_call(hass, call)
        for entry in async_resolve_entries(hass, call):
            router = _router(hass, entry)
            try:
                players = list(await router._api.player.get_players() or [])
            except Exception as err:  # noqa: BLE001 — liste facultative (code commun possible)
                _LOGGER.debug("Liste des Player indisponible : %s", err)
                players = []
            remote_code, target = resolve_remote_code(entry, player_id, players)
            if not remote_code:
                if player_id is None and not players:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="remote_no_player"
                    )
                if player_id is None and len(players) > 1:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="remote_multiple_players"
                    )
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="remote_code_missing",
                    translation_placeholders={
                        "player": str(target) if target is not None else "-"
                    },
                )
            failures = await async_send_player_keys(router, remote_code, keys)
            if failures:
                key, err = failures[0]
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="remote_failed",
                    translation_placeholders={"key": key, "error": str(err)},
                )

    for service, handler in (
        (SERVICE_REBOOT, async_reboot),
        (SERVICE_RELOAD, async_reload_config),
        (SERVICE_REMOTE, async_freebox_player_remote),
    ):
        if not hass.services.has_service(DOMAIN, service):
            hass.services.async_register(DOMAIN, service, handler)
