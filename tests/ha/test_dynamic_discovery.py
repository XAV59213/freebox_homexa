"""Discovery after genuine HA forwarding; public SDK reads, synthetic I/O only."""
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import AsyncMock, Mock, patch

import pytest
from freebox_api.api.home import Home
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import async_get_platforms

from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.router import FreeboxRouter
from test_home_platforms import home_context


@pytest.fixture
async def forwarded_empty(hass, home_context, request):
    router, seed = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    api = router._api
    router.home_devices = {}
    transport = Mock(get=AsyncMock(), post=AsyncMock(), put=AsyncMock())
    snapshot = []
    async def read(path):
        if path == 'home/nodes':
            return snapshot
        assert path.startswith('home/endpoints/')
        return {'value': False}
    transport.get.side_effect = read
    api.home = Home(transport)
    api.system.get_config.return_value = {'mac': router.mac, 'sensors': [],
        'serial': 'SYNTHETIC', 'uptime_val': 0,
        'model_info': {'pretty_name': 'Test', 'name': 'test'}, 'firmware_version': '4.9.0'}
    api.player.get_players.return_value = []
    real_forward = hass.config_entries.async_forward_entry_setups
    first = {'remote_first': 'remote', 'media_player_first': 'media_player'}.get(getattr(request, 'param', None))
    async def ordered_first(owner, domains):
        await real_forward(owner, [first])
        await real_forward(owner, [domain for domain in domains if domain != first])
    with ExitStack() as stack:
        if first is not None:
            stack.enter_context(patch.object(hass.config_entries, 'async_forward_entry_setups', side_effect=ordered_first))
        for target in ('async_setup', 'JSModuleRegistration.async_register', 'async_setup_reminders'):
            stack.enter_context(patch(f'custom_components.freebox_homexa.{target}', new=AsyncMock(return_value=True)))
        stack.enter_context(patch('custom_components.freebox_homexa.get_api', return_value=api))
        stack.enter_context(patch('custom_components.freebox_homexa.FreeboxRouter', return_value=router))
        stack.enter_context(patch.object(router, 'update_all', new=AsyncMock()))
        stack.enter_context(patch.object(router, 'update_home_devices', new=AsyncMock()))
        stack.enter_context(patch('custom_components.freebox_homexa.tnt_coordinator.ProgrammeTntFrCoordinator._async_update_data', new=AsyncMock(return_value={})))
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield router, entry, seed, snapshot, transport
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        transport.post.assert_not_called()
        transport.put.assert_not_called()
        api.player._access.post.assert_not_called()
        api.remote.send_key.assert_not_called()
        assert not hass.data.get('dispatcher', {}).get(router.signal_home_device_new)
        assert not hass.data.get('dispatcher', {}).get(router.signal_home_device_update)
        assert not hass.data.get('dispatcher', {}).get(router.signal_sensor_update)


def owned(hass, entry):
    return {row.entity_id: row for row in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}


@pytest.mark.parametrize('category,domain', [('basic_shutter', 'cover'), ('shutter', 'cover'),
    ('opener', 'cover'), ('alarm', 'alarm_control_panel'), ('camera', 'camera'),
    ('pir', 'binary_sensor'), ('dws', 'binary_sensor')])
