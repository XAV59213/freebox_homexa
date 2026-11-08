"""Document inventory consistency, explicitly not an additional runtime proof."""
import re
from pathlib import Path
import yaml


def test_every_official_rule_has_one_honest_matrix_row():
    root = Path(__file__).resolve().parents[2]
    rules = yaml.safe_load((root / "custom_components/freebox_homexa/quality_scale.yaml").read_text())["rules"]
    matrix = (root / "docs/quality-scale-proof-matrix.md").read_text()
    rows = re.findall(r"^\| \[([a-z-]+)\]\([^\n]+?\) \| (done|todo|exempt) \|", matrix, re.M)
    assert len(rows) == len(rules) == 54
    assert dict(rows) == {key: value["status"] for key, value in rules.items()}
    assert "pas certification" in matrix
    assert "Contenu local présent / revue officielle absente" in matrix
