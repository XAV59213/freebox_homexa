"""Schéma Player sans valeurs personnelles, construit avant toute mise en cache.

Les noms inconnus peuvent eux-mêmes contenir des identifiants : ils sont
remplacés par des positions. Aucune URL, titre, identité ou valeur numérique
n'est conservée. Bornes pour ne pas garder un payload arbitrairement volumineux.
"""
from itertools import islice
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


def cache_player_schema(router: Any, player_id: Any, status: Any, outcome: str) -> None:
    """Dernier relevé uniquement ; clé interne jamais incluse dans l'export."""
    cache = getattr(router, "player_diagnostic_schemas", None)
    if not isinstance(cache, dict):
        cache = router.player_diagnostic_schemas = {}
    if player_id not in cache and len(cache) >= 16:
        return
    cache[player_id] = {"outcome": outcome, "status_schema": status_schema(status)}