async def test_new_home_nodes_after_forward_are_added_once_preserving_customization(hass, forwarded_empty, category, domain):
    router, entry, seed, snapshot, transport = forwarded_empty
    before = owned(hass, entry)
    node = deepcopy(seed)
    node.update(id=600, category=category)
    node['type']['endpoints'].append({'id': 80, 'name': 'trigger', 'ep_type': 'signal', 'value': False})
    snapshot.append(node)
    await FreeboxRouter.update_home_devices(router)
    await hass.async_block_till_done()
    added = {eid: row for eid, row in owned(hass, entry).items() if eid not in before}
    assert any(row.domain == domain for row in added.values())
    registry = er.async_get(hass)
    for row in added.values():
        registry.async_update_entity(row.entity_id, name='Mon appareil', icon='mdi:star', hidden_by=er.RegistryEntryHider.USER)
        registry.async_update_entity_options(row.entity_id, 'conversation', {'should_expose': False})
    expected = {eid: registry.async_get(eid) for eid in added}
    entity_objects = {e.entity_id: e for platform in async_get_platforms(hass, DOMAIN) for e in platform.entities.values()}
    # Absence is not removal of the entity, registry ID, history or user settings.
    snapshot.clear()
    await FreeboxRouter.update_home_devices(router)
    await hass.async_block_till_done()
    snapshot.append(node)
    for _ in range(3):
        await FreeboxRouter.update_home_devices(router)
        await hass.async_block_till_done()
    assert set(owned(hass, entry)) == set(before) | set(added)
    for eid, row in expected.items():
        assert registry.async_get(eid) == row
        assert next(e for p in async_get_platforms(hass, DOMAIN) for e in p.entities.values() if e.entity_id == eid) is entity_objects[eid]
    assert any(call.args[0] == 'home/nodes' for call in transport.get.await_args_list)


async def test_existing_node_gains_battery_and_tamper_without_new_node_signal(hass, forwarded_empty):
    router, entry, seed, snapshot, _ = forwarded_empty
    snapshot.append(deepcopy(seed))
    await FreeboxRouter.update_home_devices(router)
    await hass.async_block_till_done()
    before = owned(hass, entry)
    snapshot[0]['type']['endpoints'].extend([
        {'id': 81, 'name': 'battery', 'label': 'Battery', 'ep_type': 'signal', 'value': 97},
        {'id': 82, 'name': 'cover', 'label': 'Tamper', 'ep_type': 'signal', 'value': False}])
    await FreeboxRouter.update_home_devices(router)
    await hass.async_block_till_done()
    after = owned(hass, entry)
    added = [row for eid, row in after.items() if eid not in before]
    assert {row.domain for row in added} == {'sensor', 'binary_sensor'}
    assert len(added) == 2
    for _ in range(3):
        await FreeboxRouter.update_home_devices(router)
        await hass.async_block_till_done()
    assert owned(hass, entry) == after
    router.closing = True
    snapshot[0]['id'] = 99
    async_dispatcher_send(hass, router.signal_home_device_new)
    async_dispatcher_send(hass, router.signal_home_device_update)
    await hass.async_block_till_done()
    assert owned(hass, entry) == after


async def test_late_storage_partitions_raid_and_temperature_from_real_sdk(hass, forwarded_empty):
    from freebox_api.api.storage import Storage
    router, entry, _, _, _ = forwarded_empty
    transport = Mock(get=AsyncMock(), post=AsyncMock(), put=AsyncMock())
    disks, raids = [], []
    async def read(path):
        assert path in {'storage/disk/', 'storage/raid/'}
        return disks if path == 'storage/disk/' else raids
    transport.get.side_effect = read
    router._api.storage = Storage(transport)
    router._api.connection.get_status.return_value = {}
    router._api.call.get_calls_log.return_value = []
    before = owned(hass, entry)
    disks.append({'id': 1, 'model': 'Test disk', 'partitions': [
        {'id': 1, 'label': 'Test partition', 'total_bytes': 100, 'free_bytes': 40}]})
    raids.append({'id': 4, 'name': 'Test RAID', 'degraded': False})
    router._api.system.get_config.return_value['sensors'] = [{'name': 'temp_cpu', 'value': 42}]
    await router.update_sensors()
    await hass.async_block_till_done()
    assert router.sensors_available and router.disks_available and router.raids_available
    added = {eid: row for eid, row in owned(hass, entry).items() if eid not in before}
    assert {row.domain for row in added.values()} == {'sensor', 'binary_sensor'}
    assert len(added) == 3
    # New partition on an already tracked disk; RAID display change is not a new identity.
    disks[0]['partitions'].append({'id': 2, 'label': 'Second', 'total_bytes': 200, 'free_bytes': 50})
    raids[0]['name'] = 'New display label'
    for _ in range(3):
        await router.update_sensors()
        await hass.async_block_till_done()
    after = owned(hass, entry)
    assert len(after) == len(before) + 4
    assert all(after[eid].unique_id == row.unique_id for eid, row in added.items())
    transport.post.assert_not_called()
    transport.put.assert_not_called()


