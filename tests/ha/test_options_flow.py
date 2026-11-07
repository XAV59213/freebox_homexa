"""Options through HA's manager, preserving unrelated settings and reload once."""
from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = 'freebox_homexa'


async def test_general_options_preserve_other_pages(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test', 'port': 80},
                            options={'tnt_channels': ['TF1'], 'reminder_profiles': []})
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)) as reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result['type'] == FlowResultType.MENU
        assert 'general' in result['menu_options']
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': 'general'})
        assert result['step_id'] == 'general'
        result = await hass.config_entries.options.async_configure(result['flow_id'], {})
        await hass.async_block_till_done()
        assert result['type'] == FlowResultType.CREATE_ENTRY
        assert entry.options['tnt_channels'] == ['TF1']
        assert entry.options['reminder_profiles'] == []
        reload.assert_awaited_once_with(entry.entry_id)


async def test_empty_groups_abort_without_mutation(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test'})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': 'groups'})
    assert result['type'] == FlowResultType.ABORT
    assert result['reason'] == 'no_devices'
    assert not entry.options
