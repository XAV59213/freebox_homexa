"""Every remaining availability source: true HA + SDK, mocked transport only."""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from freebox_api.access import Access
from freebox_api.api.connection import Connection
from freebox_api.api.home import Home
from freebox_api.api.player import Player
from freebox_api.api.wifi import Wifi
from freebox_api.exceptions import HttpRequestError, AuthorizationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.freebox_homexa.entity import FreeboxHomeEntity
from custom_components.freebox_homexa.media_player import FreeboxPlayerMediaPlayer
from custom_components.freebox_homexa.remote import FreeboxRemote
from custom_components.freebox_homexa.button import FreeboxPlayerAppButton, FreeboxPlayerRemoteButton
from custom_components.freebox_homexa.sensor import FreeboxSensor, CONNECTION_SENSORS
from test_home_platforms import home_context, make_platform
from test_entity_platforms import make_entity, router
from test_player_platforms import player_context


async def test_sdk_access_connection_router_rate_preserves_native_bytes(hass, home_context, aioclient_mock):
    """Actual Access HTTP JSON unwrapping and actual Connection do NOT scale rate_*.

    API ConnectionStatus rate_* = byte/s, bandwidth_* = bit/s:
    https://dev.freebox.fr/sdk/os/connection/ (indexed official field definitions).
    This is not a fixture that assumes an SDK already converted to bits or kB.
    """
    router, _ = home_context
    access = Access(async_get_clientsession(hass), 'http://freebox.test/api/v4/', 'SYNTHETIC', 'test', 10)
    access.session_token = 'SYNTHETIC'
    connection = Connection(access)
    raw = {'rate_down': 8000, 'rate_up': 125000, 'bandwidth_down': 8000000, 'bandwidth_up': 1000000}
    aioclient_mock.get('http://freebox.test/api/v4/connection/', json={'success': True, 'result': raw}, headers={'content-type': 'application/json'})
    assert await connection.get_status() == raw
    router._api.connection = connection
    router._api.system.get_config.return_value = {'sensors': [], 'uptime_val': 120, 'serial': 'SYNTHETIC'}
    router._api.call.get_calls_log.return_value = []
    router._api.storage.get_disks.return_value = []
    router._api.storage.get_raids.return_value = []
    await router.update_sensors()
    assert router.sensors_connection['rate_down'] == raw['rate_down']
    assert router.sensors_connection['rate_up'] == raw['rate_up']
    for description, expected in zip(CONNECTION_SENSORS[:2], (8, 125), strict=True):
        entity = FreeboxSensor(router, description)
        entity.async_update_state()
        assert entity.native_unit_of_measurement == 'kB/s'
        assert entity.native_value == expected
        assert entity.unique_id == f'{router.mac} {description.name}'
    assert aioclient_mock.call_count == 2


@pytest.mark.parametrize('failure', [TimeoutError(), HttpRequestError('SYNTHETIC private payload'),
                                    AuthorizationError('SYNTHETIC'), RuntimeError('SYNTHETIC'), None, {}])
async def test_home_endpoint_failure_is_unavailable_explicit_none_unknown(hass, home_context, failure):
    router, node = home_context
    transport = Mock(get=AsyncMock(return_value={'value': False}), put=AsyncMock(), post=AsyncMock())
    router._api.home = Home(transport)
    entity = FreeboxHomeEntity(hass, router, node)
    assert await entity.get_home_endpoint_value(1) is False
    assert entity.available
    if isinstance(failure, Exception):
        transport.get.side_effect = failure
    else:
        transport.get.return_value = failure
    assert await entity.get_home_endpoint_value(1) is None
    assert not entity.available
    transport.get.side_effect = None
    transport.get.return_value = {'value': None}
    assert await entity.get_home_endpoint_value(2) is None
    assert not entity.available  # successful other endpoint must not hide endpoint 1's failure
    assert await entity.get_home_endpoint_value(1) is None
    assert entity.available  # success with an explicitly unknown value
    assert await entity.get_home_endpoint_value(None) is None
    assert entity.available
    transport.put.assert_not_called()
    transport.post.assert_not_called()


@pytest.mark.parametrize('failure', [TimeoutError(), HttpRequestError('synthetic'), None, []])
async def test_real_remote_sdk_read_errors_recover_without_fake_off(player_context, failure):
    router, entry, player = player_context
    transport = Mock(get=AsyncMock(return_value={'power_state': 'standby'}), put=AsyncMock(), post=AsyncMock())
    router._api.player = Player(transport)
    entity = FreeboxRemote(router, player, entry)
    await entity.async_update()
    assert entity.available and entity.is_on is False  # standby remains controllable, not unavailable
    if isinstance(failure, Exception):
        transport.get.side_effect = failure
    else:
        transport.get.return_value = failure
    await entity.async_update()
    assert not entity.available and entity.is_on is None
    transport.get.side_effect = None
    transport.get.return_value = {}
    await entity.async_update()
    assert entity.available and entity.is_on is None
    transport.get.return_value = {'power_state': 'running'}
    await entity.async_update()
    assert entity.available and entity.is_on is True
    transport.put.assert_not_called()
    transport.post.assert_not_called()