@pytest.mark.parametrize('bad_state', [None, False, 42, [], {'unexpected': 'SYNTHETIC'}])
async def test_alarm_unknown_non_string_state_never_becomes_armed(hass, home_context, bad_state):
    from custom_components.freebox_homexa.alarm_control_panel import FreeboxAlarm
    from test_home_platforms import make_platform
    router, node = home_context
    alarm = FreeboxAlarm(hass, router, {**node, 'category': 'alarm'})
    platform = make_platform(hass, 'alarm_control_panel')
    router.home.get_home_endpoint_value.return_value = {'value': 'idle'}
    try:
        await platform.async_add_entities([alarm], update_before_add=True)
        assert hass.states.get(alarm.entity_id).state == 'disarmed'
        router.home.get_home_endpoint_value.return_value = {'value': bad_state}
        await alarm.async_update_ha_state(force_refresh=True)
        assert hass.states.get(alarm.entity_id).state == 'unknown'
        await alarm.async_update_during_arming()
        assert hass.states.get(alarm.entity_id).state == 'unknown'
        router.home.get_home_endpoint_value.return_value = {'value': 'alarm2_armed'}
        await alarm.async_update_ha_state(force_refresh=True)
        assert hass.states.get(alarm.entity_id).state == 'armed_home'
        router.home.set_home_endpoint_value.assert_not_called()
    finally:
        await platform.async_reset()


async def test_discovery_lazy_duplicate_batch_retry_and_entry_owned_unload(hass, forwarded_empty):
    from homeassistant.components.sensor import SensorEntity
    from custom_components.freebox_homexa.discovery import async_setup_discovery
    router, entry, _, _, _ = forwarded_empty
    platform = next(p for p in async_get_platforms(hass, DOMAIN) if p.domain == 'sensor')
    attempts = []
    fail = True
    def create(key):
        nonlocal fail
        attempts.append(key)
        if key == 'b' and fail:
            raise ValueError('synthetic malformed candidate')
        entity = SensorEntity()
        entity._attr_unique_id = f'discovery-{key}'
        entity._attr_name = f'Discovery {key}'
        return entity
    keys = []
    signal = f'{router.signal_sensor_update}-discovery-proof'
    def candidates():
        for key in keys:
            yield key, lambda key=key: create(key)
    def add(entities, update_before_add):
        entry.async_create_task(hass, platform.async_add_entities(entities, update_before_add), 'discovery proof add')
    async_setup_discovery(hass, entry, router, [signal], candidates, add)
    before = owned(hass, entry)
    keys[:] = ['a', 'a', 'b']
    async_dispatcher_send(hass, signal)
    await hass.async_block_till_done()
    assert attempts == ['a', 'b']
    assert owned(hass, entry) == before
    fail = False
    async_dispatcher_send(hass, signal)
    await hass.async_block_till_done()
    after = owned(hass, entry)
    assert len(after) == len(before) + 2
    assert attempts == ['a', 'b', 'a', 'b']
    async_dispatcher_send(hass, signal)
    await hass.async_block_till_done()
    assert attempts == ['a', 'b', 'a', 'b']
    assert owned(hass, entry) == after
    # The actual entry's native unload owns this subscription as well.


