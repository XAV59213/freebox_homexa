"""Exercise actual router recovery and HA dispatcher, never a real device."""
from datetime import datetime, timezone
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_homexa.router import FreeboxRouter


@pytest.fixture
def router(hass):
    entry = MockConfigEntry(domain='freebox_homexa', data={'host': 'freebox.test'})
    entry.add_to_hass(hass)
    return FreeboxRouter(hass, entry, AsyncMock(), {
        'mac': '00:00:00:00:00:01', 'model_info': {'pretty_name': 'Test', 'name': 'test'},
        'firmware_version': '4.9.0',
    })


async def test_periodic_failure_logged_once_and_recovers(hass, router, caplog):
    signal = Mock()
    remove = async_dispatcher_connect(hass, router.signal_sensor_update, signal)
    try:
        with patch.object(router, 'update_device_trackers', new=AsyncMock(side_effect=TimeoutError('offline'))) as hosts, \
             patch.object(router, 'update_sensors', new=AsyncMock()) as sensors, \
             caplog.at_level(logging.INFO, logger='custom_components.freebox_homexa.router'):
            for _ in range(3):
                await router.update_all(datetime.now(timezone.utc))
            await hass.async_block_till_done()
            assert not router.reachable
            assert caplog.text.count('Freebox injoignable (') == 1
            assert signal.call_count == 1
            sensors.assert_not_awaited()
            hosts.side_effect = None
            await router.update_all(datetime.now(timezone.utc))
            await hass.async_block_till_done()
            assert router.reachable
            assert caplog.text.count('Freebox de nouveau joignable (') == 1
            assert signal.call_count == 2
            sensors.assert_awaited_once()
    finally:
        remove()


async def test_initial_poll_propagates_and_closing_skips(router):
    with patch.object(router, 'update_device_trackers', new=AsyncMock(side_effect=TimeoutError())) as hosts:
        with pytest.raises(TimeoutError):
            await router.update_all()
        router.closing = True
        await router.update_all()
        hosts.assert_awaited_once()


async def test_home_poll_never_overlaps(router):
    async with router._home_update_lock:
        await router.update_home_devices()
    router.home.get_home_nodes.assert_not_awaited()
    router.home_granted = False
    await router.update_home_devices()
    router.home.get_home_nodes.assert_not_awaited()