@pytest.mark.parametrize('kind', ['app', 'remote'])
async def test_player_buttons_follow_existing_media_status_no_extra_reads(hass, player_context, kind):
    router, entry, player = player_context
    button = (FreeboxPlayerAppButton(router, player, 'youtube', 'YouTube', 'mdi:youtube', 'https://example.invalid', True)
              if kind == 'app' else FreeboxPlayerRemoteButton(router, player, entry, 'power', 'Power', 'mdi:power', True))
    media = FreeboxPlayerMediaPlayer(router, player, entry)
    # Real SDK Access GET contract, the same status endpoint MediaPlayer already polls.
    transport = Mock(get=AsyncMock(return_value={'power_state': 'standby', 'volume': 20}), post=AsyncMock(), put=AsyncMock())
    router._api.player = Player(transport)
    platform = make_platform(hass, 'button')
    try:
        await platform.async_add_entities([button])
        await hass.async_block_till_done()
        assert button.available
        before_id = button.entity_id
        transport.get.side_effect = TimeoutError('synthetic')
        await media.async_update()
        await hass.async_block_till_done()
        assert not media.available and not button.available
        assert hass.states.get(before_id).state == 'unavailable'
        count = transport.get.await_count
        button.async_write_ha_state()
        assert transport.get.await_count == count  # no per-button poll
        transport.get.side_effect = None
        transport.get.return_value = {'power_state': 'standby', 'volume': 0}
        await media.async_update()
        await hass.async_block_till_done()
        assert button.available and media.available
        assert str(media.state) == 'off'
        assert button.entity_id == before_id
        transport.get.return_value = {}
        await media.async_update()
        assert media.available and media.state is None  # missing fields, not fake idle
        transport.post.assert_not_called()
        transport.put.assert_not_called()
    finally:
        await platform.async_reset()


async def test_remote_unsupported_v6_does_not_override_working_media_version(hass, player_context):
    router, entry, player = player_context
    def response(path):
        if '/v8/status/' in path:
            return {'power_state': 'running', 'volume': 0}
        raise HttpRequestError('synthetic unsupported version')
    transport = Mock(get=AsyncMock(side_effect=response))
    router._api.player = Player(transport)
    media = FreeboxPlayerMediaPlayer(router, {**player, 'api_version': 'v8'}, entry)
    remote = FreeboxRemote(router, player, entry)
    button = FreeboxPlayerAppButton(router, player, 'youtube', 'YouTube', 'mdi:youtube', 'https://example.invalid', True)
    await media.async_update()
    await remote.async_update()
    assert media.available and button.available and not remote.available


@pytest.mark.parametrize('failure', [TimeoutError(), HttpRequestError('SYNTHETIC secret'), None, {}])
async def test_wifi_all_sources_fail_unavailable_disabled_wifi_recovers(hass, router, failure, caplog):
    gateway = make_entity('ap', router)
    platform = make_platform(hass, 'binary_sensor')
    access = Mock(get=AsyncMock(), post=AsyncMock(), put=AsyncMock())
    router._api.wifi = Wifi(access)
    try:
        await platform.async_add_entities([gateway])
        if isinstance(failure, Exception):
            access.get.side_effect = failure
        else:
            access.get.return_value = failure
        await router._enrich_wifi_stations()
        await router._fetch_wifi_global_state()
        router._refresh_repeaters()
        async_dispatcher_send(hass, router.signal_device_update)
        await hass.async_block_till_done()
        if failure == {}:
            assert gateway.available  # valid config, only its enabled field is missing
            assert hass.states.get(gateway.entity_id).state == 'unknown'
        else:
            assert not gateway.available
            assert hass.states.get(gateway.entity_id).state == 'unavailable'
        assert 'SYNTHETIC secret' not in caplog.text
        assert all('SYNTHETIC' not in value for value in router.wifi_api_errors.values())
        access.get.side_effect = lambda path: {'enabled': False} if path == 'wifi/config/' else []
        await router._enrich_wifi_stations()
        await router._fetch_wifi_global_state()
        router._refresh_repeaters()
        async_dispatcher_send(hass, router.signal_device_update)
        await hass.async_block_till_done()
        assert gateway.available
        assert hass.states.get(gateway.entity_id).state == 'off'  # wifi disabled isn't API failure
        access.put.assert_not_called()
        access.post.assert_not_called()
    finally:
        await platform.async_reset()


