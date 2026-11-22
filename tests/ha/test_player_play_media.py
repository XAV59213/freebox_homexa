"""Lecture audio du Player via AirMedia. Aucun appareil ni réseau réel."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.media_source.models import PlayMedia
from homeassistant.exceptions import HomeAssistantError

from custom_components.freebox_homexa.media_player import FreeboxPlayerMediaPlayer
from test_home_platforms import home_context

TOKEN = "synthetic-token"
AUDIO = f"http://192.0.2.10/local/sirene.mp3?authSig={TOKEN}"
TV = {
    "playback_state": "playing",
    "foreground_app": {"package": "fr.freebox.tv", "cur_url": "tv:"},
}
STARTED = {
    "playback_state": "playing",
    "foreground_app": {"package": "fr.freebox.airmedia", "cur_url": AUDIO},
}


def _entity(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    player = {"id": 1, "reachable": True, "api_version": "v6", "name": "Test Player"}
    entity = FreeboxPlayerMediaPlayer(router, player, entry)
    entity.hass = hass
    return router, entity


def _receivers():
    return [
        {"name": "Salon", "capabilities": {"audio": False, "video": False}},
        {"name": "Freebox Player", "capabilities": {"audio": True, "video": True}},
        "ignore",
    ]


async def _no_sleep(_delay: float) -> None:
    return None


def _patch_status(views):
    queue = list(views)

    async def read(_router, _player_id, version):
        current = queue.pop(0) if queue else views[-1]
        return current, version

    return patch(
        "custom_components.freebox_homexa.player_status.async_read_player_status",
        side_effect=read,
    )


def _patch_sleep():
    return patch(
        "custom_components.freebox_homexa.player_airmedia.asyncio.sleep",
        new=_no_sleep,
    )


@pytest.mark.parametrize("media_type", ["audio/mpeg", "AUDIO/MPEG", "audio/aac", "music"])
async def test_http_audio_starts_through_airmedia(hass, home_context, caplog, media_type):
    router, entity = _entity(hass, home_context)
    sent: list[tuple[str, dict[str, str]]] = []
    posts: list[tuple[str, object]] = []

    async def send_airmedia(name: str, data: dict[str, str]) -> None:
        sent.append((name, data))

    async def post(path: str, payload: object = None) -> None:
        posts.append((path, payload))

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = post
    with caplog.at_level("DEBUG"), _patch_status([TV, STARTED]), _patch_sleep():
        await entity.async_play_media(media_type, AUDIO)
    assert sent and sent[0][0] == "Freebox%20Player"
    assert sent[0][1] == {"action": "start", "media_type": "video", "media": AUDIO}
    assert posts == []
    assert TOKEN not in caplog.text


async def test_airmedia_audio_fallback_when_video_is_refused(hass, home_context):
    router, entity = _entity(hass, home_context)
    sent: list[str] = []

    async def send_airmedia(_name: str, data: dict[str, str]) -> None:
        sent.append(data["media_type"])
        if data["media_type"] == "video":
            raise RuntimeError("unimplemented")

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = AsyncMock()
    with _patch_status([TV, STARTED]), _patch_sleep():
        await entity.async_play_media("music", "https://192.0.2.10/stream")
    assert sent == ["video", "audio"]
    router._api.player._access.post.assert_not_called()


@pytest.mark.parametrize("suffix", [".mp3", ".aac", ".ogg", ".wav", ".flac", ".MP3"])
async def test_missing_type_uses_airmedia_for_audio_extensions(hass, home_context, suffix):
    router, entity = _entity(hass, home_context)
    sent: list[dict[str, str]] = []
    url = f"http://192.0.2.10/local/sirene{suffix}"

    async def send_airmedia(_name: str, data: dict[str, str]) -> None:
        sent.append(data)

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    started = {
        "playback_state": "playing",
        "foreground_app": {"package": "fr.freebox.tv", "cur_url": url},
    }
    with _patch_status([TV, started]), _patch_sleep():
        await entity.async_play_media("", url)
    assert sent and sent[0]["media_type"] == "video"
    assert sent[0]["media"] == url


async def test_control_open_is_the_second_attempt(hass, home_context, caplog):
    router, entity = _entity(hass, home_context)
    posts: list[tuple[str, object]] = []
    tried: list[str] = []

    async def send_airmedia(_name: str, data: dict[str, str]) -> None:
        tried.append(data["media_type"])
        raise RuntimeError("unimplemented")

    async def post(path: str, payload: object = None) -> None:
        posts.append((path, payload))

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = post
    with caplog.at_level("DEBUG"), _patch_status([TV, STARTED]), _patch_sleep():
        await entity.async_play_media("audio/mpeg", AUDIO)
    assert tried == ["video", "audio"]
    assert posts[0][0].endswith("control/mediactrl")
    assert posts[0][1] == {"cmd": "stop"}
    assert posts[1][0].endswith("control/open")
    assert posts[1][1] == {"url": AUDIO, "type": "audio/mpeg"}
    assert len(posts) == 2
    assert TOKEN not in caplog.text
    assert "192.0.2.10" not in caplog.text


async def test_unchanged_player_state_raises_translated_error(hass, home_context, caplog):
    router, entity = _entity(hass, home_context)
    posts: list[str] = []

    async def send_airmedia(_name: str, data: dict[str, str]) -> None:
        return None

    async def post(path: str, payload: object = None) -> None:
        posts.append(path)

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = post
    with caplog.at_level("DEBUG"), _patch_status([TV]), _patch_sleep():
        with pytest.raises(HomeAssistantError) as caught:
            await entity.async_play_media("audio/mpeg", AUDIO)
    assert caught.value.translation_key == "player_audio_silent"
    assert any(path.endswith("control/open") for path in posts)
    assert TOKEN not in caplog.text
    assert "192.0.2.10" not in caplog.text
    assert TOKEN not in str(caught.value)


async def test_refused_open_raises_translated_error(hass, home_context, caplog):
    router, entity = _entity(hass, home_context)

    async def post(_path: str, _payload: object = None) -> None:
        error = OSError("http://192.0.2.99/secret-token")
        error.status = "http://192.0.2.99/secret-token"
        raise error

    router._api.airmedia.get_airmedia_receivers = AsyncMock(
        side_effect=RuntimeError("http://192.0.2.99/secret-token")
    )
    router._api.player._access.post = post
    with caplog.at_level("DEBUG"), _patch_status([TV]), _patch_sleep():
        with pytest.raises(HomeAssistantError) as caught:
            await entity.async_play_media("audio/wav", "http://192.0.2.10/a.wav")
    assert caught.value.translation_key == "player_audio_refused"
    assert "secret-token" not in caplog.text
    assert "192.0.2.99" not in caplog.text


@pytest.mark.parametrize(
    "media_type,media_id,payload",
    [
        ("url", "tv:?channel=12", {"url": "tv:?channel=12"}),
        ("channel", "1", {"url": "1"}),
        ("video/mp4", "http://192.0.2.10/film.mp4", {
            "url": "http://192.0.2.10/film.mp4", "type": "video/mp4",
        }),
        ("url", "http://192.0.2.10/sirene.mp3", {"url": "http://192.0.2.10/sirene.mp3"}),
        ("", "http://192.0.2.10/film.mp4", {"url": "http://192.0.2.10/film.mp4"}),
    ],
)
async def test_tv_video_and_other_uris_stay_on_control_open(
    hass, home_context, media_type, media_id, payload
):
    router, entity = _entity(hass, home_context)
    posts: list[tuple[str, object]] = []

    async def send_airmedia(_name: str, _data: dict[str, str]) -> None:
        raise AssertionError("airmedia")

    async def post(path: str, body: object = None) -> None:
        posts.append((path, body))

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = post
    await entity.async_play_media(media_type, media_id)
    assert len(posts) == 1
    assert str(posts[0][0]).endswith("control/open")
    assert posts[0][1] == payload


async def test_media_source_resolves_before_airmedia(hass, home_context):
    router, entity = _entity(hass, home_context)
    hass.config.internal_url = "http://127.0.0.1:8123"
    sent: list[str] = []

    async def send_airmedia(_name: str, data: dict[str, str]) -> None:
        sent.append(data["media"])

    async def resolve(_hass, _media_id, _target):
        return PlayMedia("/local/sirene.mp3", "audio/mpeg")

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    started = {
        "playback_state": "play",
        "foreground_app": {"package": "browser"},
    }
    with patch(
        "homeassistant.components.media_source.is_media_source_id", return_value=True
    ), patch(
        "homeassistant.components.media_source.async_resolve_media", new=resolve
    ), _patch_status([None, started]), _patch_sleep():
        await entity.async_play_media(
            "music", "media-source://media_source/local/sirene.mp3"
        )
    assert sent == ["http://127.0.0.1:8123/local/sirene.mp3"]


async def test_missing_player_id_is_translated(hass, home_context):
    _router, entity = _entity(hass, home_context)
    entity._player_id = None
    with pytest.raises(HomeAssistantError) as caught:
        await entity.async_play_media("audio/mpeg", "http://192.0.2.10/a.mp3")
    assert caught.value.translation_key == "player_audio_refused"


async def test_string_player_id_is_accepted(hass, home_context):
    router, entity = _entity(hass, home_context)
    entity._player_id = "4"
    posts: list[str] = []

    async def send_airmedia(_name: str, _data: dict[str, str]) -> None:
        raise RuntimeError("unimplemented")

    async def post(path: str, _payload: object = None) -> None:
        posts.append(path)

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = post
    with _patch_status([TV, STARTED]), _patch_sleep():
        await entity.async_play_media("audio/mpeg", "http://192.0.2.10/a.mp3")
    assert any(path.startswith("player/4/api/") and path.endswith("control/open") for path in posts)
