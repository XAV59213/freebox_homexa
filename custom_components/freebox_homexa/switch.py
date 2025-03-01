"""Support pour les interrupteurs Freebox Delta, Revolution et Mini 4K dans Home Assistant."""
# DESCRIPTION: Ce fichier définit des interrupteurs pour contrôler des fonctionnalités comme le WiFi et l'inversion des volets.
# OBJECTIF: Intégrer des interrupteurs dans Home Assistant pour gérer des aspects spécifiques de la Freebox.

from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Any
import os
from pathlib import Path

from freebox_api.exceptions import InsufficientPermissionsError
from homeassistant.util import slugify
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION, STORAGE_KEY
from .router import FreeboxRouter
from .entity import FreeboxHomeEntity

_LOGGER = logging.getLogger(__name__)

# SECTION: Définitions des interrupteurs
@dataclass
class FreeboxSwitchEntityDescription(SwitchEntityDescription):
    """Description des entités interrupteurs Freebox."""
    pass

SWITCH_DESCRIPTIONS = [
    FreeboxSwitchEntityDescription(
        key="wifi",
        name="Freebox WiFi",
        entity_category=EntityCategory.CONFIG,
    )
]

# SECTION: Configuration des entités
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités interrupteurs pour la Freebox.

    Ajoute des interrupteurs pour le WiFi et l'inversion des volets.

    Args:
        hass: Instance de Home Assistant.
        entry: Entrée de configuration pour l'intégration Freebox.
        async_add_entities: Fonction pour ajouter des entités à Home Assistant.
    """
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    entities = []

    # Ajoute les interrupteurs d'inversion pour les volets et ouvrants
    for nodeid, node in router.home_devices.items():
        if node["category"] in {"shutter", "opener"}:
            entities.append(FreeboxShutterInvertSwitchEntity(hass, router, node))

    # Ajoute l'interrupteur WiFi
    for entity_description in SWITCH_DESCRIPTIONS:
        entities.append(FreeboxSwitch(router, entity_description))

    async_add_entities(entities, True)
    _LOGGER.debug(f"{len(entities)} entités interrupteurs ajoutées pour {router.name}")

# SECTION: Classe pour l'interrupteur WiFi
class FreeboxSwitch(SwitchEntity):
    """Représentation de l'interrupteur WiFi de la Freebox.

    Permet d'activer ou de désactiver le WiFi via l'API Freebox.
    """

    def __init__(
        self, router: FreeboxRouter, entity_description: FreeboxSwitchEntityDescription
    ) -> None:
        """Initialise l'interrupteur WiFi.

        Args:
            router: Routeur Freebox associé.
            entity_description: Description de l'entité interrupteur.
        """
        self.entity_description = entity_description
        self._router = router
        self._attr_device_info = router.device_info
        self._attr_unique_id = f"{router.mac} {entity_description.name}"
        _LOGGER.debug(f"Interrupteur WiFi initialisé pour {router.name}")

    async def _async_set_state(self, enabled: bool) -> None:
        """Active ou désactive le WiFi.

        Envoie la commande via l'API Freebox.

        Args:
            enabled: État à définir (True pour activer, False pour désactiver).
        """
        try:
            await self._router.wifi.set_global_config({"enabled": enabled})
            _LOGGER.info(f"WiFi {'activé' if enabled else 'désactivé'} pour {self._router.name}")
        except InsufficientPermissionsError:
            _LOGGER.warning(
                "Home Assistant n'a pas les permissions nécessaires pour modifier les paramètres WiFi de la Freebox. "
                "Veuillez vérifier la documentation pour configurer les permissions."
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Active le WiFi."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Désactive le WiFi."""
        await self._async_set_state(False)

    async def async_update(self) -> None:
        """Met à jour l'état de l'interrupteur WiFi.

        Récupère l'état actuel du WiFi via l'API.
        """
        try:
            data = await self._router.wifi.get_global_config()
            self._attr_is_on = bool(data["enabled"])
            _LOGGER.debug(f"État du WiFi récupéré: {'activé' if self._attr_is_on else 'désactivé'}")
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour de l'état du WiFi: {err}")
            self._attr_is_on = None

# SECTION: Classe pour l'interrupteur d'inversion des volets
class FreeboxShutterInvertSwitchEntity(FreeboxHomeEntity, SwitchEntity):
    """Représentation de l'interrupteur d'inversion pour les volets Freebox.

    Permet d'inverser le positionnement des volets via un fichier de configuration.
    """

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]) -> None:
        """Initialise l'interrupteur d'inversion pour un volet.

        Args:
            hass: Instance de Home Assistant.
            router: Routeur Freebox.
            node: Données du volet.
        """
        super().__init__(hass, router, node)
        self._attr_unique_id = f"{self._attr_unique_id}_InvertSwitch"
        self._attr_icon = "mdi:directions-fork"
        self._attr_name = "Inversion Positionnement"
        self._state = False

        # Chemin du fichier de configuration pour l'état d'inversion
        freebox_path = Store(hass, STORAGE_VERSION, STORAGE_KEY).path
        if not os.path.exists(freebox_path):
            os.makedirs(freebox_path)
        self._path = Path(f"{freebox_path}/{slugify(self._attr_unique_id)}.conf")

        # Chargement initial de l'état
        self._load_state()
        _LOGGER.debug(f"Interrupteur d'inversion pour {self._attr_name} initialisé")

    @property
    def translation_key(self) -> str:
        """Retourne la clé de traduction pour cette entité."""
        return "invert_switch"

    @property
    def is_on(self) -> bool | None:
        """Retourne l'état de l'interrupteur (True si activé)."""
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Active l'inversion et sauvegarde l'état."""
        try:
            await self._hass.async_add_executor_job(self._path.write_text, '1')
            self._state = True
            self.async_write_ha_state()
            _LOGGER.info(f"Inversion activée pour {self._attr_name}")
        except OSError as err:
            _LOGGER.error(f"Échec de l'activation de l'inversion pour {self._attr_name}: {err}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Désactive l'inversion et sauvegarde l'état."""
        try:
            await self._hass.async_add_executor_job(self._path.write_text, '0')
            self._state = False
            self.async_write_ha_state()
            _LOGGER.info(f"Inversion désactivée pour {self._attr_name}")
        except OSError as err:
            _LOGGER.error(f"Échec de la désactivation de l'inversion pour {self._attr_name}: {err}")

    @property
    def available(self) -> bool:
        """Retourne toujours True car l'entité est toujours disponible."""
        return True

    async def async_update(self) -> None:
        """Met à jour l'état de l'interrupteur à partir du fichier de configuration."""
        self._load_state()

    def _load_state(self) -> None:
        """Charge l'état de l'inversion à partir du fichier de configuration."""
        try:
            value = self._path.read_text().strip()
            self._state = value == "1"
            _LOGGER.debug(f"État de l'inversion chargé: {'activé' if self._state else 'désactivé'}")
        except FileNotFoundError:
            _LOGGER.debug(f"Fichier de configuration pour {self._attr_name} non trouvé, état par défaut: désactivé")
            self._state = False
        except OSError as err:
            _LOGGER.error(f"Erreur lors de la lecture du fichier pour {self._attr_name}: {err}")
            self._state = False