async def test_optional_station_failure_drops_stale_value_preserves_live_lan_fallback(hass, router):
    client = {'l2ident': {'id': '00:00:00:00:10:01'}, 'primary_name': 'Synthetic', 'active': True,
              '_wifi_station': {'signal': -30}, 'access_point': {'wifi_information': {}}}
    router.devices[client['l2ident']['id']] = client
    entity = make_entity('wifi_signal', router)
    # make_entity creates a current signal record; replace it with a truly station-only one.
    router.devices[client['l2ident']['id']] = client
    def get(path):
        if path == 'wifi/ap/':
            return [{'id': 0, 'status': {'state': 'active'}}]
        raise HttpRequestError('synthetic stations failure')
    access = Mock(get=AsyncMock(side_effect=get), put=AsyncMock(), post=AsyncMock())
    router._api.wifi = Wifi(access)
    await router._enrich_wifi_stations()
    entity.async_update_state()
    assert '_wifi_station' not in client
    assert entity.native_value is None and not entity.available
    # LAN wifi_information is an independent fresh source; no global failure for this valid fallback.
    client['access_point']['wifi_information']['signal'] = -42
    await router._enrich_wifi_stations()
    entity.async_update_state()
    assert entity.available and entity.native_value == -42
    access.get.side_effect = lambda path: [{'id': 0}] if path == 'wifi/ap/' else []
    client['access_point']['wifi_information'] = {}
    await router._enrich_wifi_stations()
    entity.async_update_state()
    assert entity.available and entity.native_value is None  # successful source with missing value
    client['active'] = False
    entity.async_update_state()
    assert not entity.available and entity.native_value is None
    access.put.assert_not_called()
    access.post.assert_not_called()


@pytest.mark.parametrize('kind', ['client_count', 'client_list', 'total', 'lan_group', 'repeaters', 'wifi_signal'])
async def test_lan_source_guard_and_recovery_for_all_lan_derived_families(hass, router, kind):
    entity = make_entity(kind, router)
    platform = make_platform(hass, 'sensor')
    if kind == 'wifi_signal':
        from homeassistant.helpers import entity_registry as er
        er.async_get(hass).async_get_or_create('sensor', 'freebox_homexa', entity.unique_id,
                                             suggested_object_id='existing_signal', disabled_by=None)
    try:
        await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        assert entity.available
        eid, uid = entity.entity_id, entity.unique_id
        router.lan_available = False
        async_dispatcher_send(hass, router.signal_device_update)
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == 'unavailable'
        router.lan_available = True
        async_dispatcher_send(hass, router.signal_device_update)
        await hass.async_block_till_done()
        assert entity.available and (entity.entity_id, entity.unique_id) == (eid, uid)
    finally:
        await platform.async_reset()


async def test_real_lan_bridge_code_retries_and_removed_client_not_left_present(hass, router):
    from freebox_api.api.lan import Lan
    from custom_components.freebox_homexa.device_tracker import FreeboxDevice
    client = {'l2ident': {'id': '00:00:00:00:10:01'}, 'primary_name': 'Synthetic', 'active': True}
    access = Mock(get=AsyncMock(return_value=[client]))
    router._api.lan = Lan(access)
    # This test isolates the real essential LAN SDK path from optional enrichment.
    with patch.object(router, '_enrich_wifi_stations', AsyncMock()), \
         patch.object(router, '_fetch_wifi_global_state', AsyncMock()), \
         patch.object(router, '_fetch_api_repeaters', AsyncMock()):
        await router.update_device_trackers()
        tracker = FreeboxDevice(router, client, False)
        server = FreeboxDevice(router, router.devices[router.mac], False)
        tracker.async_update_state()
        assert tracker.available and tracker.is_connected
        access.get.side_effect = HttpRequestError('Request failed (APIResponse: {"success":false,"error_code":"nodev"})')
        await router.update_device_trackers()
        assert not router.lan_available and not tracker.available
        assert server.available  # gateway presence is synthesized from the responding Server
        access.get.side_effect = None
        access.get.return_value = []
        await router.update_device_trackers()
        tracker.async_update_state()
        assert router.lan_available and tracker.available and not tracker.is_connected
        access.get.return_value = [dict(client, active=True)]
        await router.update_device_trackers()
        tracker.async_update_state()
        assert tracker.is_connected
        assert {call.args[0] for call in access.get.await_args_list} == {'lan/browser/pub'}


@pytest.mark.parametrize('kind', ['client_count', 'client_list', 'ap'])
async def test_missing_ap_is_unavailable_not_false_zero_or_disconnected(router, kind):
    entity = make_entity(kind, router)
    assert entity.available
    before = dict(router.wifi_aps)
    router.wifi_aps.clear()
    entity.async_update_state()
    assert not entity.available
    router.wifi_aps.update(before)
    entity.async_update_state()
    assert entity.available


