"""Télécommande réseau du Freebox Player (partagée par l'entité remote, les boutons et l'action).

Les touches passent par `freebox_api` (`router._api.remote.send_key`), comme l'entité
« Télécommande » : l'API joint le Player (`Freebox-Player.local`) avec le code
télécommande réseau du Player. Le Freebox Server (`entry.data[host]`) n'a pas de
`/pub/remote_control` : l'ancienne action `freebox_homexa.remote` l'appelait à tort.
"""

from __future__ import annotations

import logging
from typing import Any

from .const import DOMAIN, option_remote_code

_LOGGER = logging.getLogger(__name__)

VALID_COMMANDS = {
    "red", "green", "blue", "yellow", "power", "list", "tv", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "back", "0", "swap", "info", "epg", "mail", "media", "help", "options", "pip", "vol_inc", "vol_dec",
    "ok", "up", "right", "down", "left", "prgm_inc", "prgm_dec", "mute", "home", "rec", "bwd", "prev",
    "play", "fwd", "next"
}


def parse_keys(value: Any) -> list[str]:
    """« power, 1,2 » ou ["power", "1"] -> ["power", "1", "2"] (minuscules, sans vide)."""
    items = value if isinstance(value, (list, tuple)) else str(value or "").split(",")
    keys: list[str] = []
    for item in items:
        keys.extend(part.strip().lower() for part in str(item).split(",") if part.strip())
    return keys


def player_id_from_identifiers(identifiers: Any) -> int | None:
    """Id du Player d'après les identifiants d'un appareil Homexa (« player_<id> »)."""
    for ident in identifiers or ():
        if len(ident) >= 2 and ident[0] == DOMAIN and str(ident[1]).startswith("player_"):
            raw = str(ident[1])[len("player_"):]
            try:
                return int(raw)
            except ValueError:
                return None
    return None


def resolve_remote_code(
    entry: Any, player_id: int | None, players: list[dict[str, Any]]
) -> tuple[str | None, int | None]:
    """Code télécommande et Player visé, avec la même règle que l'entité « Télécommande ».

    - Player donné : son code, sinon le code commun ;
    - aucun Player donné et un seul Player : celui-ci ;
    - aucun Player donné et plusieurs : le code commun (comportement historique).
    """
    if player_id is None and len(players) == 1 and players[0].get("id") is not None:
        player_id = players[0]["id"]
    return option_remote_code(entry, player_id), player_id


async def async_send_player_keys(
    router: Any,
    remote_code: str,
    keys: list[str],
    long_press: bool = False,
    repeat: int = 0,
) -> list[tuple[str, Exception]]:
    """Envoie les touches au Player ; renvoie les échecs (touche, erreur).

    Une réponse non confirmée par la Player (`send_key` -> False) est seulement
    journalisée en debug : l'entité « Télécommande » fonctionne ainsi depuis toujours.
    """
    failures: list[tuple[str, Exception]] = []
    for key in keys:
        try:
            accepted = await router._api.remote.send_key(
                code=str(remote_code), key=key, long_press=long_press, repeat=repeat
            )
        except Exception as err:  # noqa: BLE001 — remonté à l'appelant
            failures.append((key, err))
            continue
        if accepted is False:
            _LOGGER.debug("Touche %s : réponse du Player non confirmée", key)
    return failures
