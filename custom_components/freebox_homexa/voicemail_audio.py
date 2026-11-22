"""Lecture audio de la messagerie : vue HTTP signée et conversion MP3.

Le fichier Freebox est souvent un WAV A-law/µ-law ou un AU ``.snd``, illisible
dans beaucoup de navigateurs. ffmpeg (déjà au manifeste) le transcode en MP3
pour la carte, la source média et chaque lecteur. Alexa / Echo doit en plus
pouvoir joindre une URL HTTPS publique.
"""

from __future__ import annotations

import asyncio
import logging
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


def _player_view(status: object) -> tuple[str, str, bool] | None:
    """Lecture, application, et si l'URL de la messagerie est au premier plan."""
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
    return playback, app.lower(), "freebox_homexa/voicemail" in blob


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


async def _player_request(
    router: FreeboxRouter, player_id: int, version: str, method: str, suffix: str, payload: object
) -> object:
    access = router._api.player._access
    path = f"player/{player_id}/api/{version}/{suffix}"
    action = getattr(access, method, None)
    if not callable(action):
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_player_refused"
        )
    if method == "get":
        return await action(path)
    return await action(path, payload)


async def _airmedia_receivers(router: FreeboxRouter) -> list[str]:
    api = getattr(router._api, "airmedia", None)
    getter = getattr(api, "get_airmedia_receivers", None)
    if not callable(getter):
        return []
    try:
        raw = await getter()
    except Exception as err:
        _LOGGER.warning("Liste AirMedia indisponible (code=%s)", stored_error_name(err))
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


async def _airmedia_start(router: FreeboxRouter, url: str) -> bool:
    """Envoie l'URL HTTP. ``audio`` est souvent ``unimplemented`` : ``video`` lit le MP3."""
    api = getattr(router._api, "airmedia", None)
    sender = getattr(api, "send_airmedia", None)
    if not callable(sender):
        return False
    names = await _airmedia_receivers(router)
    if not names:
        return False
    quoted = quote(names[0], safe="")
    for media_type in ("video", "audio"):
        try:
            await sender(
                quoted,
                {"action": "start", "media_type": media_type, "media": url},
            )
            return True
        except Exception as err:
            _LOGGER.warning("AirMedia %s refusé (code=%s)", media_type, stored_error_name(err))
    return False


async def _open_freebox_player_audio(
    hass: HomeAssistant, router: FreeboxRouter, entity_id: str, url: str
) -> None:
    """Joue le MP3 sur le Player Freebox et vérifie que l'état change.

    Music Assistant y arrive en réécrivant l'URL. Ici, AirMedia envoie la même
    URL HTTP (type ``video``, car ``audio`` répond souvent ``unimplemented``).
    ``control/open`` avec ``audio/mpeg`` est le second essai : sans type MIME,
    le Player accepte et reste sur YouTube.
    """
    from .player_status import async_read_player_status

    state = hass.states.get(entity_id)
    attributes = state.attributes if state is not None else {}
    player_id = _coerce_player_id(attributes.get("player_id"))
    raw_version = attributes.get("api_version")
    version = raw_version if isinstance(raw_version, str) and raw_version.startswith("v") else "v6"
    if player_id is None:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_player_unreachable"
        )
    before_status, version = await async_read_player_status(router, player_id, version)
    before = _player_view(before_status)

    async def _heard() -> bool:
        current = before
        for delay in (1, 1):
            await asyncio.sleep(delay)
            status, _version = await async_read_player_status(router, player_id, version)
            current = _player_view(status)
            if _player_started(before, current):
                return True
        return False

    if await _airmedia_start(router, url) and await _heard():
        return
    try:
        await _player_request(router, player_id, version, "post", "control/mediactrl", {"cmd": "stop"})
    except Exception:
        _LOGGER.debug("Arrêt du média en cours ignoré avant la messagerie")
    opened = False
    for mime in ("audio/mpeg", ""):
        body: dict[str, str] = {"url": url}
        if mime:
            body["type"] = mime
        try:
            await _player_request(router, player_id, version, "post", "control/open", body)
            opened = True
        except Exception as err:
            _LOGGER.warning(
                "Ouverture audio du Player refusée (statut=%s, code=%s)",
                getattr(err, "status", "-"),
                stored_error_name(err),
            )
            continue
        for delay in (1, 1):
            await asyncio.sleep(delay)
            status, version = await async_read_player_status(router, player_id, version)
            if _player_started(before, _player_view(status)):
                return
    if not opened:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_player_refused"
        )
    _LOGGER.warning("Le Player n'a pas changé d'état après l'ouverture audio")
    raise HomeAssistantError(
        translation_domain=DOMAIN, translation_key="voicemail_player_silent"
    )


def stored_error_name(err: BaseException) -> str:
    from .voicemail import stored_error

    return stored_error(err)


async def async_play_on_player(
    hass: HomeAssistant, router: FreeboxRouter, message_id: str, entity_id: str
) -> None:
    """Joue le message. Un échec du marquage lu ne fait pas échouer la lecture."""
    from .voicemail import (
        async_mark_voicemail_read,
        schedule_mark_read_retry,
        stored_error,
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
    own_player = False
    row = er.async_get(hass).async_get(entity_id)
    if row is not None and row.platform == DOMAIN and row.domain == "media_player":
        own_player = True
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
    from .voicemail import stored_error

    try:
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": entity_id,
                "media_content_id": url,
                "media_content_type": playback_content_type(hass, entity_id),
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
        }:
            raise
        _LOGGER.warning(
            "Lecteur a refusé la messagerie (%s)", err.translation_key or "error"
        )
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_player_refused"
        ) from err
    except Exception as err:
        _LOGGER.warning(
            "Lecteur a refusé la messagerie (%s, %s)",
            type(err).__name__,
            stored_error(err),
        )
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="voicemail_player_refused"
        ) from err
