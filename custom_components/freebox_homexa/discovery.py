"""Entry-owned incremental entity discovery from existing shared observations."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

if TYPE_CHECKING:
    from .router import FreeboxConfigEntry, FreeboxRouter

type DiscoveryCandidate = tuple[str, Callable[[], Entity]]


@callback
def async_setup_discovery(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
    router: FreeboxRouter,
    signals: Sequence[str],
    candidates: Callable[[], Iterable[DiscoveryCandidate]],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create each observed identity once; never delete registries on disappearance.

    Factories are lazy: known identities do not reconstruct entities or register
    side effects on every poll. Commit the seen batch only after it is submitted.
    A failed constructor therefore cannot permanently hide earlier new candidates.
    """
    seen: set[str] = set()

    @callback
    def discover() -> None:
        if router.closing:
            return
        entities: list[Entity] = []
        pending: set[str] = set()
        for key, factory in candidates():
            if key in seen or key in pending:
                continue
            entities.append(factory())
            pending.add(key)
        if entities:
            async_add_entities(entities, True)
            seen.update(pending)

    for signal in signals:
        entry.async_on_unload(async_dispatcher_connect(hass, signal, discover))
    discover()