async def test_player_added_after_healthy_setup_shared_poll_and_preferences(hass, forwarded_empty):
    from freebox_api.api.player import Player
    router, entry, _, _, _ = forwarded_empty
    transport = Mock(get=AsyncMock(), post=AsyncMock(), put=AsyncMock())
    players = []
    async def read(path):
        if path == 'player':
            return players
        return {'power_state': 'standby'}
    transport.get.side_effect = read
    router._api.player = Player(transport)
    before = owned(hass, entry)
    players.append({'id': 31, 'name': 'Late Player', 'api_available': False})
    await router.async_update_players()
    await hass.async_block_till_done()
    assert owned(hass, entry) == before
    players[0]['api_available'] = True
    with patch.object(router, 'update_device_trackers', new=AsyncMock()), patch.object(router, 'update_sensors', new=AsyncMock()), \
         patch.object(hass.config_entries, 'async_reload', new=AsyncMock()) as reload:
        await FreeboxRouter.update_all(router)
        await hass.async_block_till_done()
        added = {eid: row for eid, row in owned(hass, entry).items() if eid not in before}
        assert {row.domain for row in added.values()} == {'media_player', 'remote', 'button'}
        registry = er.async_get(hass)
        for row in added.values():
            registry.async_update_entity(row.entity_id, name='Mon Player', icon='mdi:star', hidden_by=er.RegistryEntryHider.USER)
            registry.async_update_entity_options(row.entity_id, 'conversation', {'should_expose': False})
        expected = {eid: registry.async_get(eid) for eid in added}
        players.clear()
        await FreeboxRouter.update_all(router)
        await hass.async_block_till_done()
        players.append({'id': 31, 'name': 'Changed source label', 'api_available': True})
        transport.get.reset_mock()
        for _ in range(3):
            await FreeboxRouter.update_all(router)
            await hass.async_block_till_done()
        assert sum(call.args[0] == 'player' for call in transport.get.await_args_list) == 3
        assert set(owned(hass, entry)) == set(before) | set(added)
        assert all(registry.async_get(eid) == row for eid, row in expected.items())
        reload.assert_not_called()
    transport.post.assert_not_called()
    transport.put.assert_not_called()
    assert not hass.data.get('dispatcher', {}).get(f'{router.signal_players_update}-other-entry')


