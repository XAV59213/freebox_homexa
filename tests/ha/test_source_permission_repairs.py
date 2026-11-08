"""Rights failures of real SDK read methods, using HA's native issue registry."""
from copy import deepcopy
from unittest.mock import AsyncMock, Mock
import pytest
from freebox_api.api.wifi import Wifi
from freebox_api.api.storage import Storage
from freebox_api.api.system import System
from freebox_api.api.connection import Connection
from freebox_api.api.call import Call
from freebox_api.api.lan import Lan
from freebox_api.api.player import Player
from freebox_api.exceptions import HttpRequestError, InsufficientPermissionsError
from homeassistant.helpers import issue_registry as ir
from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.repairs import permission_issue_id, PERMISSION_SOURCES
from test_home_platforms import home_context

CASES = [
    ('wifi_config', 'wifi/config/', '_fetch_wifi_global_state'),
    ('wifi_bss', 'wifi/bss/', '_fetch_wifi_global_state'),
    ('wifi_ap', 'wifi/ap/', '_enrich_wifi_stations'),
    ('wifi_stations', 'wifi/ap/7/stations/', '_enrich_wifi_stations'),
    ('repeaters', 'repeater/', '_fetch_api_repeaters'),
    ('disks', 'storage/disk/', '_update_disks_sensors'),
    ('raids', 'storage/raid/', '_update_raids_sensors'),
    ('system', 'system/', 'update_sensors'),
    ('connection', 'connection/', 'update_sensors'),
    ('calls', 'call/log/', 'update_sensors'),
    ('lan', 'lan/browser/pub', 'update_device_trackers'),
    ('players', 'player', 'async_update_players'),
]


def sdk_context(router, blocked_path):
    mode = {'error': InsufficientPermissionsError('SYNTHETIC secret payload')}
    payloads = {'wifi/config/': {'enabled': True}, 'wifi/bss/': [], 'wifi/ap/': [{'id': 7}],
        'wifi/ap/7/stations/': [], 'repeater/': [], 'storage/disk/': [], 'storage/raid/': [],
        'system/': {'sensors': [], 'serial': 'Synthetic', 'uptime_val': 0},
        'connection/': {}, 'call/log/': [], 'lan/browser/pub': [], 'player': []}
    async def read(path):
        assert path in payloads
        if path == blocked_path and mode['error'] is not None:
            raise mode['error']
        return deepcopy(payloads[path])
    transport = Mock(get=AsyncMock(side_effect=read), post=AsyncMock(), put=AsyncMock(), delete=AsyncMock())
    for name, cls in [('wifi', Wifi), ('storage', Storage), ('system', System), ('connection', Connection),
                      ('call', Call), ('lan', Lan), ('player', Player)]:
        setattr(router._api, name, cls(transport))
    return mode, payloads, transport


@pytest.mark.parametrize('source,path,method', CASES)
async def test_sdk_explicit_denial_ignore_transient_then_scope_recovery(hass, home_context, source, path, method, caplog):
    router, _ = home_context
    mode, payloads, transport = sdk_context(router, path)
    registry = ir.async_get(hass)
    issue_id = permission_issue_id(router.entry_id, source)
    async def refresh():
        try:
            await getattr(router, method)()
        except InsufficientPermissionsError:
            assert source == 'lan'  # existing LAN source propagates to the root poll
    await refresh()
    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue and issue.translation_key == 'source_permissions'
    assert issue.translation_placeholders == {'source': source}
    assert issue.data is None
    registry.async_ignore(DOMAIN, issue_id, True)
    ignored_version = registry.async_get_issue(DOMAIN, issue_id).dismissed_version
    await refresh()
    assert registry.async_get_issue(DOMAIN, issue_id).dismissed_version == ignored_version
    mode['error'] = TimeoutError('SYNTHETIC secret payload')
    try:
        await getattr(router, method)()
    except TimeoutError:
        assert source == 'lan'
    assert registry.async_get_issue(DOMAIN, issue_id).dismissed_version == ignored_version
    assert 'SYNTHETIC secret payload' not in caplog.text
    mode['error'] = None
    valid = payloads[path]
    payloads[path] = None
    try:
        await getattr(router, method)()
    except ValueError:
        assert source == 'lan'
    assert registry.async_get_issue(DOMAIN, issue_id).dismissed_version == ignored_version
    payloads[path] = valid
    await refresh()
    assert registry.async_get_issue(DOMAIN, issue_id) is None
    assert path in {call.args[0] for call in transport.get.await_args_list}
    transport.post.assert_not_called()
    transport.put.assert_not_called()
    transport.delete.assert_not_called()


@pytest.mark.parametrize('error', [TimeoutError('access denied'),
    TimeoutError('{"error_code":"insufficient_rights"}'), HttpRequestError('access denied'),
    HttpRequestError('nodev'), ValueError('insufficient_rights')])
