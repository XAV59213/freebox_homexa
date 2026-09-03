"""Guide TV Homexa : EPG Freebox + pont optionnel vers Programme TNT FR.

Ne recrée ni le domaine programme_tnt_fr, ni ses capteurs, ni sa carte.
Si l'intégration cyclope205/programme-tnt-fr est déjà installée, on lit ses
entités existantes (current / prime_time / second_part). Sinon on reste sur
l'EPG Freebox. Crédit source TNT : xmltvfr.fr / programme-tnt-fr.
"""

from __future__ import annotations

from datetime import datetime, time
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

TNT_DOMAIN = "programme_tnt_fr"
PRIME_TIME_START = time(21, 15)
LATE_NIGHT_START = time(22, 40)

# Noms Freebox / TNT les plus fréquents pour apparier une chaîne Player.
CHANNEL_ALIASES = {
    "tf1": 1,
    "france 2": 2,
    "france2": 2,
    "france 3": 3,
    "france3": 3,
    "canal+": 4,
    "canal plus": 4,
    "france 5": 5,
    "france5": 5,
    "m6": 6,
    "arte": 7,
    "c8": 8,
    "w9": 9,
    "tmc": 10,
    "tfx": 11,
    "nrj 12": 12,
    "lcp": 13,
    "france 4": 14,
    "bfm tv": 15,
    "bfmtv": 15,
    "cnews": 16,
    "cstar": 17,
    "gulli": 18,
}


def _norm(name: str | None) -> str:
    raw = (name or "").strip().lower().replace("+", " plus ")
    return " ".join(slugify(raw).replace("-", " ").split())


def channel_number(name: str | None) -> int | None:
    key = _norm(name)
    if key in CHANNEL_ALIASES:
        return CHANNEL_ALIASES[key]
    compact = key.replace(" ", "")
    for alias, number in CHANNEL_ALIASES.items():
        if alias.replace(" ", "") == compact:
            return number
    return None


@callback
def tnt_programs(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Read already-created Programme TNT FR sensors, if any."""
    programs: list[dict[str, Any]] = []
    for state in hass.states.async_all("sensor"):
        if not state.entity_id.startswith("sensor.programme_tnt_fr_"):
            continue
        current = state.attributes.get("current")
        if not isinstance(current, dict):
            continue
        programs.append(
            {
                "source": TNT_DOMAIN,
                "entity_id": state.entity_id,
                "channel_name": state.attributes.get("channel_name") or state.name,
                "channel_icon": state.attributes.get("channel_icon"),
                "current": current,
                "prime_time": state.attributes.get("prime_time"),
                "second_part": state.attributes.get("second_part"),
            }
        )
    return programs


def _slot_from_freebox(program: dict[str, Any], now: datetime) -> str | None:
    start = program.get("_start")
    if not isinstance(start, datetime):
        return "current"
    local = dt_util.as_local(start)
    start_t = local.timetz().replace(tzinfo=None) if hasattr(local, "timetz") else local.time()
    if start_t >= LATE_NIGHT_START:
        return "second_part"
    if start_t >= PRIME_TIME_START:
        return "prime_time"
    if program.get("_end") and program["_start"] <= now <= program["_end"]:
        return "current"
    return "current"


def summarize_guide(
    hass: HomeAssistant,
    freebox_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge TNT sensors (preferred) with Freebox EPG snippets."""
    tnt = tnt_programs(hass)
    now = dt_util.now()
    current: list[dict[str, Any]] = []
    prime: list[dict[str, Any]] = []
    late: list[dict[str, Any]] = []

    for item in tnt:
        channel = item["channel_name"]
        for key, bucket in (
            ("current", current),
            ("prime_time", prime),
            ("second_part", late),
        ):
            prog = item.get(key)
            if not isinstance(prog, dict) or not prog.get("title"):
                continue
            bucket.append(
                {
                    "channel": channel,
                    "title": prog.get("title"),
                    "category": prog.get("category"),
                    "start": prog.get("start"),
                    "stop": prog.get("stop"),
                    "poster": prog.get("poster"),
                    "tmdb_rating": prog.get("tmdb_rating"),
                    "source": TNT_DOMAIN,
                    "channel_number": channel_number(channel),
                }
            )

    if not tnt and freebox_events:
        for event in freebox_events:
            slot = _slot_from_freebox(event, now)
            payload = {
                "channel": event.get("channel"),
                "title": event.get("title"),
                "category": event.get("category"),
                "start": event.get("start"),
                "stop": event.get("stop"),
                "source": "freebox",
                "channel_number": channel_number(event.get("channel")),
            }
            if slot == "prime_time":
                prime.append(payload)
            elif slot == "second_part":
                late.append(payload)
            else:
                current.append(payload)

    return {
        "source": TNT_DOMAIN if tnt else "freebox",
        "tnt_available": bool(tnt),
        "current": current[:20],
        "prime_time": prime[:20],
        "second_part": late[:20],
    }
