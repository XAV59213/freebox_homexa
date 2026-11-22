"""Lecture audio du Player via AirMedia. Aucun appareil ni réseau réel."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.media_source.models import PlayMedia
from homeassistant.exceptions import HomeAssistantError

from custom_components.freebox_homexa.media_player import FreeboxPlayerMediaPlayer
from custom_components.freebox_homexa.player_audio import async_audio_to_mp4 as _real_audio_to_mp4
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


@pytest.fixture(autouse=True)
def _wrap_audio_as_mp4(monkeypatch):
    """Évite ffmpeg pendant les tests : le résultat reste un MP4 reconnaissable."""

    async def convert(_hass: object, payload: bytes) -> bytes:
        return b"\x00\x00\x00\x18ftypisom" + payload

    monkeypatch.setattr(
        "custom_components.freebox_homexa.player_audio.async_audio_to_mp4",
        convert,
    )


@pytest.fixture(autouse=True)
def _block_remote_fetch(monkeypatch):
    """Aucun test de ce module n'ouvre de socket vers une adresse audio."""

    async def _blocked(_hass: object, _url: str) -> bytes:
        raise OSError("blocked")

    monkeypatch.setattr(
        "custom_components.freebox_homexa.player_audio._fetch_audio",
        _blocked,
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
    assert sent[0][1] == {
        "action": "start", "media_type": "video", "media": AUDIO, "position": 0,
    }
    assert all(item[1]["media_type"] == "video" for item in sent)
    assert posts == []
    assert TOKEN not in caplog.text


async def test_unimplemented_does_not_try_the_audio_media_type(hass, home_context):
    router, entity = _entity(hass, home_context)
    sent: list[str] = []

    async def send_airmedia(_name: str, data: dict[str, str]) -> None:
        sent.append(str(data["media_type"]))
        raise RuntimeError("unimplemented")

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = AsyncMock()
    with _patch_status([TV, STARTED]), _patch_sleep():
        await entity.async_play_media("music", "https://192.0.2.10/stream")
    assert sent == ["video"]
    router._api.player._access.post.assert_called()


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
    assert tried == ["video"]
    assert posts[0][0].endswith("control/mediactrl")
    assert posts[0][1] == {"cmd": "stop"}
    assert posts[1][0].endswith("control/open")
    assert posts[1][1] == {"url": AUDIO, "type": "video/mp4"}
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


async def test_voicemail_stop_leaves_airmedia_and_restores_the_source(hass, home_context):
    router, entity = _entity(hass, home_context)
    entity.entity_id = "media_player.test_player"
    entity._attr_source = "TV"
    entity._attr_media_content_id = "freebox_homexa/voicemail"
    from custom_components.freebox_homexa.player_airmedia import remember_player_source

    remember_player_source(entity.entity_id, "TV")
    commands: list[str] = []
    stopped: list[str] = []
    restored: list[str] = []

    async def command(name: str) -> None:
        commands.append(name)

    async def stop_air(_router) -> None:
        stopped.append("air")

    async def select_source(source: str) -> None:
        restored.append(source)

    entity._command = command
    entity.async_select_source = select_source
    with patch(
        "custom_components.freebox_homexa.media_player.async_stop_player_audio",
        new=stop_air,
    ):
        await entity.async_media_stop()
    assert commands == ["stop"]
    assert stopped == ["air"]
    assert restored == ["TV"]

    commands.clear()
    stopped.clear()
    entity._attr_media_content_id = "spotify:track"
    await entity.async_media_stop()
    assert commands == ["stop"]
    assert stopped == []

    status = {
        "playback_state": "playing",
        "reachable": True,
        "title": "a" * 40,
        "foreground_app": {
            "cur_url": "http://192.0.2.10/api/freebox_homexa/voicemail/entry/token?authSig=synthetic-token",
        },
    }

    async def read(_router, _player_id, version):
        return status, version

    entity._get = AsyncMock(return_value={})
    with patch(
        "custom_components.freebox_homexa.media_player.async_read_player_status",
        side_effect=read,
    ):
        await entity.async_update()
    assert entity._attr_media_title == "Message vocal Freebox"
    assert entity._attr_media_content_id == "freebox_homexa/voicemail"
    assert "synthetic-token" not in str(entity._attr_source or "")
    assert "synthetic-token" not in str(entity._attr_media_content_id)


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


def _api_error(code: str):
    from freebox_api.exceptions import HttpRequestError

    payload = '{"success": false, "error_code": "%s"}' % code
    return HttpRequestError("Request failed (APIResponse: %s)" % payload)


def _alarm_mp3(path):
    data = path.read_bytes()
    assert 20_000 < len(data) < 100_000
    assert not data.startswith(b"ID3")
    assert b"APIC" not in data
    assert data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
    assert (data[1] >> 3) & 0x03 == 0b11
    assert (data[1] >> 1) & 0x03 == 0b01
    assert (data[2] >> 2) & 0x03 == 0
    assert (data[3] >> 6) & 0x03 == 0b11
    bitrate = (data[2] >> 4) & 0x0F
    assert bitrate in {7, 9}
    kbps = {7: 96, 9: 128}[bitrate]
    offset = 0
    frames = 0
    while offset + 4 <= len(data) and data[offset] == 0xFF and (data[offset + 1] & 0xE0) == 0xE0:
        padding = (data[offset + 2] >> 1) & 0x01
        step = 144 * kbps * 1000 // 44100 + padding
        offset += step
        frames += 1
    assert 4.5 <= frames * 1152 / 44100 <= 5.5


def test_alarm_sounds_are_small_mono_mp3s_and_ship_in_the_hacs_zip(tmp_path):
    import zipfile
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "custom_components" / "freebox_homexa"
    for name in ("alarme_sirene.mp3", "alarme_bip.mp3"):
        _alarm_mp3(source / "sounds" / name)
    archive = tmp_path / "freebox_homexa.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if not path.is_file() or "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            bundle.write(path, relative.as_posix())
    names = set(zipfile.ZipFile(archive).namelist())
    assert "sounds/alarme_sirene.mp3" in names
    assert "sounds/alarme_bip.mp3" in names
    assert "manifest.json" in names
    assert not any(name.endswith(".pyc") or name.endswith(".pyo") for name in names)
    assert not any("__pycache__" in name for name in names)


@pytest.mark.parametrize("code", ["http", "req_in_progress"])
async def test_video_is_retried_once_without_an_audio_attempt(hass, home_context, caplog, code):
    router, entity = _entity(hass, home_context)
    sent: list[str] = []
    delays: list[float] = []

    async def send_airmedia(_name: str, data: dict[str, object]) -> None:
        sent.append(str(data["media_type"]))
        assert data["position"] == 0
        if len(sent) == 1:
            raise _api_error(code)

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = AsyncMock()
    with caplog.at_level("DEBUG"), _patch_status([TV, STARTED]), patch(
        "custom_components.freebox_homexa.player_airmedia.asyncio.sleep",
        new=record_sleep,
    ):
        await entity.async_play_media("audio/mpeg", AUDIO)
    assert sent == ["video", "video"]
    assert delays[0] == 1
    assert TOKEN not in caplog.text
    assert "192.0.2.10" not in caplog.text
    assert "authSig" not in caplog.text
    router._api.player._access.post.assert_not_called()


async def test_receiver_matches_the_player_and_skips_the_server(hass, home_context, caplog):
    router, entity = _entity(hass, home_context)
    entity._player["device_name"] = "Devialet"
    sent: list[str] = []

    async def send_airmedia(name: str, data: dict[str, object]) -> None:
        sent.append(name)
        assert data["media_type"] == "video"

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=[
        {
            "name": "Freebox Server",
            "capabilities": {"video": True, "audio": True},
            "password_protected": False,
        },
        {
            "name": "Chambre",
            "capabilities": {"video": True, "audio": True},
            "password_protected": True,
        },
        {
            "name": "Salon",
            "capabilities": {"audio": True, "video": False},
            "password_protected": False,
        },
        {
            "name": "Devialet",
            "capabilities": {"video": True, "audio": False},
            "password_protected": False,
        },
        "ignore",
    ])
    router._api.airmedia.send_airmedia = send_airmedia
    with caplog.at_level("DEBUG"), _patch_status([TV, STARTED]), _patch_sleep():
        await entity.async_play_media("audio/mpeg", AUDIO)
    assert sent == ["Devialet"]
    assert "4 récepteur(s)" in caplog.text
    assert "protégé=" in caplog.text
    assert "vidéo=" in caplog.text
    assert TOKEN not in caplog.text
    assert "192.0.2.10" not in caplog.text
    assert "authSig" not in caplog.text
    assert "http://" not in caplog.text


