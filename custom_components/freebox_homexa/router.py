# custom_components/freebox_homexa/router.py
"""Représentation du routeur Freebox et de ses appareils et capteurs dans Home Assistant."""

from __future__ import annotations

import asyncio
import logging
import json
from pathlib import Path
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any, Mapping, TypeVar
from collections.abc import Awaitable, Callable

from freebox_api import Freepybox
from freebox_api.api.call import Call
from freebox_api.api.home import Home
from freebox_api.api.wifi import Wifi
from freebox_api.exceptions import HttpRequestError, NotOpenError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    API_VERSION,
    APP_DESC,
    CONNECTION_SENSORS_KEYS,
    HOME_COMPATIBLE_CATEGORIES,
    REPEATER_MODEL,
)
from .registry_compat import (
    as_version,
    registry_device_id,
    foreign_device_with_connection,
    get_device_by_connection,
    get_device_by_identifier,
    shared_with_other_entries,
)
from .sdk_contracts import (LanObservations, WifiObservations, SystemConfiguration,
    SystemActions, ConnectionObservations, CallObservations, StorageObservations, HomeObservations)
from .errors import api_error_code, is_permission_denied, is_shutdown_error
from .wifi_ap import build_wifi_aps

from .errors import async_action_errors

_LOGGER = logging.getLogger(__name__)

GROUP_SERVER_SERVICE = "server"

SCAN_INTERVAL = timedelta(seconds=120)

WIFI_BAND_LABELS = {
    "2d4g": "2.4 GHz",
    "2.4g": "2.4 GHz",
    "5g": "5 GHz",
    "6g": "6 GHz",
}


def normalize_mac(mac: str | None) -> str:
    """Normalize a MAC address for comparisons."""
    return (mac or "").upper().replace(":", "").replace("-", "")


def is_freebox_repeater(device: dict[str, Any], router_mac: str) -> bool:
    """Return True if the LAN host looks like a Free Wi-Fi repeater."""
    mac = normalize_mac((device.get("l2ident") or {}).get("id"))
    if not mac or mac == normalize_mac(router_mac):
        return False

    name = (device.get("primary_name") or "").lower()
    host_type = device.get("host_type") or ""
    vendor = (device.get("vendor_name") or "").lower()

    if any(token in name for token in ("répét", "repet", "repeater", "rp01")):
        return True
    if host_type in {"networking_device", "freebox_wifi"} and "free" in vendor:
        return True
    return False


def extract_wifi_details(device: dict[str, Any]) -> dict[str, Any]:
    """Build a stable Wi-Fi quality dict from LAN host + optional station data."""
    details: dict[str, Any] = {}
    access_point = device.get("access_point") or {}
    wifi_info = access_point.get("wifi_information") or {}
    station = device.get("_wifi_station") or {}

    signal = wifi_info.get("signal")
    if signal is None:
        signal = station.get("signal")
    if signal is not None and not isinstance(signal, bool):
        try:
            details["wifi_signal_dbm"] = int(signal)
        except (TypeError, ValueError, OverflowError):
            pass

    if wifi_info.get("ssid"):
        details["wifi_ssid"] = wifi_info["ssid"]

    band = wifi_info.get("band")
    if band:
        details["wifi_band"] = band
        details["wifi_band_label"] = WIFI_BAND_LABELS.get(str(band).lower(), str(band))

    bssid = wifi_info.get("bssid") or station.get("bssid")
    if bssid:
        details["wifi_bssid"] = bssid

    standard = wifi_info.get("standard")
    if standard:
        details["wifi_standard"] = standard

    phy_rx = wifi_info.get("phy_rx_rate")
    phy_tx = wifi_info.get("phy_tx_rate")
    if phy_rx is not None:
        details["wifi_phy_rx_rate_mbps"] = phy_rx
    if phy_tx is not None:
        details["wifi_phy_tx_rate_mbps"] = phy_tx

    ap_mac = access_point.get("mac")
    if ap_mac:
        details["ap_mac"] = ap_mac
    ap_kind = access_point.get("type") or access_point.get("connectivity_type")
    if ap_kind:
        details["ap_type"] = ap_kind
    if station.get("_ap_name"):
        details["ap_name"] = station["_ap_name"]

    connectivity = access_point.get("connectivity_type")
    if not connectivity and (wifi_info or station):
        connectivity = "wifi"
    if connectivity:
        details["connectivity"] = connectivity

    return details


def _token_path(hass: HomeAssistant, host: str) -> Path:
    """Own token path only — never touch core Freebox .storage/freebox/."""
    slug = slugify(host)
    return Path(hass.config.path(".storage")) / "freebox_homexa" / f"{slug}.conf"


def resolve_token_file(hass: HomeAssistant, host: str) -> Path:
    """Public helper used by config_flow to locate (and optionally delete) the token file."""
    return _token_path(hass, host)


