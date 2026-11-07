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