async def test_unchanged_playback_counts_when_the_media_url_changes(hass, home_context):
    router, entity = _entity(hass, home_context)
    sent: list[str] = []

    async def send_airmedia(_name: str, data: dict[str, object]) -> None:
        sent.append(str(data["media_type"]))

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = AsyncMock()
    changed = {
        "playback_state": "playing",
        "foreground_app": {"package": "fr.freebox.tv", "cur_url": "player:audio"},
    }
    with _patch_status([TV, changed]), _patch_sleep():
        await entity.async_play_media("audio/mpeg", AUDIO)
    assert sent == ["video"]
    router._api.player._access.post.assert_not_called()


async def test_local_mp3_is_served_from_the_signed_view(
    hass, hass_client, home_context, caplog
):
    from urllib.parse import urlsplit

    from homeassistant.setup import async_setup_component

    from custom_components.freebox_homexa.player_audio import (
        async_register_player_audio_view,
        clear_player_audio_cache,
    )

    clear_player_audio_cache()
    assert await async_setup_component(hass, "http", {"http": {}})
    async_register_player_audio_view(hass)
    router, entity = _entity(hass, home_context)
    payload = b"ID3local-siren"
    sent: list[dict[str, object]] = []

    async def send_airmedia(_name: str, data: dict[str, object]) -> None:
        sent.append(data)

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    started = {
        "playback_state": "playing",
        "foreground_app": {
            "package": "fr.freebox.tv",
            "cur_url": "http://homeassistant.local/api/freebox_homexa/player_audio/token",
        },
    }
    fetched: list[str] = []

    async def fetch(_hass: object, url: str) -> bytes:
        fetched.append(url)
        return payload

    with caplog.at_level("DEBUG"), patch(
        "custom_components.freebox_homexa.player_audio._fetch_audio",
        new=fetch,
    ), patch(
        "custom_components.freebox_homexa.player_audio.get_url",
        return_value="http://homeassistant.local:8123",
    ), _patch_status([TV, started]), _patch_sleep():
        await entity.async_play_media("audio/mpeg", "http://192.0.2.10/local/sirene.mp3?authSig=local-token")
    assert fetched == ["http://192.0.2.10/local/sirene.mp3?authSig=local-token"]
    assert sent and sent[0]["media_type"] == "video"
    assert sent[0]["position"] == 0
    media = str(sent[0]["media"])
    assert "/api/freebox_homexa/player_audio/" in media
    assert "sirene.mp3" not in media
    assert "local-token" not in media
    assert "192.0.2.10" not in caplog.text
    assert "local-token" not in caplog.text
    assert "authSig" not in caplog.text
    parts = urlsplit(media)
    client = await hass_client()
    response = await client.get(f"{parts.path}?{parts.query}")
    assert response.status == 200
    assert response.headers["Content-Type"] == "video/mp4"
    assert response.headers["Cache-Control"] == "no-store"
    wrapped = b"\x00\x00\x00\x18ftypisom" + payload
    assert response.headers["Content-Length"] == str(len(wrapped))
    assert await response.read() == wrapped
    missing = await client.get("/api/freebox_homexa/player_audio/absent")
    assert missing.status == 404


