"""Support pour les alarmes Freebox."""
# DESCRIPTION: Gestion des panneaux de contrôle d'alarme Freebox dans Home Assistant
# OBJECTIF: Permettre l'armement, le désarmement et le déclenchement de l'alarme Freebox

from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FreeboxHomeCategory
from .entity import FreeboxHomeEntity
from .router import FreeboxRouter

import logging
_LOGGER = logging.getLogger(__name__)

# SECTION: Mapping des états de l'alarme Freebox aux états Home Assistant
FREEBOX_TO_STATUS = {
    "alarm1_arming": AlarmControlPanelState.ARMING,  # Alarme en cours d'activation (zone 1)
    "alarm2_arming": AlarmControlPanelState.ARMING,  # Alarme en cours d'activation (zone 2)
    "alarm1_armed": AlarmControlPanelState.ARMED_AWAY,  # Alarme activée en mode absent (zone 1)
    "alarm2_armed": AlarmControlPanelState.ARMED_HOME,  # Alarme activée en mode présent (zone 2)
    "alarm1_alert_timer": AlarmControlPanelState.TRIGGERED,  # Alarme déclenchée (zone 1)
    "alarm2_alert_timer": AlarmControlPanelState.TRIGGERED,  # Alarme déclenchée (zone 2)
    "alert": AlarmControlPanelState.TRIGGERED,  # Alarme générale déclenchée
    "idle": AlarmControlPanelState.DISARMED,  # Alarme désactivée
}

# SECTION: Configuration des entités
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités de panneau d'alarme Freebox.

    Args:
        hass: Instance de Home Assistant.
        entry: Entrée de configuration pour l'intégration Freebox.
        async_add_entities: Fonction pour ajouter des entités à Home Assistant.
    """
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]

    # Ajoute les entités d'alarme pour chaque appareil de catégorie 'alarm'
    async_add_entities(
        [
            FreeboxAlarm(hass, router, node)
            for node in router.home_devices.values()
            if node["category"] == FreeboxHomeCategory.ALARM
        ],
        True,
    )

# SECTION: Classe de l'entité Alarme
class FreeboxAlarm(FreeboxHomeEntity, AlarmControlPanelEntity):
    """Représentation d'une alarme Freebox dans Home Assistant.

    Hérite de FreeboxHomeEntity et AlarmControlPanelEntity pour combiner les fonctionnalités
    de gestion des appareils Freebox et des panneaux de contrôle d'alarme.
    """

    _attr_code_arm_required = False  # Pas besoin de code pour armer l'alarme

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        """Initialise une alarme Freebox.

        Args:
            hass: Instance de Home Assistant.
            router: Routeur Freebox gérant cette entité.
            node: Données de l'appareil d'alarme Freebox.
        """
        super().__init__(hass, router, node)

        # Récupération des identifiants de commande pour les actions d'alarme
        self._command_trigger = self.get_command_id(
            node["type"]["endpoints"], "slot", "trigger"
        )
        self._command_arm_away = self.get_command_id(
            node["type"]["endpoints"], "slot", "alarm1"
        )
        self._command_arm_home = self.get_command_id(
            node["type"]["endpoints"], "slot", "alarm2"
        )
        self._command_disarm = self.get_command_id(
            node["type"]["endpoints"], "slot", "off"
        )
        self._command_state = self.get_command_id(
            node["type"]["endpoints"], "signal", "state"
        )

        # Définition des fonctionnalités supportées en fonction des commandes disponibles
        self._attr_supported_features = (
            AlarmControlPanelEntityFeature.ARM_AWAY
            | (AlarmControlPanelEntityFeature.ARM_HOME if self._command_arm_home else 0)
            | AlarmControlPanelEntityFeature.TRIGGER
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Envoie la commande pour désarmer l'alarme.

        Args:
            code: Code optionnel (non utilisé car _attr_code_arm_required est False).
        """
        if self._command_disarm is None:
            _LOGGER.error(f"Commande de désarmement non supportée pour {self._node_id}")
            return
        await self.set_home_endpoint_value(self._command_disarm)
        _LOGGER.info(f"Alarme désarmée pour {self._node_id}")

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Envoie la commande pour armer l'alarme en mode absent.

        Args:
            code: Code optionnel (non utilisé).
        """
        if self._command_arm_away is None:
            _LOGGER.error(f"Commande d'armement en mode absent non supportée pour {self._node_id}")
            return
        await self.set_home_endpoint_value(self._command_arm_away)
        _LOGGER.info(f"Alarme armée en mode absent pour {self._node_id}")

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Envoie la commande pour armer l'alarme en mode présent.

        Args:
            code: Code optionnel (non utilisé).
        """
        if self._command_arm_home is None:
            _LOGGER.error(f"Commande d'armement en mode présent non supportée pour {self._node_id}")
            return
        await self.set_home_endpoint_value(self._command_arm_home)
        _LOGGER.info(f"Alarme armée en mode présent pour {self._node_id}")

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Envoie la commande pour déclencher l'alarme.

        Args:
            code: Code optionnel (non utilisé).
        """
        if self._command_trigger is None:
            _LOGGER.error(f"Commande de déclenchement non supportée pour {self._node_id}")
            return
        await self.set_home_endpoint_value(self._command_trigger)
        _LOGGER.info(f"Alarme déclenchée pour {self._node_id}")

    async def async_update(self) -> None:
        """Met à jour l'état de l'alarme à partir de la Freebox.

        Récupère l'état actuel via l'API et mappe cet état à celui de Home Assistant.
        """
        if self._command_state is None:
            _LOGGER.error(f"Commande d'état non disponible pour {self._node_id}")
            self._attr_alarm_state = None
            return
        try:
            state: str | None = await self.get_home_endpoint_value(self._command_state)
            self._attr_alarm_state = FREEBOX_TO_STATUS.get(state, AlarmControlPanelState.DISARMED)
            _LOGGER.debug(f"État de l'alarme mis à jour pour {self._node_id}: {self._attr_alarm_state}")
        except Exception as err:
            _LOGGER.error(f"Échec de la mise à jour de l'état de l'alarme pour {self._node_id}: {err}")
            self._attr_alarm_state = None
