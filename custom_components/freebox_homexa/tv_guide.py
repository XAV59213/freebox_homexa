"""Guide TV Homexa : EPG Freebox + guide TNT embarqué de Homexa.

Lit les données du coordinateur TNT propre à Homexa
(hass.data["freebox_homexa"]["tnt_coordinators"]) ; sinon on reste sur
l'EPG Freebox. Crédit source TNT : xmltvfr.fr / programme-tnt-fr (MIT).
"""

from __future__ import annotations

from datetime import datetime, time
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

TNT_SOURCE = "tnt"
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


def _wanted_channel_number(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _http_url(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    return None


def artwork_from_tnt_programs(
    programs: list[dict[str, Any]],
    *,
    channel_name: str | None = None,
    channel_number: int | str | None = None,
) -> str | None:
    """Poster/icone du programme en cours, sinon logo de chaîne (comme la carte TNT).

    Le capteur TNT préfère channel_icon ; la carte utilise poster || icon.
    Pour le media_player on suit la carte : artwork du programme d'abord.
    """
    resolve_number = globals()["channel_number"]
    wanted_num = _wanted_channel_number(channel_number)
    wanted_key = _norm(channel_name)
    wanted_compact = wanted_key.replace(" ", "")
    if wanted_num is None and channel_name:
        wanted_num = resolve_number(channel_name)

    for prog in programs:
        if not isinstance(prog, dict):
            continue
        name = prog.get("channel_name")
        name_s = name if isinstance(name, str) else None
        key = _norm(name_s)
        compact = key.replace(" ", "")
        prog_num = resolve_number(name_s)
        matched = False
        if wanted_key and (key == wanted_key or (wanted_compact and compact == wanted_compact)):
            matched = True
        elif wanted_num is not None and prog_num == wanted_num:
            matched = True
        if not matched:
            continue
        current = prog.get("current")
        if isinstance(current, dict):
            for field in ("poster", "icon"):
                url = _http_url(current.get(field))
                if url:
                    return url
        url = _http_url(prog.get("channel_icon"))
        if url:
            return url
    return None


def tnt_artwork_url(
    hass: HomeAssistant,
    *,
    channel_name: str | None = None,
    channel_number: int | str | None = None,
) -> str | None:
    """Recherche dans les coordinateurs TNT Homexa déjà chargés (pas de réseau)."""
    return artwork_from_tnt_programs(
        tnt_programs(hass),
        channel_name=channel_name,
        channel_number=channel_number,
    )


@callback
def tnt_programs(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Read the programmes of Homexa's own bundled TNT coordinators, if any."""
    programs: list[dict[str, Any]] = []
    seen: set[str] = set()
    coordinators = (
        hass.data.get("freebox_homexa", {}).get("tnt_coordinators", {}).values()
    )
    for coordinator in coordinators:
        data = getattr(coordinator, "data", None)
        if not isinstance(data, dict):
            continue
        for channel_id, item in data.items():
            if channel_id in seen or not isinstance(item, dict):
                continue
            current = item.get("current")
            if not isinstance(current, dict):
                continue
            seen.add(channel_id)
            programs.append(
                {
                    "source": TNT_SOURCE,
                    "channel_id": channel_id,
                    "channel_name": item.get("channel_name") or channel_id,
                    "channel_icon": item.get("channel_icon"),
                    "current": current,
                    "prime_time": item.get("prime_time"),
                    "second_part": item.get("second_part"),
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
                    "source": TNT_SOURCE,
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
        "source": TNT_SOURCE if tnt else "freebox",
        "tnt_available": bool(tnt),
        "current": current[:20],
        "prime_time": prime[:20],
        "second_part": late[:20],
    }
