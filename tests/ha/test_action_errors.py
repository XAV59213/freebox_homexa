"""User actions on owned real HA platforms; every device transport is synthetic."""
import asyncio
from datetime import timedelta
import inspect
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.components.media_player import MediaPlayerState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import EntityPlatform
from custom_components.freebox_homexa.button import (
    BUTTON_DESCRIPTIONS, PLAYER_REMOTE_BUTTONS, PLAYER_APP_BUTTONS,
    FreeboxButton, FreeboxPlayerRemoteButton, FreeboxPlayerAppButton,
)
from custom_components.freebox_homexa.media_player import FreeboxPlayerMediaPlayer
from custom_components.freebox_homexa.remote import FreeboxRemote
from custom_components.freebox_homexa.switch import FreeboxSwitch, FreeboxShutterInvertSwitchEntity, SWITCH_DESCRIPTIONS
from custom_components.freebox_homexa.cover import FreeboxBasicShutter, FreeboxShutter
from custom_components.freebox_homexa.camera import FreeboxCamera
from custom_components.freebox_homexa.alarm_control_panel import FreeboxAlarm
from custom_components.freebox_homexa.errors import async_action_errors
from test_home_platforms import home_context

# One execution test per remaining explicit action and branch family, not merely
# construction or callService assertions. Existing Home tests cover cover/camera.
CASES = [
    *[("basic", name, {}, "home") for name in ("async_open_cover", "async_close_cover", "async_stop_cover")],
    *[("position", name, {}, "home") for name in ("async_open_cover", "async_close_cover", "async_stop_cover")],
    ("position", "async_set_cover_position", {"position": 60}, "home"),
    ("camera", "async_enable_motion_detection", {}, "home"),
    ("camera", "async_disable_motion_detection", {}, "home"),
    ("invert", "async_turn_on", {}, "local_write"),
    ("invert", "async_turn_off", {}, "local_write"),
    ("media", "async_set_volume_level", {"volume": .3}, "put"),
    ("media", "async_mute_volume", {"mute": True}, "put"),
    *[("media", name, {}, "post") for name in (
        "async_media_play", "async_media_pause", "async_media_stop",
        "async_media_next_track", "async_media_previous_track")],
    ("media", "async_select_source", {"source": "Netflix"}, "post"),
    ("media", "async_play_media", {"media_type": "channel", "media_id": "1"}, "post"),
    ("media", "async_turn_on", {}, "remote"),
    ("media", "async_turn_off", {}, "remote"),
    ("remote", "async_send_command", {"command": ["home"]}, "remote"),
    ("remote", "async_turn_on", {}, "remote"),
    ("remote", "async_turn_off", {}, "remote"),
    ("server_button", "async_press", {}, "reboot"),
    ("calls_button", "async_press", {}, "calls"),
    ("remote_button", "async_press", {}, "remote"),
    ("app_button", "async_press", {}, "post"),
    ("wifi", "async_turn_on", {}, "wifi"),
    ("wifi", "async_turn_off", {}, "wifi"),
    *[("alarm", name, {}, "home") for name in (
        "async_alarm_disarm", "async_alarm_arm_away", "async_alarm_arm_home", "async_alarm_trigger")],
]


def build_entity(hass, router, node, entry, kind):
    player = {"id": 1, "reachable": True, "api_version": "v6", "name": "Test Player"}
    if kind in {"basic", "position", "camera", "invert"}:
        entity = {"basic": FreeboxBasicShutter, "position": FreeboxShutter,
            "camera": FreeboxCamera, "invert": FreeboxShutterInvertSwitchEntity}[kind](hass, router, node)
        return entity, "camera" if kind == "camera" else "switch" if kind == "invert" else "cover"
    if kind == "media":
        return FreeboxPlayerMediaPlayer(router, player, entry), "media_player"
    if kind == "remote":
        return FreeboxRemote(router, player, entry), "remote"
    if kind == "wifi":
        return FreeboxSwitch(router, SWITCH_DESCRIPTIONS[0]), "switch"
    if kind == "alarm":
        node = {**node, "category": "alarm", "type": {"endpoints": [
            {"id": index + 20, "name": name, "ep_type": kind}
            for index, (name, kind) in enumerate([(n, "slot") for n in ("trigger", "alarm1", "alarm2", "off")] + [("state", "signal")])]}}
        return FreeboxAlarm(hass, router, node), "alarm_control_panel"
    if kind in {"server_button", "calls_button"}:
        return FreeboxButton(router, BUTTON_DESCRIPTIONS[kind == "calls_button"]), "button"
    if kind == "remote_button":
        return FreeboxPlayerRemoteButton(router, player, entry, *PLAYER_REMOTE_BUTTONS[0]), "button"
    return FreeboxPlayerAppButton(router, player, *PLAYER_APP_BUTTONS[0]), "button"


