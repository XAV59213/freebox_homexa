"""Represent the Freebox router and its devices and sensors."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

from freebox_api import Freepybox
from freebox_api.api.call import Call
from freebox_api.api.home import Home
from freebox_api.api.wifi import Wifi
from freebox_api.exceptions import HttpRequestError, NotOpenError
import aiohttp  # Ajouté pour gérer le timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .const import (
    API_VERSION,
    APP_DESC,
    CONNECTION_SENSORS_KEYS,
    DOMAIN,
    HOME_COMPATIBLE_CATEGORIES,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

def is_json(json_str: str) -> bool:
    """Validate if a string is a JSON value."""
    try:
        json.loads(json_str)
        return True
    except (ValueError, TypeError):
        return False

async def get_api(hass: HomeAssistant, host: str) -> Freepybox:
    """Get the Freebox API."""
    freebox_path = Store(hass, STORAGE_VERSION, STORAGE_KEY).path

    if not os.path.exists(freebox_path):
        await hass.async_add_executor_job(os.makedirs, freebox_path)

    token_file = Path(f"{freebox_path}/{slugify(host)}.conf")
    return Freepybox(APP_DESC, token_file, API_VERSION)

async def get_hosts_list_if_supported(
    fbx_api: Freepybox,
) -> tuple[bool, list[dict[str, Any]]]:
    """Hosts list is not supported when Freebox is in bridge mode."""
    supports_hosts: bool = True
    fbx_devices: list[dict[str, Any]] = []
    try:
        fbx_devices = await fbx_api.lan.get_hosts_list()
        if fbx_devices is None:
            _LOGGER.debug("No hosts returned by API for %s", fbx_api.host)
            fbx_devices = []
    except HttpRequestError as err:
        if (
            (matcher := re.search(r"Request failed \(APIResponse: (.+)\)", str(err)))
            and is_json(json_str := matcher.group(1))
            and (json_resp := json.loads(json_str)).get("error_code") == "nodev"
        ):
            supports_hosts = False
            _LOGGER.debug(
                "Host list not available in bridge mode (%s)", json_resp.get("msg")
            )
        else:
            raise

    return supports_hosts, fbx_devices

class FreeboxRouter:
    """Representation of a Freebox router."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: Freepybox,
        freebox_config: Mapping[str, Any],
    ) -> None:
        """Initialize a Freebox router."""
        self.hass = hass
        self._host = entry.data[CONF_HOST]
        self._port = entry.data[CONF_PORT]
        self._api: Freepybox = api
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
        self.home_devices: dict[str, dict[str, Any]] = {}
        self.listeners: list[Callable[[], None]] = []

    async def update_all(self, now: datetime | None = None) -> None:
        """Update all Freebox platforms in parallel."""
        await asyncio.gather(
            self.update_device_trackers(),
            self.update_sensors(),
            self.update_home_devices(),
            return_exceptions=True,  # Log errors instead of failing entirely
        )

    async def update_device_trackers(self) -> None:
        """Update Freebox devices."""
        new_device = False
        fbx_devices: list[dict[str, Any]] = []

        if self.supports_hosts:
            self.supports_hosts, fbx_devices = await get_hosts_list_if_supported(
                self._api
            )

        # Add the Freebox itself
        fbx_devices.append(
            {
                "primary_name": self.name,
                "l2ident": {"id": self.mac},
                "vendor_name": "Freebox SAS",
                "host_type": "router",
                "active": True,
                "attrs": self._attrs,
                "model": self.model,
            }
        )

        for fbx_device in fbx_devices:
            device_mac = fbx_device["l2ident"]["id"]
            if device_mac not in self.devices:
                new_device = True
            self.devices[device_mac] = fbx_device

        async_dispatcher_send(self.hass, self.signal_device_update)
        if new_device:
            async_dispatcher_send(self.hass, self.signal_device_new)

    async def update_sensors(self) -> None:
        """Update Freebox sensors."""
        # System sensors
        try:
            syst_datas: dict[str, Any] = await self._api.system.get_config()
        except HttpRequestError as e:
            _LOGGER.error("Failed to fetch system config for %s: %s", self.name, e)
            return

        for sensor in syst_datas.get("sensors", []):
            self.sensors_temperature[sensor["name"]] = sensor.get("value", 0)

        # Connection sensors
        try:
            connection_datas: dict[str, Any] = await self._api.connection.get_status()
        except HttpRequestError as e:
            _LOGGER.error("Failed to fetch connection status for %s: %s", self.name, e)
            return

        for sensor_key in CONNECTION_SENSORS_KEYS:
            self.sensors_connection[sensor_key] = connection_datas.get(sensor_key, 0.0)

        self._attrs = {
            "IPv4": connection_datas.get("ipv4"),
            "IPv6": connection_datas.get("ipv6"),
            "connection_type": connection_datas.get("media"),
            "uptime": datetime.fromtimestamp(
                round(datetime.now().timestamp()) - syst_datas.get("uptime_val", 0)
            ),
            "firmware_version": self._sw_v,
            "serial": syst_datas.get("serial"),
        }

        try:
            self.call_list = await self._api.call.get_calls_log() or []
        except HttpRequestError as e:
            _LOGGER.warning("Failed to fetch call logs for %s: %s", self.name, e)
            self.call_list = []

        await asyncio.gather(
            self._update_disks_sensors(),
            self._update_raids_sensors(),
            return_exceptions=True,
        )

        async_dispatcher_send(self.hass, self.signal_sensor_update)

    async def _update_disks_sensors(self) -> None:
        """Update Freebox disks."""
        try:
            fbx_disks: list[dict[str, Any]] = await self._api.storage.get_disks()
            if fbx_disks is None:
                _LOGGER.debug("No disks returned by API for %s", self.name)
                fbx_disks = []
        except HttpRequestError as e:
            _LOGGER.warning("Failed to fetch disks for %s: %s", self.name, e)
            return

        for fbx_disk in fbx_disks:
            disk: dict[str, Any] = {**fbx_disk}
            disk_part: dict[int, dict[str, Any]] = {}
            for fbx_disk_part in fbx_disk.get("partitions", []):
                disk_part[fbx_disk_part["id"]] = fbx_disk_part
            disk["partitions"] = disk_part
            self.disks[fbx_disk["id"]] = disk

    async def _update_raids_sensors(self) -> None:
        """Update Freebox raids."""
        if not self.supports_raid:
            return

        try:
            fbx_raids: list[dict[str, Any]] = await self._api.storage.get_raids()
            if fbx_raids is None:
                _LOGGER.debug("No RAIDs returned by API for %s", self.name)
                fbx_raids = []
        except HttpRequestError:
            self.supports_raid = False
            _LOGGER.warning("Router %s API does not support RAID", self.name)
            return

        for fbx_raid in fbx_raids:
            self.raids[fbx_raid["id"]] = fbx_raid

    async def update_home_devices(self) -> None:
        """Update Home devices (alarm, light, sensor, switch, remote ...)."""
        if not self.home_granted:
            return

        try:
            # Ajout d'un timeout personnalisé de 60 secondes
            timeout = aiohttp.ClientTimeout(total=60)
            async with timeout:
                home_nodes: list[dict[str, Any]] = await self.home.get_home_nodes() or []
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout lors de la récupération des appareils domestiques pour %s", self.name)
            return
        except HttpRequestError as e:
            self.home_granted = False
            _LOGGER.warning(
                "Home access not granted for %s at %s:%s - %s",
                self.name,
                self._host,
                self._port,
                e,
            )
            return
        except Exception as e:
            _LOGGER.error("Erreur inattendue lors de la mise à jour des appareils domestiques pour %s: %s", self.name, e)
            return

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

    async def reboot(self) -> None:
        """Reboot the Freebox."""
        try:
            await self._api.system.reboot()
        except HttpRequestError as e:
            _LOGGER.error("Failed to reboot %s: %s", self.name, e)

    async def close(self) -> None:
        """Close the connection."""
        with suppress(NotOpenError):
            await self._api.close()

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
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
        """Event specific per Freebox entry to signal new device."""
        return f"{DOMAIN}-{self._host}-device-new"

    @property
    def signal_home_device_new(self) -> str:
        """Event specific per Freebox entry to signal new home device."""
        return f"{DOMAIN}-{self._host}-home-device-new"

    @property
    def signal_device_update(self) -> str:
        """Event specific per Freebox entry to signal updates in devices."""
        return f"{DOMAIN}-{self._host}-device-update"

    @property
    def signal_sensor_update(self) -> str:
        """Event specific per Freebox entry to signal updates in sensors."""
        return f"{DOMAIN}-{self._host}-sensor-update"

    @property
    def signal_home_device_update(self) -> str:
        """Event specific per Freebox entry to signal update in home devices."""
        return f"{DOMAIN}-{self._host}-home-device-update"

    @property
    def sensors(self) -> dict[str, Any]:
        """Return sensors."""
        return {**self.sensors_temperature, **self.sensors_connection}

    @property
    def call(self) -> Call:
        """Return the call API."""
        return self._api.call

    @property
    def wifi(self) -> Wifi:
        """Return the wifi API."""
        return self._api.wifi

    @property
    def home(self) -> Home:
        """Return the home API."""
        return self._api.home
