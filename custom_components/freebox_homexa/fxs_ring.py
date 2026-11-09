"""Sonnerie du téléphone branché sur le port FXS de la Freebox.

Les boutons démarrent ou arrêtent immédiatement. L'action ``start_fxs_ring`` peut
prendre une durée : l'arrêt est alors toujours demandé, y compris si le démarrage
échoue, si l'action est annulée ou si l'entrée est déchargée. Aucun journal
d'appels n'est lu.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
import contextlib
import logging
import math
from typing import NoReturn

from freebox_api.api.phone import Phone
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .errors import api_error_code, is_permission_denied
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

FXS_RING_MIN_SECONDS = 1
FXS_RING_MAX_SECONDS = 300
_CONTROLLER_KEY = "fxs_ring_controller"
# Codes Freebox OS « pas de périphérique / pas d'entité » : port FXS absent.
_NO_FXS_CODES = frozenset({"nodev", "noent"})


class _Slot:
    """Une sonnerie en cours pour une entrée de configuration."""

    __slots__ = (
        "armed",
        "closed",
        "done",
        "generation",
        "release_done",
        "stop_on_wake",
        "wake",
    )

    def __init__(self) -> None:
        self.generation = 0
        self.armed = False
        self.closed = False
        self.stop_on_wake = False
        self.wake: asyncio.Event | None = None
        self.done: asyncio.Future[None] | None = None
        self.release_done: asyncio.Future[None] | None = None


class FxsRingController:
    """Coordonne les sonneries FXS d'une instance Home Assistant."""

    def __init__(self) -> None:
        self._slots: dict[str, _Slot] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, entry_id: str) -> asyncio.Lock:
        lock = self._locks.get(entry_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[entry_id] = lock
        return lock

    def _slot(self, entry_id: str) -> _Slot:
        slot = self._slots.get(entry_id)
        if slot is None:
            slot = _Slot()
            self._slots[entry_id] = slot
        return slot

    async def async_start(
        self, entry_id: str, phone: Phone, duration: float | None
    ) -> None:
        """Démarre la sonnerie. ``duration`` programme un arrêt obligatoire."""
        generation, inherited = await self._bump(entry_id)
        if duration is None:
            try:
                await self._ensure_open(entry_id)
                await _invoke(phone.start_fxs_ring)
            except BaseException:
                if inherited:
                    await self._best_effort_stop(entry_id, phone, generation)
                raise
            await self._mark_armed(entry_id, generation)
            return
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        await self._watch(entry_id, generation, done)
        try:
            try:
                await self._ensure_open(entry_id)
                await _invoke(phone.start_fxs_ring)
            except BaseException:
                await self._best_effort_stop(entry_id, phone, generation)
                raise
            await self._mark_armed(entry_id, generation)
            try:
                should_stop = await self._wait(entry_id, generation, duration)
            except BaseException:
                await self._best_effort_stop(entry_id, phone, generation)
                raise
            if should_stop:
                await self._stop_if_current(entry_id, phone, generation)
        finally:
            if not done.done():
                done.set_result(None)

    async def async_stop(self, entry_id: str, phone: Phone) -> None:
        """Arrête la sonnerie et retire l'arrêt programmé précédent."""
        async with self._lock(entry_id):
            slot = self._slot(entry_id)
            slot.generation += 1
            slot.stop_on_wake = False
            generation = slot.generation
            wake = slot.wake
            slot.wake = None
        if wake is not None and not wake.is_set():
            wake.set()
        try:
            await _invoke(phone.stop_fxs_ring)
        except Exception:
            _LOGGER.debug("Arrêt de la sonnerie FXS non confirmé")
            raise
        async with self._lock(entry_id):
            slot = self._slot(entry_id)
            if slot.generation == generation:
                slot.armed = False

    async def async_release(self, entry_id: str, phone: Phone) -> None:
        """Arrête une sonnerie encore sous notre responsabilité (déchargement).

        Le créneau est retiré à la fin : un rechargement peut sonner de nouveau.
        Un second déchargement concurrent attend le premier.
        """
        async with self._lock(entry_id):
            slot = self._slots.get(entry_id)
            if slot is None:
                return
            if slot.closed:
                pending = slot.release_done
                future = None
                owner = False
            else:
                pending = None
                owner = True
                slot.closed = True
                slot.release_done = asyncio.get_running_loop().create_future()
                future = slot.done
                wake = slot.wake
                if wake is not None:
                    slot.stop_on_wake = True
                    slot.wake = None
                    wake.set()
        if not owner:
            if pending is not None and not pending.done():
                await _await_shielded(pending)
            return
        try:
            if future is not None and not future.done():
                await _await_shielded(future)
            async with self._lock(entry_id):
                current = self._slots.get(entry_id)
                armed = bool(current and current.armed)
            if not armed:
                return
            try:
                await _await_shielded(_invoke(phone.stop_fxs_ring))
            except Exception:
                _LOGGER.debug("Arrêt FXS au déchargement non confirmé")
                return
            async with self._lock(entry_id):
                current = self._slots.get(entry_id)
                if current is not None:
                    current.armed = False
        finally:
            async with self._lock(entry_id):
                finished = self._slots.pop(entry_id, None)
                release_done = finished.release_done if finished is not None else None
            if release_done is not None and not release_done.done():
                release_done.set_result(None)

    async def _bump(self, entry_id: str) -> tuple[int, bool]:
        """Passe la main : l'attente précédente ne doit plus arrêter elle-même."""
        async with self._lock(entry_id):
            slot = self._slot(entry_id)
            if slot.closed:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_failed"
                )
            inherited = slot.armed or slot.wake is not None
            slot.generation += 1
            slot.stop_on_wake = False
            wake = slot.wake
            slot.wake = None
            generation = slot.generation
        if wake is not None and not wake.is_set():
            wake.set()
        return generation, inherited

    async def _watch(
        self, entry_id: str, generation: int, done: asyncio.Future[None]
    ) -> None:
        async with self._lock(entry_id):
            slot = self._slot(entry_id)
            if slot.generation == generation:
                slot.done = done

    async def _ensure_open(self, entry_id: str) -> None:
        async with self._lock(entry_id):
            slot = self._slots.get(entry_id)
            if slot is not None and slot.closed:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_failed"
                )

    async def _mark_armed(self, entry_id: str, generation: int) -> None:
        async with self._lock(entry_id):
            slot = self._slot(entry_id)
            if slot.generation == generation and not slot.closed:
                slot.armed = True

    async def _wait(self, entry_id: str, generation: int, duration: float) -> bool:
        event = asyncio.Event()
        async with self._lock(entry_id):
            slot = self._slot(entry_id)
            if slot.generation != generation or slot.closed:
                return slot.closed and slot.generation == generation
            slot.wake = event
        try:
            elapsed = await _wait_duration(event, duration)
        finally:
            async with self._lock(entry_id):
                slot = self._slot(entry_id)
                if slot.wake is event:
                    slot.wake = None
        if elapsed:
            return True
        async with self._lock(entry_id):
            slot = self._slot(entry_id)
            return slot.generation == generation and (slot.stop_on_wake or slot.closed)

    async def _stop_if_current(self, entry_id: str, phone: Phone, generation: int) -> None:
        async with self._lock(entry_id):
            slot = self._slot(entry_id)
            if slot.generation != generation:
                return
            slot.generation += 1
            await _invoke(phone.stop_fxs_ring)
            slot.armed = False

    async def _best_effort_stop(self, entry_id: str, phone: Phone, generation: int) -> None:
        try:
            await _await_shielded(self._stop_if_current(entry_id, phone, generation))
        except Exception:
            _LOGGER.debug("Arrêt de la sonnerie FXS non confirmé")


