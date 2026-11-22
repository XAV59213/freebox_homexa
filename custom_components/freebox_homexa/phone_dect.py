"""Combinés DECT : sonnerie groupée et état (sonne / décroché).

Les numéros et les noms d'appelants ne sont ni lus, ni journalisés, ni copiés
dans les attributs. ``on_hook`` est recopié tel que la Freebox le donne : s'il
manque, le capteur « Décroché » reste inconnu.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from freebox_api.api.phone import Phone
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .availability import FreeboxReachableMixin
from .const import DOMAIN
from .discovery import DiscoveryCandidate, async_setup_discovery
from .errors import api_error_code, is_permission_denied, is_shutdown_error
from .fxs_ring import RingController, RingOps

if TYPE_CHECKING:
    from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

DECT_RING_DEFAULT_SECONDS = 30
_DECT_KEY = "dect_ring_controller"
# Base DECT coupée, ou aucun combiné : la Freebox refuse la recherche.
_DECT_DISABLED = frozenset({"dect_disabled", "disabled", "nodev", "noent"})


@dataclass(frozen=True, slots=True)
class Handset:
    """Combiné vu par ``phone/``. Jamais de numéro."""

    id: str
    kind: str
    ringing: bool | None
    on_hook: bool | None

    def __repr__(self) -> str:
        return (
            f"Handset(id={self.id!r}, kind={self.kind!r}, "
            f"ringing={self.ringing!r}, on_hook={self.on_hook!r})"
        )


def parse_handsets(payload: object) -> list[Handset]:
    """Lit ``phone/`` (FXS et DECT). Une liste vide du SDK vaut ``None``."""
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("Invalid phones collection")
    handsets: list[Handset] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Invalid phones collection")
        ident = item.get("id")
        kind = item.get("type")
        if isinstance(ident, bool) or not isinstance(ident, (int, str)):
            raise ValueError("Invalid phones collection")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("Invalid phones collection")
        text = str(ident).strip()
        if not text or "/" in text or len(text) > 64:
            raise ValueError("Invalid phones collection")
        ringing = item.get("is_ringing")
        hook = item.get("on_hook")
        handsets.append(
            Handset(
                id=text,
                kind=kind.strip().lower(),
                ringing=ringing if isinstance(ringing, bool) else None,
                on_hook=hook if isinstance(hook, bool) else None,
            )
        )
    return handsets


def handsets_of(router: FreeboxRouter) -> list[Handset]:
    return [item for item in router.phones if isinstance(item, Handset)]


def has_dect(router: FreeboxRouter) -> bool:
    return any(item.kind == "dect" for item in handsets_of(router))


def _dect_handset(router: FreeboxRouter, handset_id: str) -> Handset | None:
    for item in handsets_of(router):
        if item.kind == "dect" and item.id == handset_id:
            return item
    return None


async def async_refresh_phones(router: FreeboxRouter) -> None:
    """Relevé des combinés, isolé du reste des capteurs."""
    was_available = router.phones_available is not False
    try:
        payload = await router.phone.get_phones()
        found = parse_handsets(payload)
    except Exception as err:
        if router.closing and is_shutdown_error(err, router):
            return
        router.note_permission("calls", err)
        router.phones_available = False
        if was_available:
            _LOGGER.info("Téléphones Freebox indisponibles")
        return
    router.phones = found
    if router.phones_available is False:
        _LOGGER.info("Téléphones Freebox de nouveau disponibles")
    router.phones_available = True


async def _invoke_dect(call: Callable[[], Awaitable[object]]) -> None:
    """Traduit un refus de droit ou une base DECT coupée, sans recopier le message."""
    try:
        await call()
    except HomeAssistantError:
        raise
    except Exception as err:
        if is_permission_denied(err):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="dect_ring_permission",
            ) from err
        if api_error_code(err) in _DECT_DISABLED:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="dect_ring_disabled",
            ) from err
        raise


def _dect_ops(phone: Phone) -> RingOps:
    return RingOps(phone.start_dect_page, phone.stop_dect_page, _invoke_dect, "DECT")


def async_dect_controller(hass: HomeAssistant) -> RingController:
    bucket = hass.data.get(DOMAIN)
    if not isinstance(bucket, dict):
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="command_failed"
        )
    found = bucket.get(_DECT_KEY)
    if type(found) is RingController:
        return found
    controller = RingController()
    bucket[_DECT_KEY] = controller
    return controller


def _existing_dect_controller(hass: HomeAssistant) -> RingController | None:
    bucket = hass.data.get(DOMAIN)
    if not isinstance(bucket, dict):
        return None
    found = bucket.get(_DECT_KEY)
    return found if type(found) is RingController else None


def _prepare(router: FreeboxRouter) -> RingController:
    hass = router.hass
    if hass.data.get(DOMAIN) is None:
        hass.data[DOMAIN] = {}
    return async_dect_controller(hass)


async def async_dect_start(router: FreeboxRouter, duration: float) -> None:
    """Fait sonner les combinés DECT, puis demande toujours l'arrêt."""
    await _prepare(router).async_start(router.entry_id, _dect_ops(router.phone), duration)


