"""Actual TNT coordinators and entry ownership; XMLTV network always mocked."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_homexa.tnt_coordinator import ProgrammeTntFrCoordinator
from custom_components.freebox_homexa.tnt_setup import async_setup_bundled_tnt, async_unload_bundled_tnt, TNT_COORDINATORS_KEY


async def test_xmltv_failure_is_translated_without_fake_program(hass):
    coordinator = ProgrammeTntFrCoordinator(hass, ['TF1.fr'])
    try:
        with patch.object(coordinator, '_fetch_and_parse', new=AsyncMock(side_effect=OSError('synthetic offline'))):
            with pytest.raises(UpdateFailed) as exc:
                await coordinator._async_update_data()
        assert exc.value.translation_domain == 'freebox_homexa'
        assert exc.value.translation_key == 'cannot_fetch_tnt'
        assert exc.value.translation_placeholders == {'error': 'OSError'}
        assert not coordinator.data
    finally:
        await coordinator.async_shutdown()


async def test_empty_xmltv_is_not_an_invented_program(hass):
    coordinator = ProgrammeTntFrCoordinator(hass, ['TF1.fr'])
    try:
        with patch.object(coordinator, '_fetch_and_parse', new=AsyncMock()) as fetch:
            first = await coordinator._async_update_data()
            second = await coordinator._async_update_data()
        fetch.assert_awaited_once()  # Hourly fetch gate, not a network request every poll.
        assert first == second
        assert first['TF1.fr']['current'] is None
    finally:
        await coordinator.async_shutdown()


async def test_two_entry_tnt_setup_shutdown_isolated(hass):
    entries = [MockConfigEntry(domain='freebox_homexa', data={'host': f'box{i}.test'}, options={'tnt_channels': ['TF1.fr']}) for i in range(2)]
    for entry in entries:
        entry.add_to_hass(hass)
    with patch('custom_components.freebox_homexa.tnt_setup.async_register_homexa_websocket_api') as register, \
         patch.object(ProgrammeTntFrCoordinator, 'async_config_entry_first_refresh', new=AsyncMock()):
        coordinators = [await async_setup_bundled_tnt(hass, entry) for entry in entries]
    register.assert_called_once()
    assert all(coordinator.config_entry is entry for coordinator, entry in zip(coordinators, entries))
    try:
        async_unload_bundled_tnt(hass, entries[0])
        await entries[0]._async_process_on_unload(hass)
        assert coordinators[0]._shutdown_requested
        assert not coordinators[1]._shutdown_requested
        assert entries[0].entry_id not in hass.data['freebox_homexa'][TNT_COORDINATORS_KEY]
        assert hass.data['freebox_homexa'][TNT_COORDINATORS_KEY][entries[1].entry_id] is coordinators[1]
    finally:
        for entry in entries:
            async_unload_bundled_tnt(hass, entry)
            await entry._async_process_on_unload(hass)
