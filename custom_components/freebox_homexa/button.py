"""Boutons Freebox : box + télécommande et apps Player."""

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

# Apps ouvertes via POST player/.../control/open (pas besoin du code télécommande).
PLAYER_APP_BUTTONS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("youtube", "YouTube", "mdi:youtube", "https://www.youtube.com", True),
    ("netflix", "Netflix", "mdi:netflix", "https://www.netflix.com", True),
    ("disney", "Disney+", "mdi:star-four-points", "https://www.disneyplus.com", True),
    ("prime", "Prime Video", "mdi:amazon", "https://www.primevideo.com", True),
    ("browser", "Navigateur", "mdi:web", "https://www.google.com", True),
    ("canal", "Canal+", "mdi:ticket-confirmation", "https://www.canalplus.com", False),
    ("max", "Max", "mdi:play-box", "https://play.max.com", False),
    ("appletv", "Apple TV", "mdi:apple", "https://tv.apple.com", False),
)


def _player_api_version(player: dict[str, Any]) -> str:
    text = str(player.get("api_version") or "6").strip().lower()
    if text.startswith("v"):
        text = text[1:]
    major = text.split(".")[0] or "6"
    return f"v{major}"


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
        for key, name, icon, url, enabled in PLAYER_APP_BUTTONS:
            entities.append(
                FreeboxPlayerAppButton(
                    router, player, key, name, icon, url, enabled
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


class FreeboxPlayerAppButton(ButtonEntity):
    """Ouvre une app / URL sur le Freebox Player."""

    _attr_has_entity_name = True

    def __init__(
        self,
        router: FreeboxRouter,
        player: dict[str, Any],
        key: str,
        name: str,
        icon: str,
        url: str,
        enabled_by_default: bool,
    ) -> None:
        self._router = router
        self._player_id = player["id"]
        self._api_version = _player_api_version(player)
        self._url = url
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{router.mac}_player_{self._player_id}_app_{key}"
        self._attr_device_info = player_device_info(router, player)
        self._attr_entity_registry_enabled_default = enabled_by_default

    async def async_press(self) -> None:
        path = f"player/{self._player_id}/api/{self._api_version}/control/open"
        try:
            await self._router._api.player._access.post(path, {"url": self._url})
        except Exception as err:
            _LOGGER.error(
                "Impossible d'ouvrir %s sur Player %s : %s",
                self._attr_name,
                self._player_id,
                err,
            )
