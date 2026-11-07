"""Real HA platforms: registration, dispatcher subscriptions, state, removal."""
from datetime import timedelta
import logging
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_homexa.router import FreeboxRouter
from custom_components.freebox_homexa.sensor import FreeboxSensor, FreeboxCallSensor, FreeboxCallLogSensor, FreeboxDiskSensor
from custom_components.freebox_homexa.binary_sensor import FreeboxWifiApSensor, FreeboxRaidDegradedSensor
from custom_components.freebox_homexa.wifi_ap_sensors import (
    FreeboxRepeaterCountSensor, FreeboxWifiClientCountSensor,
    FreeboxWifiClientListSensor, FreeboxWifiTotalClientSensor,
)


@pytest.fixture
def router(hass):
    entry = MockConfigEntry(domain='freebox_homexa', data={'host': 'freebox.test'})
    entry.add_to_hass(hass)
    result = FreeboxRouter(hass, entry, AsyncMock(), {
        'mac': '00:00:00:00:00:01', 'model_info': {'pretty_name': 'Test', 'name': 'test'},
        'firmware_version': '4.9.0',
    })
    result.wifi_aps = {'gateway': {'kind': 'gateway', 'name': 'Test', 'state': 'active',
                                  'online': True, 'client_count': 0}}
    result.raids = {1: {'id': 1, 'name': 'Test raid', 'degraded': False}}
    result.disks = {1: {'id': 1, 'model': 'Test disk', 'partitions': {1: {'id': 1, 'label': 'Test', 'total_bytes': 100, 'free_bytes': 50}}}}
    return result


def make_entity(kind, router):
    if kind == 'sensor':
        return FreeboxSensor(router, SensorEntityDescription(key='uptime', name='Test uptime'))
    if kind == 'call':
        return FreeboxCallSensor(router, SensorEntityDescription(key='missed', name='Test missed'))
    if kind == 'call_log':
        return FreeboxCallLogSensor(router, SensorEntityDescription(key='call_log', name='Test calls'))
    if kind == 'disk':
        disk = router.disks[1]
        return FreeboxDiskSensor(router, disk, disk['partitions'][1], SensorEntityDescription(key='free', name='Free'))
    if kind == 'ap':
        return FreeboxWifiApSensor(router, 'gateway', router.wifi_aps['gateway'])
    if kind == 'raid':
        return FreeboxRaidDegradedSensor(router, router.raids[1], BinarySensorEntityDescription(key='raid_degraded'))
    if kind == 'wifi_signal':
        from custom_components.freebox_homexa.sensor import FreeboxWifiSignalSensor
        device = {'l2ident': {'id': '00:00:00:00:10:01'}, 'primary_name': 'Test client',
                  'wifi': {'wifi_signal_dbm': -40}, 'host_type': 'computer'}
        router.devices[device['l2ident']['id']] = device
        return FreeboxWifiSignalSensor(router, device, False)
    if kind == 'lan_group':
        from custom_components.freebox_homexa.lan_group_sensors import FreeboxLanGroupClientsSensor
        return FreeboxLanGroupClientsSensor(router, 'lan_wired', {'lan_wired'})
    return {
        'repeaters': lambda: FreeboxRepeaterCountSensor(router),
        'client_count': lambda: FreeboxWifiClientCountSensor(router, 'gateway'),
        'client_list': lambda: FreeboxWifiClientListSensor(router, 'gateway'),
        'total': lambda: FreeboxWifiTotalClientSensor(router),
    }[kind]()