async def test_two_real_entries_late_player_isolation_and_unload(hass, forwarded_empty):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    router, entry, seed, snapshot, _ = forwarded_empty
    second_entry = MockConfigEntry(domain=DOMAIN, data={'host': 'second.test'})
    second_entry.add_to_hass(hass)
    api = AsyncMock()
    info = {'mac': '00:00:00:00:00:09', 'model_info': {'pretty_name': 'Second', 'name': 'test'}, 'firmware_version': '4.9.0'}
    second = FreeboxRouter(hass, second_entry, api, info)
    api.system.get_config.return_value = info
    api.player.get_players.return_value = []
    api.wifi.get_global_config.return_value = {'enabled': True}
    with patch('custom_components.freebox_homexa.FreeboxRouter', return_value=second), \
         patch('custom_components.freebox_homexa.get_api', return_value=api), \
         patch.object(second, 'update_all', new=AsyncMock()), \
         patch.object(second, 'update_home_devices', new=AsyncMock()):
        assert await hass.config_entries.async_setup(second_entry.entry_id)
        await hass.async_block_till_done()
        initial_second = owned(hass, second_entry)
        initial_first = owned(hass, entry)
        router._api.player.get_players.return_value = [{'id': 91, 'name': 'First only', 'api_available': True}]
        router._api.player.get_player_status.return_value = {'power_state': 'standby'}
        router._api.player._access.get.return_value = {'power_state': 'standby'}
        await router.async_update_players()
        await hass.async_block_till_done()
        assert len(owned(hass, entry)) > len(initial_first)
        assert owned(hass, second_entry) == initial_second
        assert router.signal_players_update != second.signal_players_update
        first_owned = owned(hass, entry)
        api.player.get_players.return_value = [{'id': 91, 'name': 'Second only', 'api_available': True}]
        api.player.get_player_status.return_value = {'power_state': 'standby'}
        api.player._access.get.return_value = {'power_state': 'standby'}
        await second.async_update_players()
        await hass.async_block_till_done()
        assert len(owned(hass, second_entry)) > len(initial_second)
        assert owned(hass, entry) == first_owned
        initial_second = owned(hass, second_entry)
        router.devices['00:00:00:00:98:01'] = {'l2ident': {'id': '00:00:00:00:98:01'},
            'primary_name': 'First entry LAN', 'active': True, 'connectivity_type': 'wifi'}
        router.wifi_aps['gateway'] = {'kind': 'gateway', 'name': 'First AP', 'online': True, 'state': 'active'}
        async_dispatcher_send(hass, router.signal_device_new)
        async_dispatcher_send(hass, router.signal_device_update)
        await hass.async_block_till_done()
        assert owned(hass, second_entry) == initial_second

        # Other observed families must also remain isolated between real entries.
        snapshot.append(deepcopy(seed))
        await FreeboxRouter.update_home_devices(router)
        await hass.async_block_till_done()
        assert owned(hass, second_entry) == initial_second
        from custom_components.freebox_homexa.repairs import async_home_permission_denied, home_permission_issue_id, async_source_permission_result, permission_issue_id
        from freebox_api.exceptions import InsufficientPermissionsError
        from homeassistant.helpers import issue_registry as ir
        async_home_permission_denied(hass, entry.entry_id)
        async_home_permission_denied(hass, second_entry.entry_id)
        async_source_permission_result(hass, entry.entry_id, 'disks', InsufficientPermissionsError('synthetic'))
        async_source_permission_result(hass, second_entry.entry_id, 'disks', InsufficientPermissionsError('synthetic'))
        issues = ir.async_get(hass)
        issues.async_ignore(DOMAIN, home_permission_issue_id(second_entry.entry_id), True)
        ignored = issues.async_get_issue(DOMAIN, home_permission_issue_id(second_entry.entry_id))
        assert await hass.config_entries.async_unload(second_entry.entry_id)
        await hass.async_block_till_done()
        assert not hass.data.get('dispatcher', {}).get(second.signal_players_update)
        assert hass.data.get('dispatcher', {}).get(router.signal_players_update)
        assert issues.async_get_issue(DOMAIN, home_permission_issue_id(second_entry.entry_id)) == ignored
        await hass.config_entries.async_remove(second_entry.entry_id)
        assert issues.async_get_issue(DOMAIN, home_permission_issue_id(second_entry.entry_id)) is None
        assert issues.async_get_issue(DOMAIN, permission_issue_id(second_entry.entry_id, "disks")) is None
        assert issues.async_get_issue(DOMAIN, permission_issue_id(entry.entry_id, "disks")) is not None
        assert issues.async_get_issue(DOMAIN, home_permission_issue_id(entry.entry_id)) is not None
        await second.async_update_players()
        assert api.player.get_players.await_count == 2
        api.player._access.post.assert_not_called()