async def test_alarm_platform_endpoint_failure_and_explicit_unknown(hass, home_context):
    from custom_components.freebox_homexa.alarm_control_panel import FreeboxAlarm
    router, node = home_context
    access = Mock(get=AsyncMock(return_value={'value': 'idle'}), put=AsyncMock(), post=AsyncMock())
    router._api.home = Home(access)
    alarm = FreeboxAlarm(hass, router, {**node, 'category': 'alarm'})
    platform = make_platform(hass, 'alarm_control_panel')
    platform.config_entry = hass.config_entries.async_get_entry(router.entry_id)
    try:
        await platform.async_add_entities([alarm], update_before_add=True)
        await hass.async_block_till_done()
        assert alarm.available
        eid = alarm.entity_id
        access.get.side_effect = TimeoutError('synthetic')
        await alarm.async_update()
        alarm.async_write_ha_state()
        assert hass.states.get(eid).state == 'unavailable'
        access.get.side_effect = None
        access.get.return_value = {'value': None}
        await alarm.async_update()
        alarm.async_write_ha_state()
        assert alarm.available and hass.states.get(eid).state == 'unknown'
        access.get.return_value = {'value': 'idle'}
        await alarm.async_update()
        alarm.async_write_ha_state()
        assert hass.states.get(eid).state == 'disarmed'
        access.put.assert_not_called()
        access.post.assert_not_called()
    finally:
        await platform.async_reset()


async def test_temperature_disappearing_value_does_not_leave_old_cache(hass, home_context):
    from freebox_api.api.system import System
    from custom_components.freebox_homexa.sensor import temperature_sensor_description
    router, _ = home_context
    configuration = {'serial': 'SYNTHETIC', 'sensors': [{'name': 'temp_cpu', 'value': 32}]}
    access = Mock(get=AsyncMock(return_value=configuration))
    router._api.system = System(access)
    router._api.connection.get_status.return_value = {}
    router._api.call.get_calls_log.return_value = []
    router._api.storage.get_disks.return_value = []
    router._api.storage.get_raids.return_value = []
    entity = FreeboxSensor(router, temperature_sensor_description('temp_cpu'))
    await router.update_sensors()
    entity.async_update_state()
    assert entity.available and entity.native_value == 32
    configuration['sensors'] = []
    await router.update_sensors()
    entity.async_update_state()
    assert entity.available and entity.native_value is None
    access.get.side_effect = AuthorizationError('synthetic')
    await router.update_sensors()
    assert not entity.available and router.reachable
    access.get.side_effect = None
    await router.update_sensors()
    assert entity.available


def test_shared_requirement_preserves_hassfest_minimum_and_tested_version():
    import json
    from pathlib import Path
    from importlib.metadata import version
    manifest = json.loads((Path(__file__).parents[2] / 'custom_components/freebox_homexa/manifest.json').read_text())
    assert manifest['requirements'] == ['freebox-api>=1.3.1']
    assert version('freebox-api') == '1.3.1'


@pytest.mark.parametrize('signal', [True, float('nan'), float('inf'), {}, 'invalid'])
def test_invalid_rssi_is_not_fabricated_from_boolean_or_nonfinite(signal):
    from custom_components.freebox_homexa.router import extract_wifi_details
    data = extract_wifi_details({'access_point': {'wifi_information': {'signal': signal}}})
    assert 'wifi_signal_dbm' not in data


@pytest.mark.parametrize('kind', ['remote', 'media'])
async def test_confirmed_standby_with_existing_wake_channel_not_unavailable(hass, player_context, kind):
    from custom_components.freebox_homexa.const import CONF_REMOTE_CODES
    router, entry, player = player_context
    hass.config_entries.async_update_entry(entry, options={CONF_REMOTE_CODES: {'1': 'SYNTHETIC'}})
    access = Mock(get=AsyncMock(side_effect=TimeoutError('synthetic')), put=AsyncMock(), post=AsyncMock())
    router._api.player = Player(access)
    entity = (FreeboxRemote(router, player, entry) if kind == 'remote'
              else FreeboxPlayerMediaPlayer(router, player, entry))
    await entity.async_update()
    assert not entity.available  # code alone does not invent an initial power state
    access.get.side_effect = None
    access.get.return_value = {'power_state': 'standby', 'reachable': False, 'volume': 0}
    await entity.async_update()
    assert entity.available
    assert (entity.is_on is False if kind == 'remote' else str(entity.state) == 'off')
    access.get.side_effect = TimeoutError('synthetic')
    await entity.async_update()
    assert entity.available  # existing alternate channel can wake a confirmed standby
    assert (entity.is_on is False if kind == 'remote' else str(entity.state) == 'off')
    hass.config_entries.async_update_entry(entry, options={})
    await entity.async_update()
    assert not entity.available
    access.put.assert_not_called()
    access.post.assert_not_called()
    router._api.remote.send_key.assert_not_called()