@pytest.mark.parametrize('kind', ['sensor', 'call', 'call_log', 'disk', 'ap', 'raid', 'repeaters', 'client_count', 'client_list', 'total', 'wifi_signal', 'lan_group'])
async def test_real_platform_dispatch_and_removal(hass, router, kind):
    domain = 'binary_sensor' if kind in {'ap', 'raid'} else 'sensor'
    entity = make_entity(kind, router)
    unique_id = entity.unique_id
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
                              platform_name='freebox_homexa', platform=None,
                              scan_interval=timedelta(seconds=30), entity_namespace=None)
    try:
        await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        assert entity.entity_id
        assert hass.states.get(entity.entity_id) is not None
        assert entity.unique_id == unique_id
        signals = (router.signal_device_update, router.signal_sensor_update)
        assert any(hass.data.get('dispatcher', {}).get(signal) for signal in signals)
        router.reachable = False
        async_dispatcher_send(hass, router.signal_device_update)
        async_dispatcher_send(hass, router.signal_sensor_update)
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == 'unavailable'
        router.reachable = True
        async_dispatcher_send(hass, router.signal_device_update)
        async_dispatcher_send(hass, router.signal_sensor_update)
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state != 'unavailable'
        await platform.async_reset()
        assert not platform.entities
        assert all(not hass.data.get('dispatcher', {}).get(signal) for signal in signals)
        removed_state = hass.states.get(entity.entity_id)
        # HA may leave an unavailable/restored registry placeholder. A lingering callback would recreate state or log an invalid entity write.
        async_dispatcher_send(hass, router.signal_device_update)
        async_dispatcher_send(hass, router.signal_sensor_update)
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id) is removed_state
    finally:
        await platform.async_reset()


async def test_raid_disappears_and_recovers(router):
    entity = make_entity('raid', router)
    unique_id = entity.unique_id
    entity.async_update_state()
    assert entity.is_on is False
    router.raids.clear()
    entity.async_update_state()
    assert entity.is_on is None
    entity.async_update_state()
    assert entity.is_on is None
    router.raids[1] = {'id': 1, 'name': 'Renamed', 'degraded': True}
    entity.async_update_state()
    assert entity.is_on is True
    assert entity.unique_id == unique_id


async def test_two_entries_platform_unload_isolated(hass, router):
    entry2 = MockConfigEntry(domain='freebox_homexa', data={'host': 'second.test'})
    entry2.add_to_hass(hass)
    second = FreeboxRouter(hass, entry2, AsyncMock(), {
        'mac': '00:00:00:00:00:02', 'model_info': {'pretty_name': 'Second', 'name': 'test'},
        'firmware_version': '4.9.0',
    })
    platforms = [EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain='sensor',
                                platform_name='freebox_homexa', platform=None,
                                scan_interval=timedelta(seconds=30), entity_namespace=None) for _ in range(2)]
    entities = [make_entity('sensor', device) for device in (router, second)]
    try:
        for platform, entity in zip(platforms, entities):
            await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        assert entities[0].unique_id != entities[1].unique_id
        assert entities[0].entity_id != entities[1].entity_id
        await platforms[0].async_reset()
        assert hass.data['dispatcher'].get(second.signal_sensor_update)
        second.sensors_connection['uptime'] = 123
        async_dispatcher_send(hass, second.signal_sensor_update)
        await hass.async_block_till_done()
        assert hass.states.get(entities[1].entity_id).state == '123'
        assert not hass.data['dispatcher'].get(router.signal_sensor_update)
    finally:
        for platform in platforms:
            await platform.async_reset()


async def test_home_entity_subscribes_only_when_added_and_removes(hass, router):
    from custom_components.freebox_homexa.sensor import FreeboxBatterySensor
    node = {'id': 42, 'label': 'Test detector', 'category': 'pir', 'type': {},
            'show_endpoints': [{'name': 'battery', 'ep_type': 'signal', 'value': 80}]}
    router.home_devices[42] = node
    entity = FreeboxBatterySensor(hass, router, node)
    signal = router.signal_home_device_update
    assert not hass.data.get('dispatcher', {}).get(signal)
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain='sensor',
                              platform_name='freebox_homexa', platform=None,
                              scan_interval=timedelta(seconds=30), entity_namespace=None)
    try:
        await platform.async_add_entities([entity])
        assert hass.data['dispatcher'].get(signal)
        router.home_devices[42] = {**node, 'label': 'Updated test detector'}
        async_dispatcher_send(hass, signal)
        await hass.async_block_till_done()
        assert entity.name == 'Updated test detector'
        await platform.async_reset()
        assert not hass.data['dispatcher'].get(signal)
    finally:
        await platform.async_reset()


