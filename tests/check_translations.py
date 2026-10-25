"""Vérifie la cohérence strings.json / translations/*.json et les translation_key du code.

- mêmes clés (entity, exceptions, services…) dans strings.json et chaque traduction ;
- mêmes placeholders {x} d'une langue à l'autre ;
- chaque translation_key utilisée dans le code (entités, exceptions) existe partout.
Lancer depuis la racine du dépôt : python3 tests/check_translations.py
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path("custom_components/freebox_homexa")
files = {"strings.json": json.loads((ROOT / "strings.json").read_text())}
for path in sorted((ROOT / "translations").glob("*.json")):
    files[f"translations/{path.name}"] = json.loads(path.read_text())


def flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flat(v, key))
        else:
            out[key] = v
    return out


flats = {name: flat(data) for name, data in files.items()}
errors = []
ref = flats["strings.json"]
for name, f in flats.items():
    for section in ("entity", "exceptions"):
        a = {k for k in ref if k.startswith(section + ".")}
        b = {k for k in f if k.startswith(section + ".")}
        for k in sorted(a - b):
            errors.append(f"{name}: clé manquante {k}")
        for k in sorted(b - a):
            errors.append(f"{name}: clé en trop {k}")
    for k, v in f.items():
        if k in ref and isinstance(v, str) and isinstance(ref[k], str):
            if set(re.findall(r"{(\w+)}", v)) != set(re.findall(r"{(\w+)}", ref[k])):
                errors.append(f"{name}: placeholders différents pour {k}")

src = {p.name: p.read_text() for p in ROOT.glob("*.py")}
entity_keys = {k.split(".")[2] for k in ref if k.startswith("entity.")}
exc_keys = {k.split(".")[1] for k in ref if k.startswith("exceptions.")}
for fname, text in src.items():
    for key in re.findall(r'translation_key\s*=\s*"([a-z0-9_]+)"', text):
        if key not in entity_keys and key not in exc_keys:
            errors.append(f"{fname}: translation_key « {key} » absente de strings.json")
# Clés construites (boutons Player) : remote_key_<touche>, player_app_<app>.
button = src["button.py"]
for key in re.findall(r'^\s*\("([^"]+)", "[^"]+", "mdi:[^"]+", (?:True|False)\),', button, re.M):
    if f"remote_key_{key}" not in entity_keys:
        errors.append(f"button.py: remote_key_{key} absente")
for key in re.findall(r'^\s*\("([^"]+)", "[^"]+", "mdi:[^"]+", "https?://[^"]+", (?:True|False)\),', button, re.M):
    if f"player_app_{key}" not in entity_keys:
        errors.append(f"button.py: player_app_{key} absente")
for key in re.findall(r'key="([a-z_]+)",\s*\n\s*name=', button):
    if key not in entity_keys:
        errors.append(f"button.py: {key} absente")

if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"{len(files)} fichiers, {len(entity_keys)} clés d'entité, {len(exc_keys)} exceptions : cohérents")
print("CHECK_TRANSLATIONS_OK")
