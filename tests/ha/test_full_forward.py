"""Actual HA forwarding/discovery of every integration platform, mocked I/O only."""
from unittest.mock import AsyncMock, patch
import pytest
import asyncio
from homeassistant.helpers.entity_platform import async_get_platforms

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from custom_components.freebox_homexa.const import DOMAIN, PLATFORMS
from test_home_platforms import home_context


@pytest.mark.parametrize("interrupt_forward,poll_index", [(False, 0), (False, 1), ("partial", 0), ("complete", 0), ("rollback_refused", 0), ("rollback_raises", 0)] + [(False, kind) for kind in ("media", "remote", "wifi", "alarm", "calendar", "calendar_programs")])
async def test_real_forward_discovers_all_domains_then_unloads(hass, home_context, interrupt_forward, poll_index):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    api = router._api
    api.system.get_config.return_value = {"mac": router.mac,
        "model_info": {"pretty_name": "Test", "name": "test"}, "firmware_version": "4.9.0"}
    for number, category in ((43, "camera"), (44, "alarm")):
        router.home_devices[number] = {**node, "id": number, "category": category}
    router.wifi_aps = {"gateway": {"kind": "gateway", "name": "Test", "online": True, "state": "active"}}
    client = {"l2ident": {"id": "00:00:00:00:10:01"}, "primary_name": "Test", "active": True, "host_type": "computer"}
    router.devices[client["l2ident"]["id"]] = client
    api.player.get_players.return_value = [{"id": 1, "name": "Test Player", "api_available": True}]
    api.player.get_player_status.return_value = {"power_state": "standby"}
    api.player._access.get.return_value = {"power_state": "standby"}
    api.tv.get_tv_channels.return_value = {}
    api.tv.get_tv_programs_by_date.return_value = {}
    real_unload = hass.config_entries.async_unload_platforms
    async def unload(owner, domains):
        if interrupt_forward == "rollback_refused":
            return False
        if interrupt_forward == "rollback_raises":
            raise RuntimeError("synthetic rollback failure")
        return await real_unload(owner, domains)
    real_forward = hass.config_entries.async_forward_entry_setups
    async def forward(owner, domains):
        if interrupt_forward:
            await real_forward(owner, domains if interrupt_forward in ("complete", "rollback_refused", "rollback_raises") else ["camera", "switch", "sensor"])
            await hass.async_block_till_done()
            raise RuntimeError("synthetic interrupted forward")
        await real_forward(owner, domains)
    with patch("custom_components.freebox_homexa.async_track_time_interval", wraps=async_track_time_interval) as intervals, \
         patch.object(hass.config_entries, "async_forward_entry_setups", side_effect=forward), \
         patch.object(hass.config_entries, "async_unload_platforms", side_effect=unload), \
         patch("custom_components.freebox_homexa.async_setup", new=AsyncMock(return_value=True)), \
         patch("custom_components.freebox_homexa.JSModuleRegistration.async_register", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.get_api", return_value=api), \
         patch("custom_components.freebox_homexa.FreeboxRouter", return_value=router), \
         patch.object(router, "update_all", new=AsyncMock()), \
         patch.object(router, "update_home_devices", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.tnt_coordinator.ProgrammeTntFrCoordinator._async_update_data", new=AsyncMock(return_value={})), \
         patch("custom_components.freebox_homexa.async_setup_reminders", new=AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id) is (not interrupt_forward)
        await hass.async_block_till_done()
        api.player._access.post.assert_not_called()
        api.player._access.put.assert_not_called()
        api.remote.send_key.assert_not_called()
        api.home.set_home_endpoint_value.assert_not_called()
        if interrupt_forward:
            assert entry.state is ConfigEntryState.SETUP_ERROR
            if interrupt_forward in ("rollback_refused", "rollback_raises"):
                assert any(platform.entities for platform in async_get_platforms(hass, DOMAIN))
                assert router.closing
                # Characterization: no fictitious atomic rollback. Framework
                # platforms survive a refused cleanup, even though SDK is closed.
                assert await real_unload(entry, PLATFORMS)
            assert all(not platform.entities for platform in async_get_platforms(hass, DOMAIN))
            assert not hass.data.get("dispatcher", {}).get(router.signal_home_device_new)
            assert entry.entry_id not in hass.data[DOMAIN].get("tnt_coordinators", {})
            api.close.assert_awaited_once()
            return
        assert entry.state is ConfigEntryState.LOADED
        owned = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        domains = {entity.domain for entity in owned}
        assert set(PLATFORMS) <= domains
        assert all(hass.states.get(entity.entity_id) is not None for entity in owned if not entity.disabled)
        started, drained = asyncio.Event(), asyncio.Event()
        async def blocked_read(*args, **kwargs):
            started.set()
            try:
                await asyncio.Future()
            finally:
                drained.set()
        if isinstance(poll_index, int):
            (router.update_all if poll_index == 0 else router.update_home_devices).side_effect = blocked_read
            interval_callback = intervals.call_args_list[poll_index].args[1]
            task = hass.async_create_background_task(interval_callback(None), "synthetic actual interval callback")
        else:
            domain, transport = {
                "media": ("media_player", api.player._access.get),
                "remote": ("remote", api.player.get_player_status),
                "wifi": ("switch", api.wifi.get_global_config),
                "alarm": ("alarm_control_panel", api.home.get_home_endpoint_value),
                "calendar": ("calendar", api.tv.get_tv_channels),
                "calendar_programs": ("calendar", api.tv.get_tv_programs_by_date),
            }[poll_index]
            platform = next(p for p in async_get_platforms(hass, DOMAIN) if p.domain == domain)
            entity = next(e for e in platform.entities.values()
                if domain != "switch" or getattr(getattr(e, "entity_description", None), "key", None) == "wifi")
            transport.side_effect = blocked_read
            task = entry.async_create_background_task(hass,
                entity.async_update_ha_state(force_refresh=True), "synthetic entity read")
        await started.wait()
        async def close_after_drain():
            assert drained.is_set()
            assert task.done()
        api.close.side_effect = close_after_drain
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert all((state := hass.states.get(entity.entity_id)) is None or state.state == "unavailable" for entity in owned)
        assert not hass.data.get("dispatcher", {}).get(router.signal_home_device_new)
        assert not hass.data.get("dispatcher", {}).get(router.signal_device_new)
        api.close.assert_awaited_once()
        assert task.cancelled()
        assert not router.poll_tasks
        assert not router.read_tasks
        rejected = AsyncMock()
        await router.async_poll(rejected)
        rejected.assert_not_called()
        api.player._access.post.assert_not_called()
        api.player._access.put.assert_not_called()
        api.remote.send_key.assert_not_called()
        api.home.set_home_endpoint_value.assert_not_called()
