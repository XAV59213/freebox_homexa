"""Erreurs normales pendant un rechargement / déchargement de l'entrée."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from freebox_api.exceptions import NotOpenError

# Messages d'aiohttp quand la session ou le connecteur vient d'être fermé.
_CLOSED_MESSAGES = ("connector is closed", "session is closed", "session closed")


def is_shutdown_error(err: BaseException, router: Any = None) -> bool:
    """True si l'erreur vient de la fermeture de la connexion Freebox (rechargement).

    - l'entrée est en cours de déchargement (`router.closing`) ;
    - `NotOpenError` (client freebox_api déjà fermé) ;
    - « Connector is closed » / « Session is closed » d'aiohttp.
    Les autres erreurs restent des erreurs.
    """
    if router is not None and getattr(router, "closing", False):
        return True
    if isinstance(err, NotOpenError):
        return True
    if isinstance(err, (aiohttp.ClientError, RuntimeError)):
        message = str(err).lower()
        return any(text in message for text in _CLOSED_MESSAGES)
    return False


def poll_log_level(router: Any, level: int = logging.ERROR) -> int:
    """Niveau de journal d'un échec de relevé d'entité.

    Quand le routeur a déjà signalé « Freebox injoignable » (une seule fois, niveau
    info), les échecs suivants des entités passent en debug pour éviter le spam.
    """
    if router is not None and getattr(router, "reachable", True) is False:
        return logging.DEBUG
    return level