@pytest.mark.parametrize("kind,method,kwargs,target", CASES, ids=lambda value: str(value))
@pytest.mark.parametrize("failed", [False, True])
async def test_remaining_actions_success_failure_and_recovery(hass, home_context, tmp_path, kind, method, kwargs, target, failed):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    hass.config_entries.async_update_entry(entry, options={"remote_codes": {"1": "synthetic-code"}})
    entity, domain = build_entity(hass, router, node, entry, kind)
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
        platform_name="freebox_homexa", platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
    platform.config_entry = entry
    if kind == "invert":
        entity._path = tmp_path / "inversion.conf"
        entity._write = Mock(wraps=entity._write)
    operations = {"put": router._api.player._access.put, "post": router._api.player._access.post,
        "remote": router._api.remote.send_key, "reboot": router._api.system.reboot,
        "calls": router._api.call.mark_calls_log_as_read, "wifi": router._api.wifi.set_global_config,
        "home": router._api.home.set_home_endpoint_value}
    operation = entity._write if target == "local_write" else operations[target]
    router._api.remote.send_key.return_value = True
    router._api.home.get_home_endpoint_value.return_value = {"value": "idle"}
    async def execute():
        if kind == "media" and method == "async_turn_on":
            entity._attr_state = MediaPlayerState.OFF
        return await getattr(entity, method)(**kwargs)
    try:
        await platform.async_add_entities([entity])
        before = entity.source if kind == "media" else None
        if failed:
            operation.side_effect = OSError("synthetic-secret-must-not-be-in-user-message")
            with pytest.raises(HomeAssistantError) as exc:
                await execute()
            assert exc.value.translation_key == "command_failed"
            assert "synthetic-secret" not in str(exc.value)
            if kind == "media":
                assert entity.source == before
            if kind == "alarm":
                assert entity._unsub_watcher is None
            operation.side_effect = None
        await execute()  # The very same owned entity recovers, not a fresh instance.
        count = operation.call_count if target == "local_write" else operation.await_count
        assert count >= (2 if failed else 1)
    finally:
        await platform.async_reset()
    assert not platform.entities


@pytest.mark.parametrize("kind", ["remote", "remote_button", "media"])
async def test_sdk_false_is_unconfirmed_without_automatic_retry(hass, home_context, kind):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    hass.config_entries.async_update_entry(entry, options={"remote_code": "synthetic-code"})
    entity, _ = build_entity(hass, router, node, entry, kind)
    router._api.remote.send_key.return_value = False
    action = entity.async_press if kind == "remote_button" else entity.async_turn_off
    with pytest.raises(HomeAssistantError) as exc:
        await action()
    assert exc.value.translation_key == "command_unconfirmed"
    router._api.remote.send_key.assert_awaited_once()


@pytest.mark.parametrize("kwargs,key", [({"command": []}, "remote_empty_command"),
    ({"command": ["home", "invalid"]}, "remote_invalid_key")])
async def test_invalid_remote_macro_is_rejected_before_any_key(hass, home_context, kwargs, key):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    hass.config_entries.async_update_entry(entry, options={"remote_code": "synthetic-code"})
    entity = FreeboxRemote(router, {"id": 1}, entry)
    with pytest.raises(ServiceValidationError) as exc:
        await entity.async_send_command(**kwargs)
    assert exc.value.translation_key == key
    router._api.remote.send_key.assert_not_called()


@pytest.mark.parametrize("kind", ["remote", "remote_button", "media"])
async def test_missing_code_fails_before_device_side_effect(hass, home_context, kind):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entity, _ = build_entity(hass, router, node, entry, kind)
    action = entity.async_press if kind == "remote_button" else entity.async_turn_off
    with pytest.raises(ServiceValidationError) as exc:
        await action()
    assert exc.value.translation_key == "remote_code_missing"
    router._api.remote.send_key.assert_not_called()
    router._api.player._access.post.assert_not_called()


