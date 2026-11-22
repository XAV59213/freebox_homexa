"""Lecture audio de la messagerie : vue HTTP signée et conversion MP3.

Le fichier Freebox est souvent un WAV A-law/µ-law ou un AU ``.snd``, illisible
dans beaucoup de navigateurs. ffmpeg (déjà au manifeste) le transcode en MP3
pour la carte, la source média et chaque lecteur. Alexa / Echo doit en plus
pouvoir joindre une URL HTTPS publique.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING
from urllib.parse import quote

from aiohttp import web
from homeassistant.components.ffmpeg import DATA_FFMPEG
from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DOMAIN
from .voicemail import (
    async_voicemail_audio,
    resolve_voicemail_token,
    stored_error,
    validated_voicemail_id,
)

if TYPE_CHECKING:
    from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

_AUDIO_TTL = timedelta(minutes=5)
_MP3_PLATFORMS = frozenset({"alexa", "alexa_media", "alexa_devices"})


def player_needs_mp3(hass: HomeAssistant, entity_id: str) -> bool:
    """Echo et Alexa doivent joindre une URL publique. Le fichier est un MP3 pour tous."""
    row = er.async_get(hass).async_get(entity_id)
    platform = row.platform if row is not None else ""
    if platform in _MP3_PLATFORMS or platform.startswith("alexa"):
        return True
    label = entity_id.lower()
    state = hass.states.get(entity_id)
    if state is not None:
        name = state.attributes.get("friendly_name")
        if isinstance(name, str):
            label = f"{label} {name.lower()}"
    return "echo" in label or "alexa" in label


def signed_voicemail_path(
    hass: HomeAssistant, entry_id: str, message_id: str, *, mp3: bool
) -> str:
    """URL signée du jeton, jamais du nom de fichier Freebox."""
    public_id = validated_voicemail_id(message_id)
    router = _loaded_router(hass, entry_id)
    if router is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="voicemail_invalid_id"
        )
    resolve_voicemail_token(router, public_id)
    path = (
        f"/api/freebox_homexa/voicemail/{quote(entry_id, safe='')}/"
        f"{quote(public_id, safe='')}"
    )
    path += "?codec=mp3" if mp3 else "?codec=wav"
    return async_sign_path(hass, path, _AUDIO_TTL)


def absolute_voicemail_url(hass: HomeAssistant, signed_path: str, *, external: bool) -> str:
    try:
        if external:
            base = get_url(hass, allow_internal=False, allow_external=True)
        else:
            base = get_url(hass, allow_external=False)
    except NoURLAvailableError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="voicemail_public_url",
        ) from err
    return f"{base.rstrip('/')}{signed_path}"


def _ffmpeg_binary(hass: HomeAssistant) -> str:
    manager = hass.data.get(DATA_FFMPEG)
    binary = getattr(manager, "binary", None)
    if not isinstance(binary, str) or not binary:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_audio"
        )
    return binary


def audio_magic(payload: bytes | None) -> str:
    """``RIFF``, ``.snd`` ou ``other``. Jamais le contenu ni un identifiant."""
    if payload is None:
        return "other"
    if payload.startswith(b"RIFF"):
        return "RIFF"
    if payload.startswith(b".snd"):
        return ".snd"
    return "other"


def _input_format(payload: bytes) -> list[str]:
    """Le tube n'est pas cherchable : le conteneur est donné à ffmpeg."""
    if payload.startswith(b"RIFF"):
        return ["-f", "wav"]
    if payload.startswith(b".snd"):
        return ["-f", "au"]
    return []


def _log_audio_failure(err: BaseException | None, payload: bytes | None, *, code: str | None = None) -> None:
    label = code if code else stored_error(err if err is not None else RuntimeError("audio"))
    status = getattr(err, "status", None) if err is not None else None
    if isinstance(status, int) and not isinstance(status, bool):
        label = f"HTTP {status} {label}"
    _LOGGER.warning("Lecture du message vocal impossible (%s, %s)", label, audio_magic(payload))


async def async_wav_to_mp3(hass: HomeAssistant, wav: bytes) -> bytes:
    """Convertit un WAV A-law/µ-law ou un AU ``.snd`` avec le ffmpeg de Home Assistant."""
    try:
        process = await asyncio.create_subprocess_exec(
            _ffmpeg_binary(hass),
            "-hide_banner",
            "-loglevel",
            "error",
            *_input_format(wav),
            "-i",
            "pipe:0",
            "-f",
            "mp3",
            "-acodec",
            "libmp3lame",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate(wav)
    except OSError as err:
        _log_audio_failure(err, wav)
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_audio"
        ) from err
    if process.returncode != 0 or not stdout:
        _log_audio_failure(None, wav, code="ffmpeg")
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_audio"
        )
    return stdout


def _loaded_router(hass: HomeAssistant, entry_id: str) -> FreeboxRouter | None:
    from .router import FreeboxRouter

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != entry_id:
            continue
        router = getattr(entry, "runtime_data", None)
        if isinstance(router, FreeboxRouter):
            return router
    return None


class VoicemailAudioView(HomeAssistantView):
    """Flux audio authentifié (session ou URL signée de courte durée)."""

    url = "/api/freebox_homexa/voicemail/{entry_id}/{message_id:.+}"
    name = "api:freebox_homexa:voicemail"
    requires_auth = True

    async def get(
        self, request: web.Request, entry_id: str, message_id: str
    ) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        router = _loaded_router(hass, entry_id)
        if router is None:
            return web.Response(status=404, text="Messagerie vocale introuvable")
        payload: bytes | None = None
        try:
            payload = await async_voicemail_audio(router, message_id)
            wants_wav = request.query.get("codec") == "wav"
            body = payload if wants_wav else await async_wav_to_mp3(hass, payload)
        except ServiceValidationError:
            return web.Response(status=404, text="Message vocal introuvable")
        except HomeAssistantError as err:
            if payload is None:
                _log_audio_failure(err, None)
            return web.Response(status=403, text="Messagerie vocale indisponible")
        except Exception as err:
            _log_audio_failure(err, payload)
            return web.Response(status=502, text="Messagerie vocale indisponible")
        content_type = "audio/wav" if request.query.get("codec") == "wav" else "audio/mpeg"
        extension = "wav" if content_type == "audio/wav" else "mp3"
        return web.Response(
            body=body,
            status=200,
            headers={
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
                "Cache-Control": "no-store",
                "Content-Disposition": f'inline; filename="message.{extension}"',
            },
        )


def async_register_voicemail_view(hass: HomeAssistant) -> None:
    http = getattr(hass, "http", None)
    if http is None:
        return
    try:
        http.register_view(VoicemailAudioView())
    except Exception:
        _LOGGER.debug("Vue messagerie vocale déjà enregistrée")


async def async_play_on_player(
    hass: HomeAssistant, router: FreeboxRouter, message_id: str, entity_id: str
) -> None:
    """Joue le message sur un media_player, puis le marque lu."""
    from .voicemail import async_mark_voicemail_read

    if not isinstance(entity_id, str) or not entity_id.startswith("media_player."):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="voicemail_player"
        )
    if hass.states.get(entity_id) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="voicemail_player"
        )
    external = player_needs_mp3(hass, entity_id)
    signed = signed_voicemail_path(hass, router.entry_id, message_id, mp3=True)
    url = absolute_voicemail_url(hass, signed, external=external)
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": entity_id,
            "media_content_id": url,
            "media_content_type": "audio/mpeg",
        },
        blocking=True,
    )
    await async_mark_voicemail_read(router, message_id)
