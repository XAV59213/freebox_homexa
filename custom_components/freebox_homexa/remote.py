"""Support for Freebox Player remote control."""

from __future__ import annotations

from functools import partial

from collections.abc import Iterable
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.remote import RemoteEntity
if TYPE_CHECKING:
    from homeassistant.components.remote.const import RemoteEntityFeature
else:
    from homeassistant.components.remote import RemoteEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .discovery import DiscoveryCandidate, async_setup_discovery
from .const import DOMAIN, option_remote_code
from .player_remote import (
    VALID_COMMANDS as PLAYER_VALID_COMMANDS,
    async_send_player_keys,
    filter_ready_players,
)
from .media_player import player_device_info
from .availability import FreeboxReachableMixin
from .router import FreeboxConfigEntry, FreeboxRouter

from .errors import async_action_errors

_LOGGER = logging.getLogger(__name__)

# Conservé pour compatibilité (importé ailleurs) : liste partagée dans player_remote.
VALID_COMMANDS = PLAYER_VALID_COMMANDS


# Une seule action / mise à jour à la fois vers la Freebox pour cette plateforme.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: FreeboxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxRouter = entry.runtime_data
    router.player_discovery_active = True
    if not router.players_initialized:
        await router.async_update_players()

    def candidates() -> Iterable[DiscoveryCandidate]:
        valid_players, _ = filter_ready_players(router.players, log_skipped=False)
        for player in valid_players:
            yield str(player["id"]), partial(FreeboxRemote, router, player, entry)

    async_setup_discovery(hass, entry, router, [router.signal_players_update], candidates, async_add_entities)


class FreeboxRemote(FreeboxReachableMixin, RemoteEntity):
    """Télécommande du Freebox Player."""

    _attr_supported_features = RemoteEntityFeature(0)
    _attr_has_entity_name = True
    _attr_translation_key = "remote"

    def __init__(
        self, router: FreeboxRouter, player: dict[str, Any], entry: ConfigEntry
    ) -> None:
        self._router = router
        self._entry = entry
        self._player_id = player["id"]
        self._attr_unique_id = f"{router.mac}_player_{self._player_id}_remote"
        self._attr_device_info = player_device_info(router, player)
        self._attr_is_on = None
        self._last_known_standby = False
        self._attr_available = player.get("reachable") is not False

    @property
    def _remote_code(self) -> str | None:
        return option_remote_code(self._entry, self._player_id)

    @async_action_errors
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_commands(["power"], False, 0)

    @async_action_errors
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_commands(["power"], False, 0)

    @async_action_errors
    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        commands = [kwargs["code"]] if kwargs.get("code") else command
        await self._send_commands(
            [str(c) for c in commands if c],
            bool(kwargs.get("long_press", False)),
            int(kwargs.get("repeat", 0) or 0),
        )

    async def _send_commands(self, commands: list[str], long_press: bool, repeat: int) -> None:
        if not commands:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="remote_empty_command"
            )
        invalid = [cmd for cmd in commands if cmd not in VALID_COMMANDS]
        if invalid:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="remote_invalid_key",
                translation_placeholders={"key": ", ".join(invalid)},
            )
        remote_code = self._remote_code
        if not remote_code:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="remote_code_missing",
                translation_placeholders={"player": str(self._player_id)},
            )
        failures = await async_send_player_keys(
            self._router, str(remote_code), commands, long_press, repeat
        )
        if failures:
            if isinstance(failures[0][1], HomeAssistantError):
                raise failures[0][1]
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from failures[0][1]

    async def async_update(self) -> None:
        try:
            status = await self._router.async_read(lambda: self._router._api.player.get_player_status(self._player_id))
            if not isinstance(status, dict):
                raise ValueError("Invalid Player status")
            self._attr_available = status.get("reachable") is not False
            power = str(status.get("power_state") or "").lower()
            if power in {"running", "on"}:
                self._attr_is_on = True
            elif power in {"standby", "stopped", "off"}:
                self._attr_is_on = False
            else:
                self._attr_is_on = None
            self._last_known_standby = self._attr_is_on is False
            if self._last_known_standby and self._remote_code is not None:
                self._attr_available = True
        except Exception:
            self._attr_available = self._last_known_standby and self._remote_code is not None
            self._attr_is_on = False if self._attr_available else None
        self._router.note_source(("remote", self._player_id), self._attr_available, "Télécommande Player")