async def test_action_boundary_preserves_validation_and_cancellation():
    validation = ServiceValidationError(translation_domain="freebox_homexa", translation_key="invalid_source")
    @async_action_errors
    async def fail(error):
        raise error
    assert inspect.iscoroutinefunction(fail)
    with pytest.raises(ServiceValidationError) as exc:
        await fail(validation)
    assert exc.value is validation
    with pytest.raises(asyncio.CancelledError):
        await fail(asyncio.CancelledError())


@pytest.mark.parametrize("method,kwargs", [
    ("async_set_volume_level", {"volume": float("nan")}),
    ("async_set_volume_level", {"volume": 2}),
    ("async_set_volume_level", {"volume": True}),
    ("async_mute_volume", {"mute": "false"}),
    ("async_select_source", {"source": "unknown"}),
])
async def test_invalid_media_input_does_not_reach_transport(hass, home_context, method, kwargs):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entity, _ = build_entity(hass, router, node, entry, "media")
    with pytest.raises(ServiceValidationError):
        await getattr(entity, method)(**kwargs)
    router._api.player._access.put.assert_not_called()
    router._api.player._access.post.assert_not_called()
    router._api.remote.send_key.assert_not_called()


async def test_firmware_command_fallback_only_after_error(hass, home_context):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entity, _ = build_entity(hass, router, node, entry, "media")
    router._api.player._access.post.side_effect = [OSError("synthetic"), None]
    await entity.async_media_pause()
    assert router._api.player._access.post.call_args_list[0].args == ("player/1/api/v6/control/mediactrl", {"cmd": "pause"})
    assert router._api.player._access.post.call_args_list[1].args == ("player/1/api/v6/control/mediactrl", {"name": "pause"})


@pytest.mark.parametrize("service", ["reboot", "remote", "reload"])
async def test_real_ha_service_error_then_recovery(hass, home_context, service):
    from custom_components.freebox_homexa.services import async_setup_services
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    hass.config_entries.async_update_entry(entry, options={"remote_code": "synthetic-code"})
    router._api.player.get_players.return_value = [{"id": 1}]
    router._api.remote.send_key.return_value = True
    async_setup_services(hass)
    data = {"config_entry_id": entry.entry_id, **({"code": "home"} if service == "remote" else {})}
    target = router._api.system.reboot if service == "reboot" else router._api.remote.send_key
    try:
        with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=False)) as reload:
            if service != "reload":
                target.side_effect = OSError("synthetic-secret")
            with pytest.raises(HomeAssistantError) as exc:
                await hass.services.async_call("freebox_homexa", service, data, blocking=True)
            assert exc.value.translation_key == "command_failed"
            assert "synthetic-secret" not in str(exc.value)
            target.side_effect = None
            reload.return_value = True
            await hass.services.async_call("freebox_homexa", service, data, blocking=True)
    finally:
        entry._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)


@pytest.mark.parametrize("service", ["schedule_reminder", "cancel_reminder", "get_reminder_status"])
async def test_reminder_services_storage_error_then_recovery(hass, home_context, service):
    from custom_components.freebox_homexa.tnt_reminders import async_setup_reminders, _UNSUB_KEY, _reminder_id
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    hass.config_entries.async_update_entry(entry, options={"reminder_profiles": [
        {"name": "Test", "notify_target": ["synthetic_notify"]}]})
    from homeassistant.helpers.storage import Store
    store = Store(hass, 1, "homexa_synthetic_action_test")
    await store.async_save({"reminders": []})
    with patch("custom_components.freebox_homexa.tnt_reminders.Store", return_value=store):
        await async_setup_reminders(hass)
    data = {"channel_name": "Test channel", "program_title": "Test programme",
        "start_time": "2030-01-01T20:00:00+01:00", "profile_name": "Test"}
    if service != "get_reminder_status":
        data["minutes_before"] = 5
    timer = Mock()
    reminder_id = _reminder_id(data["channel_name"], data["program_title"], data["start_time"], 5, "Test")
    if service == "cancel_reminder":
        hass.data[_UNSUB_KEY][reminder_id] = timer
    operation = "async_save" if service == "schedule_reminder" else "async_load"
    with patch.object(store, operation, new=AsyncMock(side_effect=OSError("synthetic-secret"))):
        with pytest.raises(HomeAssistantError) as exc:
            await hass.services.async_call("freebox_homexa", service, data, blocking=True,
                return_response=service == "get_reminder_status")
        assert exc.value.translation_key == "command_failed"
        if service == "cancel_reminder":
            assert hass.data[_UNSUB_KEY][reminder_id] is timer
            timer.assert_not_called()
    await hass.services.async_call("freebox_homexa", service, data, blocking=True,
        return_response=service == "get_reminder_status")
    if service == "cancel_reminder":
        timer.assert_called_once()
    # Never fire the future reminder/notification during the test.
    for unsubscribe in hass.data[_UNSUB_KEY].values():
        unsubscribe()
    hass.data[_UNSUB_KEY].clear()


