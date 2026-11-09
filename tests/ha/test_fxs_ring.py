"""FXS ring actions on the real SDK Phone class. No Freebox and no call log."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from freebox_api.access import Access
from freebox_api.api.phone import Phone
from freebox_api.exceptions import HttpRequestError, InsufficientPermissionsError
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.freebox_homexa.button import BUTTON_DESCRIPTIONS, FreeboxButton
from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.fxs_ring import (
    FXS_RING_MAX_SECONDS,
    FXS_RING_MIN_SECONDS,
    async_controller,
    async_release_fxs_ring,
    async_ring_for_entry,
    async_ring_start,
    async_ring_stop,
    duration_value,
)
from custom_components.freebox_homexa.services import async_setup_services
from test_home_platforms import home_context, make_platform

SECRET = "0612345678 Martin"


class Script:
    """Transport accepted by the installed Phone class. Records paths only."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        self.start_error: BaseException | None = None
        self.stop_error: BaseException | None = None
        self.stop_entered: asyncio.Event | None = None
        self.stop_gate: asyncio.Event | None = None

    async def post(self, path: str, payload: object = None) -> None:
        self.paths.append(path)
        if path.endswith("fxs_ring_stop/") and self.stop_entered is not None:
            self.stop_entered.set()
            assert self.stop_gate is not None
            await self.stop_gate.wait()
        if path.endswith("fxs_ring_start/") and self.start_error is not None:
            raise self.start_error
        if path.endswith("fxs_ring_stop/") and self.stop_error is not None:
            raise self.stop_error


def http_error(code: str) -> HttpRequestError:
    payload = '{"success": false, "error_code": "%s", "msg": "appel %s"}' % (code, SECRET)
    return HttpRequestError(f"Request failed (APIResponse: {payload})")


def permission_error() -> InsufficientPermissionsError:
    payload = (
        '{"success": false, "error_code": "insufficient_rights", '
        f'"missing_right": "calls", "msg": "appel {SECRET}"}}'
    )
    return InsufficientPermissionsError(f"Request failed (APIResponse: {payload})")


def use_phone(router) -> Script:
    script = Script()
    router._api.phone = Phone(script)
    return script


def button(router, key: str) -> FreeboxButton:
    description = next(item for item in BUTTON_DESCRIPTIONS if item.key == key)
    return FreeboxButton(router, description)


def load(hass, router) -> None:
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)


async def test_buttons_use_sdk_paths_and_keep_existing_ids(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    start = button(router, "start_fxs_ring")
    stop = button(router, "stop_fxs_ring")
    reboot = button(router, "reboot")
    assert start.unique_id == f"{router.mac} Démarrer la sonnerie FXS"
    assert stop.unique_id == f"{router.mac} Arrêter la sonnerie FXS"
    assert reboot.unique_id == f"{router.mac} Redémarrer Freebox"
    assert router.phone is router._api.phone
    await start.async_press()
    await stop.async_press()
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]
    router._api.call.get_calls_log.assert_not_called()
    router._api.call.mark_calls_log_as_read.assert_not_called()


