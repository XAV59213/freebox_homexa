"""Disponibilité des entités (règle entity-unavailable de l'Integration Quality Scale)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from collections.abc import Mapping
from homeassistant.helpers.entity import Entity

if TYPE_CHECKING:
    from .router import FreeboxRouter

# Statut d'un nœud Freebox Home quand la Freebox ne le joint plus
# (valeurs de l'API : active, unreachable, disabled, unpaired).
HOME_NODE_UNREACHABLE = "unreachable"


def router_reachable(router: FreeboxRouter | None) -> bool:
    """False quand le dernier relevé du routeur a échoué (« Freebox injoignable »)."""
    return router is None or (
        getattr(router, "reachable", True) is not False
        and not getattr(router, "closing", False)
    )


def home_node_reachable(node: Mapping[str, object] | None) -> bool:
    """False si la Freebox signale le nœud Home « unreachable ».

    Les nœuds RTS (Somfy, radio sans retour d'état) sont ignorés : la Freebox ne
    peut pas savoir s'ils répondent, on ne les rend jamais indisponibles pour ça.
    """
    if not node:
        return True
    node_type = node.get("type")
    if isinstance(node_type, Mapping) and node_type.get("inherit") == "node::rts":
        return True
    return node.get("status") != HOME_NODE_UNREACHABLE


class FreeboxReachableMixin(Entity):
    """Entité indisponible tant que la Freebox est injoignable.

    À placer en premier dans les classes de base ; l'entité doit avoir `_router`.
    Les autres conditions (`_attr_available`, Player injoignable…) restent valables.
    """

    _router: FreeboxRouter

    @property
    def available(self) -> bool:
        if not router_reachable(getattr(self, "_router", None)):
            return False
        return super().available


class FreeboxLanReachableMixin(FreeboxReachableMixin):
    """LAN-derived inventory is unavailable when bridge mode has no hosts source."""

    @property
    def available(self) -> bool:
        return super().available and getattr(self._router, "lan_available", True) is not False


class FreeboxPlayerReachableMixin(FreeboxReachableMixin):
    """Reuse the media Player's existing status reads; no per-button polling."""

    _player_id: int
    _initial_player_reachable: bool = True

    @property
    def available(self) -> bool:
        observed = self._router.player_status_available.get(str(self._player_id))
        return super().available and (self._initial_player_reachable if observed is None else observed)