async def test_late_lan_wifi_repeater_native_observers_and_closing(hass, forwarded_empty):
    from freebox_api.api.lan import Lan
    router, entry, _, _, _ = forwarded_empty
    transport = Mock(get=AsyncMock(), post=AsyncMock(), put=AsyncMock())
    hosts = [{'l2ident': {'id': '00:00:00:00:99:01'}, 'primary_name': 'Late WiFi client',
              'active': True, 'host_type': 'smartphone', 'connectivity_type': 'wifi',
              'access_point': {'mac': '00:00:00:00:99:09', 'type': 'repeater'},
              'wifi_information': {'signal': -55}}]
    transport.get.side_effect = lambda path: deepcopy(hosts) if path == 'lan/browser/pub' else []
    router._api.lan = Lan(transport)
    router._api.wifi._access.get.return_value = [{'main_mac': '00:00:00:00:99:09', 'name': 'Late repeater', 'status': 'active'}]
    before = owned(hass, entry)
    with patch.object(router, '_enrich_wifi_stations', new=AsyncMock()), patch.object(router, '_fetch_wifi_global_state', new=AsyncMock()):
        await router.update_device_trackers()
        await hass.async_block_till_done()
        after = owned(hass, entry)
        added = {eid: row for eid, row in after.items() if eid not in before}
        assert {'device_tracker', 'sensor', 'binary_sensor'} <= {row.domain for row in added.values()}
        assert any('repeater' in row.unique_id for row in added.values())
        registry = er.async_get(hass)
        for row in added.values():
            registry.async_update_entity(row.entity_id, name='My observed device', icon='mdi:star')
        expected = {eid: registry.async_get(eid) for eid in added}
        hosts.clear()
        for _ in range(3):
            await router.update_device_trackers()
            await hass.async_block_till_done()
        assert set(owned(hass, entry)) == set(after)
        assert all(registry.async_get(eid) == row for eid, row in expected.items())
        router.closing = True
        router.devices['00:00:00:00:99:02'] = {'l2ident': {'id': '00:00:00:00:99:02'}, 'primary_name': 'Too late', 'active': True, 'connectivity_type': 'wifi'}
        router.wifi_aps['late-after-close'] = {'kind': 'gateway', 'name': 'Too late', 'online': True}
        async_dispatcher_send(hass, router.signal_device_new)
        async_dispatcher_send(hass, router.signal_device_update)
        await hass.async_block_till_done()
        assert set(owned(hass, entry)) == set(after)
    assert transport.get.await_args_list[0].args[0] == 'lan/browser/pub'
    assert router._api.wifi._access.get.await_args_list[0].args[0] == 'repeater/'
    transport.post.assert_not_called()
    transport.put.assert_not_called()


@pytest.mark.parametrize('bad_payload', [{}, [None], [{1: 'bad key'}]])
async def test_player_invalid_inventory_retains_cache_and_recovers(hass, forwarded_empty, bad_payload, caplog):
    router, entry, _, _, _ = forwarded_empty
    before = owned(hass, entry)
    router._api.player.get_players.return_value = bad_payload
    for _ in range(2):
        await router.async_update_players()
    assert router.players == []
    assert owned(hass, entry) == before
    assert caplog.text.count('Inventaire Player indisponible') == 1
    router._api.player.get_players.return_value = [{'id': 55, 'name': 'Recovered', 'api_available': True}]
    router._api.player.get_player_status.return_value = {'power_state': 'standby'}
    router._api.player._access.get.return_value = {'power_state': 'standby'}
    await router.async_update_players()
    await hass.async_block_till_done()
    assert len(owned(hass, entry)) > len(before)
    assert len(router.players) == 1
    assert caplog.text.count('Inventaire Player de nouveau disponible') == 1


@pytest.mark.parametrize('late_result', [False, True])
async def test_closing_drains_inventory_read_without_late_additions(hass, forwarded_empty, late_result):
    import asyncio
    router, entry, _, _, _ = forwarded_empty
    started, drained = asyncio.Event(), asyncio.Event()
    async def blocked_read():
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            if late_result:
                return [{'id': 77, 'name': 'Too late', 'api_available': True}]
            raise
        finally:
            drained.set()
    router._api.player.get_players.side_effect = blocked_read
    before = owned(hass, entry)
    task = entry.async_create_background_task(hass, router.async_update_players(), 'blocked Player discovery')
    await started.wait()
    await router.async_update_players()  # overlapping poll is skipped, not multiplied
    async def closed_after_read():
        assert drained.is_set()
        assert task.done()
    router._api.close.side_effect = closed_after_read
    await router.close()
    await hass.async_block_till_done()
    assert drained.is_set() and not router.read_tasks
    assert router.players == []
    assert owned(hass, entry) == before
    if not late_result:
        assert task.cancelled()


@pytest.mark.parametrize('forwarded_empty', ['remote_first', 'media_player_first'], indirect=True)
async def test_each_first_native_forward_produces_shared_metadata_once(hass, forwarded_empty):
    router, entry, _, _, _ = forwarded_empty
    # Public HA forwarding order, not a forged source/cache state: each platform
    # can be the first metadata producer; both paths must be deterministic.
    assert router.players_initialized and router.player_discovery_active
    router._api.player.get_players.assert_awaited_once()
    assert owned(hass, entry)