async def test_calendar_read_service_error_is_not_an_empty_success(hass, home_context):
    from homeassistant.util import dt as dt_util
    from custom_components.freebox_homexa.calendar import FreeboxTvGuideCalendar
    router, _ = home_context
    entity = FreeboxTvGuideCalendar(router)
    entity.hass = hass
    start = dt_util.now()
    router._api.tv.get_tv_channels.side_effect = TimeoutError
    with pytest.raises(HomeAssistantError) as exc:
        await entity.async_get_events(hass, start, start + timedelta(hours=1))
    assert exc.value.translation_key == "command_failed"
    await entity.async_update()  # Polling deliberately handles the same error gracefully.
    assert not entity.available
    assert entity.event is None
    router._api.tv.get_tv_channels.side_effect = None
    router._api.tv.get_tv_channels.return_value = {}
    router._api.tv.get_tv_programs_by_date.return_value = []
    await entity.async_update()
    assert entity.available


@pytest.mark.parametrize("status,length,timeout", [(200, 0, False), (200, 1, False), (503, 0, False), (200, 0, True)])
async def test_real_sdk_remote_acknowledgement_contract(hass, home_context, status, length, timeout):
    from freebox_api.api.remote import Remote
    router, node = home_context
    response = AsyncMock()
    response.status = status
    response.content_length = length
    get = AsyncMock(return_value=response, side_effect=TimeoutError if timeout else None)
    # Public constructor dependency, synthetic session; never inspect/mutate an SDK private session.
    router._api.remote = Remote(SimpleNamespace(session=SimpleNamespace(get=get)))
    entry = hass.config_entries.async_get_entry(router.entry_id)
    hass.config_entries.async_update_entry(entry, options={"remote_code": "synthetic-code"})
    entity, _ = build_entity(hass, router, node, entry, "remote")
    if status == 200 and length == 0 and not timeout:
        await entity.async_send_command(["home"])
    else:
        with pytest.raises(HomeAssistantError) as exc:
            await entity.async_send_command(["home"])
        assert exc.value.translation_key == "command_unconfirmed"
    get.assert_awaited_once()



