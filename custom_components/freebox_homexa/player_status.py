"""Read the existing Player status contract independently of enabled entities."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .router import FreeboxRouter

API_VERSION_FALLBACKS = ("v6", "v8", "v7", "v5")


async def async_read_player_status(
    router: FreeboxRouter, player_id: int, preferred_version: str,
) -> tuple[dict[str, Any] | None, str]:
    """Use exactly the existing status paths/version fallbacks, never a control."""
    for version in (preferred_version, *(v for v in API_VERSION_FALLBACKS if v != preferred_version)):
        try:
            status = await router.async_read(
                lambda: router._api.player._access.get(f"player/{player_id}/api/{version}/status/")
            )
            if isinstance(status, dict):
                return status, version
        except Exception:
            # Cancellation propagates; unavailable is observed only after all fallbacks.
            continue
    return None, preferred_version
