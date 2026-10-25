# custom_components/freebox_homexa/router.py
"""Représentation du routeur Freebox et de ses appareils et capteurs dans Home Assistant."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import json
from pathlib import Path
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any, Mapping

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
from .registry_compat import as_version, get_device_by_connection, get_device_by_identifier
from .wifi_ap import build_wifi_aps

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
    if signal is not None:
        try:
            details["wifi_signal_dbm"] = int(signal)
        except (TypeError, ValueError):
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

    def _ensure_directory():
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
    if token_file.is_file():
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
        fbx_devices = await fbx_api.lan.get_hosts_list() or []
    except HttpRequestError as err:
        if (
            (matcher := re.search(r"Request failed \\(APIResponse: (.+)\\)", str(err)))
            and (json_str := matcher.group(1))
            and (json_resp := json.loads(json_str)).get("error_code") == "nodev"
        ):
            supports_hosts = False
            _LOGGER.debug("Liste des hôtes non disponible en mode bridge")
        else:
            raise
    return supports_hosts, fbx_devices


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
        self.used_groups: set[str] = set()
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
        self.sensors_connection: dict[str, float] = {}
        self.call_list: list[dict[str, Any]] = []
        self.home_granted = True
        self.home_devices: dict[str, Any] = {}
        self.listeners: list = []

        _LOGGER.debug(f"Routeur Freebox {self.name} initialisé")

    async def _fetch_api_repeaters(self) -> None:
        """Liste /repeater/ (une entrée par répéteur physique : main_mac, sn, nom)."""
        try:
            data = await self._api.wifi._access.get("repeater/")
            self.api_repeaters_raw = data
            self.api_repeaters_error = None
        except Exception as err:  # noqa: BLE001 — API absente / droit manquant
            self.api_repeaters_raw = None
            self.api_repeaters_error = f"{type(err).__name__}: {err}"
            if not getattr(self, "_repeater_api_logged", False):
                _LOGGER.info("API /repeater/ indisponible (regroupement via lan/browser) : %s", err)
                self._repeater_api_logged = True
            return
        if isinstance(data, list):
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
        info: dict[str, Any] = {
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
        return DeviceInfo(**info)

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

        self.repeater_aliases = {
            normalize_mac(alias): canon
            for canon, payload in self.repeaters.items()
            for alias in payload.get("macs") or [canon]
        }
        if self.repeaters:
            _LOGGER.info("Répéteurs Wi-Fi détectés : %s", list(self.repeaters.keys()))
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

    def _wifi_api_error(self, key: str, path: str, err: Exception) -> None:
        """Mémorise l'erreur d'une API Wi-Fi ; journal (info) une seule fois par API."""
        first = key not in self.wifi_api_errors
        self.wifi_api_errors[key] = f"{type(err).__name__}: {err}"
        if first:
            _LOGGER.info("API Freebox %s indisponible (état « Wi-Fi Freebox ») : %s", path, err)

    async def _fetch_wifi_global_state(self) -> None:
        """/wifi/config/ (enabled, comme l'interrupteur) et /wifi/bss/ (état des BSS)."""
        try:
            config = await self._api.wifi.get_global_config() or {}
            enabled = config.get("enabled") if isinstance(config, dict) else None
            self.wifi_global_enabled = enabled if isinstance(enabled, bool) else None
            self.wifi_api_errors.pop("config", None)
        except Exception as err:  # noqa: BLE001
            self.wifi_global_enabled = None
            self._wifi_api_error("config", "wifi/config/", err)
        try:
            bss_list = await self._api.wifi.get_bss() or []
            self.wifi_api_errors.pop("bss", None)
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
        try:
            access_points = await self._api.wifi.get_ap_list() or []
            self.wifi_api_errors.pop("ap", None)
        except Exception as err:  # noqa: BLE001 — API wifi absente selon firmware
            self._wifi_api_error("ap", "wifi/ap/", err)
            access_points = []
        if not isinstance(access_points, list):
            access_points = []

        self.wifi_radio_status = []
        stations_by_mac: dict[str, dict[str, Any]] = {}
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
                stations = await self._api.wifi.get_station_list(ap_id) or []
            except HttpRequestError as err:
                _LOGGER.debug("Stations de l'AP %s indisponibles : %s", ap_id, err)
                continue
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Stations de l'AP %s illisibles : %s", ap_id, err)
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

        for mac, device in self.devices.items():
            station = stations_by_mac.get(str(mac).upper())
            if station:
                device["_wifi_station"] = station
            device["wifi"] = extract_wifi_details(device)

    async def update_all(self, now: datetime | None = None) -> None:
        await self.update_device_trackers()
        await self.update_sensors()

    async def update_device_trackers(self) -> None:
        new_device = False
        fbx_devices: list[dict[str, Any]] = []
        if self.supports_hosts:
            self.supports_hosts, fbx_devices = await get_hosts_list_if_supported(self._api)

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
        try:
            syst_datas: dict[str, Any] = await self._api.system.get_config()
            for sensor in syst_datas["sensors"]:
                self.sensors_temperature[sensor["name"]] = sensor.get("value")

            connection_datas: dict[str, Any] = await self._api.connection.get_status()
            for sensor_key in CONNECTION_SENSORS_KEYS:
                self.sensors_connection[sensor_key] = connection_datas.get(sensor_key, 0.0)

            uptime_seconds = syst_datas.get("uptime_val", 0)
            self.sensors_connection["uptime"] = uptime_seconds

            self._attrs = {
                "IPv4": connection_datas.get("ipv4"),
                "IPv6": connection_datas.get("ipv6"),
                "connection_type": connection_datas.get("media"),
                "uptime": datetime.fromtimestamp(
                    round(datetime.now().timestamp()) - uptime_seconds
                ),
                "firmware_version": self._sw_v,
                "serial": syst_datas["serial"],
            }

            self.call_list = await self._api.call.get_calls_log() or []
            await self._update_disks_sensors()
            await self._update_raids_sensors()

            async_dispatcher_send(self.hass, self.signal_sensor_update)
            _LOGGER.debug("Mise à jour des capteurs terminée")
        except HttpRequestError as err:
            _LOGGER.error(f"Erreur lors de la mise à jour des capteurs: {err}")

    async def _update_disks_sensors(self) -> None:
        try:
            fbx_disks: list[dict[str, Any]] = await self._api.storage.get_disks() or []
            for fbx_disk in fbx_disks:
                disk: dict[str, Any] = {**fbx_disk}
                disk_part: dict[int, dict[str, Any]] = {}
                for fbx_disk_part in fbx_disk.get("partitions", []):
                    disk_part[fbx_disk_part["id"]] = fbx_disk_part
                disk["partitions"] = disk_part
                self.disks[fbx_disk["id"]] = disk
            _LOGGER.debug("Mise à jour des disques terminée")
        except HttpRequestError as err:
            _LOGGER.error(f"Erreur lors de la mise à jour des disques: {err}")

    async def _update_raids_sensors(self) -> None:
        if not self.supports_raid:
            return
        try:
            fbx_raids: list[dict[str, Any]] = await self._api.storage.get_raids() or []
            for fbx_raid in fbx_raids:
                self.raids[fbx_raid["id"]] = fbx_raid
            _LOGGER.debug("Mise à jour des RAID terminée")
        except HttpRequestError:
            self.supports_raid = False
            _LOGGER.warning("L'API du routeur %s ne supporte pas les RAID", self.name)

    async def update_home_devices(self, now: datetime | None = None) -> None:
        if not self.home_granted:
            return
        if self._home_update_lock.locked():
            _LOGGER.debug("Poll Home déjà en cours, cycle ignoré")
            return
        async with self._home_update_lock:
            try:
                home_nodes: list[dict[str, Any]] = await self.home.get_home_nodes() or []
                new_device = False
                for home_node in home_nodes:
                    if home_node["category"] in HOME_COMPATIBLE_CATEGORIES:
                        node_id = home_node["id"]
                        if node_id not in self.home_devices:
                            new_device = True
                        self.home_devices[node_id] = home_node

                async_dispatcher_send(self.hass, self.signal_home_device_update)
                if new_device:
                    async_dispatcher_send(self.hass, self.signal_home_device_new)
                _LOGGER.debug("Mise à jour des appareils domestiques terminée")
            except TimeoutError:
                _LOGGER.debug("Timeout API home/nodes — prochain poll dans 15 s")
            except HttpRequestError:
                self.home_granted = False
                _LOGGER.warning("L'accès aux appareils domestiques n'est pas autorisé")

    async def reboot(self) -> None:
        try:
            await self._api.system.reboot()
            _LOGGER.info("Redémarrage de la Freebox effectué")
        except HttpRequestError as err:
            _LOGGER.error(f"Échec du redémarrage de la Freebox: {err}")

    async def close(self) -> None:
        with suppress(NotOpenError):
            await self._api.close()
            _LOGGER.debug("Connexion à la Freebox fermée")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            configuration_url=f"https://{self._host}:{self._port}/",
            connections={(CONNECTION_NETWORK_MAC, self.mac)},
            identifiers={(DOMAIN, self.mac)},
            manufacturer="Freebox SAS",
            name=self.name,
            model=self.model,
            sw_version=as_version(self._sw_v),
        )

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
                    return device.id
        return self.device_id

    def parent_for(
        self, key: str, name: str, auto_group: str | None, auto_link: str | None = None
    ) -> str | None:
        """device_id du service parent (surcharge utilisateur, sinon automatique).

        4 services : Freebox Server (défaut), Freebox Maison connectée, Freebox Player, TNT.
        `key` est la clé stable de l'appareil, utilisée par l'écran « Groupes des appareils ».
        `auto_link` (clients LAN, répéteurs) : parent automatique filaire / Wi-Fi / répéteur,
        sous le Freebox Server ; une surcharge de l'utilisateur reste prioritaire.
        """
        from .device_groups import (
            GROUP_AUTO,
            LAN_GROUPS,
            SERVICE_CHOICES,
            link_group,
            to_service,
        )

        auto = to_service(auto_group)
        override = self.group_overrides.get(key) or GROUP_AUTO
        if override in LAN_GROUPS:
            # Forcé dans « Clients réseau filaires » / « Clients Wi-Fi » (sous le Server).
            self.grouped_devices[key] = (name, link_group(auto_link) or auto)
            self.used_groups.add(override)
            return self.group_device_id(override)
        if override in SERVICE_CHOICES:
            self.grouped_devices[key] = (name, link_group(auto_link) or auto)
            self.used_groups.add(override)
            return self.group_device_id(override)
        if auto_link and auto == GROUP_SERVER_SERVICE:
            parent_id = self.lan_link_parent_id(auto_link)
            if parent_id:
                self.grouped_devices[key] = (name, link_group(auto_link) or auto)
                return parent_id
        self.grouped_devices[key] = (name, auto)
        self.used_groups.add(auto)
        return self.group_device_id(auto)

    # --- Clients filaires / Wi-Fi ------------------------------------------

    def lan_link_parent_id(self, link: str | None) -> str | None:
        """device_id du parent d'un lien : groupe filaire, groupe Wi-Fi ou répéteur."""
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
                return device.id
            # Répéteur pas encore enregistré : « Clients Wi-Fi » en attendant.
            link = LINK_WIFI
        group = {LINK_WIRED: GROUP_LAN_WIRED, LINK_WIFI: GROUP_LAN_WIFI}.get(link)
        if group is None:
            return None
        self.used_groups.add(group)
        return self.group_device_id(group)

    def lan_client_parent(self, mac: str, name: str) -> str | None:
        """Parent d'un client LAN : surcharge, sinon filaire / Wi-Fi box / répéteur."""
        from .device_groups import GROUP_SERVER

        link = self.lan_links.get(normalize_mac(mac))
        return self.parent_for(f"mac:{mac.lower()}", name, GROUP_SERVER, link)

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
            group_identifier,
        )

        registry = dr.async_get(self.hass)
        device = get_device_by_connection(
            registry, (CONNECTION_NETWORK_MAC, mac.lower()), self.entry_id
        )
        via = getattr(device, "via_device_id", None)
        if not via:
            return None
        for group, link in ((GROUP_LAN_WIRED, LINK_WIRED), (GROUP_LAN_WIFI, LINK_WIFI)):
            parent = get_device_by_identifier(
                registry, group_identifier(self.mac, group), self.entry_id
            )
            if parent is not None and parent.id == via:
                return link
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

    def _sync_lan_client_parents(self) -> None:
        """Déplace les appareils clients déjà enregistrés quand leur parent change."""
        from .device_groups import lan_client_name

        registry = dr.async_get(self.hass)
        for mac, device in self.devices.items():
            if not self._is_lan_client(device):
                continue
            entry = get_device_by_connection(
                registry, (CONNECTION_NETWORK_MAC, str(mac).lower()), self.entry_id
            )
            if entry is None or any(i[0] == DOMAIN for i in entry.identifiers):
                continue  # pas (encore) d'appareil, ou appareil Homexa (Player, répéteur…)
            parent_id = self.lan_client_parent(mac, lan_client_name(device))
            if parent_id and parent_id != entry.id and entry.via_device_id != parent_id:
                registry.async_update_device(entry.id, via_device_id=parent_id)

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
                    return device.id
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
