"""Source média « Freebox – Messagerie vocale ».

Les titres n'affichent ni numéro ni nom. La résolution renvoie une URL signée
de courte durée, en MP3. Alexa / Echo exige en plus une URL publique.
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
from .player_audio import (
    BUNDLED_SOUNDS,
    SOUND_TITLES,
    async_host_sound,
)
from .voicemail import (
    messages_of,
    public_message,
    resolve_voicemail_token,
    tokens_of,
)
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
        sound = _sound_name(item.identifier)
        if sound is not None:
            try:
                url = await async_host_sound(self.hass, sound)
            except HomeAssistantError as err:
                raise Unresolvable("Lecture du son impossible") from err
            return PlayMedia(url, "audio/mpeg")
        entry_id, public_id = _split_playable(item.identifier)
        router = _router(self.hass, entry_id)
        message = _message_by_token(router, public_id)
        if message is None:
            raise Unresolvable("Message vocal introuvable")
        target = item.target_media_player
        external = bool(target) and player_needs_mp3(self.hass, target)
        try:
            signed = signed_voicemail_path(self.hass, entry_id, public_id, mp3=True)
            url = absolute_voicemail_url(self.hass, signed, external=external)
        except (HomeAssistantError, ServiceValidationError) as err:
            raise Unresolvable("Lecture du message vocal impossible") from err
        return PlayMedia(url, "audio/mpeg")

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        identifier = item.identifier.strip("/")
        if not identifier:
            return _root(self.hass)
        sounds = _browse_sound(identifier)
        if sounds is not None:
            return sounds
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
        return _folder(
            entry_id,
            _SOURCE_NAME,
            [*_children(entry_id, router), *_sound_leaves()],
        )
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
    children.append(
        BrowseMediaSource(
            domain=DOMAIN,
            identifier="sound",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.PLAYLIST,
            title="Sons d'alarme",
            can_play=False,
            can_expand=True,
        )
    )
    return _folder("", _SOURCE_NAME, children)


def _sound_name(identifier: str) -> str | None:
    text = identifier.strip("/")
    if not text.startswith("sound/"):
        return None
    name = text[len("sound/"):]
    if "/" in name or name not in BUNDLED_SOUNDS:
        raise Unresolvable("Son introuvable")
    return name


def _sound_leaf(name: str) -> BrowseMediaSource:
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=f"sound/{name}",
        media_class=MediaClass.MUSIC,
        media_content_type=MediaType.MUSIC,
        title=SOUND_TITLES[name],
        can_play=True,
        can_expand=False,
    )


def _sound_leaves() -> list[BrowseMediaSource]:
    return [_sound_leaf(name) for name in BUNDLED_SOUNDS]


def _browse_sound(identifier: str) -> BrowseMediaSource | None:
    if identifier == "sound":
        return _folder("sound", "Sons d'alarme", _sound_leaves())
    if not identifier.startswith("sound/"):
        return None
    name = _sound_name(identifier)
    if name is None:
        raise Unresolvable("Son introuvable")
    return _sound_leaf(name)


def _entry_folder(hass: HomeAssistant, entry_id: str) -> BrowseMediaSource:
    match = next(((title, router) for ident, title, router in _entries(hass) if ident == entry_id), None)
    if match is None:
        raise Unresolvable("Messagerie vocale introuvable")
    title, router = match
    return _folder(entry_id, title, _children(entry_id, router))


def _message_by_token(router: object, public_id: str) -> object | None:
    from .router import FreeboxRouter

    if not isinstance(router, FreeboxRouter):
        return None
    try:
        raw = resolve_voicemail_token(router, public_id)
    except ServiceValidationError:
        return None
    return next((item for item in messages_of(router) if item.id == raw), None)


def _children(entry_id: str, router: object) -> list[BrowseMediaSource]:
    from .router import FreeboxRouter

    if not isinstance(router, FreeboxRouter):
        return []
    store = tokens_of(router)
    children: list[BrowseMediaSource] = []
    for message in messages_of(router):
        public_id = store.issue(message.id)
        payload = public_message(message, public_id=public_id)
        children.append(
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{entry_id}/{public_id}",
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
    from .voicemail import VoicemailMessage

    if not isinstance(router, FreeboxRouter):
        raise Unresolvable("Message vocal introuvable")
    message = _message_by_token(router, message_id)
    if not isinstance(message, VoicemailMessage):
        raise Unresolvable("Message vocal introuvable")
    public_id = tokens_of(router).issue(message.id)
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=f"{entry_id}/{public_id}",
        media_class=MediaClass.MUSIC,
        media_content_type=MediaType.MUSIC,
        title=_message_title(public_message(message, public_id=public_id)),
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