async def test_error_text_alone_never_creates_a_permission_issue(hass, home_context, error):
    router, _ = home_context
    mode, _, _ = sdk_context(router, 'player')
    mode['error'] = error
    await router.async_update_players()
    assert ir.async_get(hass).async_get_issue(DOMAIN, permission_issue_id(router.entry_id, 'players')) is None


async def test_station_issue_is_not_cleared_by_other_ap_success_or_empty_ap_list(hass, home_context):
    router, _ = home_context
    mode, payloads, _ = sdk_context(router, 'wifi/ap/7/stations/')
    await router._enrich_wifi_stations()
    issue_id = permission_issue_id(router.entry_id, 'wifi_stations')
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    payloads['wifi/ap/'] = []
    mode['error'] = None
    await router._enrich_wifi_stations()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    payloads['wifi/ap/'] = [{'id': 7}, {'id': 8}]
    payloads['wifi/ap/8/stations/'] = []
    mode['error'] = InsufficientPermissionsError('synthetic')
    await router._enrich_wifi_stations()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    mode['error'] = None
    await router._enrich_wifi_stations()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


def test_every_declared_source_has_a_real_sdk_case():
    assert {scope for scope, _, _ in CASES} == set(PERMISSION_SOURCES)


@pytest.mark.parametrize('language', ['fr', 'en'])
async def test_native_source_issue_translation_with_fixed_scope(hass, home_context, language):
    from homeassistant.helpers.translation import async_get_translations
    translations = await async_get_translations(hass, language, 'issues', {DOMAIN})
    prefix = f'component.{DOMAIN}.issues.source_permissions'
    assert translations[f'{prefix}.title']
    assert '{source}' in translations[f'{prefix}.description']
    assert 'Homexa' in translations[f'{prefix}.description']


async def test_cancel_resistant_home_read_cannot_clear_ignored_repair_on_close(hass, home_context):
    import asyncio
    from freebox_api.api.home import Home
    from custom_components.freebox_homexa.repairs import home_permission_issue_id
    router, node = home_context
    transport = Mock(get=AsyncMock(side_effect=InsufficientPermissionsError('synthetic')))
    router._api.home = Home(transport)
    await router.update_home_devices()
    registry = ir.async_get(hass)
    issue_id = home_permission_issue_id(router.entry_id)
    registry.async_ignore(DOMAIN, issue_id, True)
    ignored = registry.async_get_issue(DOMAIN, issue_id)
    router.home_granted = True
    started = asyncio.Event()
    async def read(path):
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            return [node]
    transport.get.side_effect = read
    task = hass.async_create_background_task(router.async_poll(router.update_home_devices), 'late Home permission retry')
    await started.wait()
    await router.close()
    assert task.done() and not router.poll_tasks
    assert registry.async_get_issue(DOMAIN, issue_id) == ignored


async def test_invalid_call_log_is_unavailable_not_a_false_zero_then_recovers(hass, home_context):
    from custom_components.freebox_homexa.sensor import FreeboxCallSensor, CALL_SENSORS
    from test_home_platforms import make_platform
    router, _ = home_context
    mode, payloads, _ = sdk_context(router, 'call/log/')
    mode['error'] = None
    payloads['call/log/'] = [{'type': 'missed', 'new': True}]
    await router.update_sensors()
    entity = FreeboxCallSensor(router, CALL_SENSORS[0])
    platform = make_platform(hass, 'sensor')
    try:
        await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        eid, uid = entity.entity_id, entity.unique_id
        assert hass.states.get(eid).state == '1'
        payloads['call/log/'] = None
        await router.update_sensors()
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == 'unavailable'
        assert router.call_list == [{'type': 'missed', 'new': True}]
        payloads['call/log/'] = []
        await router.update_sensors()
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == '0'
        assert (entity.entity_id, entity.unique_id) == (eid, uid)
    finally:
        await platform.async_reset()


async def test_older_sdk_structured_http_denial_is_actionable(hass, home_context):
    router, _ = home_context
    mode, _, _ = sdk_context(router, 'player')
    mode['error'] = HttpRequestError('Request failed (APIResponse: {"success": false, "error_code": "insufficient_rights"})')
    await router.async_update_players()
    assert ir.async_get(hass).async_get_issue(DOMAIN, permission_issue_id(router.entry_id, 'players')) is not None


async def test_vague_home_error_keeps_legacy_gate_without_inventing_a_repair(hass, home_context):
    from freebox_api.api.home import Home
    from custom_components.freebox_homexa.repairs import home_permission_issue_id
    router, _ = home_context
    router._api.home = Home(Mock(get=AsyncMock(side_effect=HttpRequestError('access denied'))))
    await router.update_home_devices()
    assert not router.home_granted
    assert ir.async_get(hass).async_get_issue(DOMAIN, home_permission_issue_id(router.entry_id)) is None
