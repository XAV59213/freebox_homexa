"""Lecture HTTP d'un fichier audio sur le Player Freebox.

Même chemin que la messagerie : AirMedia ``action=start`` en type ``video``
(le schéma freebox-api ne connaît que photo et video ; l'audio répond
``unimplemented``), avec ``position`` 0, puis ``control/open``.
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
_START_POLLS = (1, 1, 2, 2)
_VIDEO_RETRY = frozenset({"http", "req_in_progress"})
_SERVER_RECEIVER = "freebox server"
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


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _player_view(status: object, marker: str) -> tuple[str, str, str, bool] | None:
    """Lecture, application, média courant, et si l'URL demandée est au premier plan."""
    if not isinstance(status, dict):
        return None
    foreground = status.get("foreground_app")
    package = ""
    current_url = ""
    if isinstance(foreground, dict):
        package = _text(foreground.get("package"))
        current_url = _text(foreground.get("cur_url"))
    playback = str(
        status.get("playback_state") or status.get("state") or status.get("playback") or ""
    ).lower()
    media = "\n".join(
        (
            package,
            current_url,
            _text(status.get("uri")),
            _text(status.get("source")),
        )
    ).lower()
    blob = " ".join(
        part
        for part in (
            _text(status.get("uri")),
            _text(status.get("app")),
            _text(status.get("source")),
            _text(status.get("title")),
            package,
            current_url,
        )
        if part
    ).lower()
    needle = marker.lower()
    return playback, package.lower(), media, bool(needle) and needle in blob


def _player_started(
    before: tuple[str, str, str, bool] | None,
    after: tuple[str, str, str, bool] | None,
) -> bool:
    if after is None:
        return False
    if after[3]:
        return True
    if before is None:
        return after[0] in {"playing", "play"}
    if after[1] != before[1] or after[2] != before[2]:
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


def _receiver_rank(name: str, device_name: str) -> tuple[int, int]:
    label = name.casefold()
    wanted = device_name.strip().casefold()
    if wanted and label == wanted:
        return (0, -len(label))
    if wanted and (label in wanted or wanted in label):
        return (1, -len(label))
    if "player" in label:
        return (2, -len(label))
    return (3, -len(label))


async def _select_receiver(router: FreeboxRouter, device_name: str) -> str:
    """Récepteur vidéo du Player. Jamais le Freebox Server, jamais une URL au journal."""
    api = getattr(router._api, "airmedia", None)
    getter = getattr(api, "get_airmedia_receivers", None)
    if not callable(getter):
        _LOGGER.debug("AirMedia : 0 récepteur(s), vidéo=[], protégé=[]")
        return ""
    try:
        raw = await getter()
    except Exception as err:
        _LOGGER.warning("Liste AirMedia indisponible (code=%s)", _error_code(err))
        return ""
    if not isinstance(raw, list):
        _LOGGER.debug("AirMedia : 0 récepteur(s), vidéo=[], protégé=[]")
        return ""
    video_flags: list[bool] = []
    protected_flags: list[bool] = []
    names: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        label = name.strip()
        caps = item.get("capabilities")
        video = isinstance(caps, dict) and caps.get("video") is True
        video_flags.append(video)
        protected_flags.append(item.get("password_protected") is True)
        if label.casefold() == _SERVER_RECEIVER or not video:
            continue
        names.append(label)
    _LOGGER.debug(
        "AirMedia : %s récepteur(s), vidéo=%s, protégé=%s",
        len(video_flags),
        video_flags,
        protected_flags,
    )
    if not names:
        return ""
    return min(names, key=lambda value: _receiver_rank(value, device_name))


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


async def _send_airmedia(
    router: FreeboxRouter, receiver: str, body: dict[str, str | int]
) -> None:
    api = getattr(router._api, "airmedia", None)
    sender = getattr(api, "send_airmedia", None)
    if not callable(sender) or not receiver:
        raise OSError("unavailable")
    await sender(receiver, body)


async def _airmedia_start(router: FreeboxRouter, url: str, device_name: str) -> bool:
    """Envoie l'URL en ``video``. ``http`` et ``req_in_progress`` sont réessayés une fois."""
    name = await _select_receiver(router, device_name)
    if not name:
        return False
    receiver = quote(name, safe="")
    body: dict[str, str | int] = {
        "action": "start",
        "media_type": "video",
        "media": url,
        "position": 0,
    }
    try:
        await _send_airmedia(router, receiver, body)
        return True
    except Exception as err:
        code = _error_code(err)
        _LOGGER.warning("AirMedia video refusé (code=%s)", code)
        if code not in _VIDEO_RETRY:
            return False
    await asyncio.sleep(1)
    try:
        await _send_airmedia(router, receiver, body)
        return True
    except Exception as err:
        _LOGGER.warning("AirMedia video refusé (code=%s)", _error_code(err))
        return False


async def async_stop_player_audio(router: FreeboxRouter) -> None:
    """Arrête AirMedia sans renvoyer l'adresse du message."""
    name = await _select_receiver(router, "")
    if not name:
        return
    try:
        await _send_airmedia(
            router,
            quote(name, safe=""),
            {"action": "stop", "media_type": "video"},
        )
    except Exception as err:
        _LOGGER.warning("AirMedia video refusé (code=%s)", _error_code(err))


async def _wait_until_started(
    router: FreeboxRouter,
    player_id: int,
    version: str,
    before: tuple[str, str, str, bool] | None,
    marker: str,
) -> tuple[bool, str]:
    from .player_status import async_read_player_status

    for delay in _START_POLLS:
        await asyncio.sleep(delay)
        status, version = await async_read_player_status(router, player_id, version)
        if _player_started(before, _player_view(status, marker)):
            return True, version
    return False, version


async def async_open_player_audio(
    router: FreeboxRouter,
    player_id: int,
    version: str,
    url: str,
    *,
    marker: str,
    device_name: str = "",
) -> None:
    """Joue l'URL et vérifie que l'état du Player change.

    AirMedia part en ``video`` (``position`` 0). Un code ``http`` ou
    ``req_in_progress`` est réessayé une fois. ``control/open`` avec
    ``audio/mpeg``, puis sans type, est le second essai. Sans changement
    d'application ou de média, lève ``PlayerPlaybackError``.
    """
    from .player_status import async_read_player_status

    before_status, version = await async_read_player_status(router, player_id, version)
    before = _player_view(before_status, marker)

    if await _airmedia_start(router, url, device_name):
        heard, version = await _wait_until_started(
            router, player_id, version, before, marker
        )
        if heard:
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
        heard, version = await _wait_until_started(
            router, player_id, version, before, marker
        )
        if heard:
            return
    if not opened:
        raise PlayerPlaybackError("refused")
    _LOGGER.warning("Le Player n'a pas changé d'état après l'ouverture audio")
    raise PlayerPlaybackError("silent")
