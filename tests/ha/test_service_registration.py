"""Register real HA services without calling any action or device."""
from unittest.mock import patch

from custom_components.freebox_homexa import async_setup


async def test_setup_registers_all_actions_once_without_entry(hass):
    with patch('custom_components.freebox_homexa.async_register_calls_websocket_api'), \
         patch('custom_components.freebox_homexa.tnt_reminders.Store.async_load', return_value=None), \
         patch.object(type(hass.services), 'async_register', autospec=True, side_effect=type(hass.services).async_register) as register:
        assert await async_setup(hass, {})
        assert await async_setup(hass, {})
    calls = [call for call in register.call_args_list if call.args[1] == 'freebox_homexa']
    assert len(calls) == 6
    names = {call.args[2] for call in calls}
    assert names == {'reboot', 'reload', 'remote', 'schedule_reminder', 'cancel_reminder', 'get_reminder_status'}
    assert all(hass.services.has_service('freebox_homexa', name) for name in names)
