"""Lecture audio de la messagerie : vue HTTP signée et conversion MP3.

ffmpeg est déjà une dépendance du manifeste. Alexa / Echo n'est pris en charge
qu'au mieux : le lecteur doit pouvoir joindre une URL HTTPS publique.
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
from .voicemail import async_voicemail_audio, resolve_voicemail_token, validated_voicemail_id

if TYPE_CHECKING:
    from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)

_AUDIO_TTL = timedelta(minutes=5)
_CHUNK = 65536
_MP3_PLATFORMS = frozenset({"alexa", "alexa_media", "alexa_devices"})


def player_needs_mp3(hass: HomeAssistant, entity_id: str) -> bool:
    """Echo et Alexa lisent un MP3 joignable, pas le WAV interne."""
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
    if mp3:
        path += "?codec=mp3"
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


async def async_wav_to_mp3(hass: HomeAssistant, wav: bytes) -> bytes:
    """Convertit le WAV Freebox avec le binaire ffmpeg de Home Assistant."""
    try:
        process = await asyncio.create_subprocess_exec(
            _ffmpeg_binary(hass),
            "-hide_banner",
            "-loglevel",
            "error",
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
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_audio"
        ) from err
    if process.returncode != 0 or not stdout:
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
        try:
            wav = await async_voicemail_audio(router, message_id)
            mp3 = request.query.get("codec") == "mp3"
            body = await async_wav_to_mp3(hass, wav) if mp3 else wav
        except ServiceValidationError:
            return web.Response(status=404, text="Message vocal introuvable")
        except HomeAssistantError:
            return web.Response(status=403, text="Messagerie vocale indisponible")
        except Exception:
            _LOGGER.info("Messagerie vocale Freebox indisponible")
            return web.Response(status=502, text="Messagerie vocale indisponible")
        content_type = "audio/mpeg" if request.query.get("codec") == "mp3" else "audio/wav"
        extension = "mp3" if content_type == "audio/mpeg" else "wav"
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": content_type,
                "Cache-Control": "no-store",
                "Content-Disposition": f'inline; filename="message.{extension}"',
            },
        )
        await response.prepare(request)
        view = memoryview(body)
        for offset in range(0, len(body), _CHUNK):
            await response.write(view[offset : offset + _CHUNK])
        await response.write_eof()
        return response


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
    mp3 = player_needs_mp3(hass, entity_id)
    signed = signed_voicemail_path(hass, router.entry_id, message_id, mp3=mp3)
    url = absolute_voicemail_url(hass, signed, external=mp3)
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": entity_id,
            "media_content_id": url,
            "media_content_type": "music" if mp3 else "audio/wav",
        },
        blocking=True,
    )
    await async_mark_voicemail_read(router, message_id)
