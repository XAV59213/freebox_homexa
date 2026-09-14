"""Boutons Freebox : box + touches télécommande Player."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, option_remote_code
from .media_player import player_device_info
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FreeboxButtonEntityDescription(ButtonEntityDescription):
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

# Touches de la télécommande Free (API remote.send_key).
# enabled=False : pavé numérique et couleurs désactivés par défaut.
PLAYER_REMOTE_BUTTONS: tuple[tuple[str, str, str, bool], ...] = (
    ("home", "Accueil", "mdi:home", True),
    ("back", "Retour", "mdi:arrow-u-left-top", True),
    ("ok", "OK", "mdi:checkbox-blank-circle-outline", True),
    ("up", "Haut", "mdi:chevron-up", True),
    ("down", "Bas", "mdi:chevron-down", True),
    ("left", "Gauche", "mdi:chevron-left", True),
    ("right", "Droite", "mdi:chevron-right", True),
    ("tv", "TV", "mdi:television", True),
    ("mute", "Muet", "mdi:volume-off", True),
    ("vol_inc", "Volume +", "mdi:volume-plus", True),
    ("vol_dec", "Volume -", "mdi:volume-minus", True),
    ("prgm_inc", "Programme +", "mdi:skip-next", True),
    ("prgm_dec", "Programme -", "mdi:skip-previous", True),
    ("play", "Lecture", "mdi:play-pause", True),
    ("info", "Info", "mdi:information-outline", True),
    ("epg", "Guide TV", "mdi:television-guide", True),
    ("list", "Liste", "mdi:format-list-bulleted", True),
    ("red", "Rouge", "mdi:square", False),
    ("green", "Vert", "mdi:square", False),
    ("yellow", "Jaune", "mdi:square", False),
    ("blue", "Bleu", "mdi:square", False),
    ("0", "0", "mdi:numeric-0", False),
    ("1", "1", "mdi:numeric-1", False),
    ("2", "2", "mdi:numeric-2", False),
    ("3", "3", "mdi:numeric-3", False),
    ("4", "4", "mdi:numeric-4", False),
    ("5", "5", "mdi:numeric-5", False),
    ("6", "6", "mdi:numeric-6", False),
    ("7", "7", "mdi:numeric-7", False),
    ("8", "8", "mdi:numeric-8", False),
    ("9", "9", "mdi:numeric-9", False),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    entities: list[ButtonEntity] = [
        FreeboxButton(router, description) for description in BUTTON_DESCRIPTIONS
    ]

    try:
        players = await router._api.player.get_players() or []
    except Exception as err:
        _LOGGER.debug("Players indisponibles pour les boutons remote : %s", err)
        players = []

    for player in players:
        for key, name, icon, enabled in PLAYER_REMOTE_BUTTONS:
            entities.append(
                FreeboxPlayerRemoteButton(
                    router, player, entry, key, name, icon, enabled
                )
            )

    async_add_entities(entities, True)
    _LOGGER.debug("%s boutons ajoutés pour %s", len(entities), router.mac)


class FreeboxButton(ButtonEntity):
    """Bouton d'action sur le Freebox Server."""

    entity_description: FreeboxButtonEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self, router: FreeboxRouter, description: FreeboxButtonEntityDescription
    ) -> None:
        self.entity_description = description
        self._router = router
        self._attr_device_info = router.device_info
        self._attr_unique_id = f"{router.mac} {description.name}"
        self._attr_name = description.name

    async def async_press(self) -> None:
        try:
            await self.entity_description.async_press(self._router)
        except Exception as err:
            _LOGGER.error(
                "Échec bouton '%s' : %s", self.entity_description.name, err
            )


class FreeboxPlayerRemoteButton(ButtonEntity):
    """Touche de la télécommande réseau du Player."""

    _attr_has_entity_name = True

    def __init__(
        self,
        router: FreeboxRouter,
        player: dict[str, Any],
        entry: ConfigEntry,
        key: str,
        name: str,
        icon: str,
        enabled_by_default: bool,
    ) -> None:
        self._router = router
        self._entry = entry
        self._player_id = player["id"]
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{router.mac}_player_{self._player_id}_key_{key}"
        self._attr_device_info = player_device_info(router, player)
        self._attr_entity_registry_enabled_default = enabled_by_default

    async def async_press(self) -> None:
        remote_code = option_remote_code(self._entry, self._player_id)
        if not remote_code:
            _LOGGER.warning(
                "Code télécommande manquant pour le Player %s. "
                "Paramètres → Homexa → Configurer.",
                self._player_id,
            )
            return
        try:
            await self._router._api.remote.send_key(
                code=str(remote_code), key=self._key
            )
        except Exception as err:
            _LOGGER.error(
                "Touche %s échouée sur Player %s : %s",
                self._key,
                self._player_id,
                err,
            )