async def test_wav_uses_the_voicemail_ffmpeg_helper(hass, hass_client, home_context):
    from urllib.parse import urlsplit

    from homeassistant.setup import async_setup_component

    from custom_components.freebox_homexa.player_audio import (
        async_register_player_audio_view,
        clear_player_audio_cache,
    )

    clear_player_audio_cache()
    assert await async_setup_component(hass, "http", {"http": {}})
    async_register_player_audio_view(hass)
    router, entity = _entity(hass, home_context)
    converted = b"\xff\xfbconverted"
    sent: list[str] = []

    async def send_airmedia(_name: str, data: dict[str, object]) -> None:
        sent.append(str(data["media"]))

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    started = {
        "playback_state": "playing",
        "foreground_app": {"package": "fr.freebox.airmedia", "cur_url": "freebox_homexa/player_audio"},
    }
    async def fetch(_hass: object, _url: str) -> bytes:
        return b"RIFFwav"

    with patch(
        "custom_components.freebox_homexa.player_audio._fetch_audio",
        new=fetch,
    ), patch(
        "custom_components.freebox_homexa.voicemail_audio.async_wav_to_mp3",
        new=AsyncMock(return_value=converted),
    ), patch(
        "custom_components.freebox_homexa.player_audio.get_url",
        return_value="http://homeassistant.local:8123",
    ), _patch_status([TV, started]), _patch_sleep():
        await entity.async_play_media("audio/wav", "http://192.0.2.10/a.wav")
    assert sent and "/api/freebox_homexa/player_audio/" in sent[0]
    parts = urlsplit(sent[0])
    client = await hass_client()
    response = await client.get(f"{parts.path}?{parts.query}")
    assert (await response.read()).startswith(b"\x00\x00\x00\x18ftypisom")
    assert response.headers["Content-Type"] == "video/mp4"