def test_inventory_every_explicit_user_action_is_guarded():
    """Structural global check, supplemented by execution/HA-service tests above."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "custom_components/freebox_homexa"
    expected = {"button": 3, "remote": 3, "media_player": 11, "switch": 4,
        "alarm_control_panel": 4, "cover": 7, "camera": 2, "calendar": 1,
        "services": 3, "tnt_reminders": 3, "router": 1}
    exact = {"async_press", "async_set_volume_level", "async_mute_volume", "async_select_source",
        "async_play_media", "async_send_command", "async_open_cover", "async_close_cover",
        "async_stop_cover", "async_set_cover_position", "async_enable_motion_detection",
        "async_disable_motion_detection", "async_get_events", "async_handle_schedule",
        "async_handle_cancel", "async_handle_status", "async_reboot", "async_reload_config",
        "async_freebox_player_remote"}
    actual = {}
    for path in root.glob("*.py"):
        count = 0
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            action = (node.name in exact or node.name.startswith(("async_turn_", "async_media_", "async_alarm_"))
                or (path.stem == "router" and node.name == "reboot"))
            if not action:
                continue
            assert any(isinstance(d, ast.Name) and d.id == "async_action_errors" for d in node.decorator_list), (path, node.lineno, node.name)
            count += 1
        if count:
            actual[path.stem] = count
    assert actual == expected
    assert sum(actual.values()) == 42


@pytest.mark.parametrize("cancel", [False, True])
async def test_real_store_swallowed_write_error_does_not_report_success(hass, cancel):
    from homeassistant.core import ServiceCall
    from homeassistant.helpers.storage import Store
    from homeassistant.util.file import WriteError
    from custom_components.freebox_homexa.tnt_reminders import _ReminderManager, _UNSUB_KEY, _reminder_id
    store = Store(hass, 1, "homexa_synthetic_write_error")
    manager = _ReminderManager(hass, store)
    payload = {"channel_name": "Test", "program_title": "Test", "start_time": "2030-01-01T20:00:00+01:00", "minutes_before": 5}
    rid = _reminder_id("Test", "Test", payload["start_time"], 5, None)
    persisted = {"reminders": [{"id": rid}], "unrelated": "preserved"}
    await store.async_save(persisted)
    timer = Mock()
    hass.data.setdefault(_UNSUB_KEY, {})[rid] = timer
    service = "cancel_reminder" if cancel else "schedule_reminder"
    action = manager.async_handle_cancel if cancel else manager.async_handle_schedule
    with patch.object(manager, "_resolve_targets", return_value=(["synthetic_notify"], [], None, None)), \
         patch.object(manager, "_schedule") as schedule:
        # The HA plugin models disk I/O. Inject at its low-level write seam,
        # leaving the real Store.async_save/error-catching/read-back path intact.
        # This is a test seam in HA storage, never an SDK session or runtime hook.
        with patch.object(store, "_async_write_data", new=AsyncMock(side_effect=WriteError("synthetic disk failure"))):
            with pytest.raises(HomeAssistantError) as exc:
                await action(ServiceCall(hass, "freebox_homexa", service, payload))
        assert exc.value.translation_key == "reminder_storage_failed"
        assert await store.async_load() == persisted
        assert hass.data[_UNSUB_KEY][rid] is timer
        timer.assert_not_called()
        schedule.assert_not_called()
        await action(ServiceCall(hass, "freebox_homexa", service, payload))
        assert (await store.async_load())["unrelated"] == "preserved"
        if cancel:
            timer.assert_called_once()
            assert (await store.async_load())["reminders"] == []
        else:
            schedule.assert_called_once()
    hass.data[_UNSUB_KEY].clear()


async def test_concurrent_reminder_saves_keep_both_records(hass):
    from homeassistant.helpers.storage import Store
    from custom_components.freebox_homexa.tnt_reminders import _ReminderManager
    store = Store(hass, 1, "homexa_synthetic_concurrent_reminders")
    await store.async_save({"reminders": [], "unrelated": "preserved"})
    manager = _ReminderManager(hass, store)
    await asyncio.gather(manager._async_save({"id": "first"}), manager._async_save({"id": "second"}))
    data = await store.async_load()
    assert {record["id"] for record in data["reminders"]} == {"first", "second"}
    assert data["unrelated"] == "preserved"


async def test_status_waits_for_inflight_persistence_not_speculative_cache(hass):
    from homeassistant.core import ServiceCall
    from homeassistant.helpers.storage import Store
    from custom_components.freebox_homexa.tnt_reminders import _ReminderManager, _reminder_id
    store = Store(hass, 1, "homexa_synthetic_inflight_store")
    await store.async_save({"reminders": []})
    manager = _ReminderManager(hass, store)
    payload = {"channel_name": "Test", "program_title": "Test", "start_time": "2030-01-01T20:00:00+01:00"}
    rid = _reminder_id("Test", "Test", payload["start_time"], 5, None)
    started, release = asyncio.Event(), asyncio.Event()
    original_save = store.async_save
    async def delayed_save(data):
        started.set()
        await release.wait()
        await original_save(data)
    with patch.object(store, "async_save", side_effect=delayed_save):
        save_task = asyncio.create_task(manager._async_save({"id": rid}))
        await started.wait()
        read_task = asyncio.create_task(manager.async_handle_status(ServiceCall(hass, "freebox_homexa", "get_reminder_status", payload)))
        try:
            await asyncio.sleep(0)
            assert not read_task.done()
        finally:
            release.set()
            await save_task
        assert await read_task == {"scheduled_minutes": [5]}


@pytest.mark.parametrize("failure", [OSError("private SDK response"), TimeoutError()])
async def test_home_action_does_not_log_again_before_raising(hass, home_context, caplog, failure):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    from custom_components.freebox_homexa.cover import FreeboxShutter
    entity = FreeboxShutter(hass, router, node)
    router.home.set_home_endpoint_value.side_effect = failure
    caplog.clear()
    with pytest.raises(HomeAssistantError) as caught:
        await entity.async_open_cover()
    assert caught.value.translation_key == "command_failed"
    assert not [record for record in caplog.records if record.name == "custom_components.freebox_homexa.entity"]
