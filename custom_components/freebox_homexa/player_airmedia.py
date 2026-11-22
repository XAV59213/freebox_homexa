"""Lecture HTTP d'un fichier audio sur le Player Freebox.

Même chemin que la messagerie : AirMedia ``action=start`` en type ``video``
(l'audio direct répond souvent ``unimplemented``), puis ``control/open``.
Le succès se voit au changement d'état du Player, pas seulement à l'acceptation
de la requête.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

if TYPE_CHECKING:
    from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

_AUDIO_SUFFIXES = (".mp3", ".aac", ".ogg", ".wav", ".flac")
VOICEMAIL_MARKER = "freebox_homexa/voicemail"
VOICEMAIL_TITLE = "Message vocal Freebox"
_PREVIOUS_SOURCE: dict[str, str] = {}


class PlayerPlaybackError(Exception):
    """La lecture n'a pas démarré. ``kind`` vaut ``refused`` ou ``silent``."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(kind)


def is_http_audio(media_type: str, media_id: str) -> bool:
    """URL http(s) à envoyer par AirMedia.

    ``audio/*`` et ``music`` comptent. Sans type, seules les extensions
    ``.mp3``, ``.aac``, ``.ogg``, ``.wav`` et ``.flac`` comptent.
    """
    if not isinstance(media_id, str) or not media_id.lower().startswith(("http://", "https://")):
        return False
    kind = media_type.strip().lower() if isinstance(media_type, str) else ""
    if kind == "music" or kind.startswith("audio/"):
        return True
    if kind:
        return False
    return urlsplit(media_id).path.lower().endswith(_AUDIO_SUFFIXES)


def _error_code(err: BaseException) -> str:
    from .voicemail import stored_error

    return stored_error(err)


def _player_view(status: object, marker: str) -> tuple[str, str, bool] | None:
    """Lecture, application, et si l'URL demandée est au premier plan."""
    if not isinstance(status, dict):
        return None
    foreground = status.get("foreground_app")
    app = ""
    parts = [
        status.get("uri"),
        status.get("app"),
        status.get("source"),
        status.get("title"),
    ]
    if isinstance(foreground, dict):
        app = str(foreground.get("package") or "")
        parts.append(foreground.get("cur_url"))
    blob = " ".join(str(part) for part in parts if isinstance(part, str)).lower()
    playback = str(
        status.get("playback_state") or status.get("state") or status.get("playback") or ""
    ).lower()
    needle = marker.lower()
    return playback, app.lower(), bool(needle) and needle in blob


def _player_started(
    before: tuple[str, str, bool] | None,
    after: tuple[str, str, bool] | None,
) -> bool:
    if after is None:
        return False
    if after[2]:
        return True
    if before is None:
        return after[0] in {"playing", "play"}
    if after == before:
        return False
    if after[0] in {"playing", "play"} and after[1] != before[1]:
        return True
    return False


async def _player_post(
    router: FreeboxRouter, player_id: int, version: str, suffix: str, payload: dict[str, str]
) -> None:
    access = router._api.player._access
    action = getattr(access, "post", None)
    if not callable(action):
        raise OSError("unavailable")
    await action(f"player/{player_id}/api/{version}/{suffix}", payload)


async def _airmedia_receivers(router: FreeboxRouter) -> list[str]:
    api = getattr(router._api, "airmedia", None)
    getter = getattr(api, "get_airmedia_receivers", None)
    if not callable(getter):
        return []
    try:
        raw = await getter()
    except Exception as err:
        _LOGGER.warning("Liste AirMedia indisponible (code=%s)", _error_code(err))
        return []
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        caps = item.get("capabilities")
        if isinstance(caps, dict) and caps.get("audio") is False and caps.get("video") is False:
            continue
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    names.sort(key=lambda value: (0 if "player" in value.lower() else 1, value.lower()))
    return names


def remember_player_source(key: str, source: object) -> None:
    """Mémorise une source nommée, jamais une adresse."""
    if not isinstance(key, str) or not key:
        return
    if not isinstance(source, str):
        return
    cleaned = source.strip()
    if not cleaned or "://" in cleaned or VOICEMAIL_MARKER in cleaned:
        return
    _PREVIOUS_SOURCE[key] = cleaned


def take_player_source(key: str) -> str:
    if not isinstance(key, str) or not key:
        return ""
    return _PREVIOUS_SOURCE.pop(key, "")


async def _airmedia_command(router: FreeboxRouter, action_name: str, url: str) -> bool:
    api = getattr(router._api, "airmedia", None)
    sender = getattr(api, "send_airmedia", None)
    if not callable(sender):
        return False
    names = await _airmedia_receivers(router)
    if not names:
        return False
    quoted = quote(names[0], safe="")
    for media_type in ("video", "audio"):
        body: dict[str, str] = {"action": action_name, "media_type": media_type}
        if url:
            body["media"] = url
        try:
            await sender(quoted, body)
            return True
        except Exception as err:
            _LOGGER.warning("AirMedia %s refusé (code=%s)", media_type, _error_code(err))
    return False


async def _airmedia_start(router: FreeboxRouter, url: str) -> bool:
    """Envoie l'URL HTTP. ``audio`` est souvent ``unimplemented`` : ``video`` lit le MP3."""
    return await _airmedia_command(router, "start", url)


async def async_stop_player_audio(router: FreeboxRouter) -> None:
    """Arrête AirMedia sans renvoyer l'adresse du message."""
    await _airmedia_command(router, "stop", "")


async def async_open_player_audio(
    router: FreeboxRouter,
    player_id: int,
    version: str,
    url: str,
    *,
    marker: str,
) -> None:
    """Joue l'URL et vérifie que l'état du Player change.

    AirMedia part en ``video``. ``control/open`` avec ``audio/mpeg``, puis sans
    type, est le second essai. Sans changement d'état, lève ``PlayerPlaybackError``.
    """
    from .player_status import async_read_player_status

    before_status, version = await async_read_player_status(router, player_id, version)
    before = _player_view(before_status, marker)

    async def _heard() -> bool:
        for delay in (1, 1):
            await asyncio.sleep(delay)
            status, _version = await async_read_player_status(router, player_id, version)
            if _player_started(before, _player_view(status, marker)):
                return True
        return False

    if await _airmedia_start(router, url) and await _heard():
        return
    try:
        await _player_post(router, player_id, version, "control/mediactrl", {"cmd": "stop"})
    except Exception:
        _LOGGER.debug("Arrêt du média en cours ignoré avant la lecture audio")
    opened = False
    for mime in ("audio/mpeg", ""):
        body: dict[str, str] = {"url": url}
        if mime:
            body["type"] = mime
        try:
            await _player_post(router, player_id, version, "control/open", body)
            opened = True
        except Exception as err:
            raw_status = getattr(err, "status", None)
            shown = (
                raw_status
                if isinstance(raw_status, int) and not isinstance(raw_status, bool)
                else "-"
            )
            _LOGGER.warning(
                "Ouverture audio du Player refusée (statut=%s, code=%s)",
                shown,
                _error_code(err),
            )
            continue
        for delay in (1, 1):
            await asyncio.sleep(delay)
            status, version = await async_read_player_status(router, player_id, version)
            if _player_started(before, _player_view(status, marker)):
                return
    if not opened:
        raise PlayerPlaybackError("refused")
    _LOGGER.warning("Le Player n'a pas changé d'état après l'ouverture audio")
    raise PlayerPlaybackError("silent")
