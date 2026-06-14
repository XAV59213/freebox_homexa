# custom_components/freebox_homexa/router.py
"""Représentation du routeur Freebox et de ses appareils et capteurs dans Home Assistant."""

from __future__ import annotations

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
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    API_VERSION,
    APP_DESC,
    CONNECTION_SENSORS_KEYS,
    HOME_COMPATIBLE_CATEGORIES,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=120)


async def get_api(hass: HomeAssistant, host: str) -> Freepybox:
    """Obtient l'API Freebox avec un dossier de stockage sécurisé.

    Cette version corrige définitivement le NotADirectoryError :
    - Crée un vrai dossier
    - Supprime automatiquement tout fichier bloquant du même nom
    """
    storage_dir = hass.config.path(".storage", "freebox_homexa")

    def _ensure_directory():
        if os.path.isfile(storage_dir):
            try:
                os.remove(storage_dir)
                _LOGGER.warning(
                    "Fichier bloquant '%s' supprimé automatiquement (cause du NotADirectoryError)",
                    storage_dir,
                )
            except Exception as err:
                _LOGGER.error("Impossible de supprimer le fichier bloquant : %s", err)

        Path(storage_dir).mkdir(parents=True, exist_ok=True)

    await hass.async_add_executor_job(_ensure_directory)

    token_file = str(Path(storage_dir) / f"{slugify(host)}.conf")
    return Freepybox(APP_DESC, token_file, API_VERSION)


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
            (matcher := re.search(r"Request failed \(APIResponse: (.+)\)", str(err)))
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
        self._api = api
        self.name: str = freebox_config["model_info"]["pretty_name"]
        self.mac: str = freebox_config["mac"]
        self.model: str = freebox_config["model_info"]["name"]
        self._sw_v: str = freebox_config["firmware_version"]
        self._attrs: dict[str, Any] = {}

        self.supports_hosts = True
        self.devices: dict[str, dict[str, Any]] = {}
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

    async def update_all(self, now: datetime | None = None) -> None:
        await self.update_device_trackers()
        await self.update_sensors()
        await self.update_home_devices()

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

    async def update_home_devices(self) -> None:
        if not self.home_granted:
            return
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
            sw_version=self._sw_v,
        )

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
