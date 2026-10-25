"""Disponibilité des entités (règle entity-unavailable de l'Integration Quality Scale)."""

from __future__ import annotations

from typing import Any

# Statut d'un nœud Freebox Home quand la Freebox ne le joint plus
# (valeurs de l'API : active, unreachable, disabled, unpaired).
HOME_NODE_UNREACHABLE = "unreachable"


def router_reachable(router: Any) -> bool:
    """False quand le dernier relevé du routeur a échoué (« Freebox injoignable »)."""
    return router is None or getattr(router, "reachable", True) is not False


def home_node_reachable(node: dict[str, Any] | None) -> bool:
    """False si la Freebox signale le nœud Home « unreachable ».

    Les nœuds RTS (Somfy, radio sans retour d'état) sont ignorés : la Freebox ne
    peut pas savoir s'ils répondent, on ne les rend jamais indisponibles pour ça.
    """
    if not node:
        return True
    if (node.get("type") or {}).get("inherit") == "node::rts":
        return True
    return node.get("status") != HOME_NODE_UNREACHABLE


class FreeboxReachableMixin:
    """Entité indisponible tant que la Freebox est injoignable.

    À placer en premier dans les classes de base ; l'entité doit avoir `_router`.
    Les autres conditions (`_attr_available`, Player injoignable…) restent valables.
    """

    _router: Any

    @property
    def available(self) -> bool:
        if not router_reachable(getattr(self, "_router", None)):
            return False
        return super().available  # type: ignore[misc]
