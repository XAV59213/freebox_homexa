"""Lifecycle failures against real HA entries; all device I/O is mocked."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from freebox_api.exceptions import AuthorizationError, HttpRequestError, InvalidTokenError, InsufficientPermissionsError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from test_home_platforms import home_context

from custom_components.freebox_homexa import async_setup_entry, async_unload_entry, async_migrate_entry

DOMAIN = 'freebox_homexa'


def entry_for(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test', 'port': 80}, version=1, minor_version=1)
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize('stage', ['open', 'probe'])
@pytest.mark.parametrize('error,expected', [
    (TimeoutError(), ConfigEntryNotReady),
    (aiohttp.ClientError('offline'), ConfigEntryNotReady),
    (OSError('offline'), ConfigEntryNotReady),
    (HttpRequestError('offline'), ConfigEntryNotReady),
    (AuthorizationError('denied'), ConfigEntryAuthFailed),
    (InvalidTokenError('invalid'), ConfigEntryAuthFailed),
    (InsufficientPermissionsError('denied'), ConfigEntryAuthFailed),
    (AuthorizationError('timed out'), ConfigEntryNotReady),
])
async def test_setup_failure_closes_sdk(hass, stage, error, expected):
    api = AsyncMock()
    (api.open if stage == 'open' else api.system.get_config).side_effect = error
    with patch('custom_components.freebox_homexa.JSModuleRegistration.async_register', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.Store.async_load', return_value={}), \
         patch('custom_components.freebox_homexa.get_api', return_value=api):
        with pytest.raises(expected):
            await async_setup_entry(hass, entry_for(hass))
    api.close.assert_awaited_once()


async def test_cancelled_probe_closes_sdk(hass):
    api = AsyncMock()
    api.system.get_config.side_effect = asyncio.CancelledError()
    with patch('custom_components.freebox_homexa.JSModuleRegistration.async_register', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.Store.async_load', return_value={}), \
         patch('custom_components.freebox_homexa.get_api', return_value=api):
        with pytest.raises(asyncio.CancelledError):
            await async_setup_entry(hass, entry_for(hass))
    api.close.assert_awaited_once()


@pytest.mark.parametrize('success', [True, False])
async def test_unload_retains_resources_on_platform_failure(hass, home_context, success):
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    entry.runtime_data = router
    store = MagicMock(async_save=AsyncMock(), async_load=AsyncMock(return_value={"synthetic": True}))
    hass.data[DOMAIN] = {'store': store, 'config': {'synthetic': True}}
    with patch.object(hass.config_entries, 'async_unload_platforms', return_value=success), \
         patch('custom_components.freebox_homexa.async_unload_bundled_tnt') as tnt:
        assert await async_unload_entry(hass, entry) is success
    assert router.closing is success
    assert router._api.close.await_count == int(success)
    assert store.async_save.await_count == 1
    assert tnt.call_count == int(success)


async def test_migration_preserves_existing_lan_devices(hass):
    entry = entry_for(hass)
    assert await async_migrate_entry(hass, entry)
    assert entry.options['create_lan_devices'] is True
    assert entry.minor_version == 2
    assert await async_migrate_entry(hass, entry)
    assert entry.options['create_lan_devices'] is True


async def test_success_probes_before_forwarding_and_unloads(hass):
    entry = entry_for(hass)
    api = AsyncMock()
    api.system.get_config.return_value = {
        'mac': '00:00:00:00:00:01', 'model_info': {'pretty_name': 'Test Freebox'},
        'firmware_version': '4.9.0',
    }
    router = MagicMock(update_all=AsyncMock(), update_home_devices=AsyncMock(), close=AsyncMock(),
                       mac='00:00:00:00:00:01', repeaters={}, wifi_aps={}, devices={})
    with patch('custom_components.freebox_homexa.JSModuleRegistration.async_register', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.Store.async_load', return_value={}), \
         patch('custom_components.freebox_homexa.Store.async_save', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.get_api', return_value=api), \
         patch('custom_components.freebox_homexa.FreeboxRouter', return_value=router), \
         patch('custom_components.freebox_homexa.async_setup_bundled_tnt', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.async_setup_reminders', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.async_track_time_interval', return_value=lambda: None) as intervals, \
         patch('custom_components.freebox_homexa.async_call_later', return_value=lambda: None), \
         patch.object(hass.config_entries, 'async_forward_entry_setups', new=AsyncMock()) as forward, \
         patch.object(hass.config_entries, 'async_unload_platforms', return_value=True):
        async def check_probe(*args):
            api.system.get_config.assert_awaited_once()
            router.update_all.assert_awaited_once()
            router.update_home_devices.assert_awaited_once()
        forward.side_effect = check_probe
        assert await async_setup_entry(hass, entry)
        assert entry.runtime_data is router
        assert intervals.call_count == 2
        api.close.assert_not_awaited()
        assert await async_unload_entry(hass, entry)
        router.close.assert_awaited_once()
        await entry._async_process_on_unload(hass)


async def test_close_error_does_not_mask_probe_error(hass):
    api = AsyncMock()
    api.open.side_effect = TimeoutError('original failure')
    api.close.side_effect = RuntimeError('close failure')
    with patch('custom_components.freebox_homexa.JSModuleRegistration.async_register', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.Store.async_load', return_value={}), \
         patch('custom_components.freebox_homexa.get_api', return_value=api):
        with pytest.raises(ConfigEntryNotReady) as exc:
            await async_setup_entry(hass, entry_for(hass))
    assert isinstance(exc.value.__cause__, TimeoutError)


@pytest.mark.parametrize("stage", ["registry", "initial_poll"])
@pytest.mark.parametrize("close_fails", [False, True])
async def test_real_ha_manager_cleans_failure_after_successful_probe(hass, stage, close_fails):
    from homeassistant.config_entries import ConfigEntryState
    entry = entry_for(hass)
    api = AsyncMock()
    api.system.get_config.return_value = {
        "mac": "00:00:00:00:00:05", "model_info": {"pretty_name": "Test", "name": "test"},
        "firmware_version": "4.9.0"}
    if stage == "registry":
        api.system.get_config.return_value["model_info"] = {}
    if close_fails:
        api.close.side_effect = RuntimeError("synthetic cleanup failure")
    with patch("custom_components.freebox_homexa.async_setup", new=AsyncMock(return_value=True)), \
         patch("custom_components.freebox_homexa.JSModuleRegistration.async_register", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.get_api", return_value=api), \
         patch("custom_components.freebox_homexa.FreeboxRouter.update_all", new=AsyncMock(side_effect=RuntimeError("synthetic initial poll failure"))):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    api.open.assert_awaited_once()
    api.system.get_config.assert_awaited_once()
    api.close.assert_awaited_once()


@pytest.mark.parametrize("cancel", [False, True])
async def test_failed_unload_restores_read_admission_and_preserves_failure(hass, home_context, cancel):
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    store = MagicMock(async_save=AsyncMock(), async_load=AsyncMock(return_value={"synthetic": True}))
    hass.data[DOMAIN] = {"store": store, "config": {"synthetic": True}}
    started = asyncio.Event()
    failure = RuntimeError("synthetic unload failure")
    async def unload(*args):
        assert router.closing
        started.set()
        if cancel:
            await asyncio.Future()
        raise failure
    with patch.object(hass.config_entries, "async_unload_platforms", side_effect=unload), \
         patch("custom_components.freebox_homexa.async_unload_bundled_tnt") as tnt:
        task = hass.async_create_background_task(async_unload_entry(hass, entry), "synthetic failing unload")
        await asyncio.wait_for(started.wait(), timeout=5)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else RuntimeError) as exc:
            await task
        if not cancel:
            assert exc.value is failure
        assert router.closing is False
        router._api.close.assert_not_called()
        tnt.assert_not_called()
        read = AsyncMock(return_value="synthetic read")
        assert await router.async_read(read) == "synthetic read"
        read.assert_awaited_once()


@pytest.mark.parametrize("raises", [False, True])
async def test_failed_unload_does_not_reopen_reads_during_another_close(hass, home_context, raises):
    from freebox_api.exceptions import NotOpenError
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    store = MagicMock(async_save=AsyncMock(), async_load=AsyncMock(return_value={"synthetic": True}))
    hass.data[DOMAIN] = {"store": store, "config": {"synthetic": True}}
    closing, release = asyncio.Event(), asyncio.Event()
    async def close_sdk():
        closing.set()
        await release.wait()
    router._api.close.side_effect = close_sdk
    close_task = None
    async def unload(*args):
        nonlocal close_task
        close_task = hass.async_create_background_task(router.close(), "synthetic concurrent close")
        await asyncio.wait_for(closing.wait(), timeout=5)
        if raises:
            raise RuntimeError("synthetic unload failure")
        return False
    try:
        with patch.object(hass.config_entries, "async_unload_platforms", side_effect=unload):
            if raises:
                with pytest.raises(RuntimeError):
                    await async_unload_entry(hass, entry)
            else:
                assert await async_unload_entry(hass, entry) is False
        assert router.closing
        read = AsyncMock()
        with pytest.raises(NotOpenError):
            await router.async_read(read)
        read.assert_not_called()
    finally:
        release.set()
        if close_task is not None:
            await close_task
    router.resume_reads_after_failed_unload()
    assert router.closing  # a completed SDK close cannot be "resumed" either
