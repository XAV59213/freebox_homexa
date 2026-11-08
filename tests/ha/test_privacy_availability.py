"""Real diagnostics entry point and HA entity availability, no production data."""
import json
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from homeassistant.helpers.entity import Entity
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_homexa.availability import (
    FreeboxReachableMixin, home_node_reachable, router_reachable,
)
from custom_components.freebox_homexa.diagnostics import async_get_config_entry_diagnostics
from custom_components.freebox_homexa.player_diagnostics import cache_player_schema, status_schema, player_diagnostics


class ProbeEntity(FreeboxReachableMixin, Entity):
    def __init__(self, router):
        self._router = router


@pytest.mark.parametrize('reachable,expected', [(True, True), (False, False), (None, True)])
def test_availability_recovery(reachable, expected):
    router = SimpleNamespace(reachable=reachable)
    entity = ProbeEntity(router)
    assert entity.available is expected
    router.reachable = False
    assert not entity.available
    router.reachable = True
    assert entity.available
    entity._attr_available = False
    assert not entity.available


@pytest.mark.parametrize('node,expected', [
    (None, True), ({}, True), ({'status': 'unreachable'}, False),
    ({'status': 'reachable'}, True),
    ({'type': {'inherit': 'node::rts'}, 'status': 'unreachable'}, True),
])
def test_home_node_reachability(node, expected):
    assert home_node_reachable(node) is expected
    assert router_reachable(None)


@pytest.mark.parametrize('loaded', [True, False])
async def test_export_has_no_private_values_or_unknown_keys(hass, loaded):
    private = 'SYNTHETIC_PRIVATE_NAME_IP_TOKEN_TITLE'
    entry = MockConfigEntry(domain='freebox_homexa', title=private, options={'token': private, private: private})
    entry.add_to_hass(hass)
    if loaded:
        router = SimpleNamespace(
            mac=private, model=private, devices={private: {'access_point': {'type': 'repeater'}, 'name': private}},
            repeaters={private: {'name': private, 'model': private, 'macs': [private], 'grouping': private, 'client_count': 2}},
            lan_links={private: 'wired'}, lan_client_types={private: (private, 'net_servers')},
            wifi_radio_status={private: private}, wifi_aps={},
            api_repeaters_raw={private: {'title': private, 'token': private}},
        )
        cache_player_schema(router, private, {
            'foreground_app': {'package': 'youtube', 'cur_url': private},
            'player': {'state': {'title': private, private: private, 'duration_ms': 100, 'position_ms': 20}},
        }, 'received')
        entry.runtime_data = router
    with patch('custom_components.freebox_homexa.diagnostics.repeater_registry_devices', return_value=[{private: private}]):
        result = await async_get_config_entry_diagnostics(hass, entry)
    assert private not in json.dumps(result)
    if loaded:
        assert result['players'][0]['timing_samples'][0]['duration_ms'] == 100
        assert result['players'][0]['timing_samples'][0]['position_ms'] == 20


@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf'), 999999999999, 'secret'])
def test_invalid_timing_never_exported(value):
    router = SimpleNamespace()
    cache_player_schema(router, 'private-id', {'player': {'state': {'duration_ms': value, 'position_ms': value}}}, 'received')
    sample = router.player_diagnostic_schemas['private-id']['timing_samples'][0]
    assert sample['duration_ms'] is None
    assert sample['position_ms'] is None


def test_schema_bounded_and_unknown_keys_removed():
    assert len(status_schema({f'private-{i}': 'secret' for i in range(100)})['fields']) == 64
    assert len(status_schema(['secret'] * 100)['items']) == 8
    nested = 'private'
    for _ in range(30):
        nested = {'private-key': nested}
    encoded = json.dumps(status_schema(nested))
    assert 'private' not in encoded
    assert 'truncated' in encoded


@pytest.mark.parametrize('package,expected', [('netflix', 'Netflix'), ('tv:1', 'TV'), ('fr.freebox.tv', 'TV'), ('other', 'other')])
def test_safe_category_and_samples_lifecycle(package, expected):
    router = SimpleNamespace()
    payload = {'foreground_app': {'package': package}, 'player': {'state': {'playback_state': 'playing'}}}
    for _ in range(3):
        cache_player_schema(router, 'synthetic', payload, 'received')
    result = player_diagnostics(router)[0]
    assert len(result['timing_samples']) == 2
    assert result['timing_samples'][0]['application_category'] == expected
    assert result['timing_samples'][0]['playback_state'] == 'playing'
    cache_player_schema(router, 'synthetic', None, 'error with private message')
    result = player_diagnostics(router)[0]
    assert result['outcome'] == 'unavailable'
    assert result['timing_samples'] == []


def test_changed_category_expired_samples_and_cache_bound():
    router = SimpleNamespace()
    cache_player_schema(router, 'synthetic', {'foreground_app': {'package': 'youtube'}}, 'received')
    cache_player_schema(router, 'synthetic', {'foreground_app': {'package': 'netflix'}}, 'received')
    assert len(player_diagnostics(router)[0]['timing_samples']) == 1
    old = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()
    stored = router.player_diagnostic_schemas['synthetic']
    stored['observed_at'] = old
    stored['timing_samples'][0]['observed_at'] = old
    result = player_diagnostics(router)[0]
    assert result['stale'] is True
    assert result['timing_samples'] == []
    for index in range(30):
        cache_player_schema(router, index, {}, 'received')
    assert len(router.player_diagnostic_schemas) == 16


@pytest.mark.parametrize('value,kind', [(None, 'null'), (True, 'boolean'), (4, 'number'), (object(), 'unsupported')])
def test_schema_type_only(value, kind):
    assert status_schema(value)['type'] == kind


def test_schema_budget_bounds_wide_nested_payload():
    result = status_schema({str(i): {str(j): 'secret' for j in range(64)} for i in range(64)})
    assert len(result['fields']) < 64
    assert 'secret' not in json.dumps(result)
