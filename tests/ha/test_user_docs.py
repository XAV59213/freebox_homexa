"""Documentation inventory/syntax only, not official home-assistant.io review."""
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_guide_covers_every_custom_action_and_field():
    guide = (ROOT / 'docs/guide-utilisateur.md').read_text()
    metadata = yaml.safe_load((ROOT / 'custom_components/freebox_homexa/services.yaml').read_text())
    for name, service in metadata.items():
        assert f'### `freebox_homexa.{name}`' in guide
        for field in service.get('fields', {}):
            assert f'`{field}`' in guide, (name, field)


def test_guide_yaml_examples_parse_without_execution():
    guide = (ROOT / 'docs/guide-utilisateur.md').read_text()
    examples = re.findall(r'```yaml\n(.*?)```', guide, re.S)
    assert len(examples) >= 2
    for example in examples:
        assert isinstance(yaml.safe_load(example), dict)
