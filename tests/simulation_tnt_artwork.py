"""Tests du matching artwork TNT (poster/icone → logo), hors HA.

Lancer : python3 -B tests/simulation_tnt_artwork.py
"""
import importlib.util
import sys
import types
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


def slugify(value: str) -> str:
    out = []
    for ch in (value or "").lower():
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    return "-".join(part for part in "".join(out).split("-") if part)


module("homeassistant")
module("homeassistant.core", HomeAssistant=object, callback=lambda f: f)
module("homeassistant.util")
module("homeassistant.util.dt", now=lambda: None, as_local=lambda x: x)
sys.modules["homeassistant.util"].slugify = slugify
sys.modules["homeassistant.util"].dt = sys.modules["homeassistant.util.dt"]

spec = importlib.util.spec_from_file_location(
    "freebox_homexa.tv_guide",
    ROOT / "custom_components/freebox_homexa/tv_guide.py",
)
tv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tv)

POSTER = "https://image.tmdb.org/t/p/w500/bfm-poster.jpg"
PROG_ICON = "https://example.com/prog-icon.png"
CHANNEL_ICON = "https://example.com/bfm-logo.png"

PROGRAMS = [
    {
        "channel_name": "BFM TV",
        "channel_icon": CHANNEL_ICON,
        "current": {"title": "JT", "poster": POSTER, "icon": PROG_ICON},
    },
    {
        "channel_name": "M6",
        "channel_icon": "https://example.com/m6.png",
        "current": {"title": "Serie", "icon": "https://example.com/m6-prog.png"},
    },
]


def run():
    # BFM TV : poster prioritaire (comme la carte TNT).
    assert tv.artwork_from_tnt_programs(PROGRAMS, channel_name="BFM TV") == POSTER
    assert tv.artwork_from_tnt_programs(PROGRAMS, channel_name="BFMTV") == POSTER
    assert tv.artwork_from_tnt_programs(PROGRAMS, channel_number=15) == POSTER
    assert tv.artwork_from_tnt_programs(PROGRAMS, channel_name="bfm tv", channel_number=15) == POSTER

    # Sans poster : icone programme avant logo chaîne.
    no_poster = [
        {
            "channel_name": "BFM TV",
            "channel_icon": CHANNEL_ICON,
            "current": {"title": "JT", "icon": PROG_ICON},
        }
    ]
    assert tv.artwork_from_tnt_programs(no_poster, channel_name="BFM TV") == PROG_ICON

    # Sans programme : logo chaîne.
    logo_only = [
        {"channel_name": "BFM TV", "channel_icon": CHANNEL_ICON, "current": {"title": "JT"}}
    ]
    assert tv.artwork_from_tnt_programs(logo_only, channel_name="BFM TV") == CHANNEL_ICON

    # Pas de match / pas de données : None (pas d'overwrite inventé).
    assert tv.artwork_from_tnt_programs([], channel_name="BFM TV") is None
    assert tv.artwork_from_tnt_programs(PROGRAMS, channel_name="Chaîne inconnue") is None
    assert tv.artwork_from_tnt_programs(PROGRAMS, channel_number=99) is None

    # URL non HTTP ignorée.
    bad = [
        {
            "channel_name": "BFM TV",
            "channel_icon": "/local/logo.png",
            "current": {"poster": "ftp://bad", "icon": None},
        }
    ]
    assert tv.artwork_from_tnt_programs(bad, channel_name="BFM TV") is None

    # M6 par numéro (alias).
    assert tv.artwork_from_tnt_programs(PROGRAMS, channel_number=6) == "https://example.com/m6-prog.png"

    print("OK : artwork TNT BFM/variants, priorité poster→icon→logo, sans match=None")


if __name__ == "__main__":
    run()