def _app_desc_from_token(token_file: Path) -> dict[str, str]:
    """Keep the descriptor stored with the token so freebox-api does not re-pair."""
    app_desc = dict(APP_DESC)
    try:
        data = json.loads(token_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return app_desc
    if not data.get("app_token"):
        return app_desc
    for key in ("app_id", "app_name", "app_version", "device_name"):
        if data.get(key):
            app_desc[key] = str(data[key])
    return app_desc


async def get_api(hass: HomeAssistant, host: str) -> Freepybox:
    """Obtient l'API Freebox en réutilisant le token déjà enregistré."""
    token_file = _token_path(hass, host)
    storage_dir = token_file.parent

    def _ensure_directory() -> None:
        if storage_dir.is_file():
            backup = storage_dir.with_suffix(".bak")
            try:
                storage_dir.replace(backup)
                _LOGGER.warning("Fichier bloquant '%s' déplacé vers %s", storage_dir, backup)
            except OSError as err:
                _LOGGER.error("Impossible de déplacer le fichier bloquant : %s", err)
        storage_dir.mkdir(parents=True, exist_ok=True)

    await hass.async_add_executor_job(_ensure_directory)

    app_desc = APP_DESC
    if await hass.async_add_executor_job(token_file.is_file):  # pas d'E/S dans la boucle
        app_desc = await hass.async_add_executor_job(_app_desc_from_token, token_file)
        _LOGGER.info("Token Freebox réutilisé : %s", token_file)

    return Freepybox(app_desc, str(token_file), API_VERSION)


async def get_hosts_list_if_supported(
    fbx_api: Freepybox,
) -> tuple[bool, list[dict[str, Any]]]:
    """Récupère la liste des hôtes si supportée."""
    supports_hosts: bool = True
    fbx_devices: list[dict[str, Any]] = []
    try:
        lan: LanObservations = fbx_api.lan
        response = await lan.get_hosts_list()
        if not isinstance(response, list):
            raise ValueError("Invalid LAN hosts collection")
        if any(not isinstance(row, dict) for row in response):
            raise ValueError("Invalid LAN host record")
        fbx_devices = response
    except HttpRequestError as err:
        if api_error_code(err) == "nodev":
            supports_hosts = False
            _LOGGER.debug("Liste des hôtes non disponible en mode bridge")
        else:
            raise
    return supports_hosts, fbx_devices


_ReadT = TypeVar("_ReadT")

class FreeboxRouter:
    """Représentation du routeur Freebox dans Home Assistant."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: Freepybox,
        freebox_config: Mapping[str, Any],
    ) -> None:
        self.hass = hass
        self._host = entry.data[CONF_HOST]
        self._port = entry.data.get(CONF_PORT, 80)
        self._api = api
        self.name: str = freebox_config["model_info"]["pretty_name"]
        self.mac: str = freebox_config["mac"]
        self.model: str = freebox_config["model_info"]["name"]
        self._sw_v: str = freebox_config["firmware_version"]
        self._attrs: dict[str, Any] = {}
        self.device_id: str | None = None
        self.group_device_ids: dict[str, str] = {}
        self.entry_id: str = entry.entry_id
        from .device_groups import (
            CONF_DEVICE_GROUP_OVERRIDES,
            CONF_REPEATER_MERGES,
            migrate_overrides,
            migrate_repeater_merges,
        )

        # Fusions manuelles de répéteurs choisies dans les options (doublon -> cible).
        self.repeater_merges: dict[str, str] = migrate_repeater_merges(
            entry.options.get(CONF_REPEATER_MERGES)
        )

        self.group_overrides: dict[str, str] = migrate_overrides(
            entry.options.get(CONF_DEVICE_GROUP_OVERRIDES)
        )
        from .device_groups import CONF_DEVICE_TYPE_OVERRIDES, migrate_type_overrides

        # Types forcés des clients réseau (« Types des clients réseau ») : clé -> net_*.
        self.type_overrides: dict[str, str] = migrate_type_overrides(
            entry.options.get(CONF_DEVICE_TYPE_OVERRIDES)
        )
        # clé stable « mac:… » -> (nom, type automatique) pour l'écran des types
        self.lan_client_types: dict[str, tuple[str, str]] = {}
        # Clients LAN dont l'entité device_tracker est ACTIVE (ajoutée à HA) : MAC normalisées.
        # Seuls ceux-là reçoivent un appareil (pas de groupes vides pour des entités désactivées).
        self.tracked_lan_macs: set[str] = set()
        # MAC normalisée -> device_id de l'appareil du client (pour relier l'entité).
        self.lan_device_ids: dict[str, str] = {}
        # MAC normalisée -> (sous-)groupe où l'appareil du client est rangé :
        # « lan_wired_net_servers », « lan_wifi », « repeater:<MAC canonique> »… (capteurs
        # « Clients connectés » des groupes).
        self.lan_client_placements: dict[str, str] = {}
        # MAC canonique d'un répéteur -> device_id (rangement des clients sous le répéteur).
        self.repeater_device_ids: dict[str, str] = {}
        # Option « Créer les appareils des clients LAN » (renseignée par device_tracker).
        self.create_lan_devices: bool = True
        self.used_groups: set[str] = set()
        # Entrée en cours de déchargement / rechargement (erreurs de connexion attendues).
        self.closing: bool = False
        # Journalisation unique de l'indisponibilité (règle log-when-unavailable).
        self.reachable: bool = True
        self.sensors_available: bool = True
        self.disks_available = True
        self.raids_available = True
        self.home_available = True
        self.home_snapshot_known = False
        # Vrai seulement après une liste complète réussie. L'état initial et un échec
        # ne prouvent pas qu'un appareil a disparu.
        self.disks_snapshot_known = False
        self.lan_snapshot_known = False
        self.lan_available = True
        self.wifi_stations_available = True
        self.player_status_available: dict[str, bool] = {}
        self.player_status_providers: set[str] = set()
        self._player_button_readers: dict[str, tuple[int, int, str]] = {}
        self._player_standby: set[str] = set()
        self._source_states: dict[object, bool] = {}
        # nœuds Home dont les entités vivent sur un appareil de groupe (module d'alarme)
        self.merged_node_ids: set[Any] = set()
        self.player_identifiers: set[str] = set()
        # clé stable -> (nom, groupe automatique) pour l'écran d'options
        self.grouped_devices: dict[str, tuple[str, str]] = {}
        # Client LAN (MAC normalisée) -> lien retenu : « wired », « wifi », « repeater:<MAC> ».
        # Dernier classement connu : conservé tant que l'appareil est hors ligne.
        self.lan_links: dict[str, str] = {}
        self._lan_link_pending: dict[str, tuple[str, int]] = {}
        self._home_update_lock = asyncio.Lock()
        self._players_update_lock = asyncio.Lock()
        self.players: list[dict[str, object]] = []
        self.players_initialized = False
        self.player_discovery_active = False

        self.supports_hosts = True
        self.devices: dict[str, dict[str, Any]] = {}
        self.repeaters: dict[str, dict[str, Any]] = {}
        # MAC normalisée -> MAC canonique du répéteur physique
        self.repeater_aliases: dict[str, str] = {}
        self.api_repeaters: list[dict[str, Any]] = []
        self.api_repeaters_raw: Any = None
        self.api_repeaters_error: str | None = None
        self.wifi_aps: dict[str, dict[str, Any]] = {}
        self.wifi_radio_status: list[dict[str, Any]] = []
        self.wifi_bss_status: list[dict[str, Any]] = []
        self.wifi_global_enabled: bool | None = None
        self.wifi_api_errors: dict[str, str] = {}
        self.disks: dict[int, dict[str, Any]] = {}
        self.supports_raid = True
        self.raids: dict[int, dict[str, Any]] = {}
        self.sensors_temperature: dict[str, int] = {}
        self.sensors_connection: dict[str, float | None] = {}
        self.call_list: list[dict[str, Any]] = []
        self.home_granted = True
        self.home_devices: dict[str, Any] = {}
        self.listeners: list[object] = []
        self.poll_tasks: set[asyncio.Task[None]] = set()
        self.read_tasks: set[asyncio.Task[object]] = set()
        self._close_lock = asyncio.Lock()
        self._closed = False

        _LOGGER.debug("Routeur Freebox %s initialisé", self.name)

    async def _fetch_api_repeaters(self) -> None:
        """Liste /repeater/ (une entrée par répéteur physique : main_mac, sn, nom)."""
        try:
            data = await self._api.wifi._access.get("repeater/")
            self.api_repeaters_raw = data
            self.api_repeaters_error = None
        except Exception as err:  # noqa: BLE001 — API absente / droit manquant
            self.api_repeaters_raw = None
            self.api_repeaters_error = type(err).__name__
            self.note_permission("repeaters", err)
            if not getattr(self, "_repeater_api_logged", False):
                _LOGGER.info("API /repeater/ indisponible (regroupement via lan/browser) : %s", type(err).__name__)
                self._repeater_api_logged = True
            return
        if isinstance(data, list):
            self.note_permission("repeaters")
            self.api_repeaters = [r for r in data if isinstance(r, dict)]

    def is_repeater_host(self, device: dict[str, Any]) -> bool:
        """Hôte LAN rattaché à un répéteur physique reconnu (OUI Free ou lié à une MAC Free)."""
        from .wifi_ap import normalize_mac

        mac = normalize_mac((device.get("l2ident") or {}).get("id"))
        return bool(mac) and mac in self.repeater_aliases

    def repeater_canonical_mac(self, mac: str | None) -> str:
        """MAC canonique du répéteur physique auquel appartient `mac`."""
        from .wifi_ap import normalize_mac

        return self.repeater_aliases.get(normalize_mac(mac), mac or "")

    def repeater_device_info(
        self, mac: str | None, name: str, model: str | None = None, manufacturer: str | None = None
    ) -> DeviceInfo:
        """DeviceInfo unique d'un répéteur physique (identifiant + toutes ses MAC)."""
        canon = self.repeater_canonical_mac(mac)
        payload = self.repeaters.get(canon) or {}
        macs = payload.get("macs") or [canon]
        name = payload.get("name") or name
        info: DeviceInfo = {
            "identifiers": {(DOMAIN, f"repeater_{canon}")},
            "connections": {(CONNECTION_NETWORK_MAC, m.lower()) for m in macs},
            "manufacturer": manufacturer or payload.get("vendor_name") or "Freebox SAS",
            "model": payload.get("model") or model,
            "name": name,
        }
        if payload.get("serial"):
            info["serial_number"] = payload["serial"]
        from .device_groups import LINK_WIFI

        # Les répéteurs se rangent sous « Clients Wi-Fi » (avec leurs propres clients).
        parent_id = self.parent_for(f"repeater_{canon}", name, "server", LINK_WIFI)
        if parent_id:
            info["via_device_id"] = parent_id
        return info

    def _refresh_repeaters(self) -> None:
        """Build gateway + repeater maps and attach Wi-Fi clients."""
        self.wifi_aps, self.repeaters = build_wifi_aps(
            router_mac=self.mac,
            router_name=self.name,
            router_model=self.model,
            devices=self.devices,
            radio_status=self.wifi_radio_status,
            api_repeaters=self.api_repeaters,
            manual_links=self.repeater_merges,
            bss_status=self.wifi_bss_status,
            wifi_enabled=self.wifi_global_enabled,
        )
        from .wifi_ap import normalize_mac

        # « ap_aliases » : MAC de point d'accès non Free (rattachement des clients
        # uniquement) ; jamais un hôte LAN, ni une connexion de l'appareil répéteur.
        lan_norms = {normalize_mac(m) for m in self.devices}
        self.repeater_aliases = {}
        for canon, payload in self.repeaters.items():
            for alias in payload.get("ap_aliases") or []:
                if normalize_mac(alias) not in lan_norms:
                    self.repeater_aliases[normalize_mac(alias)] = canon
        for canon, payload in self.repeaters.items():
            for alias in payload.get("macs") or [canon]:
                self.repeater_aliases[normalize_mac(alias)] = canon
        if self.repeaters:
            # À chaque relevé (40 s) : debug, le détail est journalisé en info s'il change.
            _LOGGER.debug("Répéteurs Wi-Fi détectés : %s", list(self.repeaters.keys()))
        _LOGGER.debug(
            "API /repeater/ : %s",
            [
                (r.get("id"), r.get("name"), r.get("model"), r.get("main_mac"), r.get("sn"))
                for r in self.api_repeaters
            ],
        )
        summary = {
            canon: (payload.get("name"), payload.get("model"), payload.get("macs"), payload.get("grouping"))
            for canon, payload in self.repeaters.items()
        }
        if summary != getattr(self, "_repeater_summary", None):
            self._repeater_summary = summary
            for canon, (name, model, macs, grouping) in summary.items():
                _LOGGER.info(
                    "Répéteur physique %s (%s, %s) : MAC %s ; regroupement : %s",
                    canon, name, model, macs, grouping or "aucun (MAC seule)",
                )

    def note_permission(self, source: str, error: Exception | None = None) -> None:
        """Report rights only; transient outages never create or clear an issue."""
        from .repairs import async_source_permission_result

        if not self.closing:
            async_source_permission_result(self.hass, self.entry_id, source, error)

    def _wifi_api_error(self, key: str, path: str, err: Exception) -> None:
        """Mémorise l'erreur d'une API Wi-Fi ; journal (info) une seule fois par API."""
        self.note_permission("wifi_" + key, err)
        self.wifi_api_errors[key] = type(err).__name__
        self.note_source(("wifi", key), False, "API Freebox Wi-Fi " + key)

    async def _fetch_wifi_global_state(self) -> None:
        """/wifi/config/ (enabled, comme l'interrupteur) et /wifi/bss/ (état des BSS)."""
        try:
            wifi: WifiObservations = self._api.wifi
            config = await wifi.get_global_config()
            if not isinstance(config, dict):
                raise ValueError("Invalid Wi-Fi config")
            enabled = config.get("enabled") if isinstance(config, dict) else None
            self.wifi_global_enabled = enabled if isinstance(enabled, bool) else None
            self.wifi_api_errors.pop("config", None)
            self.note_permission("wifi_config")
            self.note_source(("wifi", "config"), True, "API Freebox Wi-Fi config")
        except Exception as err:  # noqa: BLE001
            self.wifi_global_enabled = None
            self._wifi_api_error("config", "wifi/config/", err)
        try:
            bss_api: WifiObservations = self._api.wifi
            bss_list = await bss_api.get_bss()
            if not isinstance(bss_list, list):
                raise ValueError("Invalid Wi-Fi BSS collection")
            self.wifi_api_errors.pop("bss", None)
            self.note_permission("wifi_bss")
            self.note_source(("wifi", "bss"), True, "API Freebox Wi-Fi bss")
        except Exception as err:  # noqa: BLE001 — API absente selon firmware
            self._wifi_api_error("bss", "wifi/bss/", err)
            bss_list = []
        self.wifi_bss_status = []
        for bss in bss_list if isinstance(bss_list, list) else []:
            if not isinstance(bss, dict):
                continue
            status = bss.get("status") or {}
            config = bss.get("config") or {}
            self.wifi_bss_status.append(
                {
                    "id": bss.get("id"),
                    "phy_id": bss.get("phy_id"),
                    "ssid": config.get("ssid") if isinstance(config, dict) else None,
                    "state": status.get("state") if isinstance(status, dict) else None,
                }
            )

    async def _enrich_wifi_stations(self) -> None:
        """Merge /wifi/ap/{id}/stations signal data onto LAN hosts."""
        self.wifi_stations_available = True
        for device in self.devices.values():
            device.pop("_wifi_station", None)
        try:
            wifi: WifiObservations = self._api.wifi
            access_points = await wifi.get_ap_list()
            if not isinstance(access_points, list):
                raise ValueError("Invalid Wi-Fi AP collection")
            self.wifi_api_errors.pop("ap", None)
            self.note_permission("wifi_ap")
            self.note_source(("wifi", "ap"), True, "API Freebox Wi-Fi ap")
        except Exception as err:  # noqa: BLE001 — API wifi absente selon firmware
            self.wifi_stations_available = False
            self._wifi_api_error("ap", "wifi/ap/", err)
            access_points = []
        if not isinstance(access_points, list):
            access_points = []

        self.wifi_radio_status = []
        stations_by_mac: dict[str, dict[str, Any]] = {}
        stations_observed = False
        for access_point in access_points:
            if not isinstance(access_point, dict):
                continue
            status = access_point.get("status") or {}
            if not isinstance(status, dict):
                status = {}
            self.wifi_radio_status.append(
                {
                    "id": access_point.get("id"),
                    "name": access_point.get("name"),
                    "state": status.get("state"),
                }
            )
            ap_id = access_point.get("id")
            if ap_id is None:
                continue
            try:
                stations = await wifi.get_station_list(ap_id)
                if not isinstance(stations, list):
                    raise ValueError("Invalid Wi-Fi stations collection")
                stations_observed = True
            except HttpRequestError as err:
                self.note_permission("wifi_stations", err)
                self.wifi_stations_available = False
                _LOGGER.debug("Stations Wi-Fi indisponibles (%s)", type(err).__name__)
                continue
            except Exception as err:  # noqa: BLE001
                self.wifi_stations_available = False
                _LOGGER.debug("Stations Wi-Fi illisibles (%s)", type(err).__name__)
                continue
            for station in stations:
                mac = (station.get("mac") or "").upper()
                if not mac:
                    host = station.get("host") or {}
                    mac = ((host.get("l2ident") or {}).get("id") or "").upper()
                if not mac:
                    continue
                merged = dict(station)
                merged["_ap_id"] = ap_id
                merged["_ap_name"] = access_point.get("name")
                stations_by_mac[mac] = merged

        if stations_observed and self.wifi_stations_available:
            self.note_permission("wifi_stations")
        self.note_source("wifi_stations", self.wifi_stations_available, "Stations Wi-Fi")
        for mac, device in self.devices.items():
            station = stations_by_mac.get(str(mac).upper())
            if station:
                device["_wifi_station"] = station
            device["wifi"] = extract_wifi_details(device)

    def note_source(self, key: object, available: bool, label: str) -> None:
        """One sanitized loss/recovery notification per source, not per poll."""
        previous = self._source_states.get(key, True)
        self._source_states[key] = available
        if previous != available and not self.closing:
            _LOGGER.info("%s %s", label, "de nouveau disponible" if available else "indisponible")

    def register_player_button(self, player_id: int, version: str) -> Callable[[], None]:
        """Reference-count active buttons, without adding one timer per button."""
        key = str(player_id)
        count, _, preferred = self._player_button_readers.get(key, (0, player_id, version))
        self._player_button_readers[key] = (count + 1, player_id, preferred)

        def remove() -> None:
            count, identifier, preferred = self._player_button_readers[key]
            if count == 1:
                del self._player_button_readers[key]
            else:
                self._player_button_readers[key] = (count - 1, identifier, preferred)
        return remove

    async def update_player_buttons(self) -> None:
        """Fallback at the existing central interval only if no media provider lives."""
        from .player_status import async_read_player_status
        from .const import option_remote_code

        for key, (_, player_id, version) in list(self._player_button_readers.items()):
            if key in self.player_status_providers:
                continue
            status, preferred = await async_read_player_status(self, player_id, version)
            if key in self._player_button_readers:
                count, _, _ = self._player_button_readers[key]
                self._player_button_readers[key] = (count, player_id, preferred)
            if status is not None:
                power = str(status.get("power_state") or status.get("power") or "").lower()
                if power in {"standby", "off", "shutdown"}:
                    self._player_standby.add(key)
                else:
                    self._player_standby.discard(key)
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            can_wake = entry is not None and option_remote_code(entry, player_id) is not None
            self.player_status_available[key] = (
                (status is not None and status.get("reachable") is not False)
                or (key in self._player_standby and can_wake)
            )
            self.note_source(("player", player_id), self.player_status_available[key], "Player")
        if self._player_button_readers:
            async_dispatcher_send(self.hass, self.signal_device_update)

    async def async_update_players(self) -> None:
        """Observe metadata once at the existing interval, never issue commands."""
        if self.closing or self._players_update_lock.locked():
            return
        async with self._players_update_lock:
            try:
                payload: object = await self.async_read(self._api.player.get_players)
                if self.closing:
                    return
                if not isinstance(payload, list):
                    raise ValueError("Invalid Player collection")
                players: list[dict[str, object]] = []
                for item in payload:
                    if not isinstance(item, dict):
                        raise ValueError("Invalid Player metadata")
                    player: dict[str, object] = {}
                    for key, value in item.items():
                        if not isinstance(key, str):
                            raise ValueError("Invalid Player metadata key")
                        player[key] = value
                    players.append(player)
                self.note_permission("players")
                self.players = players
                self.players_initialized = True
                self.note_source(("player_inventory", self.entry_id), True, "Inventaire Player")
                async_dispatcher_send(self.hass, self.signal_players_update)
            except Exception as err:
                self.note_permission("players", err)
                if not self.closing:
                    self.note_source(("player_inventory", self.entry_id), False, "Inventaire Player")

    @property
    def signal_players_update(self) -> str:
        """Entry-owned discovery, unlike legacy host-scoped state signals."""
        return f"{DOMAIN}-{self.entry_id}-players-update"

    async def update_all(self, now: datetime | None = None) -> None:
        """Relevé principal (appareils + capteurs).

        Appel direct (``now is None``, mise en place) : l'erreur est propagée.
        Relevé périodique : la perte de la Freebox est journalisée une seule fois
        (« Freebox injoignable »), puis son retour (« Freebox de nouveau joignable »),
        sans répéter l'erreur à chaque cycle.
        """
        if self.closing:
            return
        try:
            await self.update_device_trackers()
            await self.update_sensors()
            if self.player_discovery_active:
                await self.async_update_players()
            await self.update_player_buttons()
        except Exception as err:
            if self.closing and is_shutdown_error(err, self):
                _LOGGER.debug("Relevé interrompu (connexion fermée, rechargement) : %s", err)
                return
            if now is None:
                raise
            if self.reachable:
                self.reachable = False
                _LOGGER.info("Freebox injoignable (%s)", type(err).__name__)
                self._signal_reachability_changed()
            else:
                _LOGGER.debug("Freebox toujours injoignable (%s)", type(err).__name__)
            return
        if not self.reachable:
            self.reachable = True
            _LOGGER.info("Freebox de nouveau joignable")
            self._signal_reachability_changed()

    def _signal_reachability_changed(self) -> None:
        """Réécrit l'état des entités à l'écoute (disponible / indisponible).

        Les entités interrogées par Home Assistant (volets, alarme, Player…) suivent
        au relevé suivant ; celles pilotées par signal sont réécrites tout de suite.
        """
        async_dispatcher_send(self.hass, self.signal_device_update)
        async_dispatcher_send(self.hass, self.signal_sensor_update)
        async_dispatcher_send(self.hass, self.signal_home_device_update)

    async def update_device_trackers(self) -> None:
        new_device = False
        fbx_devices: list[dict[str, Any]] = []
        # Bridge mode can change at runtime; retry at the existing poll interval.
        try:
            self.supports_hosts, fbx_devices = await get_hosts_list_if_supported(self._api)
        except Exception as err:
            self.note_permission("lan", err)
            self.lan_available = False
            self.lan_snapshot_known = False
            self.note_source("lan", False, "Source LAN")
            raise
        self.note_source("lan", self.supports_hosts, "Source LAN")

        if self.supports_hosts:
            self.note_permission("lan")
        self.lan_available = self.supports_hosts
        self.lan_snapshot_known = bool(self.supports_hosts)
        seen_macs = {device["l2ident"]["id"] for device in fbx_devices}
        if self.lan_available:
            for mac, previous in self.devices.items():
                if mac != self.mac and mac not in seen_macs:
                    previous["active"] = False

        fbx_devices.append({
            "primary_name": self.name,
            "l2ident": {"id": self.mac},
            "vendor_name": "Freebox SAS",
            "host_type": "router",
            "active": True,
            "attrs": self._attrs,
            "model": self.model,
        })

        for fbx_device in fbx_devices:
            device_mac = fbx_device["l2ident"]["id"]
            if device_mac not in self.devices:
                new_device = True
            self.devices[device_mac] = fbx_device

        await self._enrich_wifi_stations()
        await self._fetch_wifi_global_state()
        await self._fetch_api_repeaters()
        self._refresh_repeaters()
        try:
            self._update_lan_links()
            self._sync_lan_client_parents()
        except Exception:  # noqa: BLE001 — le classement ne doit jamais bloquer le poll
            _LOGGER.debug("Classement filaire / Wi-Fi des clients impossible", exc_info=True)
        async_dispatcher_send(self.hass, self.signal_device_update)
        if new_device:
            async_dispatcher_send(self.hass, self.signal_device_new)
        _LOGGER.debug("Mise à jour des appareils connectés terminée")

    async def update_sensors(self) -> None:
        permission_source = "system"
        try:
            system: SystemConfiguration = self._api.system
            syst_datas = await system.get_config()
            if not isinstance(syst_datas, dict):
                raise ValueError("Invalid system configuration")
            self.sensors_temperature = {
                sensor["name"]: sensor.get("value") for sensor in syst_datas["sensors"]
            }

            serial = syst_datas["serial"]
            self.note_permission("system")
            permission_source = "connection"
            connection: ConnectionObservations = self._api.connection
            connection_datas = await connection.get_status()
            if not isinstance(connection_datas, dict):
                raise ValueError("Invalid connection status")
            for sensor_key in CONNECTION_SENSORS_KEYS:
                value = connection_datas.get(sensor_key)
                self.sensors_connection[sensor_key] = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

            self.note_permission("connection")
            raw_uptime = syst_datas.get("uptime_val")
            uptime_seconds = (raw_uptime if isinstance(raw_uptime, (int, float))
                              and not isinstance(raw_uptime, bool) and raw_uptime >= 0 else None)
            self.sensors_connection["uptime"] = uptime_seconds

            self._attrs = {
                "IPv4": connection_datas.get("ipv4"),
                "IPv6": connection_datas.get("ipv6"),
                "connection_type": connection_datas.get("media"),
                "uptime": datetime.fromtimestamp(
                    round(datetime.now().timestamp()) - uptime_seconds
                ) if uptime_seconds is not None else None,
                "firmware_version": self._sw_v,
                "serial": serial,
            }

            permission_source = "calls"
            call_api: CallObservations = self._api.call
            calls = await call_api.get_calls_log()
            if not isinstance(calls, list):
                raise ValueError("Invalid call log collection")
            self.call_list = calls
            self.note_permission("calls")
            await self._update_disks_sensors()
            await self._update_raids_sensors()

            if not self.sensors_available:
                _LOGGER.info("Capteurs Freebox de nouveau disponibles")
            self.sensors_available = True
            async_dispatcher_send(self.hass, self.signal_sensor_update)
            _LOGGER.debug("Mise à jour des capteurs terminée")
        except Exception as err:
            self.note_permission(permission_source, err)
            # The global router may still answer LAN requests. Do not leave
            # sensor snapshots looking fresh after a separate sensor API error.
            if self.sensors_available:
                _LOGGER.info("Capteurs Freebox indisponibles")
            self.sensors_available = False
            async_dispatcher_send(self.hass, self.signal_sensor_update)

    async def _update_disks_sensors(self) -> None:
        try:
            storage: StorageObservations = self._api.storage
            fbx_disks = await storage.get_disks()
            if not isinstance(fbx_disks, list):
                raise ValueError("Invalid disks collection")
            disks: dict[int, dict[str, Any]] = {}
            for fbx_disk in fbx_disks:
                disk = {**fbx_disk}
                disk["partitions"] = {part["id"]: part for part in fbx_disk.get("partitions", [])}
                disks[fbx_disk["id"]] = disk
            self.note_permission("disks")
            self.disks = disks
            self.disks_snapshot_known = True
            if not self.disks_available:
                _LOGGER.info("Source disques Freebox de nouveau disponible")
            self.disks_available = True
        except Exception as err:  # An unsuccessful read
            self.note_permission("disks", err)
            self.disks_snapshot_known = False
            if self.disks_available:
                _LOGGER.info("Source disques Freebox indisponible")
            self.disks_available = False

    async def _update_raids_sensors(self) -> None:
        if not self.supports_raid:
            return
        try:
            storage: StorageObservations = self._api.storage
            fbx_raids = await storage.get_raids()
            if not isinstance(fbx_raids, list):
                raise ValueError("Invalid RAID collection")
            raids = {raid["id"]: raid for raid in fbx_raids}
            self.note_permission("raids")
            self.raids = raids
            if not self.raids_available:
                _LOGGER.info("Source RAID Freebox de nouveau disponible")
            self.raids_available = True
        except Exception as err:  # An unsuccessful read
            self.note_permission("raids", err)
            # An API error is not proof of permanent hardware incapability.
            if self.raids_available:
                _LOGGER.info("Source RAID Freebox indisponible")
            self.raids_available = False

    async def update_home_devices(self, now: datetime | None = None) -> None:
        from .repairs import async_clear_home_permission_issue, async_home_permission_denied, is_structured_permission_denial

        if not self.home_granted or self.closing:
            return
        if self._home_update_lock.locked():
            _LOGGER.debug("Poll Home déjà en cours, cycle ignoré")
            return
        async with self._home_update_lock:
            try:
                home: HomeObservations = self.home
                home_nodes = await home.get_home_nodes()
                if self.closing:
                    return
                if not isinstance(home_nodes, list):
                    raise ValueError("Invalid Home collection")
                devices: dict[str, Any] = {}
                new_device = False
                for home_node in home_nodes:
                    if home_node["category"] in HOME_COMPATIBLE_CATEGORIES:
                        node_id = home_node["id"]
                        if node_id not in self.home_devices:
                            new_device = True
                        devices[node_id] = home_node

                from .availability import home_node_reachable
                for node_id in self.home_devices.keys() | devices.keys():
                    node = devices.get(node_id)
                    self.note_source(("home_node", node_id),
                                     node is not None and home_node_reachable(node), "Appareil Home")
                self.home_devices = devices
                self.home_snapshot_known = True
                async_clear_home_permission_issue(self.hass, self.entry_id)
                if not self.home_available:
                    _LOGGER.info("Source Freebox Home de nouveau disponible")
                self.home_available = True
                async_dispatcher_send(self.hass, self.signal_home_device_update)
                if new_device:
                    async_dispatcher_send(self.hass, self.signal_home_device_new)
                _LOGGER.debug("Mise à jour des appareils domestiques terminée")
            except Exception as err:  # Source failure; cancellation still propagates.
                if self.closing and is_shutdown_error(err, self):
                    return
                if self.home_available:
                    _LOGGER.info("Source Freebox Home indisponible")
                self.home_available = False
                async_dispatcher_send(self.hass, self.signal_home_device_update)
                if isinstance(err, HttpRequestError) and is_permission_denied(err):
                    # Reload after granting rights rechecks the explicit gate.
                    # Transient failures must not permanently disable polling.
                    self.home_granted = False
                    if is_structured_permission_denial(err):
                        async_home_permission_denied(self.hass, self.entry_id)
                    _LOGGER.warning("L'accès aux appareils domestiques n'est pas autorisé ; "
                        "dans Freebox OS → Gestion des accès → Applications, vérifiez les droits Homexa")

    @async_action_errors
    async def reboot(self) -> None:
        system: SystemActions = self._api.system
        await system.reboot()
        _LOGGER.info("Redémarrage de la Freebox effectué")

    async def async_read(self, read: Callable[[], Awaitable[_ReadT]]) -> _ReadT:
        """Own entity I/O until it completes, independently of HA task teardown."""
        if self.closing:
            raise NotOpenError("Freebox connection is closing")
        task = asyncio.current_task()
        if task is not None:
            self.read_tasks.add(task)
        try:
            return await read()
        finally:
            if task is not None:
                self.read_tasks.discard(task)

    async def async_poll(self, update: Callable[[], Awaitable[None]]) -> None:
        """Own only integration interval jobs, not initial reads or entity actions."""
        if self.closing:
            return
        task = asyncio.current_task()
        if task is not None:
            self.poll_tasks.add(task)
        try:
            await update()
        finally:
            if task is not None:
                self.poll_tasks.discard(task)

    def resume_reads_after_failed_unload(self) -> None:
        """Do not reopen admission while another owner is closing the SDK."""
        if not self._closed and not self._close_lock.locked():
            self.closing = False

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            # Stop new interval reads, drain current ones, then close the public SDK.
            self.closing = True
            pending = (self.poll_tasks | self.read_tasks) - {asyncio.current_task()}
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            try:
                await self._api.close()
            except NotOpenError:
                # Preserve historical suppression, but do not treat a missing
                # access object as proof that the SDK session was closed.
                return
            _LOGGER.debug("Connexion à la Freebox fermée")
            # Failed close remains retryable; only memoize a normal SDK return.
            self._closed = True

    @property
    def device_info(self) -> DeviceInfo:
        info = DeviceInfo(
            configuration_url=f"https://{self._host}:{self._port}/",
            connections={(CONNECTION_NETWORK_MAC, self.mac)},
            identifiers={(DOMAIN, self.mac)},
            manufacturer="Freebox SAS",
            name=self.name,
            model=self.model,
            sw_version=as_version(self._sw_v),
        )
        serial = self._attrs.get("serial") if isinstance(self._attrs, dict) else None
        if isinstance(serial, str) and serial.strip():
            info["serial_number"] = serial.strip()
        return info

    def via_device_id_for(self, identifier: str | None = None) -> str | None:
        """device_id du parent (via_device_id), à la place de via_device=(DOMAIN, …) déprécié.

        Cherche d'abord (DOMAIN, identifier), puis (DOMAIN, "repeater_<identifier>"),
        sinon renvoie le device Freebox Server.
        """
        if identifier and identifier != self.mac:
            registry = dr.async_get(self.hass)
            for ident in (identifier, f"repeater_{identifier}"):
                device = get_device_by_identifier(registry, (DOMAIN, ident), self.entry_id)
                if device is not None:
                    return registry_device_id(device)
        return self.device_id

    def parent_for(
        self,
        key: str,
        name: str,
        auto_group: str | None,
        auto_link: str | None = None,
        lan_type: str | None = None,
    ) -> str | None:
        """device_id du service parent (surcharge utilisateur, sinon automatique).

        4 services : Freebox Server (défaut), Freebox Maison connectée, Freebox Player, TNT.
        `key` est la clé stable de l'appareil, utilisée par l'écran « Groupes des appareils ».
        `auto_link` (clients LAN, répéteurs) : parent automatique filaire / Wi-Fi / répéteur,
        sous le Freebox Server ; une surcharge de l'utilisateur reste prioritaire.
        `lan_type` (clients LAN) : sous-groupe de type dans « filaires » / « Wi-Fi »
        (pas de sous-groupe sous un répéteur).
        """
        from .device_groups import (
            GROUP_AUTO,
            LAN_GROUPS,
            SERVICE_CHOICES,
            to_service,
        )

        auto = to_service(auto_group)
        override = self.group_overrides.get(key) or GROUP_AUTO
        auto_value = self._auto_value(auto_link, lan_type) or auto
        if override in LAN_GROUPS:
            # Forcé dans « Clients réseau filaires » / « Clients Wi-Fi » (sous le Server).
            self.grouped_devices[key] = (name, auto_value)
            return self.lan_group_parent_id(override, lan_type)
        if override in SERVICE_CHOICES:
            self.grouped_devices[key] = (name, auto_value)
            self.used_groups.add(override)
            return self.group_device_id(override)
        if auto_link and auto == GROUP_SERVER_SERVICE:
            parent_id = self.lan_link_parent_id(auto_link, lan_type)
            if parent_id:
                self.grouped_devices[key] = (name, auto_value)
                return parent_id
        self.grouped_devices[key] = (name, auto)
        self.used_groups.add(auto)
        return self.group_device_id(auto)

    def _auto_value(self, link: str | None, lan_type: str | None) -> str | None:
        """Classement automatique affiché (« auto : … ») pour un lien et un type."""
        from .device_groups import LINK_REPEATER, link_group, lan_type_group

        if not link:
            return None
        if link.startswith(LINK_REPEATER):
            return f"{LINK_REPEATER}{self.repeater_canonical_mac(link[len(LINK_REPEATER):])}"
        group = link_group(link)
        if group and lan_type:
            return lan_type_group(group, lan_type)
        return group

    def repeater_names(self) -> dict[str, str]:
        """MAC canonique -> nom du répéteur (libellés de l'écran d'options)."""
        return {
            canon: str(payload.get("name") or canon)
            for canon, payload in (self.repeaters or {}).items()
        }

    # --- Clients filaires / Wi-Fi ------------------------------------------

    def lan_group_parent_id(self, group: str, lan_type: str | None = None) -> str | None:
        """Groupe filaire / Wi-Fi, ou son sous-groupe de type (créé à la demande)."""
        from .device_groups import LAN_TYPES, async_get_lan_type_device, lan_type_group

        self.used_groups.add(group)
        group_id = self.group_device_id(group)
        if lan_type not in LAN_TYPES:
            return group_id
        key = lan_type_group(group, lan_type)
        self.used_groups.add(key)
        if key not in self.group_device_ids:
            self.group_device_ids[key] = async_get_lan_type_device(
                self.hass, self.entry_id, self.mac, group, lan_type, group_id
            )
        return self.group_device_ids[key]

    def lan_link_parent_id(self, link: str | None, lan_type: str | None = None) -> str | None:
        """device_id du parent d'un lien : (sous-)groupe filaire, (sous-)groupe Wi-Fi ou répéteur."""
        from .device_groups import (
            GROUP_LAN_WIFI,
            GROUP_LAN_WIRED,
            LINK_REPEATER,
            LINK_WIFI,
            LINK_WIRED,
        )

        if not link:
            return None
        if link.startswith(LINK_REPEATER):
            canon = self.repeater_canonical_mac(link[len(LINK_REPEATER):])
            registry = dr.async_get(self.hass)
            device = get_device_by_identifier(
                registry, (DOMAIN, f"repeater_{canon}"), self.entry_id
            )
            if device is not None:
                identifier = registry_device_id(device)
                if identifier is not None:
                    self.repeater_device_ids[canon] = identifier
                    return identifier  # clients Wi-Fi du répéteur
            # Répéteur pas encore enregistré : « Clients Wi-Fi » en attendant.
            link = LINK_WIFI
        group = {LINK_WIRED: GROUP_LAN_WIRED, LINK_WIFI: GROUP_LAN_WIFI}.get(link)
        if group is None:
            return None
        return self.lan_group_parent_id(group, lan_type)

    def lan_client_type(self, mac: str, name: str | None = None) -> str:
        """Type d'un client réseau : forcé dans les options, sinon automatique (statique)."""
        from .device_groups import NET_OTHER, lan_client_type

        key = f"mac:{mac.lower()}"
        device = self.devices.get(mac)
        if device is None:
            norm = normalize_mac(mac)
            device = next(
                (d for m, d in self.devices.items() if normalize_mac(m) == norm), None
            )
        auto = lan_client_type(device) if device else NET_OTHER
        self.lan_client_types[key] = (name or key, auto)
        return self.type_overrides.get(key) or auto

    def lan_client_parent(self, mac: str, name: str) -> str | None:
        """Parent d'un client LAN : surcharge, sinon filaire / Wi-Fi box (par type) / répéteur."""
        from .device_groups import GROUP_SERVER

        link = self.lan_links.get(normalize_mac(mac))
        lan_type = self.lan_client_type(mac, name)
        return self.parent_for(f"mac:{mac.lower()}", name, GROUP_SERVER, link, lan_type)

    def _is_lan_client(self, device: dict[str, Any]) -> bool:
        return device.get("attrs") is None and not self.is_repeater_host(device)

    def _link_from_registry(self, mac: str) -> str | None:
        """Classement déjà appliqué (redémarrage) : déduit du via_device actuel."""
        from .device_groups import (
            GROUP_LAN_WIFI,
            GROUP_LAN_WIRED,
            LINK_REPEATER,
            LINK_WIFI,
            LINK_WIRED,
            LAN_TYPE_GROUPS,
            group_identifier,
        )

        registry = dr.async_get(self.hass)
        device = get_device_by_connection(
            registry, (CONNECTION_NETWORK_MAC, mac.lower()), self.entry_id
        )
        if device is not None and any(
            len(i) >= 1 and i[0] == DOMAIN for i in getattr(device, "identifiers", None) or ()
        ):
            # Appareil Homexa (répéteur portant encore la MAC d'un client, Player…) :
            # son parent n'est pas le classement du client.
            return None
        via = getattr(device, "via_device_id", None)
        if not via:
            return None
        for group, link in ((GROUP_LAN_WIRED, LINK_WIRED), (GROUP_LAN_WIFI, LINK_WIFI)):
            parent = get_device_by_identifier(
                registry, group_identifier(self.mac, group), self.entry_id
            )
            if parent is not None and parent.id == via:
                return link
        # Sous-groupes de type (« Serveurs (filaire) »…) : lien de leur groupe parent.
        for sub_key, (group, _lan_type) in LAN_TYPE_GROUPS.items():
            parent = get_device_by_identifier(
                registry, group_identifier(self.mac, sub_key), self.entry_id
            )
            if parent is not None and parent.id == via:
                return LINK_WIRED if group == GROUP_LAN_WIRED else LINK_WIFI
        for canon in self.repeaters:
            parent = get_device_by_identifier(
                registry, (DOMAIN, f"repeater_{canon}"), self.entry_id
            )
            if parent is not None and parent.id == via:
                return f"{LINK_REPEATER}{canon}"
        return None

    def _update_lan_links(self) -> None:
        """Classe chaque client LAN (filaire / Wi-Fi box / répéteur), sans va-et-vient."""
        from .device_groups import lan_client_link, next_lan_link

        def repeater_of(mac: str) -> str:
            return self.repeater_aliases.get(normalize_mac(mac), "")

        for mac, device in self.devices.items():
            if not self._is_lan_client(device):
                continue
            norm = normalize_mac(mac)
            current = self.lan_links.get(norm)
            if current is None:
                current = self._link_from_registry(mac)
            seen = lan_client_link(device, repeater_of)
            new, pending = next_lan_link(
                current, seen, bool(device.get("active")), self._lan_link_pending.get(norm)
            )
            if pending:
                self._lan_link_pending[norm] = pending
            else:
                self._lan_link_pending.pop(norm, None)
            if new:
                if current and new != current:
                    _LOGGER.debug("Client %s : %s -> %s", mac, current, new)
                self.lan_links[norm] = new

    def _stale_repeater_idents(self, device_entry: Any) -> set[tuple[str, str]]:
        """Identifiants « repeater_<MAC> » d'un appareil qui n'est plus un répéteur reconnu."""
        stale: set[tuple[str, str]] = set()
        for ident in getattr(device_entry, "identifiers", None) or ():
            if len(ident) < 2 or ident[0] != DOMAIN or not isinstance(ident[1], str):
                continue
            if ident[1].startswith("repeater_") and normalize_mac(ident[1][9:]) not in self.repeater_aliases:
                stale.add(ident)
        return stale

    def _is_current_repeater_device(self, device_entry: Any) -> bool:
        for ident in getattr(device_entry, "identifiers", None) or ():
            if (
                len(ident) >= 2
                and ident[0] == DOMAIN
                and isinstance(ident[1], str)
                and ident[1].startswith("repeater_")
                and normalize_mac(ident[1][9:]) in self.repeater_aliases
            ):
                return True
        return False

    def _lan_client_device(self, registry: Any, mac: str) -> Any:
        """Appareil de ce client LAN, après nettoyage des restes d'anciennes versions.

        - MAC d'un client (non répéteur) restée dans les connexions d'un appareil
          répéteur (Grange…) : retirée du répéteur (sinon l'entité du client est rattachée
          au répéteur et le client ne peut pas avoir son propre appareil) ;
        - identifiant « repeater_<MAC> » périmé (ancien faux répéteur) : retiré, l'appareil
          redevient un client réseau ordinaire.
        Renvoie None pour un appareil Homexa légitime (Server, Player…) ou absent.
        """
        connection = (CONNECTION_NETWORK_MAC, str(mac).lower())
        entry = get_device_by_connection(registry, connection, self.entry_id)
        if entry is None:
            return None
        if self._is_current_repeater_device(entry):
            conns = {
                c for c in entry.connections
                if not (c[0] == CONNECTION_NETWORK_MAC and normalize_mac(c[1]) == normalize_mac(mac))
            }
            if conns != set(entry.connections) and conns:
                _LOGGER.warning(
                    "MAC %s (client réseau) retirée de l'appareil répéteur %s",
                    mac, getattr(entry, "name_by_user", None) or entry.name,
                )
                registry.async_update_device(entry.id, new_connections=conns)
            return None
        stale = self._stale_repeater_idents(entry)
        if stale:
            idents = set(entry.identifiers) - stale
            _LOGGER.warning(
                "Appareil %s (%s) : identifiant répéteur périmé %s retiré (client réseau)",
                getattr(entry, "name_by_user", None) or entry.name, mac, sorted(i[1] for i in stale),
            )
            entry = registry.async_update_device(entry.id, new_identifiers=idents) or entry
        if any(len(i) >= 1 and i[0] == DOMAIN for i in entry.identifiers):
            return None  # appareil Homexa (Server, Player, disque…)
        return entry

    def ensure_lan_client_device(self, mac: str) -> str | None:
        """Crée / range l'appareil d'un client LAN dont l'entité est active ; renvoie son id.

        Les entités device_tracker (ScannerEntity) ne créent pas d'appareil elles-mêmes
        (device_info figé à None par HA) : Homexa le crée ici, rangé sous « Clients réseau
        filaires › type », « Clients Wi-Fi › type » ou le répéteur.
        """
        from .device_groups import lan_client_name

        norm = normalize_mac(mac)
        device = self.devices.get(mac) or next(
            (d for m, d in self.devices.items() if normalize_mac(m) == norm), None
        )
        self.lan_device_ids.pop(norm, None)
        self.lan_client_placements.pop(norm, None)
        if not self.create_lan_devices:
            # Option désactivée : comportement Home Assistant (ScannerEntity). Aucun
            # appareil créé, aucun appareil existant (même d'une autre intégration)
            # déplacé ; pas de groupes de clients ni de « Clients connectés ».
            return None
        if device is None or not self._is_lan_client(device):
            return None
        registry = dr.async_get(self.hass)
        connection = (CONNECTION_NETWORK_MAC, str(mac).lower())
        if foreign_device_with_connection(registry, connection, self.entry_id) is not None:
            # MAC déjà portée par un appareil d'une autre intégration (Shelly, ESPHome…)
            # ou auquel Home Assistant a relié le tracker : jamais renommé, modifié,
            # rattaché à cette entrée, re-parenté ni déplacé dans un groupe Homexa.
            return None
        entry = self._lan_client_device(registry, mac)
        if entry is not None and shared_with_other_entries(entry, self.entry_id):
            return None
        if entry is None:
            if not self.create_lan_devices or norm not in self.tracked_lan_macs:
                return None
            if get_device_by_connection(
                registry, (CONNECTION_NETWORK_MAC, str(mac).lower()), self.entry_id
            ) is not None:
                return None  # MAC portée par un appareil Homexa (Player…)
            name = lan_client_name(device)
            entry = registry.async_get_or_create(
                config_entry_id=self.entry_id,
                connections={(CONNECTION_NETWORK_MAC, str(mac).lower())},
                manufacturer=device.get("vendor_name") or None,
                name=name,
            )
            _LOGGER.debug("Appareil créé pour le client réseau %s (%s)", name, mac)
        identifier = registry_device_id(entry)
        if identifier is None:
            return None
        parent_id = self.lan_client_parent(mac, lan_client_name(device))
        if parent_id and parent_id != identifier and entry.via_device_id != parent_id:
            registry.async_update_device(identifier, via_device_id=parent_id)
        self.lan_device_ids[norm] = identifier
        placement = self._placement_of(parent_id)
        if placement:
            self.lan_client_placements[norm] = placement
        return identifier

    def _placement_of(self, parent_id: str | None) -> str | None:
        """Clé du (sous-)groupe ou du répéteur correspondant à un device_id parent."""
        from .device_groups import LAN_GROUPS, LAN_TYPE_GROUPS, LINK_REPEATER

        if not parent_id:
            return None
        for key, device_id in self.group_device_ids.items():
            if device_id == parent_id and (key in LAN_GROUPS or key in LAN_TYPE_GROUPS):
                return key
        for canon, device_id in self.repeater_device_ids.items():
            if device_id == parent_id:
                return f"{LINK_REPEATER}{canon}"
        return None

    def lan_group_members(self, key: str) -> list[dict[str, Any]]:
        """Clients LAN rangés dans ce (sous-)groupe (ou ses sous-groupes / répéteurs).

        « lan_wired » : ses sous-groupes ; « lan_wifi » : ses sous-groupes et les clients
        des répéteurs (rangés sous « Clients Wi-Fi ») ; « lan_wired_net_servers » : lui seul.
        """
        from .device_groups import GROUP_LAN_WIFI, LAN_GROUPS, LINK_REPEATER

        members: list[dict[str, Any]] = []
        by_norm = {normalize_mac(m): d for m, d in self.devices.items()}
        for norm, placement in self.lan_client_placements.items():
            if key in LAN_GROUPS:
                match = placement == key or placement.startswith(f"{key}_") or (
                    key == GROUP_LAN_WIFI and placement.startswith(LINK_REPEATER)
                )
            else:
                match = placement == key
            if match and norm in by_norm:
                members.append(by_norm[norm])
        return members

    def _sync_lan_client_parents(self) -> None:
        """Crée / déplace les appareils des clients LAN quand leur parent change."""
        try:
            from .device_groups import async_clean_repeater_connections

            async_clean_repeater_connections(self.hass, self.entry_id, self.mac, self.repeaters)
        except Exception:  # noqa: BLE001 — le nettoyage ne doit jamais bloquer le poll
            _LOGGER.debug("Nettoyage des connexions des répéteurs impossible", exc_info=True)
        for mac, device in self.devices.items():
            if not self._is_lan_client(device):
                continue
            try:
                self.ensure_lan_client_device(mac)
            except Exception:  # noqa: BLE001 — un client ne doit pas bloquer les autres
                _LOGGER.debug("Rangement de l'appareil %s impossible", mac, exc_info=True)
        self._prune_empty_lan_groups()

    def _prune_empty_lan_groups(self) -> None:
        """Retire les (sous-)groupes filaires / Wi-Fi devenus vides (jamais un non vide)."""
        from .device_groups import LAN_GROUPS, LAN_TYPE_GROUPS, _has_entities
        from .registry_compat import entry_devices, remove_device

        registry = dr.async_get(self.hass)
        for keys in (list(LAN_TYPE_GROUPS), list(LAN_GROUPS)):  # sous-groupes d'abord
            children = {d.via_device_id for d in entry_devices(registry, self.entry_id)}
            for key in keys:
                device_id = self.group_device_ids.get(key)
                if device_id is None:
                    continue
                if device_id in children or _has_entities(self.hass, device_id):
                    continue
                remove_device(registry, device_id)
                self.group_device_ids.pop(key, None)
                self.used_groups.discard(key)

    def group_device_id(self, group: str | None) -> str | None:
        """device_id du service ; repli sur le Freebox Server."""
        from .device_groups import GROUP_HOME, GROUP_PLAYER, GROUP_TNT, LAN_GROUPS

        if group in LAN_GROUPS:
            if group not in self.group_device_ids:
                from .device_groups import async_get_lan_group_device

                self.group_device_ids[group] = async_get_lan_group_device(
                    self.hass, self.entry_id, self.mac, group, self.device_id
                )
            return self.group_device_ids[group]

        if group == GROUP_HOME:
            if group not in self.group_device_ids:
                from .device_groups import async_get_group_device

                self.group_device_ids[group] = async_get_group_device(
                    self.hass, self.entry_id, self.mac, group
                )
            return self.group_device_ids[group]
        if group in (GROUP_PLAYER, GROUP_TNT):
            registry = dr.async_get(self.hass)
            idents = (
                [(DOMAIN, "programme_tnt_fr")]
                if group == GROUP_TNT
                else [(DOMAIN, i) for i in sorted(self.player_identifiers)]
            )
            for ident in idents:
                device = get_device_by_identifier(registry, ident, self.entry_id)
                if device is not None:
                    return registry_device_id(device)
        return self.device_id

    @property
    def signal_device_new(self) -> str:
        return f"{DOMAIN}-{self._host}-device-new"

    @property
    def signal_home_device_new(self) -> str:
        return f"{DOMAIN}-{self._host}-home-device-new"

    @property
    def signal_device_update(self) -> str:
        return f"{DOMAIN}-{self._host}-device-update"

    @property
    def signal_sensor_update(self) -> str:
        return f"{DOMAIN}-{self._host}-sensor-update"

    @property
    def signal_home_device_update(self) -> str:
        return f"{DOMAIN}-{self._host}-home-device-update"

    @property
    def sensors(self) -> dict[str, Any]:
        return {**self.sensors_temperature, **self.sensors_connection}

    @property
    def call(self) -> Call:
        return self._api.call

    @property
    def wifi(self) -> Wifi:
        return self._api.wifi

    @property
    def home(self) -> Home:
        return self._api.home


# Entrée de configuration typée : le routeur est rangé dans entry.runtime_data.
type FreeboxConfigEntry = ConfigEntry[FreeboxRouter]
