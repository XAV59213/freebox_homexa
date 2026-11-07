"""Actual SDK public read methods + real HA states, synthetic transports only."""
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import ClientPayloadError
from freebox_api.api.storage import Storage
from freebox_api.api.home import Home
from freebox_api.exceptions import HttpRequestError, NotOpenError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.freebox_homexa.sensor import FreeboxSensor, CONNECTION_SENSORS
from custom_components.freebox_homexa.cover import FreeboxBasicShutter
from custom_components.freebox_homexa.tnt_coordinator import ProgrammeTntFrCoordinator
from custom_components.freebox_homexa.tnt_sensor import HomexaTntSensor
from custom_components.freebox_homexa.tnt_const import XMLTV_URL
from test_entity_platforms import router, make_entity
from test_home_platforms import home_context, make_platform


@pytest.mark.parametrize('kind,path,method,flag', [
    ('disk', 'storage/disk/', '_update_disks_sensors', 'disks_available'),
    ('raid', 'storage/raid/', '_update_raids_sensors', 'raids_available'),
])
@pytest.mark.parametrize('failure', [HttpRequestError('SYNTHETIC private payload'), TimeoutError(),
                                      ClientPayloadError('SYNTHETIC private payload'), NotOpenError('synthetic closed'), None, [{}]])
async def test_storage_error_empty_and_recovery_real_sdk(hass, router, kind, path, method, flag, failure, caplog):
    transport = Mock(get=AsyncMock(), post=AsyncMock(), put=AsyncMock())
    router._api.storage = Storage(transport)
    initial = list(router.raids.values()) if kind == 'raid' else [
        {**router.disks[1], 'partitions': list(router.disks[1]['partitions'].values())}]
    entity = make_entity(kind, router)
    platform = make_platform(hass, 'binary_sensor' if kind == 'raid' else 'sensor')
    update = getattr(router, method)
    try:
        transport.get.return_value = initial
        await update()
        await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        uid, eid = entity.unique_id, entity.entity_id
        assert entity.available
        before = hass.states.get(eid).state
        if isinstance(failure, Exception):
            transport.get.side_effect = failure
        else:
            transport.get.return_value = failure
        for _ in range(2):
            await update()
            async_dispatcher_send(hass, router.signal_sensor_update)
            await hass.async_block_till_done()
            assert hass.states.get(eid).state == 'unavailable'
        assert getattr(router, flag) is False
        assert router.reachable and router.supports_raid
        assert 'SYNTHETIC private payload' not in caplog.text
        assert caplog.text.count('Source disques Freebox indisponible' if kind == 'disk'
                                 else 'Source RAID Freebox indisponible') == 1
        # A *valid* empty snapshot means removed, without deleting registry/history.
        transport.get.side_effect = None
        transport.get.return_value = []
        await update()
        assert getattr(router, flag) and not entity.available
        transport.get.return_value = initial
        await update()
        async_dispatcher_send(hass, router.signal_sensor_update)
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == before
        assert (entity.unique_id, entity.entity_id) == (uid, eid)
        assert {call.args[0] for call in transport.get.await_args_list} == {path}
        transport.post.assert_not_called()
        transport.put.assert_not_called()
    finally:
        await platform.async_reset()


@pytest.mark.parametrize('total,free,expected', [(1000, 250, 25), (1000, 0, 0), (None, 2, None),
    (0, 0, None), (-1, 0, None), (True, 1, None), ('1000', 1, None), (1000, None, None),
    (1000, -1, None), (1000, 1001, None), (1000, False, None), (1000, '1', None)])
async def test_disk_bytes_percentage_unknown_not_fake_zero(router, total, free, expected):
    # Public storage fields are bytes, not KiB, and zero capacity is not 0% free.
    entity = make_entity('disk', router)
    router.disks[1]['partitions'][1].update(total_bytes=total, free_bytes=free)
    entity.async_update_state()
    assert entity.native_value == expected
    assert entity.available


@pytest.mark.parametrize('uptime', [None, False, '12', -1, 0, 120])
async def test_connection_byte_rate_and_missing_uptime_contract(hass, home_context, uptime):
    router, _ = home_context
    router._api.system.get_config.return_value = {'sensors': [], 'serial': 'SYNTHETIC', 'uptime_val': uptime}
    router._api.connection.get_status.return_value = {'rate_down': 8000, 'rate_up': 0}
    router._api.call.get_calls_log.return_value = []
    router._api.storage.get_disks.return_value = []
    router._api.storage.get_raids.return_value = []
    await router.update_sensors()
    entity = FreeboxSensor(router, CONNECTION_SENSORS[0])
    entity.async_update_state()
    assert entity.native_value == 8  # 8000 BYTE/s => 8 decimal kB/s, not 1.
    assert entity.native_unit_of_measurement == 'kB/s'
    assert entity.unique_id == f'{router.mac} Vitesse de téléchargement Freebox'
    known = type(uptime) is int and uptime >= 0
    assert router.sensors_connection['uptime'] == (uptime if known else None)
    assert (router._attrs['uptime'] is not None) is known


@pytest.mark.parametrize('failure', [HttpRequestError('synthetic transient'), TimeoutError(),
                                    ClientPayloadError('synthetic payload'), None, [{}]])
