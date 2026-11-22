"""Lecture audio de la messagerie : vue HTTP signée et conversion MP3.

Le fichier Freebox est souvent un WAV A-law/µ-law ou un AU ``.snd``, illisible
dans beaucoup de navigateurs. ffmpeg (déjà au manifeste) le transcode en MP3
pour la carte, la source média et chaque lecteur. Alexa / Echo doit en plus
pouvoir joindre une URL HTTPS publique.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import quote

from aiohttp import web
from homeassistant.components.ffmpeg import DATA_FFMPEG
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
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
_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def public_error_code(err: BaseException) -> str:
    """Code affichable. Jamais une URL, un jeton, un nom ou un numéro."""
    key = getattr(err, "translation_key", None)
    if isinstance(key, str) and _CODE.fullmatch(key) and not re.search(r"\d{6,}", key):
        return key
    code = stored_error(err)
    if _CODE.fullmatch(code) and not re.search(r"\d{6,}", code):
        return code
    return "error"


def _registry_platform(hass: HomeAssistant, entity_id: str) -> str:
    row = er.async_get(hass).async_get(entity_id)
    if row is None or not isinstance(row.platform, str):
        return ""
    return row.platform


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


def playback_content_type(hass: HomeAssistant, entity_id: str) -> str:
    """Music Assistant accepte ``audio/mpeg``. Le Player Freebox ouvre une URL (``music``)."""
    row = er.async_get(hass).async_get(entity_id)
    if row is not None and row.platform == DOMAIN and row.domain == "media_player":
        return "music"
    return "audio/mpeg"


def absolute_voicemail_url(hass: HomeAssistant, signed_path: str, *, external: bool) -> str:
    try:
        if external:
            base = get_url(hass, allow_internal=False, allow_external=True, prefer_external=True)
        else:
            base = get_url(hass, prefer_external=False)
    except NoURLAvailableError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key=(
                "voicemail_public_url" if external else "voicemail_player_unreachable"
            ),
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
            wants_wav = request.query.get("codec") == "wav"
            if wants_wav:
                payload = await async_voicemail_audio(router, message_id)
                body = payload
            else:
                body = await async_cached_mp3(hass, router, message_id)
                payload = body
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


def _mp3_cache(router: FreeboxRouter) -> dict[str, bytes]:
    store = router.voicemail_mp3_cache
    if not isinstance(store, dict):
        store = {}
        router.voicemail_mp3_cache = store
    return store


async def async_cached_mp3(hass: HomeAssistant, router: FreeboxRouter, message_id: str) -> bytes:
    """Réutilise le MP3 déjà produit pour « Écouter ». Sinon convertit et mémorise."""
    from .voicemail import resolve_voicemail_token

    ident = resolve_voicemail_token(router, message_id)
    cache = _mp3_cache(router)
    found = cache.get(ident)
    if isinstance(found, bytes) and found:
        return found
    payload = await async_voicemail_audio(router, message_id)
    body = payload if _looks_like_mp3(payload) else await async_wav_to_mp3(hass, payload)
    while len(cache) >= 8:
        cache.pop(next(iter(cache)))
    cache[ident] = body
    return body


def _looks_like_mp3(payload: bytes) -> bool:
    return payload.startswith((b"ID3", b"\xff\xfb"))


def _coerce_player_id(raw: object) -> int | None:
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


async def _open_freebox_player_audio(
    hass: HomeAssistant, router: FreeboxRouter, entity_id: str, url: str
) -> None:
    """Joue le MP3 sur le Player Freebox et vérifie que l'état change.

    Music Assistant y arrive en réécrivant l'URL. Ici, AirMedia envoie la même
    URL HTTP (type ``video``, car ``audio`` répond souvent ``unimplemented``).
    ``control/open`` avec ``audio/mpeg`` est le second essai : sans type MIME,
    le Player accepte et reste sur YouTube. Le même envoi sert à
    ``media_player.play_media`` pour un fichier audio.
    """
    from .player_airmedia import PlayerPlaybackError, async_open_player_audio

    state = hass.states.get(entity_id)
    attributes = state.attributes if state is not None else {}
    from .player_airmedia import remember_player_source

    source = attributes.get("source") if isinstance(attributes, dict) else None
    remember_player_source(entity_id, source)
    player_id = _coerce_player_id(attributes.get("player_id"))
    raw_version = attributes.get("api_version")
    version = raw_version if isinstance(raw_version, str) and raw_version.startswith("v") else "v6"
    raw_name = attributes.get("friendly_name") if isinstance(attributes, dict) else None
    device_name = raw_name.strip() if isinstance(raw_name, str) else ""
    if player_id is None:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_player_unreachable"
        )
    try:
        await async_open_player_audio(
            router,
            player_id,
            version,
            url,
            marker="freebox_homexa/voicemail",
            device_name=device_name,
        )
    except PlayerPlaybackError as err:
        if err.kind == "silent":
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="voicemail_player_silent"
            ) from err
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="voicemail_player_refused",
            translation_placeholders={"code": "refused"},
        ) from err


async def async_play_on_player(
    hass: HomeAssistant, router: FreeboxRouter, message_id: str, entity_id: str
) -> None:
    """Joue le message. Un échec du marquage lu ne fait pas échouer la lecture."""
    from .voicemail import (
        async_mark_voicemail_read,
        schedule_mark_read_retry,
        stored_error,
        voicemail_player_enabled,
    )

    if not isinstance(entity_id, str) or not entity_id.startswith("media_player."):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="voicemail_player"
        )
    state = hass.states.get(entity_id)
    if state is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="voicemail_player"
        )
    if state.state == "unavailable":
        _LOGGER.warning("Lecteur injoignable pour la messagerie")
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_player_unreachable"
        )
    if not voicemail_player_enabled(router):
        _LOGGER.warning("Lecture de la messagerie sur un lecteur désactivée")
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_player_disabled"
        )
    platform = _registry_platform(hass, entity_id)
    if platform == "alexa_media" or platform == "alexa_devices":
        # play_media n'accepte pas une URL : Alexa Devices cherche un titre chez un
        # fournisseur (audio/mpeg lève cannot_retrieve_data) et Alexa Media ne joue
        # un MP3 qu'en le retéléchargeant sous son propre public_url, avec announce.
        _LOGGER.warning("Lecteur Alexa direct ignoré (plateforme=%s)", platform)
        shown = "alexa_media" if platform == "alexa_media" else "alexa_devices"
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="voicemail_alexa_direct",
            translation_placeholders={"platform": shown},
        )
    external = player_needs_mp3(hass, entity_id)
    try:
        signed = signed_voicemail_path(hass, router.entry_id, message_id, mp3=True)
        url = absolute_voicemail_url(hass, signed, external=external)
    except HomeAssistantError:
        raise
    except Exception as err:
        _LOGGER.warning("URL de lecture indisponible (%s)", type(err).__name__)
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_audio"
        ) from err
    own_player = platform == DOMAIN
    if own_player:
        await _open_freebox_player_audio(hass, router, entity_id, url)
    else:
        await _play_via_media_player(hass, entity_id, url)
    try:
        await async_mark_voicemail_read(router, message_id)
    except Exception as err:
        _LOGGER.warning(
            "Lecture commencée, marquage lu reporté (%s)",
            err.translation_key if isinstance(err, HomeAssistantError) and err.translation_key
            else stored_error(err),
        )
        schedule_mark_read_retry(router, message_id)


async def _play_via_media_player(hass: HomeAssistant, entity_id: str, url: str) -> None:
    try:
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": entity_id,
                "media_content_id": url,
                "media_content_type": playback_content_type(hass, entity_id),
                "extra": {"title": "Message vocal Freebox"},
            },
            blocking=True,
        )
    except HomeAssistantError as err:
        if err.translation_key in {
            "voicemail_player",
            "voicemail_player_unreachable",
            "voicemail_public_url",
            "voicemail_audio",
            "voicemail_player_refused",
            "voicemail_player_silent",
            "voicemail_alexa_direct",
        }:
            raise
        code = public_error_code(err)
        _LOGGER.warning("Lecteur a refusé la messagerie (code=%s)", code)
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="voicemail_player_refused",
            translation_placeholders={"code": code},
        ) from err
    except Exception as err:
        code = public_error_code(err)
        _LOGGER.warning("Lecteur a refusé la messagerie (code=%s)", code)
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="voicemail_player_refused",
            translation_placeholders={"code": code},
        ) from err