async def test_fetch_failure_falls_back_to_the_original_url_without_logging_it(
    hass, home_context, caplog
):
    router, entity = _entity(hass, home_context)
    sent: list[str] = []

    async def send_airmedia(_name: str, data: dict[str, object]) -> None:
        sent.append(str(data["media"]))

    async def fetch(_hass: object, _url: str) -> bytes:
        raise OSError("http://192.0.2.99/secret-token")

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    with caplog.at_level("DEBUG"), patch(
        "custom_components.freebox_homexa.player_audio._fetch_audio",
        new=fetch,
    ), _patch_status([TV, STARTED]), _patch_sleep():
        await entity.async_play_media("audio/mpeg", AUDIO)
    assert sent == [AUDIO]
    assert "secret-token" not in caplog.text
    assert "192.0.2.99" not in caplog.text
    assert TOKEN not in caplog.text
    assert "authSig" not in caplog.text


async def test_bundled_sound_ids_resolve_to_the_signed_view(
    hass, hass_client, home_context, caplog
):
    from urllib.parse import urlsplit

    from homeassistant.components.media_source.models import MediaSourceItem
    from homeassistant.setup import async_setup_component

    from custom_components.freebox_homexa.const import DOMAIN
    from custom_components.freebox_homexa.media_source import async_get_media_source
    from custom_components.freebox_homexa.player_audio import (
        async_host_bytes,
        async_register_player_audio_view,
        clear_player_audio_cache,
    )

    clear_player_audio_cache()
    assert await async_setup_component(hass, "http", {"http": {}})
    async_register_player_audio_view(hass)
    async_register_player_audio_view(hass)
    source = await async_get_media_source(hass)
    folder = await source.async_browse_media(MediaSourceItem(hass, DOMAIN, "sound", None))
    assert [child.identifier for child in folder.children or []] == [
        "sound/alarme_sirene",
        "sound/alarme_bip",
    ]
    assert [child.title for child in folder.children or []] == ["Sirène", "Bip d'alarme"]
    with patch(
        "custom_components.freebox_homexa.player_audio.get_url",
        return_value="http://homeassistant.local:8123",
    ):
        first = await source.async_resolve_media(
            MediaSourceItem(hass, DOMAIN, "sound/alarme_sirene", None)
        )
        second = await source.async_resolve_media(
            MediaSourceItem(hass, DOMAIN, "sound/alarme_sirene", None)
        )
    assert first.mime_type == "video/mp4"
    assert first.url == second.url
    assert "/api/freebox_homexa/player_audio/" in first.url
    assert "alarme_sirene" not in first.url
    router, entity = _entity(hass, home_context)
    sent: list[dict[str, object]] = []

    async def send_airmedia(_name: str, data: dict[str, object]) -> None:
        sent.append(data)

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    started = {
        "playback_state": "playing",
        "foreground_app": {
            "package": "fr.freebox.airmedia",
            "cur_url": "http://homeassistant.local/api/freebox_homexa/player_audio/token",
        },
    }
    with caplog.at_level("DEBUG"), patch(
        "custom_components.freebox_homexa.player_audio.get_url",
        return_value="http://homeassistant.local:8123",
    ), _patch_status([TV, started]), _patch_sleep():
        await entity.async_play_media("music", "freebox_homexa://sound/alarme_bip")
        await entity.async_play_media(
            "audio/mpeg", "media-source://freebox_homexa/sound/alarme_sirene"
        )
    assert len(sent) == 2
    assert all(item["media_type"] == "video" and item["position"] == 0 for item in sent)
    assert all("/api/freebox_homexa/player_audio/" in str(item["media"]) for item in sent)
    assert "authSig" not in caplog.text
    assert "homeassistant.local" not in caplog.text
    parts = urlsplit(str(sent[0]["media"]))
    client = await hass_client()
    response = await client.get(f"{parts.path}?{parts.query}")
    assert response.status == 200
    assert response.headers["Content-Type"] == "video/mp4"
    assert response.headers["Cache-Control"] == "no-store"
    from pathlib import Path

    alarm = (
        Path(__file__).resolve().parents[2]
        / "custom_components" / "freebox_homexa" / "sounds" / "alarme_bip.mp3"
    ).read_bytes()
    expected = b"\x00\x00\x00\x18ftypisom" + alarm
    assert response.headers["Content-Length"] == str(len(expected))
    assert await response.read() == expected
    with pytest.raises(HomeAssistantError) as refused:
        await entity.async_play_media("music", "freebox_homexa://sound/absent")
    assert refused.value.translation_key == "player_audio_refused"
    from homeassistant.components.media_source.error import Unresolvable
    with pytest.raises(Unresolvable):
        await source.async_resolve_media(MediaSourceItem(hass, DOMAIN, "sound/absent", None))
    hosted: list[str] = []
    with patch(
        "custom_components.freebox_homexa.player_audio.get_url",
        return_value="http://homeassistant.local:8123",
    ):
        for index in range(9):
            hosted.append(await async_host_bytes(hass, f"clip-{index}", b"\xff\xfb" + bytes([index]) * 16))
    client = await hass_client()
    oldest = urlsplit(hosted[0])
    newest = urlsplit(hosted[-1])
    assert (await client.get(f"{oldest.path}?{oldest.query}")).status == 404
    assert (await client.get(f"{newest.path}?{newest.query}")).status == 200


