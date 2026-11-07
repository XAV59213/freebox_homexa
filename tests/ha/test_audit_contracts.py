"""Static contracts complement, not replace, real framework/runtime tests."""
from pathlib import Path
from homeassistant.const import Platform
from custom_components.freebox_homexa.const import PLATFORMS

ROOT = Path(__file__).resolve().parents[2] / 'custom_components' / 'freebox_homexa'


def test_specific_trigger_condition_exemptions():
    """Only HA generic state/event conditions exist; no integration platform."""
    assert Platform.EVENT not in PLATFORMS
    assert not any((ROOT / name).exists() for name in (
        'condition.py', 'trigger.py', 'device_condition.py', 'device_trigger.py',
        'conditions.yaml', 'triggers.yaml',
    ))


def test_every_exported_platform_has_explicit_parallel_updates():
    import ast
    for platform in PLATFORMS:
        module = ast.parse((ROOT / f'{platform}.py').read_text())
        updates = [node.value.value for node in module.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'PARALLEL_UPDATES'
                           for target in node.targets) and isinstance(node.value, ast.Constant)]
        assert len(updates) == 1, platform
        assert isinstance(updates[0], int) and updates[0] >= 0


def test_entity_subscriptions_never_start_in_constructor():
    """Complete inventory: explicit entity subscriptions start after HA addition/action."""
    import ast
    subscriptions = {'async_dispatcher_connect', 'async_track_time_interval', 'async_listen', 'async_listen_once', 'async_add_listener'}
    count = 0
    for path in ROOT.rglob('*.py'):
        tree = ast.parse(path.read_text())
        for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            for method in (node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
                for call in (node for node in ast.walk(method) if isinstance(node, ast.Call)):
                    name = call.func.id if isinstance(call.func, ast.Name) else call.func.attr if isinstance(call.func, ast.Attribute) else ''
                    if name not in subscriptions:
                        continue
                    count += 1
                    assert method.name != '__init__', (path, cls.name)
                    if path.name != '__init__.py':
                        assert method.name in {'async_added_to_hass', '_start_arming_watcher', 'async_register'}, (path, cls.name, method.name)
    assert count >= 13


def test_codeowners_match_manifest_for_component_scope():
    import json
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    declared = manifest['codeowners']
    assert declared and '@XAV59213' in declared
    codeowners = (ROOT.parents[1] / '.github' / 'CODEOWNERS').read_text()
    lines = [line.split() for line in codeowners.splitlines() if line and not line.startswith('#')]
    assert lines == [['/custom_components/freebox_homexa/', *declared]]
