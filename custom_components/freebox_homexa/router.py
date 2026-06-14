"""Représentation du routeur Freebox."""

import logging
import os
import re
import json
from pathlib import Path
from datetime import timedelta
from typing import Any

from freebox_api import Freepybox
from freebox_api.exceptions import HttpRequestError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .const import DOMAIN, APP_DESC, API_VERSION

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=120)


async def get_api(hass: HomeAssistant, host: str, port: int = 80):
    """Obtient l'API Freebox."""
    storage_dir = hass.config.path(".storage", "freebox_homexa")
    Path(storage_dir).mkdir(parents=True, exist_ok=True)

    token_file = str(Path(storage_dir) / f"{slugify(host)}.conf")
    api = Freepybox(APP_DESC, token_file, api_version=API_VERSION)

    await api.open(host, port)
    return api


async def get_hosts_list_if_supported(fbx_api: Freepybox):
    """Récupère la liste des hôtes si supportée (utilisée dans config_flow)."""
    try:
        devices = await fbx_api.lan.get_hosts_list() or []
        return True, devices
    except HttpRequestError as err:
        if "nodev" in str(err):
            _LOGGER.debug("Liste des hôtes non disponible")
            return False, []
        raise
    except Exception as err:
        _LOGGER.warning("Erreur lors de la récupération des hôtes : %s", err)
        return False, []


class FreeboxRouter:
    """Représentation du routeur Freebox."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: Freepybox,
    ) -> None:
        self.hass = hass
        self._host = entry.data[CONF_HOST]
        self._port = entry.data.get(CONF_PORT, 80)
        self._api = api
        self._sw_v = None
        self._model = None
        self._name = None
        self._mac = None

    @property
    def device_info(self) -> DeviceInfo:
        scheme = "http" if self._port == 80 else "https"
        return DeviceInfo(
            configuration_url=f"{scheme}://{self._host}:{self._port}/",
            connections={(CONNECTION_NETWORK_MAC, self.mac)},
            identifiers={(DOMAIN, self.mac)},
            manufacturer="Freebox SAS",
            name=self.name,
            model=self.model,
            sw_version=self._sw_v,
        )

    async def async_update(self) -> None:
        """Mise à jour des informations du routeur."""
        try:
            config = await self._api.system.get_config()
            self._sw_v = config.get("firmware_version")
            self._model = config.get("model_info", {}).get("pretty_name")
            self._name = self._model
            self._mac = config.get("mac")
        except Exception as err:
            _LOGGER.error("Erreur mise à jour routeur : %s", err)