def _enable_remote(hass, router, code: str = "12345678") -> None:
    entry = hass.config_entries.async_get_entry(router.entry_id)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "remote_code": code}
    )


async def test_ok_is_sent_twice_at_most_when_the_chooser_stays(hass, home_context, caplog):
    router, entity = _entity(hass, home_context)
    _enable_remote(hass, router)
    keys: list[str] = []

    async def send_airmedia(_name: str, _data: dict[str, object]) -> None:
        raise RuntimeError("unimplemented")

    async def send_key(**kwargs: object) -> bool:
        keys.append(str(kwargs.get("key")))
        return True

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = AsyncMock()
    router._api.remote.send_key = send_key
    with caplog.at_level("DEBUG"), _patch_status([TV]), _patch_sleep():
        with pytest.raises(HomeAssistantError) as caught:
            await entity.async_play_media("audio/mpeg", AUDIO)
    assert caught.value.translation_key == "player_audio_silent"
    assert keys == ["ok", "ok"]
    assert "12345678" not in caplog.text
    assert TOKEN not in caplog.text
    assert "192.0.2.10" not in caplog.text


async def test_ok_stops_when_the_media_player_starts(hass, home_context):
    router, entity = _entity(hass, home_context)
    _enable_remote(hass, router)
    keys: list[str] = []

    async def send_airmedia(_name: str, _data: dict[str, object]) -> None:
        raise RuntimeError("unimplemented")

    async def send_key(**kwargs: object) -> bool:
        keys.append(str(kwargs.get("key")))
        return True

    playing = {
        "playback_state": "playing",
        "foreground_app": {"package": "fr.freebox.mediaplayer", "cur_url": "video/mp4"},
    }
    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = AsyncMock()
    router._api.remote.send_key = send_key
    with _patch_status([TV, TV, playing]), _patch_sleep():
        await entity.async_play_media("audio/mpeg", AUDIO)
    assert keys == ["ok"]


