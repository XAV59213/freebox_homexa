"""Source média « Freebox – Messagerie vocale ».

Les titres n'affichent ni numéro ni nom. La résolution renvoie une URL signée
de courte durée (WAV, ou MP3 si le lecteur visé en a besoin).
"""

from __future__ import annotations

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source.error import Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .voicemail import messages_of, public_message
from .voicemail_audio import (
    absolute_voicemail_url,
    player_needs_mp3,
    signed_voicemail_path,
)

_SOURCE_NAME = "Freebox – Messagerie vocale"


class FreeboxVoicemailSource(MediaSource):
    """Parcourt les messages vocaux des Freebox chargées."""

    name = _SOURCE_NAME

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        entry_id, message_id = _split_playable(item.identifier)
        router = _router(self.hass, entry_id)
        if router is None or not any(message.id == message_id for message in messages_of(router)):
            raise Unresolvable("Message vocal introuvable")
        target = item.target_media_player
        mp3 = bool(target) and player_needs_mp3(self.hass, target)
        try:
            signed = signed_voicemail_path(self.hass, entry_id, message_id, mp3=mp3)
            url = absolute_voicemail_url(self.hass, signed, external=mp3)
        except (HomeAssistantError, ServiceValidationError) as err:
            raise Unresolvable("Lecture du message vocal impossible") from err
        return PlayMedia(url, "audio/mpeg" if mp3 else "audio/wav")

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        identifier = item.identifier.strip("/")
        if not identifier:
            return _root(self.hass)
        if "/" not in identifier:
            return _entry_folder(self.hass, identifier)
        entry_id, message_id = _split_playable(identifier)
        return _message_leaf(self.hass, entry_id, message_id)


async def async_get_media_source(hass: HomeAssistant) -> FreeboxVoicemailSource:
    return FreeboxVoicemailSource(hass)


def _entries(hass: HomeAssistant) -> list[tuple[str, str, object]]:
    from .router import FreeboxRouter

    found: list[tuple[str, str, object]] = []
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        router = getattr(entry, "runtime_data", None)
        if isinstance(router, FreeboxRouter):
            found.append((entry.entry_id, entry.title or "Freebox", router))
    return found


def _router(hass: HomeAssistant, entry_id: str) -> object | None:
    for ident, _title, router in _entries(hass):
        if ident == entry_id:
            return router
    return None


def _split_playable(identifier: str) -> tuple[str, str]:
    if "/" not in identifier:
        raise Unresolvable("Message vocal introuvable")
    entry_id, message_id = identifier.split("/", 1)
    if not entry_id or not message_id or "/" in message_id:
        raise Unresolvable("Message vocal introuvable")
    return entry_id, message_id


def _message_title(payload: dict[str, object]) -> str:
    when = payload.get("date") or "date inconnue"
    duration = payload.get("duration")
    state = "non lu" if payload.get("read") is False else "lu"
    return f"{when} · {duration} s · {state}"


def _root(hass: HomeAssistant) -> BrowseMediaSource:
    entries = _entries(hass)
    if len(entries) == 1:
        entry_id, _title, router = entries[0]
        return _folder(entry_id, _SOURCE_NAME, _children(entry_id, router))
    children = [
        BrowseMediaSource(
            domain=DOMAIN,
            identifier=entry_id,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.PLAYLIST,
            title=title,
            can_play=False,
            can_expand=True,
        )
        for entry_id, title, _router in entries
    ]
    return _folder("", _SOURCE_NAME, children)


def _entry_folder(hass: HomeAssistant, entry_id: str) -> BrowseMediaSource:
    match = next(((title, router) for ident, title, router in _entries(hass) if ident == entry_id), None)
    if match is None:
        raise Unresolvable("Messagerie vocale introuvable")
    title, router = match
    return _folder(entry_id, title, _children(entry_id, router))


def _children(entry_id: str, router: object) -> list[BrowseMediaSource]:
    from .router import FreeboxRouter

    if not isinstance(router, FreeboxRouter):
        return []
    children: list[BrowseMediaSource] = []
    for message in messages_of(router):
        payload = public_message(message)
        children.append(
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{entry_id}/{message.id}",
                media_class=MediaClass.MUSIC,
                media_content_type=MediaType.MUSIC,
                title=_message_title(payload),
                can_play=True,
                can_expand=False,
            )
        )
    return children


def _message_leaf(hass: HomeAssistant, entry_id: str, message_id: str) -> BrowseMediaSource:
    router = _router(hass, entry_id)
    from .router import FreeboxRouter

    if not isinstance(router, FreeboxRouter):
        raise Unresolvable("Message vocal introuvable")
    message = next((item for item in messages_of(router) if item.id == message_id), None)
    if message is None:
        raise Unresolvable("Message vocal introuvable")
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=f"{entry_id}/{message.id}",
        media_class=MediaClass.MUSIC,
        media_content_type=MediaType.MUSIC,
        title=_message_title(public_message(message)),
        can_play=True,
        can_expand=False,
    )


def _folder(identifier: str, title: str, children: list[BrowseMediaSource]) -> BrowseMediaSource:
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=identifier,
        media_class=MediaClass.DIRECTORY,
        media_content_type=MediaType.PLAYLIST,
        title=title,
        can_play=False,
        can_expand=True,
        children=children,
    )
