"""Support for Freebox button entities (reboot and call management)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from freebox_api.exceptions import HttpRequestError

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

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FreeboxButtonEntityDescription(ButtonEntityDescription):
    """Class describing Freebox button entities."""

    async_press: Callable[[FreeboxRouter], Awaitable[None]]


BUTTON_DESCRIPTIONS: tuple[FreeboxButtonEntityDescription, ...] = (
    FreeboxButtonEntityDescription(
        key="reboot",
        name="Freebox Reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        async_press=lambda router: router.reboot(),
    ),
    FreeboxButtonEntityDescription(
        key="mark_calls_as_read",
        name="Freebox Mark Calls as Read",
        entity_category=EntityCategory.DIAGNOSTIC,
        async_press=lambda router: router.call.mark_calls_log_as_read(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Freebox button entities from a config entry."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    entities = [
        FreeboxButton(router, description) for description in BUTTON_DESCRIPTIONS
    ]
    async_add_entities(entities, update_before_add=True)
    _LOGGER.debug(
        "Added %d button entities for %s (%s)",
        len(entities),
        router.name,
        router.mac,
    )


class FreeboxButton(ButtonEntity):
    """Representation of a Freebox button entity."""

    entity_description: FreeboxButtonEntityDescription

    def __init__(
        self, router: FreeboxRouter, description: FreeboxButtonEntityDescription
    ) -> None:
        """Initialize a Freebox button entity."""
        self.entity_description = description
        self._router = router
        self._attr_device_info = router.device_info
        self._attr_unique_id = f"{router.mac}_{description.key}"

    async def async_press(self) -> None:
        """Press the button by executing its associated action."""
        try:
            await self.entity_description.async_press(self._router)
            _LOGGER.info(
                "Button '%s' pressed successfully for %s",
                self.entity_description.name,
                self._router.name,
            )
        except HttpRequestError as err:
            _LOGGER.error(
                "Failed to press '%s' for %s: %s",
                self.entity_description.name,
                self._router.name,
                err,
            )
            raise