async def test_failed_press_keeps_the_button_available(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    script.start_error = http_error("nodev")
    entity = button(router, "start_fxs_ring")
    platform = make_platform(hass, "button")
    try:
        await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        with pytest.raises(HomeAssistantError) as exc:
            await entity.async_press()
        assert exc.value.translation_key == "fxs_ring_unavailable"
        assert SECRET not in str(exc.value)
        state = hass.states.get(entity.entity_id)
        assert state is not None
        assert state.state != "unavailable"
        assert entity.available
        assert script.paths == ["phone/fxs_ring_start/"]
    finally:
        await platform.async_reset()


@pytest.mark.parametrize("code", ["nodev", "noent"])
async def test_missing_fxs_port_is_translated_for_stop(hass, home_context, code):
    router, _node = home_context
    script = use_phone(router)
    script.stop_error = http_error(code)
    with pytest.raises(HomeAssistantError) as exc:
        await async_ring_stop(router)
    assert exc.value.translation_key == "fxs_ring_unavailable"
    assert SECRET not in str(exc.value)
    assert script.paths == ["phone/fxs_ring_stop/"]


async def test_missing_telephony_permission_is_not_success(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    script.start_error = permission_error()
    with pytest.raises(HomeAssistantError) as exc:
        await async_ring_start(router, None)
    assert exc.value.translation_key == "fxs_ring_permission"
    assert SECRET not in str(exc.value)
    assert script.paths == ["phone/fxs_ring_start/"]
    script.start_error = None
    await async_ring_start(router, None)
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_start/"]


async def test_duration_stops_even_when_start_fails(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    script.start_error = permission_error()
    script.stop_error = permission_error()
    with pytest.raises(HomeAssistantError) as exc:
        await async_ring_start(router, 5)
    assert exc.value.translation_key == "fxs_ring_permission"
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]


async def test_other_sdk_error_is_command_failed_without_payload(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    script.start_error = OSError(f"synthetic-secret {SECRET}")
    entity = button(router, "start_fxs_ring")
    with pytest.raises(HomeAssistantError) as exc:
        await entity.async_press()
    assert exc.value.translation_key == "command_failed"
    assert SECRET not in str(exc.value)
    assert "synthetic-secret" not in str(exc.value)


async def test_timed_ring_stops_when_the_duration_elapses(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    seen: list[float] = []

    async def immediate(seconds: float) -> None:
        seen.append(seconds)

    with patch("custom_components.freebox_homexa.fxs_ring._pause", immediate):
        await async_ring_start(router, 5)
    assert seen == [5]
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]


async def test_real_pause_path_stops(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    await async_ring_start(router, 0.01)
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]


async def test_cancellation_still_stops(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    paused = asyncio.Event()
    stop_entered = asyncio.Event()
    release_stop = asyncio.Event()

    async def block(_seconds: float) -> None:
        paused.set()
        await asyncio.Event().wait()

    script.stop_entered = stop_entered
    script.stop_gate = release_stop
    with patch("custom_components.freebox_homexa.fxs_ring._pause", block):
        task = hass.async_create_task(async_ring_start(router, 5))
        await paused.wait()
        task.cancel()
        await stop_entered.wait()
        release_stop.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]


async def test_replacing_a_timed_ring_does_not_stop_early(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    gates: list[asyncio.Event] = []

    async def gate(_seconds: float) -> None:
        event = asyncio.Event()
        gates.append(event)
        await event.wait()

    with patch("custom_components.freebox_homexa.fxs_ring._pause", gate):
        first = hass.async_create_task(async_ring_start(router, 10))
        while len(gates) < 1:
            await asyncio.sleep(0)
        second = hass.async_create_task(async_ring_start(router, 3))
        while len(gates) < 2:
            await asyncio.sleep(0)
        assert script.paths.count("phone/fxs_ring_stop/") == 0
        gates[1].set()
        await second
        await first
    assert script.paths == [
        "phone/fxs_ring_start/",
        "phone/fxs_ring_start/",
        "phone/fxs_ring_stop/",
    ]


async def test_manual_stop_cancels_the_programmed_stop(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    paused = asyncio.Event()

    async def block(_seconds: float) -> None:
        paused.set()
        await asyncio.Event().wait()

    with patch("custom_components.freebox_homexa.fxs_ring._pause", block):
        task = hass.async_create_task(async_ring_start(router, 8))
        await paused.wait()
        await async_ring_stop(router)
        await task
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]


async def test_unload_stops_a_timed_ring_and_a_manual_ring(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    paused = asyncio.Event()

    async def block(_seconds: float) -> None:
        paused.set()
        await asyncio.Event().wait()

    with patch("custom_components.freebox_homexa.fxs_ring._pause", block):
        task = hass.async_create_task(async_ring_start(router, 8))
        await paused.wait()
        await async_release_fxs_ring(router)
        await task
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]
    await async_ring_start(router, None)
    await async_release_fxs_ring(router)
    assert script.paths[-2:] == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]
    await async_release_fxs_ring(router)
    assert script.paths.count("phone/fxs_ring_stop/") == 2


async def test_parallel_unload_waits_for_the_first_stop(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    paused = asyncio.Event()

    async def block(_seconds: float) -> None:
        paused.set()
        await asyncio.Event().wait()

    with patch("custom_components.freebox_homexa.fxs_ring._pause", block):
        ringing = hass.async_create_task(async_ring_start(router, 6))
        await paused.wait()
        first = hass.async_create_task(async_release_fxs_ring(router))
        controller = async_controller(hass)
        slot = controller._slots.get(router.entry_id)
        assert slot is not None and slot.closed
        second = hass.async_create_task(async_release_fxs_ring(router))
        await first
        await second
        await ringing
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]
    await async_ring_start(router, None)
    script.stop_error = OSError("synthetic-secret")
    await async_release_fxs_ring(router)
    assert script.paths[-2:] == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]
    script.stop_error = None
    await async_ring_start(router, None)


async def test_existing_home_assistant_error_is_not_rewritten(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    script.start_error = HomeAssistantError(
        translation_domain=DOMAIN, translation_key="command_failed"
    )
    with pytest.raises(HomeAssistantError) as exc:
        await async_ring_start(router, None)
    assert exc.value.translation_key == "command_failed"
    assert script.paths == ["phone/fxs_ring_start/"]


async def test_release_without_controller_does_not_call_the_phone(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    await async_release_fxs_ring(router)
    hass.data[DOMAIN] = {"fxs_ring_controller": "not-a-controller"}
    await async_release_fxs_ring(router)
    assert script.paths == []


async def test_stop_failure_after_a_timed_ring_is_not_success(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    script.stop_error = OSError(f"synthetic-secret {SECRET}")
    load(hass, router)
    async_setup_services(hass)

    async def immediate(_seconds: float) -> None:
        return None

    with patch("custom_components.freebox_homexa.fxs_ring._pause", immediate):
        with pytest.raises(HomeAssistantError) as exc:
            await hass.services.async_call(
                DOMAIN, "start_fxs_ring", {"duration": 2}, blocking=True
            )
    assert exc.value.translation_key == "command_failed"
    assert SECRET not in str(exc.value)
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]


@pytest.mark.parametrize(
    "raw",
    [0, 301, -1, True, False, "5", float("nan"), float("inf"), object()],
)
async def test_invalid_duration_does_not_reach_the_phone(hass, home_context, raw):
    router, _node = home_context
    script = use_phone(router)
    load(hass, router)
    async_setup_services(hass)
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call(
            DOMAIN, "start_fxs_ring", {"duration": raw}, blocking=True
        )
    assert exc.value.translation_key == "fxs_ring_duration"
    assert exc.value.translation_placeholders == {
        "minimum": str(FXS_RING_MIN_SECONDS),
        "maximum": str(FXS_RING_MAX_SECONDS),
    }
    assert script.paths == []


@pytest.mark.parametrize("duration", [1, 300, 1.5])
async def test_service_duration_bounds_call_start_then_stop(hass, home_context, duration):
    router, _node = home_context
    script = use_phone(router)
    load(hass, router)
    async_setup_services(hass)

    async def immediate(_seconds: float) -> None:
        return None

    with patch("custom_components.freebox_homexa.fxs_ring._pause", immediate):
        await hass.services.async_call(
            DOMAIN,
            "start_fxs_ring",
            {"duration": duration, "config_entry_id": router.entry_id},
            blocking=True,
        )
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]


async def test_service_without_duration_and_explicit_stop(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    load(hass, router)
    async_setup_services(hass)
    await hass.services.async_call(
        DOMAIN, "start_fxs_ring", {"duration": None, "device_id": []}, blocking=True
    )
    assert script.paths == ["phone/fxs_ring_start/"]
    await hass.services.async_call(DOMAIN, "stop_fxs_ring", {}, blocking=True)
    assert script.paths == ["phone/fxs_ring_start/", "phone/fxs_ring_stop/"]


async def test_real_access_rejects_failed_json_and_accepts_success(hass, home_context):
    router, _node = home_context
    payloads = [
        {"success": False, "error_code": "nodev", "msg": f"ligne {SECRET}"},
        {"success": True, "result": None},
    ]

    def session_for(payload: dict[str, object]) -> SimpleNamespace:
        response = SimpleNamespace(
            content_type="application/json",
            json=AsyncMock(return_value=payload),
        )
        return SimpleNamespace(post=AsyncMock(return_value=response))

    denied = session_for(payloads[0])
    access = Access(denied, "https://freebox.test/api/v8/", "synthetic-token", "hass", 1)
    access.session_token = "synthetic-session"
    router._api.phone = Phone(access)
    with pytest.raises(HomeAssistantError) as exc:
        await async_ring_start(router, None)
    assert exc.value.translation_key == "fxs_ring_unavailable"
    assert SECRET not in str(exc.value)
    assert denied.post.await_args.args[0].endswith("phone/fxs_ring_start/")
    router._api.call.get_calls_log.assert_not_called()

    allowed = session_for(payloads[1])
    access = Access(allowed, "https://freebox.test/api/v8/", "synthetic-token", "hass", 1)
    access.session_token = "synthetic-session"
    router._api.phone = Phone(access)
    await async_ring_stop(router)
    assert allowed.post.await_args.args[0].endswith("phone/fxs_ring_stop/")


async def test_broken_runtime_and_controller_bucket_are_errors(hass, home_context):
    router, _node = home_context
    use_phone(router)
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = object()
    with pytest.raises(HomeAssistantError) as exc:
        await async_ring_for_entry(entry, None)
    assert exc.value.translation_key == "command_failed"
    hass.data[DOMAIN] = "not-a-bucket"
    with pytest.raises(HomeAssistantError) as broken:
        async_controller(hass)
    assert broken.value.translation_key == "command_failed"
    with pytest.raises(ServiceValidationError) as duration:
        duration_value(object())
    assert duration.value.translation_key == "fxs_ring_duration"
    assert duration_value({}) is None


async def test_start_is_refused_once_the_entry_is_closing(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    paused = asyncio.Event()

    async def block(_seconds: float) -> None:
        paused.set()
        await asyncio.Event().wait()

    with patch("custom_components.freebox_homexa.fxs_ring._pause", block):
        task = hass.async_create_task(async_ring_start(router, 4))
        await paused.wait()
        release = hass.async_create_task(async_release_fxs_ring(router))
        controller = async_controller(hass)
        slot = controller._slots.get(router.entry_id)
        assert slot is not None and slot.closed
        with pytest.raises(HomeAssistantError) as exc:
            await async_ring_start(router, None)
        assert exc.value.translation_key == "command_failed"
        await task
        await release
    assert script.paths.count("phone/fxs_ring_start/") == 1
    assert "phone/fxs_ring_stop/" in script.paths


async def test_controller_branches_for_a_closed_or_foreign_generation(hass, home_context):
    router, _node = home_context
    script = use_phone(router)
    await async_ring_start(router, None)
    script.start_error = OSError("synthetic-secret")
    with pytest.raises(OSError):
        await async_ring_start(router, None)
    assert script.paths == [
        "phone/fxs_ring_start/",
        "phone/fxs_ring_start/",
        "phone/fxs_ring_stop/",
    ]
    controller = async_controller(hass)
    slot = controller._slot(router.entry_id)
    await controller._ensure_open(router.entry_id)
    slot.closed = True
    with pytest.raises(HomeAssistantError) as exc:
        await controller._ensure_open(router.entry_id)
    assert exc.value.translation_key == "command_failed"
    slot.generation = 4
    assert await controller._wait(router.entry_id, 4, 5) is True
    assert await controller._wait(router.entry_id, 9, 5) is False
    await controller._stop_if_current(router.entry_id, router.phone, 1)
    await controller._mark_armed(router.entry_id, 1)
    assert script.paths.count("phone/fxs_ring_stop/") == 1
