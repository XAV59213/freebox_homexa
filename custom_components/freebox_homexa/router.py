# custom_components/freebox_homexa/router.py
"""Représentation du routeur Freebox et de ses appareils et capteurs dans Home Assistant."""
# DESCRIPTION: Ce fichier définit la classe FreeboxRouter, qui gère la connexion à la Freebox,
#              la mise à jour des données des appareils, capteurs et services associés.
# OBJECTIF: Centraliser la gestion de la Freebox pour une intégration fluide dans Home Assistant.

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import datetime, timedelta
import os
from pathlib import Path
import re
from typing import Any

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

from .const import DOMAIN, API_VERSION, APP_DESC, CONNECTION_SENSORS_KEYS, HOME_COMPATIBLE_CATEGORIES

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)  # Changé à 10s pour refresh plus fréquent (améliore les transitions d'alarme)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Freebox Homexa from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load()
    if stored_data is None:
        _LOGGER.info("Aucune configuration Freebox existante trouvée. Création d'une nouvelle configuration.")
        stored_data = {}

    hass.data[DOMAIN]["config"] = stored_data
    hass.data[DOMAIN]["store"] = store

    async def save_data():
        """Sauvegarde les données de configuration avant l'arrêt de Home Assistant."""
        _LOGGER.debug("Sauvegarde des données de configuration Freebox en cours...")
        await store.async_save(hass.data[DOMAIN]["config"])
        _LOGGER.info("Données de configuration Freebox sauvegardées avec succès.")

    api = await get_api(hass, entry.data[CONF_HOST])
    try:
        await api.open(entry.data[CONF_HOST], entry.data.get("port", 80))
        _LOGGER.debug(f"Connexion établie avec la Freebox à {entry.data[CONF_HOST]}.")
    except HttpRequestError as err:
        _LOGGER.error(f"Erreur lors de la connexion à la Freebox {entry.data[CONF_HOST]}: {err}")
        raise ConfigEntryNotReady from err

    freebox_config = await api.system.get_config()

    # Création explicite du device parent (hub Freebox) pour éviter l'erreur via_device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, freebox_config["mac"])},
        connections={(dr.CONNECTION_NETWORK_MAC, freebox_config["mac"])},
        manufacturer="Freebox SAS",
        name="Freebox Server",
        model=freebox_config["model_info"]["pretty_name"],
        sw_version=freebox_config["firmware_version"],
    )

    router = FreeboxRouter(hass, entry, api, freebox_config)
    await router.update_all()

    entry.async_on_unload(
        async_track_time_interval(hass, router.update_all, SCAN_INTERVAL)
    )

    hass.data[DOMAIN][entry.unique_id] = router
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_reboot(call: ServiceCall) -> None:
        """Gère le service de redémarrage de la Freebox."""
        _LOGGER.warning(
            "Le service 'freebox.reboot' est déprécié et remplacé par une entité bouton dédiée ; "
            "veuillez utiliser cette entité pour redémarrer la Freebox."
        )
        await router.reboot()
        await save_data()
        _LOGGER.info("Redémarrage de la Freebox effectué avec succès.")

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, async_reboot)

    async def async_close_connection(event: Event) -> None:
        """Ferme la connexion à la Freebox lors de l'arrêt de Home Assistant."""
        _LOGGER.debug("Fermeture de la connexion à la Freebox en cours...")
        await router.close()
        await save_data()
        _LOGGER.info("Connexion Freebox fermée proprement.")

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    async def async_freebox_player_remote(call: ServiceCall) -> None:
        """Gère le contrôle à distance du Freebox Player."""
        code_list = call.data.get("code", "")
        if not code_list:
            _LOGGER.warning("Aucun code fourni pour la télécommande du Freebox Player.")
            return

        async with aiohttp.ClientSession() as session:
            for code in code_list.split(','):
                url = PLAYER_PATH_TEMPLATE.format(
                    host=entry.data[CONF_HOST],
                    remote_code=entry.data["remote_code"],
                    key=code.strip()
                )
                try:
                    async with session.get(url, ssl=False) as response:
                        if response.status != 200:
                            _LOGGER.error(f"Échec de l'envoi de la commande '{code}' : HTTP {response.status}")
                        else:
                            _LOGGER.debug(f"Commande '{code}' envoyée avec succès au Freebox Player.")
                except aiohttp.ClientError as err:
                    _LOGGER.error(f"Erreur lors de l'envoi de la commande '{code}' : {err}")

    hass.services.async_register(DOMAIN, "remote", async_freebox_player_remote)
    _LOGGER.info("L'intégration Freebox a été configurée avec succès.")
    return True

