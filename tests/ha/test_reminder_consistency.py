"""Ambiguous commits and timers, using public HA Store and real future timers."""
from unittest.mock import AsyncMock, Mock, patch
import pytest
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util.file import WriteError
from custom_components.freebox_homexa.tnt_reminders import _ReminderManager, _UNSUB_KEY

PAYLOAD = {"channel_name": "Synthetic", "program_title": "Synthetic", "start_time": "2030-01-01T20:00:00+01:00", "minutes_before": 5}


@pytest.mark.parametrize("cancel", [False, True])
async def test_successful_write_failed_readback_never_confirms_inconsistent_status(hass, cancel):
    store = Store(hass, 1, "homexa_synthetic_ambiguous")
    await store.async_save({"reminders": [], "unrelated": True})
    manager = _ReminderManager(hass, store)
    schedule = ServiceCall(hass, "freebox_homexa", "schedule_reminder", PAYLOAD)
    cancel_call = ServiceCall(hass, "freebox_homexa", "cancel_reminder", PAYLOAD)
    status = ServiceCall(hass, "freebox_homexa", "get_reminder_status", PAYLOAD)
    try:
        with patch.object(manager, "_resolve_targets", return_value=(["synthetic_notify"], [], None, None)):
            if cancel:
                await manager.async_handle_schedule(schedule)
            before = await store.async_load()
            action, call = (manager.async_handle_cancel, cancel_call) if cancel else (manager.async_handle_schedule, schedule)
            with patch.object(store, "async_load", side_effect=[before, OSError("synthetic verification failure")]):
                with pytest.raises(HomeAssistantError) as caught:
                    await action(call)
            assert caught.value.translation_key == "reminder_storage_failed"
            # The write DID commit, but the timer change did NOT occur.
            assert bool((await store.async_load())["reminders"]) is not cancel
            assert bool(hass.data.get(_UNSUB_KEY)) is cancel
            with pytest.raises(HomeAssistantError) as caught:
                await manager.async_handle_status(status)
            assert caught.value.translation_key == "reminder_state_unconfirmed"
            await action(call)  # explicit user retry reconciles; no automatic retry
            assert await manager.async_handle_status(status) == {"scheduled_minutes": [] if cancel else [5]}
            assert (await store.async_load())["unrelated"] is True
    finally:
        for unsub in hass.data.pop(_UNSUB_KEY, {}).values():
            unsub()


async def test_reschedule_replaces_the_previous_timer_without_duplicate_callback(hass):
    store = Store(hass, 1, "homexa_synthetic_replace")
    manager = _ReminderManager(hass, store)
    call = ServiceCall(hass, "freebox_homexa", "schedule_reminder", PAYLOAD)
    try:
        with patch.object(manager, "_resolve_targets", return_value=(["synthetic_notify"], [], None, None)):
            await manager.async_handle_schedule(call)
            timers = hass.data[_UNSUB_KEY]
            rid, previous = next(iter(timers.items()))
            timers[rid] = observed = Mock(wraps=previous)
            await manager.async_handle_schedule(call)
            observed.assert_called_once_with()
            assert len(timers) == 1
            assert timers[rid] is not observed
            assert len((await store.async_load())["reminders"]) == 1
    finally:
        for unsub in hass.data.pop(_UNSUB_KEY, {}).values():
            unsub()


async def test_restore_pruning_failure_preserves_future_timer_and_unrelated_fields(hass):
    store = Store(hass, 1, "homexa_synthetic_restore")
    data = {"reminders": [{"id": "future", "fire_time": "2030-01-01T19:55:00+01:00"},
                          {"id": "expired", "fire_time": "2000-01-01T19:55:00+01:00"}], "unrelated": True}
    await store.async_save(data)
    manager = _ReminderManager(hass, store)
    try:
        with patch.object(store, "_async_write_data", new=AsyncMock(side_effect=WriteError("synthetic disk failure"))):
            with pytest.raises(HomeAssistantError):
                await manager.async_restore_pending()
        assert set(hass.data[_UNSUB_KEY]) == {"future"}
        assert await store.async_load() == data
        await manager.async_restore_pending()
        assert (await store.async_load()) == {"reminders": [data["reminders"][0]], "unrelated": True}
        assert set(hass.data[_UNSUB_KEY]) == {"future"}
    finally:
        for unsub in hass.data.pop(_UNSUB_KEY, {}).values():
            unsub()