def async_controller(hass: HomeAssistant) -> FxsRingController:
    """Contrôleur de cette instance Home Assistant, créé au premier usage."""
    bucket = hass.data.get(DOMAIN)
    if not isinstance(bucket, dict):
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="command_failed"
        )
    found = bucket.get(_CONTROLLER_KEY)
    if isinstance(found, FxsRingController):
        return found
    controller = FxsRingController()
    bucket[_CONTROLLER_KEY] = controller
    return controller


def _existing_controller(hass: HomeAssistant) -> FxsRingController | None:
    bucket = hass.data.get(DOMAIN)
    if not isinstance(bucket, dict):
        return None
    found = bucket.get(_CONTROLLER_KEY)
    return found if isinstance(found, FxsRingController) else None


def _router_from_entry(entry: ConfigEntry) -> FreeboxRouter:
    router = entry.runtime_data
    if not isinstance(router, FreeboxRouter):
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="command_failed"
        )
    return router


async def async_ring_start(router: FreeboxRouter, duration: float | None) -> None:
    """Démarre la sonnerie FXS de cette Freebox."""
    hass = router.hass
    if hass.data.get(DOMAIN) is None:
        hass.data[DOMAIN] = {}
    await async_controller(hass).async_start(router.entry_id, router.phone, duration)