def is_json(json_str: str) -> bool:
    """Valide si une chaîne est un JSON valide.

    Args:
        json_str: Chaîne à vérifier.

    Returns:
        bool: True si la chaîne est un JSON valide, False sinon.
    """
    try:
        json.loads(json_str)
    except (ValueError, TypeError) as err:
        _LOGGER.error(f"Échec de la validation JSON pour '{json_str}': {err}")
        return False
    return True

async def get_api(hass: HomeAssistant, host: str) -> Freepybox:
    """Obtient l'API Freebox pour l'hôte spécifié.

    Crée le chemin de stockage si nécessaire et initialise l'API avec le fichier de token.

    Args:
        hass: Instance de Home Assistant.
        host: Hôte de la Freebox.

    Returns:
        Freepybox: Instance de l'API Freebox.
    """
    freebox_path = Store(hass, STORAGE_VERSION, STORAGE_KEY).path
    if not os.path.exists(freebox_path):
        await hass.async_add_executor_job(os.makedirs, freebox_path)
    token_file = Path(f"{freebox_path}/{slugify(host)}.conf")
    return Freepybox(APP_DESC, token_file, API_VERSION)

async def get_hosts_list_if_supported(
    fbx_api: Freepybox,
) -> tuple[bool, list[dict[str, Any]]]:
    """Récupère la liste des hôtes si supportée.

    La liste des hôtes n'est pas disponible en mode bridge.

    Args:
        fbx_api: Instance de l'API Freebox.

    Returns:
        tuple[bool, list[dict[str, Any]]]: Support des hôtes (bool) et liste des hôtes.
    """
    supports_hosts: bool = True
    fbx_devices: list[dict[str, Any]] = []
    try:
        fbx_devices = await fbx_api.lan.get_hosts_list() or []
    except HttpRequestError as err:
        if (
            (matcher := re.search(r"Request failed \(APIResponse: (.+)\)", str(err)))
            and is_json(json_str := matcher.group(1))
            and (json_resp := json.loads(json_str)).get("error_code") == "nodev"
        ):
            supports_hosts = False
            _LOGGER.debug(
                "La liste des hôtes n'est pas disponible en mode bridge (%s)",
                json_resp.get("msg"),
            )
        else:
            raise
    return supports_hosts, fbx_devices