async def test_ok_is_not_sent_when_playback_already_started(hass, home_context):
    router, entity = _entity(hass, home_context)
    _enable_remote(hass, router)
    keys: list[str] = []

    async def send_airmedia(_name: str, _data: dict[str, object]) -> None:
        raise RuntimeError("unimplemented")

    async def send_key(**kwargs: object) -> bool:
        keys.append(str(kwargs.get("key")))
        return True

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = AsyncMock()
    router._api.remote.send_key = send_key
    with _patch_status([TV, STARTED]), _patch_sleep():
        await entity.async_play_media("audio/mpeg", AUDIO)
    assert keys == []


async def test_ok_is_not_sent_when_mediaplayer_is_already_foreground(hass, home_context):
    router, entity = _entity(hass, home_context)
    _enable_remote(hass, router)
    keys: list[str] = []
    same = {
        "playback_state": "playing",
        "foreground_app": {"package": "fr.freebox.mediaplayer", "cur_url": "app:media"},
    }

    async def send_airmedia(_name: str, _data: dict[str, object]) -> None:
        raise RuntimeError("unimplemented")

    async def send_key(**kwargs: object) -> bool:
        keys.append(str(kwargs.get("key")))
        return True

    router._api.airmedia.get_airmedia_receivers = AsyncMock(return_value=_receivers())
    router._api.airmedia.send_airmedia = send_airmedia
    router._api.player._access.post = AsyncMock()
    router._api.remote.send_key = send_key
    with _patch_status([same]), _patch_sleep():
        with pytest.raises(HomeAssistantError) as caught:
            await entity.async_play_media("audio/mpeg", AUDIO)
    assert caught.value.translation_key == "player_audio_silent"
    assert keys == []


async def test_mp4_wrapper_uses_a_black_frame_and_aac(hass):
    from types import SimpleNamespace
    from pathlib import Path

    from homeassistant.components.ffmpeg import DATA_FFMPEG

    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="synthetic-ffmpeg")
    seen: list[tuple[object, ...]] = []

    class _Process:
        returncode = 0

        async def communicate(self, _data: bytes) -> tuple[bytes, bytes]:
            return b"", b""

    async def fake_exec(*args: object, **_kwargs: object) -> _Process:
        seen.append(args)
        Path(str(args[-1])).write_bytes(b"\x00\x00\x00\x18ftypisom")
        return _Process()

    with patch(
        "custom_components.freebox_homexa.player_audio.asyncio.create_subprocess_exec",
        new=fake_exec,
    ):
        body = await _real_audio_to_mp4(hass, b"ID3siren")
    assert body.startswith(b"\x00\x00\x00\x18ftypisom")
    command = [str(part) for part in seen[0]]
    assert "color=c=black:s=64x64:r=1" in command
    assert "aac" in command
    assert "libx264" in command
    assert "mp4" in command
    assert "http://" not in " ".join(command)
