"""Support pour les caméras Freebox dans Home Assistant."""
# DESCRIPTION: Gestion des caméras Freebox avec streaming et détection de mouvement
# OBJECTIF: Intégrer les flux vidéo et la gestion de la détection de mouvement des caméras Freebox

from __future__ import annotations
from urllib.parse import quote

import logging
from typing import Any

from homeassistant.components.camera import CameraEntityFeature
from homeassistant.components.ffmpeg.camera import (
    CONF_EXTRA_ARGUMENTS,
    CONF_INPUT,
    DEFAULT_ARGUMENTS,
    FFmpegCamera,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_DETECTION, DOMAIN, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

# SECTION: Configuration des entités
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités de caméras Freebox.

    Initialise la détection automatique des nouvelles caméras et les ajoute à Home Assistant.

    Args:
        hass: Instance de Home Assistant.
        entry: Entrée de configuration pour l'intégration Freebox.
        async_add_entities: Fonction pour ajouter des entités à Home Assistant.
    """
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    tracked: set[str] = set()

    @callback
    def update_callback() -> None:
        """Callback pour ajouter de nouvelles caméras détectées."""
        add_entities(hass, router, async_add_entities, tracked)

    # Écoute les nouveaux appareils domestiques et déclenche la mise à jour
    router.listeners.append(
        async_dispatcher_connect(hass, router.signal_home_device_new, update_callback)
    )
    update_callback()

    # Récupération de la plateforme actuelle pour les services
    entity_platform.async_get_current_platform()

# SECTION: Fonction utilitaire pour ajouter des entités
@callback
def add_entities(
    hass: HomeAssistant,
    router: FreeboxRouter,
    async_add_entities: AddEntitiesCallback,
    tracked: set[str],
) -> None:
    """Ajoute de nouvelles entités de caméras à partir des données du routeur.

    Args:
        hass: Instance de Home Assistant.
        router: Routeur Freebox.
        async_add_entities: Fonction pour ajouter des entités.
        tracked: Ensemble des identifiants de caméras déjà suivis.
    """
    new_tracked: list[FreeboxCamera] = []

    for nodeid, node in router.home_devices.items():
        if (node["category"] != FreeboxHomeCategory.CAMERA) or (nodeid in tracked):
            continue
        new_tracked.append(FreeboxCamera(hass, router, node))
        tracked.add(nodeid)
        _LOGGER.debug(f"Caméra {node['label']} ajoutée pour {router.name}")

    if new_tracked:
        async_add_entities(new_tracked, True)

# SECTION: Classe de la caméra Freebox
class FreeboxCamera(FreeboxHomeEntity, FFmpegCamera):
    """Représentation d'une caméra Freebox dans Home Assistant.

    Hérite de FreeboxHomeEntity et FFmpegCamera pour gérer les flux vidéo et la détection de mouvement.
    """

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        """Initialise une caméra Freebox.

        Args:
            hass: Instance de Home Assistant.
            router: Routeur Freebox gérant cette entité.
            node: Données de la caméra Freebox.
        """
        super().__init__(hass, router, node)

        # Gestion du mot de passe avec caractères spéciaux
        pathpass = node["props"]["Pass"]
        path = node["props"]["Stream"].replace(pathpass, quote(pathpass, safe=''))

        # Configuration pour FFmpegCamera
        device_info = {
            CONF_NAME: node["label"].strip(),
            CONF_INPUT: str(path),
            CONF_EXTRA_ARGUMENTS: DEFAULT_ARGUMENTS,
        }
        FFmpegCamera.__init__(self, hass, device_info)

        # Fonctionnalités supportées
        self._supported_features = (
            CameraEntityFeature.ON_OFF | CameraEntityFeature.STREAM
        )

        # Commande pour la détection de mouvement
        self._command_motion_detection = self.get_command_id(
            node["type"]["endpoints"], "slot", ATTR_DETECTION
        )

        # Attributs d'état supplémentaires
        self._attr_extra_state_attributes = {}
        self.update_node(node)
        _LOGGER.debug(f"Caméra {self._name} initialisée avec succès")

    async def async_enable_motion_detection(self) -> None:
        """Active la détection de mouvement sur la caméra.

        Envoie la commande pour activer la détection via l'API Freebox.
        """
        if self._command_motion_detection is None:
            _LOGGER.error(f"Détection de mouvement non supportée pour {self._node_id}")
            return
        try:
            await self.set_home_endpoint_value(self._command_motion_detection, True)
            self._attr_motion_detection_enabled = True
            _LOGGER.info(f"Détection de mouvement activée pour {self._node_id}")
        except Exception as err:
            _LOGGER.error(f"Échec de l'activation de la détection de mouvement pour {self._node_id}: {err}")

    async def async_disable_motion_detection(self) -> None:
        """Désactive la détection de mouvement sur la caméra.

        Envoie la commande pour désactiver la détection via l'API Freebox.
        """
        if self._command_motion_detection is None:
            _LOGGER.error(f"Détection de mouvement non supportée pour {self._node_id}")
            return
        try:
            await self.set_home_endpoint_value(self._command_motion_detection, False)
            self._attr_motion_detection_enabled = False
            _LOGGER.info(f"Détection de mouvement désactivée pour {self._node_id}")
        except Exception as err:
            _LOGGER.error(f"Échec de la désactivation de la détection de mouvement pour {self._node_id}: {err}")

    async def async_update_signal(self) -> None:
        """Met à jour les données de la caméra à partir du routeur Freebox.

        Récupère les dernières informations et met à jour l'état dans Home Assistant.
        """
        try:
            node = self._router.home_devices.get(self._id)
            if node is None:
                _LOGGER.warning(f"Caméra {self._id} non trouvée dans les données du routeur")
                return
            self.update_node(node)
            self.async_write_ha_state()
            _LOGGER.debug(f"Caméra {self._name} mise à jour avec succès")
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour de la caméra {self._node_id}: {err}")

    def update_node(self, node: dict[str, Any]) -> None:
        """Met à jour les paramètres de la caméra à partir des données du nœud.

        Args:
            node: Données mises à jour de la caméra.
        """
        self._name = node["label"].strip()

        # Mise à jour du statut de streaming
        self._attr_is_streaming = node["status"] == "active"

        # Mise à jour des attributs d'état supplémentaires
        for endpoint in filter(lambda x: x["ep_type"] == "signal", node["show_endpoints"]):
            self._attr_extra_state_attributes[endpoint["name"]] = endpoint["value"]

        # Mise à jour de l'état de la détection de mouvement
        self._attr_motion_detection_enabled = self._attr_extra_state_attributes.get(ATTR_DETECTION, False)