async def test_home_snapshot_error_removal_and_recovery(hass, home_context, failure):
    router, node = home_context
    transport = Mock(get=AsyncMock(return_value=[node]), put=AsyncMock(), post=AsyncMock())
    router._api.home = Home(transport)
    platform = make_platform(hass, 'cover')
    entity = FreeboxBasicShutter(hass, router, node)
    try:
        await router.update_home_devices()
        await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        eid, uid = entity.entity_id, entity.unique_id
        assert entity.available
        if isinstance(failure, Exception):
            transport.get.side_effect = failure
        else:
            transport.get.return_value = failure
        await router.update_home_devices()
        await hass.async_block_till_done()
        assert router.home_granted  # no permanent permission downgrade for transient failure
        assert not router.home_available and not entity.available
        assert hass.states.get(eid).state == 'unavailable'
        assert node['id'] in router.home_devices  # cache retained, but not advertised as fresh
        transport.get.side_effect = None
        transport.get.return_value = []
        await router.update_home_devices()
        await hass.async_block_till_done()
        assert router.home_available and not entity.available
        transport.get.return_value = [node]
        await router.update_home_devices()
        await hass.async_block_till_done()
        assert entity.available and hass.states.get(eid).state != 'unavailable'
        assert (entity.entity_id, entity.unique_id) == (eid, uid)
        assert {call.args[0] for call in transport.get.await_args_list} == {'home/nodes'}
        transport.put.assert_not_called()
        transport.post.assert_not_called()
    finally:
        await platform.async_reset()


async def test_xmltv_cached_data_retained_but_failed_refresh_unavailable(hass, aioclient_mock):
    coordinator = ProgrammeTntFrCoordinator(hass, ['TF1.fr'])
    platform = make_platform(hass, 'sensor')
    entity = HomexaTntSensor(coordinator, 'TF1.fr', 'synthetic')
    xml = '<tv><channel id="TF1.fr"><display-name>Synthetic</display-name></channel></tv>'
    aioclient_mock.get(XMLTV_URL, text=xml)
    try:
        await coordinator.async_refresh()
        await platform.async_add_entities([entity])
        assert entity.available
        original = coordinator.data
        coordinator._last_fetch -= timedelta(days=1)
        aioclient_mock.clear_requests()
        aioclient_mock.get(XMLTV_URL, status=503)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert not coordinator.last_update_success and not entity.available
        assert coordinator.data is original
        assert hass.states.get(entity.entity_id).state == 'unavailable'
        aioclient_mock.clear_requests()
        aioclient_mock.get(XMLTV_URL, text=xml)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.last_update_success and entity.available
        assert hass.states.get(entity.entity_id).state != 'unavailable'
    finally:
        await platform.async_reset()
        await coordinator.async_shutdown()


@pytest.mark.parametrize("degraded,expected", [(True, True), (False, False), (None, None), ("false", None), (0, None)])
async def test_raid_unknown_does_not_invent_healthy_state(router, degraded, expected):
    entity = make_entity("raid", router)
    router.raids[1]["degraded"] = degraded
    entity.async_update_state()
    assert entity.available and entity.is_on is expected


async def test_explicit_home_permission_gate_is_retained(hass, home_context):
    from freebox_api.exceptions import InsufficientPermissionsError
    router, node = home_context
    transport = Mock(get=AsyncMock(side_effect=InsufficientPermissionsError("synthetic")))
    router._api.home = Home(transport)
    await router.update_home_devices()
    assert not router.home_available and not router.home_granted
    await router.update_home_devices()
    transport.get.assert_awaited_once_with("home/nodes")
    assert router.home_devices[node["id"]] == node


async def test_home_source_guard_covers_all_home_families(hass, home_context):
    from custom_components.freebox_homexa.entity import FreeboxHomeEntity
    from test_entity_inventory import build_inventory
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    objects, coordinator = build_inventory(hass, router, node, entry)
    try:
        entities = [entity for variant, entity in objects
                    if isinstance(entity, FreeboxHomeEntity) and variant != "inversion"]
        local_inversion = next(entity for variant, entity in objects if variant == "inversion")
        assert len(entities) == 10
        for entity in entities:
            entity.hass = hass
            assert entity.available
        router.home_available = False
        assert all(not entity.available for entity in entities)
        assert local_inversion.available  # local preference does not depend on API Home
        router.home_available = True
        assert all(entity.available for entity in entities)
        router.home_snapshot_known = True
        router.home_devices = {}
        assert all(not entity.available for entity in entities)
        router.home_devices[node["id"]] = node
        assert all(entity.available for entity in entities)
    finally:
        await coordinator.async_shutdown()


async def test_unexpected_sdk_close_is_not_a_successful_periodic_poll(hass, home_context):
    from homeassistant.util import dt as dt_util
    router, _ = home_context
    with patch.object(router, "update_device_trackers", AsyncMock(side_effect=NotOpenError("synthetic closed"))):
        await router.update_all(dt_util.now())
        assert not router.reachable
        with pytest.raises(NotOpenError):
            await router.update_all()
    with patch.object(router, "update_device_trackers", AsyncMock()), patch.object(router, "update_sensors", AsyncMock()):
        await router.update_all(dt_util.now())
        assert router.reachable
