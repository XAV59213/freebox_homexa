"""Erreurs normales pendant un rechargement / déchargement de l'entrée."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import aiohttp
from freebox_api.exceptions import InsufficientPermissionsError, NotOpenError

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


def api_error_code(err: BaseException) -> str | None:
    """Extrait `error_code` d'une HttpRequestError freebox_api, ou None."""
    text = str(err)
    matcher = re.search(r"APIResponse:\s*(\{.*\})\s*\)\s*$", text)
    if matcher is None:
        matcher = re.search(r"Request failed \(APIResponse: (.+)\)", text)
    if matcher is None:
        return None
    try:
        data = json.loads(matcher.group(1))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    code = data.get("error_code")
    return str(code) if code is not None else None


def is_permission_denied(err: BaseException) -> bool:
    """True pour un vrai refus de droit Freebox OS (`insufficient_rights`).

    freebox_api lève `InsufficientPermissionsError` (sous-classe de
    `HttpRequestError`) pour `error_code == insufficient_rights`. On accepte
    aussi le code / les mots-clés dans le message pour les versions anciennes.
    """
    if isinstance(err, InsufficientPermissionsError):
        return True
    if api_error_code(err) == "insufficient_rights":
        return True
    message = str(err).lower()
    return (
        "insufficient_rights" in message
        or "missing_right" in message
        or "access denied" in message
    )