async def test_alarm_replaces_timer_and_cleans_on_platform_remove(hass, router):
    from unittest.mock import Mock, patch
    from custom_components.freebox_homexa.alarm_control_panel import FreeboxAlarm
    node = {'id': 7, 'label': 'Test alarm', 'category': 'alarm', 'type': {'endpoints': [
        {'id': index, 'name': name, 'ep_type': kind} for index, (name, kind) in enumerate([
            ('trigger', 'slot'), ('alarm1', 'slot'), ('alarm2', 'slot'), ('off', 'slot'), ('state', 'signal')])
    ]}, 'show_endpoints': [{'name': 'pin', 'ep_type': 'signal', 'value': 'SYNTHETIC_SECRET'}]}
    entity = FreeboxAlarm(hass, router, node)
    assert 'pin' not in entity.extra_state_attributes
    first, second = Mock(), Mock()
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain='alarm_control_panel',
                              platform_name='freebox_homexa', platform=None,
                              scan_interval=timedelta(seconds=30), entity_namespace=None)
    try:
        await platform.async_add_entities([entity])
        with patch('custom_components.freebox_homexa.alarm_control_panel.async_track_time_interval', side_effect=[first, second]):
            entity._start_arming_watcher()
            entity._start_arming_watcher()
        first.assert_called_once_with()
        second.assert_not_called()
        await platform.async_reset()
        second.assert_called_once_with()
        assert entity._unsub_watcher is None
        assert not hass.data['dispatcher'].get(router.signal_home_device_update)
    finally:
        await platform.async_reset()


async def test_tracker_subscription_and_registry_cleanup(hass, router):
    from custom_components.freebox_homexa.device_tracker import FreeboxDevice
    device = {'l2ident': {'id': '00:00:00:00:10:01'}, 'primary_name': 'Test client',
              'active': True, 'host_type': 'computer'}
    router.devices[device['l2ident']['id']] = device
    entity = FreeboxDevice(router, device, False)
    # ScannerEntity is opt-in. Simulate an already enabled registry entity, not a production change.
    from homeassistant.helpers import entity_registry as er
    er.async_get(hass).async_get_or_create('device_tracker', 'freebox_homexa', entity.unique_id,
                                         disabled_by=None)
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain='device_tracker',
                              platform_name='freebox_homexa', platform=None,
                              scan_interval=timedelta(seconds=30), entity_namespace=None)
    try:
        await platform.async_add_entities([entity])
        assert entity.registry_entry.disabled_by is None
        assert hass.data.get('dispatcher', {}).get(router.signal_device_update)
        assert entity.is_connected
        device['active'] = False
        async_dispatcher_send(hass, router.signal_device_update)
        await hass.async_block_till_done()
        assert not entity.is_connected
        await platform.async_reset()
        assert not hass.data['dispatcher'].get(router.signal_device_update)
        assert entity._norm_mac not in router.tracked_lan_macs
    finally:
        await platform.async_reset()


async def test_tnt_coordinator_listener_removed_with_platform(hass):
    from custom_components.freebox_homexa.tnt_coordinator import ProgrammeTntFrCoordinator
    from custom_components.freebox_homexa.tnt_sensor import HomexaTntSensor
    entry = MockConfigEntry(domain='freebox_homexa', data={'host': 'guide.test'})
    entry.add_to_hass(hass)
    coordinator = ProgrammeTntFrCoordinator(hass, ['TF1.fr'], config_entry=entry)
    assert coordinator.config_entry is entry
    coordinator.async_set_updated_data({'TF1.fr': {'current': {'title': 'Programme test'}}})
    entity = HomexaTntSensor(coordinator, 'TF1.fr', 'test-prefix')
    assert not coordinator._listeners
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain='sensor',
                              platform_name='freebox_homexa', platform=None,
                              scan_interval=timedelta(seconds=30), entity_namespace=None)
    try:
        await platform.async_add_entities([entity])
        assert coordinator._listeners
        assert hass.states.get(entity.entity_id).state == 'Programme test'
        await platform.async_reset()
        assert not coordinator._listeners
    finally:
        await platform.async_reset()
