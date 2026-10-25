"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K)."""

import logging
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from datetime import datetime, timedelta
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from freebox_api.exceptions import AuthorizationError, HttpRequestError
import homeassistant.helpers.device_registry as dr

from .const import (
    CONF_CREATE_LAN_DEVICES,
    DEFAULT_CREATE_LAN_DEVICES,
    DOMAIN,
    PLATFORMS,
    option_enabled,
    option_home_poll_interval,
)
from .frontend import JSModuleRegistration
from .device_groups import (
    CONF_DEVICE_GROUP_OVERRIDES,
    async_detach_top_level_devices,
    async_remove_lan_client_devices,
    async_merge_repeater_devices,
    async_remove_merged_node_devices,
    async_remove_unused_group_devices,
    migrate_overrides,
)
from .router import FreeboxConfigEntry, FreeboxRouter, get_api
from .tnt_setup import (
    TNT_COORDINATORS_KEY,
    async_setup_bundled_tnt,
    async_unload_bundled_tnt,
)
from .services import async_setup_services
from .tnt_reminders import async_setup_reminders
from .registry_compat import as_version

SCAN_INTERVAL = timedelta(seconds=40)
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"

# Configuration par l'interface uniquement (aucune option YAML lue).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Services de l'intégration, enregistrés une seule fois (pas par entrée)."""
    hass.data.setdefault(DOMAIN, {})
    async_setup_services(hass)
    try:
        await async_setup_reminders(hass)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Rappels TNT indisponibles (le reste de l'intégration n'est pas affecté)")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FreeboxConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    if not hass.data[DOMAIN].get("_card_registered"):
        await JSModuleRegistration(hass).async_register()
        hass.data[DOMAIN]["_card_registered"] = True

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
                translation_domain=DOMAIN,
                translation_key="auth_pending",
            ) from err
        _LOGGER.error("Autorisation Freebox refusée pour %s: %s", host, err)
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="auth_failed",
        ) from err
    except HttpRequestError as err:
        _LOGGER.error("Erreur réseau Freebox %s: %s", host, err)
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": host, "error": str(err)},
        ) from err

    freebox_config = await api.system.get_config()

    # Migration des surcharges « Groupes des appareils » (groupes par type -> par service).
    saved = entry.options.get(CONF_DEVICE_GROUP_OVERRIDES)
    if saved and migrate_overrides(saved) != saved:
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_DEVICE_GROUP_OVERRIDES: migrate_overrides(saved)},
        )

    device_registry = dr.async_get(hass)
    parent_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, freebox_config["mac"])},
        connections={(dr.CONNECTION_NETWORK_MAC, freebox_config["mac"])},
        manufacturer="Freebox SAS",
        name="Freebox Server",
        model=freebox_config["model_info"]["pretty_name"],
        sw_version=as_version(freebox_config.get("firmware_version")),
    )

    router = FreeboxRouter(hass, entry, api, freebox_config)
    router.device_id = parent_device.id
    create_lan_devices = option_enabled(
        entry, CONF_CREATE_LAN_DEVICES, DEFAULT_CREATE_LAN_DEVICES
    )
    if not create_lan_devices:
        removed = async_remove_lan_client_devices(hass, entry, freebox_config["mac"])
        if removed:
            _LOGGER.info("%s appareil(s) client réseau retiré(s) du registre", removed)
    await router.update_all()
    # Un appareil par répéteur physique : fusion des doublons avant l'ajout des entités.
    try:
        merged = async_merge_repeater_devices(
            hass,
            entry,
            router.mac,
            router.repeaters,
            (router.wifi_aps.get("gateway") or {}).get("rejected_repeater_macs"),
            set(router.devices),
        )
        if merged:
            _LOGGER.info("%s appareil(s) répéteur en double fusionné(s)", merged)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Fusion des répéteurs en double impossible")
    try:
        from .device_groups import repeater_registry_devices

        rep_devices = repeater_registry_devices(hass, entry)
        if len(rep_devices) > len(router.repeaters):
            _LOGGER.warning(
                "Répéteurs : %s appareil(s) dans le registre pour %s répéteur(s) détecté(s) "
                "(non fusionnés) : %s. Téléchargez les diagnostics Homexa pour analyse.",
                len(rep_devices),
                len(router.repeaters),
                [
                    (d["name_by_user"] or d["name"], d["model"], d["identifiers"], d["entity_count"])
                    for d in rep_devices
                ],
            )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Résumé des répéteurs impossible", exc_info=True)
    await router.update_home_devices()

    async def _poll_home(_now: datetime | None = None) -> None:
        try:
            await router.update_home_devices()
        except Exception:
            _LOGGER.debug("Poll Home ignoré (API lente ou occupée)", exc_info=True)

    home_interval = option_home_poll_interval(entry)
    _LOGGER.info("Poll Home toutes les %s s", home_interval)

    entry.async_on_unload(async_track_time_interval(hass, router.update_all, SCAN_INTERVAL))
    entry.async_on_unload(
        async_track_time_interval(hass, _poll_home, timedelta(seconds=home_interval))
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    entry.runtime_data = router
    try:
        await async_setup_bundled_tnt(hass, entry)
    except Exception:
        _LOGGER.exception("Guide TNT embarqué indisponible")
    # Rappels TNT : services et rappels en attente chargés par async_setup (idempotent).
    try:
        await async_setup_reminders(hass)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Rappels TNT indisponibles (le reste de l'intégration n'est pas affecté)")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Parents virtuels créés à la demande par les entités. Les groupes inutilisés
    # sont retirés un peu plus tard : certaines plateformes ajoutent leurs entités
    # via des signaux après le setup (retirer trop tôt détachait p. ex. les volets).
    @callback
    def _cleanup_groups(_now: datetime | None = None) -> None:
        # D'abord détacher Players / TNT de leurs anciens groupes, puis retirer les vides.
        async_detach_top_level_devices(
            hass,
            entry,
            [(DOMAIN, "programme_tnt_fr")]
            + [(DOMAIN, ident) for ident in router.player_identifiers],
        )
        removed = async_remove_unused_group_devices(
            hass, entry, freebox_config["mac"], set(router.used_groups)
        )
        for group in list(router.group_device_ids):
            if group not in router.used_groups:
                router.group_device_ids.pop(group, None)
        if removed:
            _LOGGER.debug("Groupes vides retirés : %s", ", ".join(removed))
        merged = async_remove_merged_node_devices(hass, entry, set(router.merged_node_ids))
        if merged:
            _LOGGER.debug("%s ancien(s) appareil(s) alarme retiré(s)", merged)

    entry.async_on_unload(async_call_later(hass, 120, _cleanup_groups))

    async def async_close_connection(event: Event) -> None:
        await router.close()
        await save_data()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    _LOGGER.info("Freebox Homexa prêt")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FreeboxConfigEntry) -> bool:
    router: FreeboxRouter | None = getattr(entry, "runtime_data", None)
    if router is not None:
        # Déchargement / rechargement : les relevés encore en vol ne journalisent plus
        # « Connector is closed » comme une erreur.
        router.closing = True
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        if router is not None:
            router.closing = False
        return False
    async_unload_bundled_tnt(hass, entry)
    if router is not None:
        await router.close()
    store = hass.data[DOMAIN].get("store")
    if store is not None and "config" in hass.data[DOMAIN]:
        await store.async_save(hass.data[DOMAIN]["config"])
    # Services enregistrés une fois dans async_setup : conservés (ils renvoient une
    # erreur traduite tant qu'aucune entrée n'est chargée). Rappels TNT conservés.
    return True


async def async_reload_entry(hass: HomeAssistant, entry: FreeboxConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
