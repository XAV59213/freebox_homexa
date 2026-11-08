"""Validate reminders and storage with real HA calls, never fire notifications."""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ServiceValidationError

from custom_components.freebox_homexa.tnt_reminders import _ReminderManager

DOMAIN = 'freebox_homexa'
BASE = {'channel_name': 'Test channel', 'program_title': 'Programme test', 'minutes_before': 5}


@pytest.mark.parametrize('when,key', [
    ('not a date', 'invalid_start_time'),
    ('2030-01-01T20:00:00', 'invalid_start_time'),
    ('2000-01-01T20:00:00+01:00', 'reminder_too_late'),
])
async def test_invalid_dates_raise_translated_error_without_saving(hass, when, key):
    store = AsyncMock()
    manager = _ReminderManager(hass, store)
    with patch.object(manager, '_resolve_targets', return_value=(['test_notify'], [], None, None)):
        with pytest.raises(ServiceValidationError) as exc:
            await manager.async_handle_schedule(ServiceCall(hass, DOMAIN, 'schedule_reminder', {**BASE, 'start_time': when}))
    assert exc.value.translation_key == key
    store.async_save.assert_not_awaited()


async def test_schedule_status_cancel_mock_storage_no_notification(hass):
    data = None
    async def load():
        return data
    async def save(value):
        nonlocal data
        data = value
    store = Mock(async_load=AsyncMock(side_effect=load), async_save=AsyncMock(side_effect=save))
    manager = _ReminderManager(hass, store)
    payload = {**BASE, 'start_time': '2030-01-01T20:00:00+01:00'}
    with patch.object(manager, '_resolve_targets', return_value=(['test_notify'], [], None, None)), \
         patch.object(manager, '_schedule', wraps=manager._schedule) as schedule:
        await manager.async_handle_schedule(ServiceCall(hass, DOMAIN, 'schedule_reminder', payload))
        schedule.assert_called_once()
    status = await manager.async_handle_status(ServiceCall(hass, DOMAIN, 'get_reminder_status', payload))
    assert status == {'scheduled_minutes': [5]}
    await manager.async_handle_cancel(ServiceCall(hass, DOMAIN, 'cancel_reminder', payload))
    status = await manager.async_handle_status(ServiceCall(hass, DOMAIN, 'get_reminder_status', payload))
    assert status == {'scheduled_minutes': []}


@pytest.mark.parametrize("fire_time", ["not-a-date", "2026-11-07T19:00:00"])
async def test_invalid_restored_timer_never_replaces_existing_timer(hass, fire_time):
    from unittest.mock import Mock
    from custom_components.freebox_homexa.tnt_reminders import _UNSUB_KEY
    store = AsyncMock()
    manager = _ReminderManager(hass, store)
    existing = Mock()
    hass.data[_UNSUB_KEY] = {"stable": existing}
    with pytest.raises(ServiceValidationError):
        manager._schedule({"id": "stable", "fire_time": fire_time})
    assert hass.data[_UNSUB_KEY]["stable"] is existing
    existing.assert_not_called()
    store.async_save.assert_not_called()


@pytest.mark.parametrize("profile", [
    {"name": "Saved", "notify_target": [42]},
    {"name": "Saved", "media_player_targets": {"bad": "shape"}},
    {"name": "Saved", "tts_engine": 42},
    {"name": "Saved", "announce_volume": "loud"},
])
async def test_malformed_profile_contract_rejected_without_mutating_options(hass, profile):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"reminder_profiles": [profile]})
    entry.add_to_hass(hass)
    manager = _ReminderManager(hass, AsyncMock())
    with pytest.raises(ServiceValidationError):
        manager._resolve_targets("Saved")
    assert entry.options["reminder_profiles"] == [profile]
