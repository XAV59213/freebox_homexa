"""Offline checklist validation; optionally run the pinned official HA schema.

python -B tests/validate_quality_scale.py [--upstream-schema /path/quality_scale.py]
Dependencies: PyYAML; probatio only for the official schema check.
No HA session, network, credentials or runtime imports.
"""
import argparse
import ast
from collections import Counter
import json
import re
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate(data, rules):
    """Strict key/status/comment validation (not the semantic hassfest checks)."""
    assert isinstance(data, dict) and set(data) == {'rules'}
    assert isinstance(data['rules'], dict)
    assert set(data['rules']) == {r['name'] for r in rules}
    for name, value in data['rules'].items():
        assert isinstance(value, dict), name
        assert set(value) == {'status', 'comment'}, name
        assert value['status'] in {'done', 'todo', 'exempt'}, name
        assert isinstance(value['comment'], str) and value['comment'].strip(), name


def validate_evidence_coherence(data, matrix):
    """Keep shipped YAML comments/statuses identical to the proof matrix."""
    rows = {}
    for line in matrix.splitlines():
        match = re.match(r"^\| \[([^\]]+)\]\([^)]*\) \| (done|todo|exempt) \| (.*?) \|", line)
        if match:
            rows[match[1]] = {"status": match[2], "comment": match[3]}
    assert rows == data["rules"], "YAML/matrix evidence or status drift"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream-schema', type=Path)
    args = parser.parse_args()
    snapshot = json.loads((ROOT / 'docs/quality-scale-rules.json').read_text())
    data = yaml.safe_load((ROOT / 'custom_components/freebox_homexa/quality_scale.yaml').read_text())
    rules = snapshot['rules']
    validate(data, rules)
    matrix = (ROOT / "docs/quality-scale-proof-matrix.md").read_text()
    validate_evidence_coherence(data, matrix)
    # Negative controls: missing rule, invented rule, invalid status must fail.
    import copy
    for mutate in (
        lambda d: d['rules'].pop('test-coverage'),
        lambda d: d['rules'].update({'invented-rule': {'status': 'done', 'comment': 'x'}}),
        lambda d: d['rules']['test-coverage'].update(status='certified'),
    ):
        bad = copy.deepcopy(data)
        mutate(bad)
        try:
            validate(bad, rules)
        except AssertionError:
            pass
        else:
            raise AssertionError('Negative control accepted')
    stale = copy.deepcopy(data)
    stale["rules"]["test-coverage"]["comment"] = "stale evidence"
    try:
        validate_evidence_coherence(stale, matrix)
    except AssertionError:
        pass
    else:
        raise AssertionError("Evidence drift negative control accepted")
    if args.upstream_schema:
        import probatio
        tree = ast.parse(args.upstream_schema.read_text())
        assignments = {n.targets[0].id: n for n in tree.body
                       if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
        upstream = assignments['ALL_RULES'].value.elts
        actual = [{'name': n.args[0].value, 'tier': n.args[1].attr.lower()} for n in upstream]
        assert actual == rules, 'Pinned official rules differ from snapshot'
        # Evaluate the official SCHEMA assignment verbatim, without importing HA
        # or executing the unrelated hassfest integration validators.
        env = {'probatio': probatio,
               'ALL_RULES': [SimpleNamespace(name=r['name']) for r in rules]}
        code = ast.Module(body=[assignments['SCHEMA']], type_ignores=[])
        exec(compile(code, str(args.upstream_schema), 'exec'), env)
        env['SCHEMA'](data)
        print('Official probatio SCHEMA: OK (structure only, NOT semantic hassfest)')
    print(f"{len(rules)} rules: {dict(Counter(v['status'] for v in data['rules'].values()))}")
    print('Offline validation and negative controls: OK')


if __name__ == '__main__':
    main()
