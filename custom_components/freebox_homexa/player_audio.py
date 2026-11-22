"""Fichier audio du Player : MP4 signé, cache court, sons embarqués.

Home Assistant récupère l'adresse demandée, l'emballe en MP4 (AAC et image
noire) pour que le Player propose le lecteur multimédia, puis la sert sur une
vue de courte durée. Les deux sons d'alarme sont synthétisés (aucun
enregistrement tiers).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
import tempfile
import time
from collections import OrderedDict
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote, urlsplit

import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLAYER_AUDIO_MARKER = "freebox_homexa/player_audio"
PLAYER_AUDIO_TITLE = "Son du Player"
BUNDLED_SOUNDS: dict[str, str] = {
    "alarme_sirene": "alarme_sirene.mp3",
    "alarme_bip": "alarme_bip.mp3",
}
SOUND_TITLES: dict[str, str] = {
    "alarme_sirene": "Sirène",
    "alarme_bip": "Bip d'alarme",
}
_SCHEME_PREFIXES = (
    "freebox_homexa://sound/",
    "media-source://freebox_homexa/sound/",
)
_CACHE_LIMIT = 8
_REUSE_SECONDS = 240.0
_MAX_BYTES = 16 * 1024 * 1024
_AUDIO_TTL = timedelta(minutes=5)
_FILES: OrderedDict[str, bytes] = OrderedDict()
_ISSUED: OrderedDict[str, tuple[float, str]] = OrderedDict()
_TOKENS: dict[str, str] = {}


def clear_player_audio_cache() -> None:
    """Oublie les MP3 préparés. Les tests s'en servent, pas l'interface."""
    _FILES.clear()
    _ISSUED.clear()
    _TOKENS.clear()


def bundled_sound_name(media_id: str) -> str | None:
    """Nom du son embarqué, ou None si l'identifiant n'est pas un son.

    Un préfixe ``freebox_homexa://sound/`` inconnu est refusé.
    """
    if not isinstance(media_id, str):
        return None
    text = media_id.strip()
    prefix = next((item for item in _SCHEME_PREFIXES if text.startswith(item)), "")
    if not prefix:
        return None
    name = text[len(prefix):].split("?", 1)[0].strip("/")
    if name.endswith(".mp3"):
        name = name[:-4]
    if name in BUNDLED_SOUNDS:
        return name
    raise HomeAssistantError(
        translation_domain=DOMAIN, translation_key="player_audio_refused"
    )


def _safe_code(err: BaseException) -> str:
    from .voicemail import stored_error

    code = stored_error(err)
    if "://" in code or "/" in code or len(code) > 64:
        return "error"
    return code


def _prepare_failed(err: BaseException) -> HomeAssistantError:
    _LOGGER.warning("Préparation du son impossible (code=%s)", _safe_code(err))
    return HomeAssistantError(
        translation_domain=DOMAIN, translation_key="player_audio_prepare"
    )


def _looks_like_mp4(payload: bytes) -> bool:
    return len(payload) > 11 and payload[4:8] == b"ftyp"


async def async_audio_to_mp4(hass: HomeAssistant, audio: bytes) -> bytes:
    """Emballe l'audio en MP4 AAC avec une image noire.

    ``control/open`` ne connaît que ``url`` et ``type``. Un MP4 ``video/mp4``
    préselectionne le lecteur multimédia ; un MP3 ouvre d'abord le navigateur.
    """
    from .voicemail_audio import _ffmpeg_binary, _input_format

    destination = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    destination.close()
    path = destination.name
    try:
        try:
            process = await asyncio.create_subprocess_exec(
                _ffmpeg_binary(hass),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                *_input_format(audio),
                "-i",
                "pipe:0",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=64x64:r=1",
                "-shortest",
                "-map",
                "1:v:0",
                "-map",
                "0:a:0",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-tune",
                "stillimage",
                "-preset",
                "ultrafast",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-ac",
                "1",
                "-movflags",
                "+faststart",
                "-f",
                "mp4",
                path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate(audio)
        except OSError as err:
            raise _prepare_failed(err) from err
        if process.returncode != 0:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="player_audio_prepare"
            )
        try:
            body = Path(path).read_bytes()
        except OSError as err:
            raise _prepare_failed(err) from err
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if not body:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="player_audio_prepare"
        )
    return body


def _read_sound(name: str) -> bytes:
    filename = BUNDLED_SOUNDS.get(name, "")
    if not filename:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="player_audio_refused"
        )
    path = Path(__file__).parent / "sounds" / filename
    try:
        payload = path.read_bytes()
    except OSError as err:
        raise _prepare_failed(err) from err
    if not payload or len(payload) > 100 * 1024:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="player_audio_prepare"
        )
    return payload


def _remember(key: str, body: bytes) -> str:
    """Garde au plus huit MP3. Le même fichier réutilise son jeton quelques minutes."""
    _FILES[key] = body
    _FILES.move_to_end(key)
    while len(_FILES) > _CACHE_LIMIT:
        dropped, _old = _FILES.popitem(last=False)
        issued = _ISSUED.pop(dropped, None)
        if issued is not None:
            _TOKENS.pop(issued[1], None)
    now = time.monotonic()
    current = _ISSUED.get(key)
    if current is not None and now - current[0] < _REUSE_SECONDS and current[1] in _TOKENS:
        _ISSUED.move_to_end(key)
        return current[1]
    if current is not None:
        _TOKENS.pop(current[1], None)
    token = secrets.token_urlsafe(18)
    _ISSUED[key] = (now, token)
    _ISSUED.move_to_end(key)
    _TOKENS[token] = key
    return token


def _body_for_token(token: str) -> bytes | None:
    key = _TOKENS.get(token)
    if not isinstance(key, str):
        return None
    body = _FILES.get(key)
    if not isinstance(body, bytes) or not body:
        return None
    return body


def _signed_url(hass: HomeAssistant, token: str) -> str:
    path = f"/api/freebox_homexa/player_audio/{quote(token, safe='')}"
    signed = async_sign_path(hass, path, _AUDIO_TTL)
    try:
        base = get_url(hass, prefer_external=False)
    except NoURLAvailableError as err:
        raise _prepare_failed(err) from err
    return f"{base.rstrip('/')}{signed}"


async def async_host_bytes(hass: HomeAssistant, key: str, payload: bytes) -> str:
    """Sert un MP4. Un MP3, un WAV ou un AU est emballé, un MP4 est gardé."""
    body = payload if _looks_like_mp4(payload) else await async_audio_to_mp4(hass, payload)
    if not body or len(body) > _MAX_BYTES:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="player_audio_prepare"
        )
    return _signed_url(hass, _remember(key, body))


async def async_host_sound(hass: HomeAssistant, name: str) -> str:
    """URL signée d'un son embarqué."""
    payload = _read_sound(name)
    try:
        return await async_host_bytes(hass, f"sound:{name}", payload)
    except HomeAssistantError:
        raise
    except Exception as err:
        raise _prepare_failed(err) from err