class FreeboxRouter:
    """Représentation du routeur Freebox dans Home Assistant.

    Gère la connexion à la Freebox, les mises à jour des données, et les interactions avec les appareils et capteurs.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: Freepybox,
        freebox_config: Mapping[str, Any],
    ) -> None:
        """Initialise une instance du routeur Freebox.

        Args:
            hass: Instance de Home Assistant.
            entry: Entrée de configuration pour l'intégration Freebox.
            api: Instance de l'API Freebox.
            freebox_config: Configuration système de la Freebox.
        """
        self.hass = hass
        self._host = entry.data[CONF_HOST]
        self._port = entry.data[CONF_PORT]
        self._api = api
        self.name: str = freebox_config["model_info"]["pretty_name"]
        self.mac: str = freebox_config["mac"]
        self.model: str = freebox_config["model_info"]["name"]
        self._sw_v: str = freebox_config["firmware_version"]
        self._attrs: dict[str, Any] = {}

        # Initialisation des données
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
        self.listeners: list[Callable[[], None]] = []
        _LOGGER.debug(f"Routeur Freebox {self.name} initialisé")

    # SECTION: Méthodes de mise à jour
    async def update_all(self, now: datetime | None = None) -> None:
        """Met à jour toutes les données de la Freebox.

        Appelle les méthodes de mise à jour pour les appareils, capteurs et appareils domestiques.

        Args:
            now: Heure actuelle (facultatif).
        """
        await self.update_device_trackers()
        await self.update_sensors()
        await self.update_home_devices()

    async def update_device_trackers(self) -> None:
        """Met à jour les données des appareils connectés.

        Récupère la liste des hôtes et ajoute le routeur lui-même comme appareil.
        """
        new_device = False
        fbx_devices: list[dict[str, Any]] = []

        if self.supports_hosts:
            self.supports_hosts, fbx_devices = await get_hosts_list_if_supported(self._api)

        # Ajoute le routeur lui-même
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
        _LOGGER.debug("Mise à jour des appareils connectés terminée")

    async def update_sensors(self) -> None:
        """Met à jour les capteurs système et de connexion.

        Récupère les données système, de connexion, et met à jour les capteurs de température et de débit.
        """
        try:
            syst_datas: dict[str, Any] = await self._api.system.get_config()
            for sensor in syst_datas["sensors"]:
                self.sensors_temperature[sensor["name"]] = sensor.get("value")

            connection_datas: dict[str, Any] = await self._api.connection.get_status()
            for sensor_key in CONNECTION_SENSORS_KEYS:
                self.sensors_connection[sensor_key] = connection_datas.get(sensor_key, 0.0)

            uptime_val = syst_datas.get("uptime_val", 0)
            if uptime_val == 0:
                _LOGGER.warning("Uptime val is 0 or None, setting to 0 seconds")
            uptime_seconds = uptime_val
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
        """Met à jour les données des disques connectés à la Freebox.

        Récupère et structure les informations sur les disques et leurs partitions.
        """
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
        """Met à jour les données des configurations RAID si supportées.

        Vérifie si la Freebox supporte les RAID et récupère les données correspondantes.
        """
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
        """Met à jour les données des appareils domestiques (alarme, lumière, capteur, etc.).

        Récupère et met à jour les appareils compatibles avec Freebox Home.
        """
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

    # SECTION: Méthodes d'action
    async def reboot(self) -> None:
        """Redémarre la Freebox.

        Envoie une commande de redémarrage via l'API.
        """
        try:
            await self._api.system.reboot()
            _LOGGER.info("Redémarrage de la Freebox effectué")
        except HttpRequestError as err:
            _LOGGER.error(f"Échec du redémarrage de la Freebox: {err}")

    async def close(self) -> None:
        """Ferme la connexion à la Freebox.

        Supprime les exceptions si la connexion n'est pas ouverte.
        """
        with suppress(NotOpenError):
            await self._api.close()
            _LOGGER.debug("Connexion à la Freebox fermée")

    # SECTION: Propriétés du routeur
    @property
    def device_info(self) -> DeviceInfo:
        """Retourne les informations sur l'appareil pour le registre de Home Assistant.

        Returns:
            DeviceInfo: Informations sur le routeur Freebox.
        """
        return DeviceInfo(
            configuration_url=f"https://{self._host}:{self._port}/",
            connections={(CONNECTION_NETWORK_MAC, self.mac)},
            identifiers={(DOMAIN, self.mac)},
            manufacturer="Freebox SAS",
            name=self.name,
            model=self.model,
            sw_version=self._sw_v,
        )

    # SECTION: Signaux de mise à jour
    @property
    def signal_device_new(self) -> str:
        """Signal pour les nouveaux appareils connectés.

        Returns:
            str: Nom du signal pour les nouveaux appareils.
        """
        return f"{DOMAIN}-{self._host}-device-new"

    @property
    def signal_home_device_new(self) -> str:
        """Signal pour les nouveaux appareils domestiques.

        Returns:
            str: Nom du signal pour les nouveaux appareils domestiques.
        """
        return f"{DOMAIN}-{self._host}-home-device-new"

    @property
    def signal_device_update(self) -> str:
        """Signal pour les mises à jour des appareils connectés.

        Returns:
            str: Nom du signal pour les mises à jour des appareils.
        """
        return f"{DOMAIN}-{self._host}-device-update"

    @property
    def signal_sensor_update(self) -> str:
        """Signal pour les mises à jour des capteurs.

        Returns:
            str: Nom du signal pour les mises à jour des capteurs.
        """
        return f"{DOMAIN}-{self._host}-sensor-update"

    @property
    def signal_home_device_update(self) -> str:
        """Signal pour les mises à jour des appareils domestiques.

        Returns:
            str: Nom du signal pour les mises à jour des appareils domestiques.
        """
        return f"{DOMAIN}-{self._host}-home-device-update"

    # SECTION: Accès aux données
    @property
    def sensors(self) -> dict[str, Any]:
        """Retourne les capteurs combinés de température et de connexion.

        Returns:
            dict[str, Any]: Dictionnaire des capteurs.
        """
        return {**self.sensors_temperature, **self.sensors_connection}

    # SECTION: Accès aux APIs spécifiques
    @property
    def call(self) -> Call:
        """Retourne l'API pour les appels téléphoniques.

        Returns:
            Call: Instance de l'API pour les appels.
        """
        return self._api.call

    @property
    def wifi(self) -> Wifi:
        """Retourne l'API pour la gestion du WiFi.

        Returns:
            Wifi: Instance de l'API WiFi.
        """
        return self._api.wifi

    @property
    def home(self) -> Home:
        """Retourne l'API pour la gestion des appareils domestiques.

        Returns:
            Home: Instance de l'API Home.
        """
        return self._api.home
