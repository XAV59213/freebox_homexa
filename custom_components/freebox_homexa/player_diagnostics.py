"""Schéma Player sans valeurs personnelles, construit avant toute mise en cache.

Les noms inconnus peuvent eux-mêmes contenir des identifiants : ils sont
remplacés par des positions. Aucune URL, titre ou identité n'est conservé. Les seules valeurs numériques
autorisées sont les durées/positions bornées des observations de lecture. Bornes pour ne pas garder un payload arbitrairement volumineux.
"""
from datetime import datetime, timezone
from itertools import islice
import math
from typing import Any

_KEYS = frozenset('''foreground_app package package_id cur_url context player state
metadata title artist author album description thumbnail thumbnail_url image artwork
url uri source duration duration_ms position position_ms playback_state playbackState
power_state capabilities name channel channelName channelNumber cur_info program_name
volume mute mediaState videoList audioList subtitleList'''.split())


def status_schema(value: Any, depth: int = 0, _budget: list[int] | None = None) -> dict[str, Any]:
    """Ne conserve que types, présence et quelques noms de champs approuvés."""
    if _budget is None:
        _budget = [512]
    _budget[0] -= 1
    if depth >= 10 or _budget[0] < 0:
        return {"type": "truncated"}
    if isinstance(value, dict):
        fields = {}
        for index, (key, child) in enumerate(islice(value.items(), 64)):
            if _budget[0] <= 0:
                break
            safe_key = key if isinstance(key, str) and key in _KEYS else f"unknown_field_{index}"
            fields[safe_key] = status_schema(child, depth + 1, _budget)
        return {"type": "object", "fields": fields}
    if isinstance(value, (list, tuple)):
        return {"type": "array", "items": [status_schema(v, depth + 1, _budget) for v in value[:8] if _budget[0] > 0]}
    if value is None:
        return {"type": "null"}
    if isinstance(value, str):
        return {"type": "string", "present": bool(value)}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    return {"type": "unsupported"}


MAX_TIMING_MS = 7 * 24 * 60 * 60 * 1000  # Sept jours, pas un horodatage Unix.
MAX_SAMPLE_AGE = 120
_STATES = frozenset({"playing", "paused", "stopped", "unknown", "idle", "buffering"})


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _timing(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if 0 <= value <= MAX_TIMING_MS and math.isfinite(value):
        return value
    return None


def _recent(samples: list, now: datetime) -> list:
    return [s for s in samples if 0 <= (
        now - datetime.fromisoformat(s["observed_at"])
    ).total_seconds() <= MAX_SAMPLE_AGE]


def cache_player_schema(router: Any, player_id: Any, status: Any, outcome: str) -> None:
    """Schéma et deux observations filtrées ; aucune copie du statut brut."""
    cache = getattr(router, "player_diagnostic_schemas", None)
    if not isinstance(cache, dict):
        cache = router.player_diagnostic_schemas = {}
    if player_id not in cache and len(cache) >= 16:
        return
    now = datetime.now(timezone.utc)
    outcome = "received" if outcome == "received" else "unavailable"
    previous = cache.get(player_id, {})
    samples = _recent(previous.get("timing_samples", []), now)
    if outcome != "received" or not isinstance(status, dict):
        samples = []
    else:
        state = _dict(_dict(status.get("player")).get("state"))
        foreground = _dict(status.get("foreground_app"))
        package = foreground.get("package")
        cur_url = foreground.get("cur_url")
        # Même logique large que media_player (sous-chaîne youtube/netflix),
        # sans jamais exporter le package brut.
        category = "other"
        candidates = [v for v in (package, cur_url) if isinstance(v, str)]
        blob = " ".join(candidates).lower()
        if any(v.startswith("tv:") or v == "fr.freebox.tv" for v in candidates):
            category = "TV"
        elif "youtube" in blob:
            category = "YouTube"
        elif "netflix" in blob:
            category = "Netflix"
        playback = state.get("playback_state")
        sample = {
            "observed_at": now.isoformat(),
            "application_category": category,
            "playback_state": playback if isinstance(playback, str) and playback in _STATES else "unknown",
            "duration_ms": _timing(state.get("duration_ms")),
            "position_ms": _timing(state.get("position_ms")),
        }
        if samples and samples[-1]["application_category"] != category:
            samples = []
        samples = (samples + [sample])[-2:]
    cache[player_id] = {
        "outcome": outcome, "status_schema": status_schema(status),
        "observed_at": now.isoformat(), "timing_samples": samples,
    }


def player_diagnostics(router: Any) -> list[dict]:
    """Retire les observations périmées lors de l'export, sans trafic réseau."""
    now = datetime.now(timezone.utc)
    result = []
    for entry in getattr(router, "player_diagnostic_schemas", {}).values():
        age = max(0, (now - datetime.fromisoformat(entry["observed_at"])).total_seconds())
        result.append({**entry, "age_seconds": round(age, 1),
                       "stale": age > MAX_SAMPLE_AGE,
                       "timing_samples": _recent(entry["timing_samples"], now)})
    return result
