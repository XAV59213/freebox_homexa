"""Télécommande réseau du Freebox Player (partagée par l'entité remote, les boutons et l'action).

Les touches passent par `freebox_api` (`router._api.remote.send_key`), comme l'entité
« Télécommande » : l'API joint le Player (`Freebox-Player.local`) avec le code
télécommande réseau du Player. Le Freebox Server (`entry.data[host]`) n'a pas de
`/pub/remote_control` : l'ancienne action `freebox_homexa.remote` l'appelait à tort.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError

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

    False means unconfirmed, not proof of physical failure: expose a distinct
    translated error and never automatically retry a potentially accepted key.
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
            failures.append((key, HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_unconfirmed"
            )))
    return failures


# Délais (s) avant rechargement si un Player sans API devient contrôlable plus tard.
PLAYER_API_RETRY_DELAYS = (120, 300, 600)


def player_display_name(player: dict[str, Any]) -> str:
    """Nom affiché d'un Player (device_name / name / id / générique)."""
    name = player.get("device_name") or player.get("name")
    if name:
        return str(name)
    if player.get("id") is not None:
        return f"Freebox Player {player['id']}"
    return "Freebox Player"


def player_api_ready(player: Any) -> bool:
    """True si l'API Player Freebox OS peut contrôler cet appareil.

    L'API `/player/` omet souvent `id` quand `api_available` vaut False (cas
    documenté pour le Player POP / stb_v8 / fbx8am). Sans `id`, freebox-api ne
    peut pas appeler status/volume/open (`players[0]["id"]` planterait). On
    n'invente pas de contrôle alternatif : Free ne publie pas d'API locale pour
    ces modèles ; Android TV Remote reste hors périmètre Homexa.
    """
    if not isinstance(player, dict):
        return False
    if player.get("id") is None:
        return False
    # Clé absente = anciens firmwares qui exposaient déjà l'id : on accepte.
    if player.get("api_available") is False:
        return False
    return True


def player_skip_message(player: dict[str, Any], context: str = "") -> str:
    """Message actionnable quand un Player n'est pas contrôlable via Freebox OS."""
    name = player_display_name(player)
    suffix = f" ({context})" if context else ""
    api_available = player.get("api_available")
    has_id = player.get("id") is not None
    model = player.get("device_model") or player.get("stb_type") or "?"
    if api_available is False or not has_id:
        return (
            f"Player « {name} » ignoré{suffix} : son API Freebox OS est indisponible "
            f"(api_available={api_available!r}, "
            f"id={'présent' if has_id else 'absent'}, "
            f"modèle={model}). Vérifier que le Player est allumé et joignable sur le "
            f"réseau. Sur Player POP / Mini 4K (Android TV), Free n'expose souvent "
            f"aucune API locale : utiliser Android TV Remote, ou patienter — Homexa "
            f"réessaiera automatiquement si l'API devient disponible."
        )
    return f"Player « {name} » ignoré{suffix} : charge utile inattendue : {player}"


def filter_ready_players(
    players: list[Any],
    *,
    logger: logging.Logger | None = None,
    context: str = "",
    log_skipped: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Sépare les Players contrôlables des autres."""
    log = logger or _LOGGER
    ready: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for player in players or []:
        if player_api_ready(player):
            ready.append(player)
            continue
        if isinstance(player, dict):
            skipped.append(player)
            if log_skipped:
                log.warning("%s", player_skip_message(player, context))
        elif log_skipped:
            log.warning(
                "Player Freebox ignoré%s : charge utile non dict : %r",
                f" ({context})" if context else "",
                player,
            )
    return ready, skipped


async def async_schedule_player_api_retry(hass: Any, entry: Any, router: Any) -> None:
    """Recharge l'entrée si un Player sans API devient contrôlable plus tard.

    Utile quand le Player était éteint / injoignable au démarrage (`api_available=
    False`, pas d'`id`) puis se met à exposer l'API. On ne crée pas d'entité sans
    `id` : Freebox OS ne fournit alors aucun endpoint de contrôle.
    """
    from homeassistant.helpers.event import async_call_later

    if getattr(router, "_player_api_retry_scheduled", False):
        return
    router._player_api_retry_scheduled = True
    attempt = {"n": 0}

    async def _attempt(_now: Any = None) -> None:
        if getattr(router, "closing", False):
            return
        try:
            players = list(await router._api.player.get_players() or [])
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Nouvelle tentative Player impossible : %s", err)
            return
        ready = [p for p in players if player_api_ready(p)]
        known = set(getattr(router, "player_identifiers", ()) or ())
        new_ready = [p for p in ready if f"player_{p['id']}" not in known]
        if new_ready:
            _LOGGER.info(
                "API Player devenue disponible pour %s — rechargement de l'intégration",
                ", ".join(player_display_name(p) for p in new_ready),
            )
            await hass.config_entries.async_reload(entry.entry_id)
            return
        attempt["n"] += 1
        if attempt["n"] >= len(PLAYER_API_RETRY_DELAYS):
            _LOGGER.debug(
                "Aucune API Player contrôlable après %s tentatives — stop",
                attempt["n"],
            )
            return
        delay = PLAYER_API_RETRY_DELAYS[attempt["n"]]
        # Passer la coroutine directement : HassJob la planifie sur la boucle
        # d'événements. Un lambda + hass.async_create_task depuis un SyncWorker
        # déclenche RuntimeError (thread-safety HA).
        entry.async_on_unload(async_call_later(hass, delay, _attempt))

    entry.async_on_unload(
        async_call_later(hass, PLAYER_API_RETRY_DELAYS[0], _attempt)
    )