async def _fetch_audio(hass: HomeAssistant, url: str) -> bytes:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise OSError("scheme")
    session = async_get_clientsession(hass)
    timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=10)
    async with session.get(url, timeout=timeout) as response:
        if response.status != 200:
            raise OSError("status")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.content.iter_chunked(65536):
            size += len(chunk)
            if size > _MAX_BYTES:
                raise OSError("size")
            chunks.append(chunk)
    body = b"".join(chunks)
    if not body:
        raise OSError("empty")
    return body


async def async_host_http_audio(hass: HomeAssistant, url: str) -> str | None:
    """Prépare l'adresse. None : l'appelant envoie l'adresse d'origine."""
    try:
        payload = await _fetch_audio(hass, url)
        key = hashlib.sha256(url.encode()).hexdigest()
        return await async_host_bytes(hass, key, payload)
    except Exception as err:
        _LOGGER.warning(
            "Préparation du fichier audio impossible (code=%s)", _safe_code(err)
        )
        return None


class PlayerAudioView(HomeAssistantView):
    """MP4 authentifié (session ou URL signée de courte durée)."""

    url = "/api/freebox_homexa/player_audio/{token}"
    name = "api:freebox_homexa:player_audio"
    requires_auth = True

    async def get(self, request: web.Request, token: str) -> web.Response:
        body = _body_for_token(token)
        if body is None:
            return web.Response(status=404, text="Média introuvable")
        return web.Response(
            body=body,
            status=200,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(body)),
                "Cache-Control": "no-store",
                "Content-Disposition": 'inline; filename="audio.mp4"',
            },
        )


def async_register_player_audio_view(hass: HomeAssistant) -> None:
    http = getattr(hass, "http", None)
    if http is None:
        return
    try:
        http.register_view(PlayerAudioView())
    except Exception:
        _LOGGER.debug("Vue audio du Player déjà enregistrée")
