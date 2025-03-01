"""Support pour les appareils Freebox (Freebox v6 et Freebox mini 4K) dans Home Assistant."""
# DESCRIPTION: Gestion des boutons pour les appareils Freebox dans Home Assistant
# OBJECTIF: Permettre des actions comme le redémarrage de la Freebox ou marquer les appels comme lus

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .router import FreeboxRouter

import logging
_LOGGER = logging.getLogger(__name__)

# SECTION: Définitions des boutons Freebox
@dataclass(frozen=True, kw_only=True)
class FreeboxButtonEntityDescription(ButtonEntityDescription):
    """Description des entités boutons Freebox.

    Hérite de ButtonEntityDescription et ajoute une fonction asynchrone pour gérer l:action du bouton.
    """
    async_press: Callable[[FreeboxRouter], Awaitable]

BUTTON_DESCRIPTIONS: tuple[FreeboxButtonEntityDescription, ...] = (
    FreeboxButtonEntityDescription(
        key="reboot",
        name="Redémarrer Freebox",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        async_press=lambda router: router.reboot(),
    ),
    FreeboxButtonEntityDescription(
        key="mark_calls_as_read",
        name="Marquer les appels comme lus",
        entity_category=EntityCategory.DIAGNOSTIC,
        async_press=lambda router: router.call.mark_calls_log_as_read(),
    ),
)

# SECTION: Configuration des entités
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configure les entités boutons Freebox.

    Crée et ajoute les entités boutons pour le redémarrage et la gestion des appels.

    Args:
        hass: Instance de Home Assistant.
        entry: Entrée de configuration pour l'intégration Freebox.
        async_add_entities: Fonction pour ajouter des entités à Home Assistant.
    """
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    entities = [
        FreeboxButton(router, description) for description in BUTTON_DESCRIPTIONS
    ]
    async_add_entities(entities, True)
    _LOGGER.debug(f"{len(entities)} entités boutons ajoutées pour {router.name} ({router.mac})")

# SECTION: Classe du bouton Freebox
class FreeboxButton(ButtonEntity):
    """Représentation d'un bouton Freebox dans Home Assistant.

    Permet d'exécuter des actions spécifiques sur la Freebox, comme le redémarrage ou marquer les appels comme lus.
    """

    entity_description: FreeboxButtonEntityDescription

    def __init__(
        self, router: FreeboxRouter, description: FreeboxButtonEntityDescription
    ) -> None:
        """Initialise un bouton Freebox.

        Args:
            router: Routeur Freebox gérant cette entité.
            description: Description de l'entité bouton.
        """
        self.entity_description = description
        self._router = router
        self._attr_device_info = router.device_info
        self._attr_unique_id = f"{router.mac} {description.name}"
        _LOGGER.debug(f"Bouton '{description.name}' initialisé pour {router.name}")

    async def async_press(self) -> None:
        """Exécute l'action associée au bouton.

        Appelle la fonction asynchrone définie dans la description du bouton et gère les éventuelles erreurs.
        """
        try:
            await self.entity_description.async_press(self._router)
            _LOGGER.info(f"Action '{self.entity_description.name}' exécutée avec succès pour {self._router.name}")
        except Exception as err:
            _LOGGER.error(f"Échec de l'exécution de l'action '{self.entity_description.name}' pour {self._router.name}: {err}")