async def async_dect_stop(router: FreeboxRouter) -> None:
    await _prepare(router).async_stop(router.entry_id, _dect_ops(router.phone))


async def async_dect_for_entry(entry: ConfigEntry, duration: float) -> None:
    from .fxs_ring import _router_from_entry

    await async_dect_start(_router_from_entry(entry), duration)


async def async_dect_stop_for_entry(entry: ConfigEntry) -> None:
    from .fxs_ring import _router_from_entry

    await async_dect_stop(_router_from_entry(entry))


async def async_release_dect_ring(router: FreeboxRouter) -> None:
    controller = _existing_dect_controller(router.hass)
    if controller is None:
        return
    await controller.async_release(router.entry_id, _dect_ops(router.phone))


class FreeboxDectBinarySensor(FreeboxReachableMixin, BinarySensorEntity):
    """État d'un combiné DECT, rattaché au Freebox Server."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, router: FreeboxRouter, handset_id: str, role: str) -> None:
        self._router = router
        self._handset_id = handset_id
        self._role = role
        ringing = role == "ringing"
        self._attr_unique_id = (
            f"{router.mac} dect {handset_id} {'sonne' if ringing else 'decroche'}"
        )
        self._attr_translation_key = "dect_ringing" if ringing else "dect_off_hook"
        self._attr_translation_placeholders = {"handset": handset_id}
        self._attr_device_info = router.device_info

    def _handset(self) -> Handset | None:
        return _dect_handset(self._router, self._handset_id)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._router.phones_available is not False
            and self._handset() is not None
        )

    @property
    def is_on(self) -> bool | None:
        handset = self._handset()
        if handset is None:
            return None
        if self._role == "ringing":
            return handset.ringing
        if handset.on_hook is None:
            return None
        return not handset.on_hook

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"handset_id": self._handset_id, "dect_role": self._role}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._router.signal_sensor_update, self._refresh
            )
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()


def async_setup_dect_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry,
    router: FreeboxRouter,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Un capteur Sonne et un capteur Décroché par combiné DECT."""

    def candidates() -> Iterable[DiscoveryCandidate]:
        if router.phones_available is False:
            return
        for handset in handsets_of(router):
            if handset.kind != "dect":
                continue
            for role in ("ringing", "off_hook"):
                yield (
                    f"dect:{handset.id}:{role}",
                    _sensor(router, handset.id, role),
                )

    async_setup_discovery(
        hass,
        entry,
        router,
        [router.signal_sensor_update],
        candidates,
        async_add_entities,
    )


def _sensor(router: FreeboxRouter, handset_id: str, role: str) -> Callable[[], FreeboxDectBinarySensor]:
    def build() -> FreeboxDectBinarySensor:
        return FreeboxDectBinarySensor(router, handset_id, role)

    return build
