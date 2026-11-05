"""Confidentialité : schémas Player et export complet, sans requête réseau."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1] / 'custom_components/freebox_homexa'
pkg = types.ModuleType('freebox_homexa')
pkg.__path__ = [str(ROOT)]
sys.modules['freebox_homexa'] = pkg
from freebox_homexa.player_diagnostics import cache_player_schema, status_schema

secrets = ['SECRET_TOKEN', 'alice@example.test', '01:23:45:67:89:ab', '192.0.2.99',
           'Mon titre privé', 'Auteur privé', 'https://example.test/image?token=secret&uid=123']
payload = {'foreground_app': {'package':'youtube-private', 'context': {'player': {
    'metadata': {'title':secrets[4], 'artist':secrets[5], 'thumbnail_url':secrets[6],
                 'deep': {'cookie':secrets[0], secrets[1]: {'mac':secrets[2], 'ip':secrets[3]}}}}}},
    'player': {'state': {'playback_state':'playing', 'duration_ms':12345}},
    'calls': [{'phone':'PRIVATE_PHONE', 'identity':secrets[1]}],
    'session_auth':{'password':secrets[0]}}
schema = status_schema(payload)
encoded = json.dumps(schema)
for secret in secrets + ['youtube-private', 'PRIVATE_PHONE', '12345', 'cookie', 'session_auth']:
    assert secret not in encoded
metadata = schema['fields']['foreground_app']['fields']['context']['fields']['player']['fields']['metadata']['fields']
assert metadata['title'] == {'type':'string', 'present':True}
assert metadata['thumbnail_url'] == {'type':'string', 'present':True}
assert status_schema(None) == {'type':'null'}
assert status_schema('') == {'type':'string', 'present':False}
cycle = {}; cycle['metadata'] = cycle
assert len(json.dumps(status_schema(cycle))) < 3000
wide = {'metadata': [{str(i):list(range(100)) for i in range(100)}] * 20}
assert len(json.dumps(status_schema(wide))) < 40000
router = types.SimpleNamespace()
cache_player_schema(router, 17, payload, 'received')
assert 'Mon titre privé' not in repr(router.player_diagnostic_schemas)
cache_player_schema(router, 17, None, 'unavailable')
assert router.player_diagnostic_schemas[17]['status_schema'] == {'type':'null'}
for i in range(100):
    cache_player_schema(router, i, {}, 'received')
assert len(router.player_diagnostic_schemas) == 16

# Charger le diagnostic HA avec des services minimaux sans accès réseau.
def module(name, **attrs):
    mod = types.ModuleType(name); mod.__dict__.update(attrs); sys.modules[name] = mod
module('homeassistant'); module('homeassistant.components')
module('homeassistant.components.diagnostics', async_redact_data=lambda data, keys:data)
module('homeassistant.config_entries', ConfigEntry=object)
module('homeassistant.core', HomeAssistant=object)
module('freebox_homexa.device_groups', repeater_registry_devices=lambda *a:{secrets[2]:secrets[1]})
module('freebox_homexa.wifi_ap', is_freebox_repeater=lambda *a:False)
from freebox_homexa.diagnostics import async_get_config_entry_diagnostics
entry = types.SimpleNamespace(title=secrets[1], version=1, options={'unknown_secret':secrets[0]}, runtime_data=None)
result = asyncio.run(async_get_config_entry_diagnostics(None, entry))
assert result['players'] == []
for secret in secrets:
    assert secret not in json.dumps(result)
router = types.SimpleNamespace(mac=secrets[2], model=secrets[1], devices={}, repeaters={},
    wifi_radio_status={'token':secrets[0]}, wifi_api_errors={}, wifi_aps={},
    player_diagnostic_schemas={})
cache_player_schema(router, 17, payload, 'received')
entry.runtime_data = router
result = asyncio.run(async_get_config_entry_diagnostics(None, entry))
assert len(result['players']) == 1 and result['players'][0]['outcome'] == 'received'
assert 'player_id' not in json.dumps(result)
for secret in secrets:
    assert secret not in json.dumps(result)
assert not hasattr(router, '_api')  # Aucune API nécessaire au téléchargement.
print('OK : cache borné, aucun secret/URL/titre/identifiant/valeur personnelle, export complet, entrée non chargée')
