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
    """Obtient l'API Freebox avec un dossier de stockage sécurisé."""
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
        self._port = entry.data.get(CONF_PORT, 80)   # ← Correction ajoutée
        self._api = api
        self._sw_v: str | None = None
        self._model: str | None = None
        self._name: str | None = None
        self._mac: str | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Informations sur l'appareil pour le registre des appareils."""
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

    # === Ajoute ici tout le reste de ta classe FreeboxRouter ===
    # (propriétés name, model, mac, async_update, capteurs, etc.)
    # Le code que tu avais déjà peut rester tel quel.
