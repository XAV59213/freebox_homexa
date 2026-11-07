"""Translation contracts and multi-entry resolution, no service/device command."""
import ast
import json
from pathlib import Path
from string import Formatter
from types import SimpleNamespace

import pytest
import yaml
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.translation import async_get_translations
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_homexa.services import async_resolve_entries

ROOT = Path(__file__).resolve().parents[2] / 'custom_components/freebox_homexa'
DOMAIN = 'freebox_homexa'


def alternatives(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return alternatives(node.body) | alternatives(node.orelse)
    raise AssertionError(f'Unreviewed dynamic translation key: {ast.dump(node)}')


@pytest.mark.parametrize('filename', ['strings.json', 'translations/fr.json', 'translations/en.json'])
def test_all_raised_custom_ha_exceptions_translatable(filename):
    messages = json.loads((ROOT / filename).read_text())['exceptions']
    kinds = {'HomeAssistantError', 'ServiceValidationError', 'ConfigEntryError',
             'ConfigEntryAuthFailed', 'ConfigEntryNotReady', 'UpdateFailed'}
    count = 0
    for path in ROOT.rglob('*.py'):
        for raised in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(raised, ast.Raise) and isinstance(raised.exc, ast.Call)
                    and isinstance(raised.exc.func, ast.Name) and raised.exc.func.id in kinds):
                continue
            call = raised.exc
            count += 1
            fields = {item.arg: item.value for item in call.keywords}
            assert not call.args, (path, raised.lineno)
            assert isinstance(fields.get('translation_domain'), ast.Name)
            assert fields['translation_domain'].id == 'DOMAIN'
            keys = alternatives(fields['translation_key'])
            placeholders = fields.get('translation_placeholders')
            provided = set() if placeholders is None else {node.value for node in placeholders.keys}
            for key in keys:
                assert key in messages, (path, raised.lineno, key)
                used = {name for _, name, _, _ in Formatter().parse(messages[key]['message']) if name is not None}
                assert used == provided, (key, used, provided)
    assert count >= 17  # Includes setup errors, user actions and coordinator UpdateFailed.


@pytest.mark.parametrize('filename', ['strings.json', 'translations/fr.json', 'translations/en.json'])
def test_every_service_and_field_has_matching_translation(filename):
    services = yaml.safe_load((ROOT / 'services.yaml').read_text())
    translated = json.loads((ROOT / filename).read_text())['services']
    assert services.keys() == translated.keys()
    for name, metadata in services.items():
        assert translated[name]['name'] and translated[name]['description']
        assert metadata.get('fields', {}).keys() == translated[name].get('fields', {}).keys()
        for field in metadata.get('fields', {}):
            assert translated[name]['fields'][field]['name']
            assert translated[name]['fields'][field]['description']


async def test_ha_loads_french_exception_translations(hass):
    translated = await async_get_translations(hass, 'fr', 'exceptions', {DOMAIN})
    assert translated[f'component.{DOMAIN}.exceptions.cannot_fetch_tnt.message'] == 'Impossible de récupérer le guide TNT : {error}'
    assert '{service}' in translated[f'component.{DOMAIN}.exceptions.multiple_entries.message']


async def test_resolve_multi_entries_without_calling_action(hass):
    call = ServiceCall(hass, DOMAIN, 'reboot', {})
    with pytest.raises(ServiceValidationError) as exc:
        async_resolve_entries(hass, call)
    assert exc.value.translation_key == 'no_loaded_entry'
    entries = []
    for index in range(2):
        entry = MockConfigEntry(domain=DOMAIN, data={'host': f'freebox{index}.test'})
        entry.add_to_hass(hass)
        entry.runtime_data = SimpleNamespace()
        entry._async_set_state(hass, ConfigEntryState.LOADED, None)
        entries.append(entry)
    with pytest.raises(ServiceValidationError) as exc:
        async_resolve_entries(hass, call)
    assert exc.value.translation_key == 'multiple_entries'
    assert async_resolve_entries(hass, ServiceCall(hass, DOMAIN, 'reboot', {'config_entry_id': entries[1].entry_id})) == [entries[1]]
    assert async_resolve_entries(hass, call, allow_many=True) == entries
    entries[1]._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)
    with pytest.raises(ServiceValidationError) as exc:
        async_resolve_entries(hass, ServiceCall(hass, DOMAIN, 'reboot', {'config_entry_id': entries[1].entry_id}))
    assert exc.value.translation_key == 'entry_not_loaded'