async def async_ring_stop(router: FreeboxRouter) -> None:
    """Arrête la sonnerie FXS de cette Freebox."""
    hass = router.hass
    if hass.data.get(DOMAIN) is None:
        hass.data[DOMAIN] = {}
    await async_controller(hass).async_stop(router.entry_id, router.phone)


async def async_ring_for_entry(entry: ConfigEntry, duration: float | None) -> None:
    """Démarre la sonnerie de l'entrée visée par une action."""
    await async_ring_start(_router_from_entry(entry), duration)


async def async_stop_for_entry(entry: ConfigEntry) -> None:
    """Arrête la sonnerie de l'entrée visée par une action."""
    await async_ring_stop(_router_from_entry(entry))


async def async_release_fxs_ring(router: FreeboxRouter) -> None:
    """Arrête la sonnerie encore armée avant la fermeture de la session."""
    controller = _existing_controller(router.hass)
    if controller is None:
        return
    await controller.async_release(router.entry_id, router.phone)


def duration_from_data(data: Mapping[str, object]) -> float | None:
    """Durée facultative de l'action, refusée avant tout appel Freebox si elle est invalide."""
    if "duration" not in data:
        return None
    raw = data["duration"]
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        _reject_duration()
    if raw < FXS_RING_MIN_SECONDS or raw > FXS_RING_MAX_SECONDS:
        _reject_duration()
    return float(raw)


def duration_value(data: object) -> float | None:
    """Lit une charge d'action qui n'est pas forcément un mapping."""
    if not isinstance(data, Mapping):
        _reject_duration()
    return duration_from_data(data)


def duration_from_call(call: ServiceCall) -> float | None:
    """Lit ``duration`` sur l'appel d'action."""
    return duration_value(call.data)


def _reject_duration() -> NoReturn:
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="fxs_ring_duration",
        translation_placeholders={
            "minimum": str(FXS_RING_MIN_SECONDS),
            "maximum": str(FXS_RING_MAX_SECONDS),
        },
    )


async def _pause(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _wait_duration(event: asyncio.Event, duration: float) -> bool:
    """True si la durée s'écoule, False si ``event`` est signalé avant."""
    pause = asyncio.create_task(_pause(duration))
    woken = asyncio.create_task(event.wait())
    try:
        done, _pending = await asyncio.wait(
            {pause, woken}, return_when=asyncio.FIRST_COMPLETED
        )
        elapsed = pause in done and not pause.cancelled()
        if elapsed:
            pause.result()
        return elapsed
    finally:
        for task in (pause, woken):
            if not task.done():
                task.cancel()
        for task in (pause, woken):
            with contextlib.suppress(asyncio.CancelledError):
                await _await_shielded(task)


async def _await_shielded(awaitable: Awaitable[object]) -> None:
    """Attend la fin même si cette tâche est déjà en cours d'annulation."""
    current = asyncio.current_task()
    suspended = 0
    if current is not None:
        while current.cancelling():
            current.uncancel()
            suspended += 1
    try:
        await awaitable
    finally:
        if current is not None:
            for _index in range(suspended):
                current.cancel()


async def _invoke(call: Callable[[], Awaitable[object]]) -> None:
    """Appelle le SDK et traduit un refus de droit ou un port FXS absent.

    Le message Freebox n'est pas recopié : il ne doit pas exposer de détail
    d'appel. Les autres erreurs restent brutes pour la frontière d'action.
    """
    try:
        await call()
    except HomeAssistantError:
        raise
    except Exception as err:
        if is_permission_denied(err):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="fxs_ring_permission",
            ) from err
        if api_error_code(err) in _NO_FXS_CODES:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="fxs_ring_unavailable",
            ) from err
        raise
