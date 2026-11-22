"""DECT ring, handset state and voicemail. No Freebox, no real numbers in logs."""
import logging
import re
import struct
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from freebox_api.api.phone import Phone
from freebox_api.exceptions import HttpRequestError, InsufficientPermissionsError
import pytest
from homeassistant.components.ffmpeg import DATA_FFMPEG
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir

from custom_components.freebox_homexa.binary_sensor import async_setup_entry as setup_binary
from custom_components.freebox_homexa.button import async_setup_entry as setup_buttons
from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.fxs_ring import FXS_RING_MAX_SECONDS, FXS_RING_MIN_SECONDS
from custom_components.freebox_homexa.phone_dect import (
    DECT_RING_DEFAULT_SECONDS,
    async_dect_start,
    async_dect_stop,
    async_release_dect_ring,
    parse_handsets,
)
from custom_components.freebox_homexa.repairs import permission_issue_id
from custom_components.freebox_homexa.sensor import async_setup_entry as setup_sensors
from custom_components.freebox_homexa.services import async_setup_services
from custom_components.freebox_homexa.voicemail import (
    NEW_VOICEMAIL_EVENT,
    parse_voicemails,
    public_summary,
    tokens_of,
    validated_voicemail_id,
)
from custom_components.freebox_homexa.voicemail_audio import (
    async_play_on_player,
    async_register_voicemail_view,
    async_wav_to_mp3,
)
from custom_components.freebox_homexa.voicemail_ws import async_register_voicemail_websocket_api
from homeassistant.setup import async_setup_component
from test_home_platforms import home_context, make_platform

_LOG = "custom_components.freebox_homexa"

SECRET = "0612345678"
MESSAGE = "20221215_154135_r0999999999.au"


def alaw_wav() -> bytes:
    fmt = struct.pack("<HHIIHH", 6, 1, 8000, 8000, 1, 8)
    data = bytes((0xD5, 0x55))
    chunks = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(chunks)) + chunks


def au_snd() -> bytes:
    data = bytes((0xD5, 0x55))
    return struct.pack(">4sIIIII", b".snd", 24, len(data), 27, 8000, 1) + data
PHONES = [
    {"id": 1, "type": "fxs", "is_ringing": False, "on_hook": True, "vendor": "Free"},
    {"id": 2, "type": "dect", "is_ringing": True, "on_hook": False, "vendor": "Gigaset",
     "phone_number": SECRET},
    {"id": 3, "type": "DECT", "is_ringing": "nope", "on_hook": None, "vendor": SECRET},
]


def http_error(code: str) -> HttpRequestError:
    payload = '{"success": false, "error_code": "%s", "msg": "appel %s"}' % (code, SECRET)
    return HttpRequestError(f"Request failed (APIResponse: {payload})")


def permission_error() -> InsufficientPermissionsError:
    payload = (
        '{"success": false, "error_code": "insufficient_rights", '
        f'"missing_right": "calls", "msg": "appel {SECRET}"}}'
    )
    return InsufficientPermissionsError(f"Request failed (APIResponse: {payload})")


class Script:
    def __init__(self) -> None:
        self.paths: list[tuple[object, ...]] = []
        self.phones: object = list(PHONES)
        self.messages: object = []
        self.audio: object = b"RIFF-wav"
        self.error_on: str | None = None
        self.error: BaseException | None = None
        self.status: int | None = None

    async def get(self, path: str) -> object:
        self.paths.append(("get", path))
        if self.status == 404 and "voicemail" in path:
            return NotFound()
        if self.error is not None and (self.error_on is None or self.error_on in path):
            raise self.error
        if path == "phone/":
            return self.phones
        if path == "call/voicemail/":
            return self.messages
        if path.endswith("/audio_file"):
            return self.audio
        raise AssertionError(path)

    async def post(self, path: str, payload: object = None) -> None:
        self.paths.append(("post", path))
        if self.error is not None and (self.error_on is None or self.error_on in path):
            raise self.error

    async def put(self, path: str, payload: object = None) -> None:
        self.paths.append(("put", path, payload))
        if self.error is not None and (self.error_on is None or "voicemail" in path):
            raise self.error

    async def delete(self, path: str, payload: object = None) -> None:
        self.paths.append(("delete", path))
        if self.error is not None:
            raise self.error


def bind(router) -> Script:
    script = Script()
    router._api.phone = Phone(script)
    router._api.call._access = script
    return script


def load(hass, router) -> None:
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    hass.data.setdefault(DOMAIN, {})


def message(read: bool = False, ident: str = MESSAGE) -> dict[str, object]:
    return {
        "id": ident,
        "country_code": "33",
        "phone_number": SECRET,
        "date": 1671111695,
        "read": read,
        "duration": 12,
        "name": "Martin",
    }


class Collector:
    def __init__(self) -> None:
        self.entities: list[object] = []

    def add(self, entities, update: bool = False) -> None:
        self.entities.extend(entities)


def test_parse_keeps_fxs_and_dect_without_publishing_the_number():
    handsets = parse_handsets(PHONES)
    assert [item.kind for item in handsets] == ["fxs", "dect", "dect"]
    assert handsets[1].ringing is True and handsets[1].on_hook is False
    assert handsets[2].ringing is None and handsets[2].on_hook is None
    assert SECRET not in repr(handsets)
    assert parse_handsets(None) == []
    with pytest.raises(ValueError):
        parse_handsets({"id": 1})
    messages = parse_voicemails([message(), {"id": "other.au", "read": True, "date": 10, "duration": 1}])
    assert messages[0].phone_number == SECRET
    assert SECRET not in repr(messages[0])
    summary = public_summary(messages)
    assert summary["total"] == 2
    assert SECRET not in str(summary)
    assert "phone_number" not in str(summary)
    with pytest.raises(ServiceValidationError) as exc:
        validated_voicemail_id("../" + SECRET)
    assert exc.value.translation_key == "voicemail_invalid_id"
    assert SECRET not in str(exc.value)


async def test_dect_buttons_and_handset_sensors_follow_the_phone_list(hass, home_context):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    router.players_initialized = True
    router.players = []
    await router._update_phones()
    buttons = Collector()
    binary = Collector()
    await setup_buttons(hass, hass.config_entries.async_get_entry(router.entry_id), buttons.add)
    await setup_binary(hass, hass.config_entries.async_get_entry(router.entry_id), binary.add)
    dect_buttons = [entity for entity in buttons.entities if "DECT" in str(entity.unique_id)]
    assert [entity.unique_id for entity in dect_buttons] == [
        f"{router.mac} Faire sonner les combinés DECT",
        f"{router.mac} Arrêter la sonnerie DECT",
    ]
    sensors = [entity for entity in binary.entities if " dect " in str(entity.unique_id)]
    assert {entity.unique_id for entity in sensors} == {
        f"{router.mac} dect 2 sonne",
        f"{router.mac} dect 2 decroche",
        f"{router.mac} dect 3 sonne",
        f"{router.mac} dect 3 decroche",
    }
    ringing = next(entity for entity in sensors if entity.unique_id.endswith("2 sonne"))
    off = next(entity for entity in sensors if entity.unique_id.endswith("2 decroche"))
    unknown = next(entity for entity in sensors if entity.unique_id.endswith("3 decroche"))
    assert ringing.is_on is True
    assert off.is_on is True
    assert unknown.is_on is None
    assert SECRET not in str(ringing.extra_state_attributes)
    script.phones = [item for item in PHONES if item["type"] == "fxs"]
    await router._update_phones()
    ringing.async_write_ha_state = lambda: None
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    async_dispatcher_send(hass, router.signal_sensor_update)
    await hass.async_block_till_done()
    assert ringing.available is False


async def test_dect_ring_duration_stop_and_errors(hass, home_context, caplog):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    async_setup_services(hass)

    async def immediate(_seconds: float) -> None:
        seen.append(_seconds)

    seen: list[float] = []
    with caplog.at_level(logging.DEBUG, logger=_LOG), patch(
        "custom_components.freebox_homexa.fxs_ring._pause", immediate
    ):
        await hass.services.async_call(DOMAIN, "start_dect_ring", {}, blocking=True)
    assert seen == [float(DECT_RING_DEFAULT_SECONDS)]
    assert ("post", "phone/dect_page_start/") in script.paths
    assert ("post", "phone/dect_page_stop/") in script.paths
    assert SECRET not in caplog.text

    script.paths.clear()
    with patch("custom_components.freebox_homexa.fxs_ring._pause", immediate):
        await async_dect_start(router, 5)
    assert script.paths == [("post", "phone/dect_page_start/"), ("post", "phone/dect_page_stop/")]

    script.paths.clear()
    script.error = permission_error()
    script.error_on = "dect_page"
    with pytest.raises(HomeAssistantError) as denied:
        await async_dect_start(router, 2)
    assert denied.value.translation_key == "dect_ring_permission"
    assert SECRET not in str(denied.value)
    assert ("post", "phone/dect_page_stop/") in script.paths

    script.paths.clear()
    script.error = http_error("dect_disabled")
    with pytest.raises(HomeAssistantError) as disabled:
        await async_dect_stop(router)
    assert disabled.value.translation_key == "dect_ring_disabled"
    assert SECRET not in str(disabled.value)

    script.error = None
    with pytest.raises(ServiceValidationError) as bounds:
        await hass.services.async_call(
            DOMAIN, "start_dect_ring", {"duration": 0}, blocking=True
        )
    assert bounds.value.translation_key == "dect_ring_duration"
    assert bounds.value.translation_placeholders == {
        "minimum": str(FXS_RING_MIN_SECONDS),
        "maximum": str(FXS_RING_MAX_SECONDS),
    }
    await async_dect_start(router, 0.01)
    await async_release_dect_ring(router)


async def test_voicemail_sensor_event_repair_and_actions(hass, home_context, caplog):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    async_setup_services(hass)
    events: list[dict[str, object]] = []
    hass.bus.async_listen(NEW_VOICEMAIL_EVENT, lambda event: events.append(dict(event.data)))
    script.messages = [message()]
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        await router._update_voicemails()
        await hass.async_block_till_done()
    assert events == []
    assert SECRET not in caplog.text
    sensors = Collector()
    entry = hass.config_entries.async_get_entry(router.entry_id)
    await setup_sensors(hass, entry, sensors.add)
    sensor = next(entity for entity in sensors.entities if entity.unique_id.endswith("Messages vocaux non lus"))
    platform = make_platform(hass, "sensor")
    await platform.async_add_entities([sensor])
    await hass.async_block_till_done()
    state = hass.states.get(sensor.entity_id)
    assert state.state == "1"
    assert SECRET not in str(state.attributes)
    assert MESSAGE not in str(state.attributes)
    assert state.attributes["total"] == 1
    assert state.attributes["voicemail"] is True
    assert state.attributes["voicemail_available"] is True
    assert state.attributes["voicemail_supported"] is True
    assert state.attributes["voicemail_error"] is None

    script.messages = [message(), message(ident="fresh.au")]
    await router._update_voicemails()
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0]["id"] != "fresh.au"
    assert "fresh.au" not in str(events[0])
    assert MESSAGE not in str(events[0])
    assert "phone_number" not in events[0]
    assert SECRET not in str(events[0])
    assert re.fullmatch(r"[0-9a-f]{64}", str(events[0]["id"]))

    await hass.services.async_call(
        DOMAIN, "mark_voicemail_read", {"id": tokens_of(router).issue(MESSAGE)}, blocking=True
    )
    assert ("put", f"call/voicemail/{MESSAGE}", {"read": True}) in script.paths
    assert events[0]["caller"] == "Martin"
    assert events[0]["name"] == "Martin"
    assert "number" not in events[0]
    await hass.services.async_call(
        DOMAIN, "delete_voicemail", {"id": events[0]["id"]}, blocking=True
    )
    assert ("delete", "call/voicemail/fresh.au") in script.paths
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "delete_voicemail", {"id": f"../{SECRET}"}, blocking=True
        )
    assert SECRET not in caplog.text

    script.error = permission_error()
    script.error_on = "voicemail"
    script.messages = [message()]
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        await router._update_voicemails()
    assert router.voicemail_available is False
    issue = ir.async_get(hass).async_get_issue(DOMAIN, permission_issue_id(router.entry_id, "calls"))
    assert issue is not None
    assert SECRET not in caplog.text
    sensor.async_write_ha_state()
    assert hass.states.get(sensor.entity_id).state == "unavailable"
    script.error = None
    router.calls_available = True
    await router._update_voicemails()
    assert router.voicemail_available is True
    assert ir.async_get(hass).async_get_issue(DOMAIN, permission_issue_id(router.entry_id, "calls")) is None
    await platform.async_reset()


async def test_audio_view_auth_signed_path_and_mp3(
    hass, hass_client, hass_client_no_auth, home_context, caplog
):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    script.messages = [message()]
    await router._update_voicemails()
    assert await async_setup_component(hass, "http", {"http": {}})
    async_register_voicemail_view(hass)
    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="synthetic-ffmpeg")
    client = await hass_client()
    anonymous = await hass_client_no_auth()
    public = tokens_of(router).issue(MESSAGE)
    path = f"/api/freebox_homexa/voicemail/{router.entry_id}/{public}"
    assert MESSAGE not in path
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        denied = await anonymous.get(path)
    assert denied.status == 401

    class Process:
        returncode = 0

        async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
            assert data.startswith(b"RIFF")
            return b"mp3-bytes", b""

    script.audio = alaw_wav()
    with patch(
        "custom_components.freebox_homexa.voicemail_audio.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=Process()),
    ):
        ok = await client.get(path)
    assert ok.status == 200
    assert ok.headers["Content-Type"] == "audio/mpeg"
    mpeg = await ok.read()
    assert mpeg == b"mp3-bytes"
    assert int(ok.headers["Content-Length"]) == len(mpeg)
    assert any(
        item[0] == "get" and item[1].endswith("/audio_file") and ".au" in item[1] and "%2E" not in item[1]
        for item in script.paths
    )
    wav = await client.get(path + "?codec=wav")
    assert wav.status == 200
    assert wav.headers["Content-Type"] == "audio/wav"
    raw = await wav.read()
    assert raw == script.audio
    assert int(wav.headers["Content-Length"]) == len(raw)
    missing = await client.get(f"/api/freebox_homexa/voicemail/{router.entry_id}/a%20b")
    assert missing.status == 404
    own = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith(_LOG)
    )
    assert SECRET not in own
    script.error = permission_error()
    script.error_on = "audio_file"
    router.voicemail_mp3_cache.clear()
    forbidden = await client.get(path)
    assert forbidden.status == 403
    assert SECRET not in caplog.text
    script.error = None

    from custom_components.freebox_homexa.voicemail_audio import signed_voicemail_path
    signed = signed_voicemail_path(hass, router.entry_id, public, mp3=False)
    assert MESSAGE not in signed
    opened = await anonymous.get(signed)
    assert opened.status == 200


async def test_play_marks_read_and_echo_needs_a_public_url(hass, home_context, caplog):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    assert await async_setup_component(hass, "http", {"http": {}})
    script.messages = [message()]
    await router._update_voicemails()
    played: list[dict[str, object]] = []

    async def play(call) -> None:
        played.append(dict(call.data))

    hass.services.async_register("media_player", "play_media", play)
    hass.states.async_set("media_player.box", "idle", {"friendly_name": "Salon"})
    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="synthetic-ffmpeg")
    with patch(
        "custom_components.freebox_homexa.voicemail_audio.get_url",
        return_value="http://homeassistant.local:8123",
    ), caplog.at_level(logging.DEBUG, logger=_LOG):
        played_id = tokens_of(router).issue(MESSAGE)
        await async_play_on_player(hass, router, played_id, "media_player.box")
    assert played and played[0]["media_content_type"] == "audio/mpeg"
    assert "codec=mp3" in str(played[0]["media_content_id"])
    assert SECRET not in str(played) and MESSAGE not in str(played) and SECRET not in caplog.text
    assert any(item[0] == "put" for item in script.paths)

    hass.states.async_set("media_player.echo", "idle", {"friendly_name": "Echo cuisine"})
    from homeassistant.helpers.network import NoURLAvailableError

    def external(hass, **kwargs):
        if kwargs.get("allow_internal") is False:
            raise NoURLAvailableError
        return "http://homeassistant.local:8123"

    before = len([item for item in script.paths if item[0] == "put"])
    with patch("custom_components.freebox_homexa.voicemail_audio.get_url", side_effect=external):
        with pytest.raises(HomeAssistantError) as exc:
            await async_play_on_player(hass, router, tokens_of(router).issue(MESSAGE), "media_player.echo")
    assert exc.value.translation_key == "voicemail_public_url"
    assert len([item for item in script.paths if item[0] == "put"]) == before
    with pytest.raises(ServiceValidationError) as missing:
        await async_play_on_player(hass, router, MESSAGE, "light.lampe")
    assert missing.value.translation_key == "voicemail_player"
    with pytest.raises(HomeAssistantError):
        await async_wav_to_mp3(hass, b"RIFF-wav")


async def test_media_source_browse_and_resolve_hide_numbers(hass, home_context):
    from custom_components.freebox_homexa.media_source import async_get_media_source
    from homeassistant.components.media_source.models import MediaSourceItem

    router, _node = home_context
    script = bind(router)
    load(hass, router)
    assert await async_setup_component(hass, "http", {"http": {}})
    script.messages = [message()]
    await router._update_voicemails()
    source = await async_get_media_source(hass)
    assert source.name == "Freebox – Messagerie vocale"
    root = await source.async_browse_media(MediaSourceItem(hass, DOMAIN, "", None))
    assert SECRET not in root.title
    dumped = str([getattr(child, "title", "") for child in (root.children or [])])
    assert SECRET not in dumped
    child = (root.children or [None])[0]
    assert child is not None
    assert MESSAGE not in child.identifier
    assert SECRET not in child.identifier
    item = MediaSourceItem(hass, DOMAIN, child.identifier, None)
    with patch(
        "custom_components.freebox_homexa.voicemail_audio.get_url",
        return_value="http://homeassistant.local:8123",
    ):
        play = await source.async_resolve_media(item)
    assert play.mime_type == "audio/mpeg"
    assert "codec=mp3" in play.url
    assert SECRET not in play.url
    other = hass.config_entries.async_get_entry(router.entry_id)
    assert other is not None
    folder = await source.async_browse_media(
        MediaSourceItem(hass, DOMAIN, router.entry_id, None)
    )
    assert folder.can_expand is True
    leaf = await source.async_browse_media(item)
    assert leaf.can_play is True
    assert SECRET not in leaf.title


async def test_voicemail_websocket_list_read_delete_and_privacy(
    hass, hass_ws_client, home_context, caplog
):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    script.messages = [message()]
    await router._update_voicemails()
    from homeassistant.helpers import entity_registry as er

    entry = hass.config_entries.async_get_entry(router.entry_id)
    row = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{router.mac} Messages vocaux non lus", config_entry=entry
    )
    async_register_voicemail_websocket_api(hass)
    client = await hass_ws_client(hass)
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        await client.send_json_auto_id({
            "type": "freebox_homexa/voicemails",
            "entity_id": row.entity_id,
        })
        listed = await client.receive_json()
    assert listed["success"] is True
    assert listed["result"]["unread"] == 1
    assert listed["result"]["available"] is True
    assert SECRET not in str(listed)
    assert MESSAGE not in str(listed)
    public = listed["result"]["messages"][0]["id"]
    assert public != MESSAGE
    await client.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "list",
        "entity_id": row.entity_id,
        "include_number": True,
    })
    shown = await client.receive_json()
    assert shown["result"]["messages"][0]["phone_number"] == SECRET
    await client.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "audio_url",
        "entity_id": row.entity_id,
        "message_id": public,
    })
    audio = await client.receive_json()
    assert audio["success"] is True
    assert audio["result"]["url"].startswith("/api/freebox_homexa/voicemail/")
    assert SECRET not in audio["result"]["url"]
    assert MESSAGE not in audio["result"]["url"]
    await client.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "mark_read",
        "entity_id": row.entity_id,
        "message_id": public,
    })
    marked = await client.receive_json()
    assert marked["success"] is True
    await client.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "delete",
        "entity_id": row.entity_id,
        "message_id": "../secret",
    })
    rejected = await client.receive_json()
    assert rejected["success"] is False
    assert rejected["error"]["code"] == "invalid_format"
    own = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith(_LOG)
    )
    assert SECRET not in own
    await client.send_json_auto_id({"type": "freebox_homexa/voicemails", "action": "nope"})
    assert (await client.receive_json())["success"] is False


async def test_remaining_phone_and_voicemail_branches(
    hass, hass_client, hass_client_no_auth, hass_ws_client, hass_read_only_access_token, home_context
):
    """Branches de validation, droits, lecteur et source média. Toujours sans numéro journalisé."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from homeassistant.components.media_source.models import MediaSourceItem
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.network import NoURLAvailableError

    from custom_components.freebox_homexa.media_source import (
        _children,
        async_get_media_source,
    )
    from custom_components.freebox_homexa.phone_dect import (
        FreeboxDectBinarySensor,
        _invoke_dect,
        async_dect_controller,
        async_refresh_phones,
    )
    from custom_components.freebox_homexa.voicemail import parse_voicemails

    router, _node = home_context
    script = bind(router)
    load(hass, router)
    assert await async_setup_component(hass, "http", {"http": {}})
    async_setup_services(hass)
    for bad in (
        [{"id": True, "type": "dect"}],
        [{"id": 1, "type": ""}],
        [{"id": "a/b", "type": "dect"}],
        [{"id": "x" * 65, "type": "dect"}],
        ["nope"],
    ):
        with pytest.raises(ValueError):
            parse_handsets(bad)
    assert parse_voicemails(None) == []
    parsed = parse_voicemails([{"id": "a.au", "date": -1, "duration": True, "read": "yes"}])
    assert parsed[0].date == 0 and parsed[0].duration == 0 and parsed[0].read is False
    assert parse_voicemails([{"id": ""}, {"id": 4242, "read": True, "date": 3, "duration": 2}, "bad"])[0].id == "4242"
    with pytest.raises(ValueError):
        parse_voicemails({"id": "nope"})

    router.closing = True
    script.error = RuntimeError("closed")
    await async_refresh_phones(router)
    await router._update_voicemails()
    router.closing = False
    script.error = None
    router.phones_available = False
    script.phones = list(PHONES)
    await async_refresh_phones(router)
    assert router.phones_available is True

    async def boom() -> None:
        raise OSError("synthetic")

    with pytest.raises(OSError):
        await _invoke_dect(boom)

    async def translated() -> None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="command_failed")

    with pytest.raises(HomeAssistantError):
        await _invoke_dect(translated)
    hass.data[DOMAIN] = "not-a-bucket"
    with pytest.raises(HomeAssistantError):
        async_dect_controller(hass)
    hass.data[DOMAIN] = {}
    await async_release_dect_ring(router)

    script.phones = list(PHONES)
    await async_refresh_phones(router)
    sensor = FreeboxDectBinarySensor(router, "2", "ringing")
    platform = make_platform(hass, "binary_sensor")
    await platform.async_add_entities([sensor])
    await hass.async_block_till_done()
    router.phones = []
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    async_dispatcher_send(hass, router.signal_sensor_update)
    await hass.async_block_till_done()
    assert sensor.is_on is None
    await platform.async_reset()

    script.messages = [message()]
    await router._update_voicemails()

    class Raw:
        def __init__(self, body: object, await_release: bool = False) -> None:
            self._body = body
            self.await_release = await_release

        async def read(self) -> object:
            return self._body

        def release(self) -> object:
            if self.await_release:
                async def _done() -> None:
                    return None
                return _done()
            return None

    script.audio = Raw(b"wav")
    assert await script.get("call/voicemail/x/audio_file")
    from custom_components.freebox_homexa.voicemail import async_voicemail_audio
    script.paths.clear()
    script.audio = Raw("audio", await_release=True)
    heard = tokens_of(router).issue(MESSAGE)
    assert await async_voicemail_audio(router, heard) == b"audio"
    script.audio = Raw(1)
    with pytest.raises(HomeAssistantError):
        await async_voicemail_audio(router, heard)
    script.audio = object()
    with pytest.raises(HomeAssistantError):
        await async_voicemail_audio(router, heard)
    script.audio = b"RIFF-wav"
    script.error = permission_error()
    script.error_on = "voicemail"
    with pytest.raises(HomeAssistantError) as denied:
        await async_delete_voicemail_direct(router)
    assert denied.value.translation_key == "voicemail_permission"
    script.error = None

    async def immediate(_seconds: float) -> None:
        return None

    with patch("custom_components.freebox_homexa.fxs_ring._pause", immediate):
        await hass.services.async_call(
            DOMAIN, "start_dect_ring", {"duration": 12}, blocking=True
        )
    await hass.services.async_call(DOMAIN, "stop_dect_ring", {}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "mark_voicemail_read", {"id": 5}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "play_voicemail", {"id": MESSAGE}, blocking=True)
    hass.states.async_set("media_player.box", "idle")

    async def _play(call) -> None:
        return None

    hass.services.async_register("media_player", "play_media", _play)
    with patch(
        "custom_components.freebox_homexa.voicemail_audio.get_url",
        return_value="http://homeassistant.local:8123",
    ):
        await hass.services.async_call(
            DOMAIN,
            "play_voicemail",
            {"id": tokens_of(router).issue(MESSAGE), "entity_id": "media_player.box"},
            blocking=True,
        )
    with pytest.raises(ServiceValidationError):
        await async_play_on_player(hass, router, MESSAGE, "media_player.absent")

    registry = er.async_get(hass)
    registry.async_get_or_create("media_player", "alexa_media", "echo", suggested_object_id="echo_box")
    echo = registry.async_get_entity_id("media_player", "alexa_media", "echo")
    assert echo is not None
    hass.states.async_set(echo, "idle")
    from custom_components.freebox_homexa.voicemail_audio import player_needs_mp3
    assert player_needs_mp3(hass, echo) is True

    class BadProcess:
        returncode = 1

        async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
            return b"", b""

    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="synthetic-ffmpeg")
    with patch(
        "custom_components.freebox_homexa.voicemail_audio.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=BadProcess()),
    ):
        with pytest.raises(HomeAssistantError) as failed_mp3:
            await async_wav_to_mp3(hass, b"RIFF")
    assert failed_mp3.value.translation_key == "voicemail_audio"

    async_register_voicemail_view(hass)
    async_register_voicemail_view(hass)
    row = registry.async_get_or_create(
        "sensor", DOMAIN, f"{router.mac} Messages vocaux non lus",
        config_entry=hass.config_entries.async_get_entry(router.entry_id),
    )
    async_register_voicemail_websocket_api(hass)
    limited = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await limited.send_json_auto_id({"type": "freebox_homexa/voicemails"})
    assert (await limited.receive_json())["error"]["code"] == "unauthorized"
    await limited.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "mark_read",
        "entity_id": row.entity_id,
        "message_id": MESSAGE,
    })
    assert (await limited.receive_json())["error"]["code"] == "unauthorized"
    admin = await hass_ws_client(hass)
    await admin.send_json_auto_id({"type": "freebox_homexa/voicemails", "codec": "ogg"})
    assert (await admin.receive_json())["success"] is False
    await admin.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "delete",
        "entity_id": "sensor.unknown",
        "message_id": MESSAGE,
    })
    assert (await admin.receive_json())["error"]["code"] == "not_found"
    await admin.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "audio_url",
        "entity_id": row.entity_id,
        "message_id": MESSAGE,
        "codec": "mp3",
        "config_entry_id": "other",
    })
    assert (await admin.receive_json())["error"]["code"] == "invalid_format"
    script.error = permission_error()
    script.error_on = "voicemail"
    await admin.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "mark_read",
        "config_entry_id": router.entry_id,
        "message_id": tokens_of(router).issue(MESSAGE),
    })
    assert (await admin.receive_json())["success"] is False
    script.error = OSError("synthetic")
    await admin.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "delete",
        "config_entry_id": router.entry_id,
        "message_id": tokens_of(router).issue(MESSAGE),
    })
    assert (await admin.receive_json())["success"] is False
    script.error = None
    script.error_on = None
    client = await hass_client()
    missing_box = await client.get("/api/freebox_homexa/voicemail/missing/a.au")
    assert missing_box.status == 404
    script.error = OSError("synthetic")
    script.error_on = "audio_file"
    broken = await client.get(
        f"/api/freebox_homexa/voicemail/{router.entry_id}/{tokens_of(router).issue(MESSAGE)}"
    )
    assert broken.status == 502
    script.error = None

    source = await async_get_media_source(hass)
    assert _children("entry", object()) == []
    with pytest.raises(Exception):
        await source.async_resolve_media(MediaSourceItem(hass, DOMAIN, "noslash", None))
    with pytest.raises(Exception):
        await source.async_browse_media(MediaSourceItem(hass, DOMAIN, "missing-entry", None))
    second = MockConfigEntry(domain=DOMAIN, data={}, title="Deuxième Freebox")
    second.add_to_hass(hass)
    second.runtime_data = router
    second.mock_state(hass, ConfigEntryState.LOADED)
    root = await source.async_browse_media(MediaSourceItem(hass, DOMAIN, "", None))
    assert root.can_expand is True
    assert len(root.children or []) == 2
    with patch(
        "custom_components.freebox_homexa.voicemail_audio.get_url",
        side_effect=NoURLAvailableError,
    ):
        with pytest.raises(Exception):
            await source.async_resolve_media(
                MediaSourceItem(
                    hass, DOMAIN, f"{router.entry_id}/{tokens_of(router).issue(MESSAGE)}", echo
                )
            )


async def test_last_coverage_gaps(hass, hass_ws_client, home_context):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from homeassistant.components.media_source.models import MediaSourceItem
    from homeassistant.helpers import entity_registry as er

    from custom_components.freebox_homexa.media_source import async_get_media_source
    from custom_components.freebox_homexa.phone_dect import async_dect_stop
    from custom_components.freebox_homexa.voicemail import (
        async_mark_voicemail_read,
        async_voicemail_audio,
        public_summary,
        parse_voicemails,
    )
    from custom_components.freebox_homexa.voicemail_audio import _ffmpeg_binary

    router, _node = home_context
    script = bind(router)
    load(hass, router)
    assert await async_setup_component(hass, "http", {"http": {}})
    script.messages = [message(ident="plain.au")]
    await router._update_voicemails()
    assert public_summary(parse_voicemails([{"id": "a.au", "date": 0}]))["latest"] is None
    kept = parse_voicemails(["not-a-dict", {"id": "kept.au", "date": 4, "duration": 1, "read": False}])
    assert [item.id for item in kept] == ["kept.au"]
    sensor = next(iter(()), None)
    from custom_components.freebox_homexa.voicemail import FreeboxVoicemailSensor
    entity = FreeboxVoicemailSensor(router)
    router.voicemail_available = False
    assert entity.native_value is None
    router.voicemail_available = True

    plain = tokens_of(router).issue("plain.au")
    script.error = HomeAssistantError(translation_domain=DOMAIN, translation_key="command_failed")
    script.error_on = "voicemail"
    with pytest.raises(HomeAssistantError):
        await async_mark_voicemail_read(router, plain)
    script.error = OSError("synthetic")
    with pytest.raises(HomeAssistantError) as failed_write:
        await async_mark_voicemail_read(router, plain)
    assert failed_write.value.translation_key == "voicemail_write_failed"
    script.error = None

    class Raw:
        async def read(self) -> bytearray:
            return bytearray(b"wav")
        def release(self) -> None:
            return None
    script.audio = Raw()
    assert await async_voicemail_audio(router, plain) == b"wav"
    hass.data.pop(DATA_FFMPEG, None)
    with pytest.raises(HomeAssistantError):
        _ffmpeg_binary(hass)

    saved = hass.data.pop(DOMAIN)
    await async_dect_stop(router)
    hass.data[DOMAIN] = saved

    source = await async_get_media_source(hass)
    with pytest.raises(Exception):
        await source.async_resolve_media(MediaSourceItem(hass, DOMAIN, f"{router.entry_id}/absent.au", None))
    with pytest.raises(Exception):
        await source.async_browse_media(MediaSourceItem(hass, DOMAIN, f"{router.entry_id}/absent.au", None))
    with pytest.raises(Exception):
        await source.async_resolve_media(MediaSourceItem(hass, DOMAIN, "entry/a/b", None))

    second = MockConfigEntry(domain=DOMAIN, data={})
    second.add_to_hass(hass)
    second.runtime_data = router
    second.mock_state(hass, ConfigEntryState.LOADED)
    unloaded = MockConfigEntry(domain=DOMAIN, data={})
    unloaded.add_to_hass(hass)
    registry = er.async_get(hass)
    foreign = registry.async_get_or_create(
        "sensor", DOMAIN, f"{router.mac} Messages vocaux non lus extra",
        config_entry=unloaded, suggested_object_id="foreign_voicemail",
    )
    # unique id must end with the voicemail suffix for the command to accept it.
    registry.async_update_entity(foreign.entity_id, new_unique_id=f"{router.mac} Messages vocaux non lus")
    async_register_voicemail_websocket_api(hass)
    admin = await hass_ws_client(hass)
    await admin.send_json_auto_id({"type": "freebox_homexa/voicemails"})
    assert (await admin.receive_json())["error"]["code"] == "not_found"
    await admin.send_json_auto_id({
        "type": "freebox_homexa/voicemails", "action": "mark_read", "config_entry_id": router.entry_id,
    })
    assert (await admin.receive_json())["success"] is False
    await admin.send_json_auto_id({
        "type": "freebox_homexa/voicemails", "config_entry_id": "missing-entry",
    })
    assert (await admin.receive_json())["error"]["code"] == "not_found"
    await admin.send_json_auto_id({
        "type": "freebox_homexa/voicemails", "entity_id": foreign.entity_id,
    })
    assert (await admin.receive_json())["error"]["code"] == "not_found"
    def fail_register(*_args, **_kwargs):
        raise RuntimeError("frozen")
    hass.http.register_view = fail_register
    async_register_voicemail_view(hass)


class VersionScript:
    """v6 puis, si besoin, la version annoncée. Pas de session : ``get('/api_version')``."""

    def __init__(self, *, fail_relative: bool, fail_absolute: bool = False, code: str = "invalid_request") -> None:
        self.paths: list[tuple[object, ...]] = []
        self.messages: object = []
        self.audio: object = b"RIFF-wav"
        self.fail_relative = fail_relative
        self.fail_absolute = fail_absolute
        self.code = code

    def _mismatch(self) -> HttpRequestError:
        return http_error(self.code)

    async def get(self, path: str) -> object:
        self.paths.append(("get", path))
        if path == "/api_version":
            return {"api_version": "10.4", "api_base_url": "/api/"}
        if path == "call/voicemail/" and self.fail_relative:
            raise self._mismatch()
        if path == "call/voicemail/":
            return self.messages
        if path == "/api/v10/call/voicemail/":
            if self.fail_absolute:
                raise self._mismatch()
            return self.messages
        if path.startswith("/api/v10/") and path.endswith("/audio_file"):
            return self.audio
        if path.endswith("/audio_file"):
            return self.audio
        raise AssertionError(path)

    async def put(self, path: str, payload: object = None) -> None:
        self.paths.append(("put", path, payload))
        if path.startswith("/api/v10/"):
            return None
        raise self._mismatch()

    async def delete(self, path: str, payload: object = None) -> None:
        self.paths.append(("delete", path))
        if not path.startswith("/api/v10/"):
            raise self._mismatch()


def test_parse_skips_a_bad_item_and_keeps_the_rest():
    kept = parse_voicemails([
        {"id": ""},
        "bad",
        {"id": 7, "read": False, "date": 8, "duration": 1, "phone_number": SECRET},
        message(),
    ])
    assert [item.id for item in kept] == ["7", MESSAGE]
    assert kept[0].phone_number == SECRET
    assert SECRET not in repr(kept[0])


async def test_relative_api_is_kept_when_voicemail_answers(hass, home_context):
    router, _node = home_context
    script = VersionScript(fail_relative=False)
    script.messages = [message()]
    router._api.call._access = script
    load(hass, router)
    await router._update_voicemails()
    assert script.paths == [("get", "call/voicemail/")]
    assert router.voicemail_api_prefix == ""
    assert router.voicemail_supported is True
    assert router.voicemail_available is True
    await router._update_voicemails()
    assert script.paths == [("get", "call/voicemail/"), ("get", "call/voicemail/")]


async def test_advertised_api_version_is_remembered_for_every_verb(hass, home_context):
    router, _node = home_context
    script = VersionScript(fail_relative=True)
    script.messages = [message()]
    router._api.call._access = script
    load(hass, router)
    await router._update_voicemails()
    assert ("get", "/api_version") in script.paths
    assert ("get", "/api/v10/call/voicemail/") in script.paths
    assert router.voicemail_api_prefix == "/api/v10/"
    assert router.voicemail_supported is True
    assert len(router.voicemails) == 1
    script.paths.clear()
    await router._update_voicemails()
    public = tokens_of(router).issue(MESSAGE)
    from custom_components.freebox_homexa.voicemail import (
        async_delete_voicemail,
        async_mark_voicemail_read,
        async_voicemail_audio,
    )
    await async_mark_voicemail_read(router, public)
    await async_delete_voicemail(router, public)
    await async_voicemail_audio(router, public)
    relative = [item for item in script.paths if isinstance(item[1], str) and item[1].startswith("call/")]
    assert relative == []
    assert any(isinstance(item[1], str) and item[1].startswith("/api/v10/call/voicemail/") for item in script.paths)
    assert any(item[0] == "put" for item in script.paths)
    assert any(item[0] == "delete" for item in script.paths)
    assert any(item[0] == "get" and str(item[1]).endswith("/audio_file") for item in script.paths)


async def test_missing_voicemail_api_stays_available_after_one_fallback(
    hass, hass_ws_client, home_context, caplog
):
    router, _node = home_context
    script = VersionScript(fail_relative=True, fail_absolute=True, code="invalid_request")
    router._api.call._access = script
    load(hass, router)
    sensors = Collector()
    entry = hass.config_entries.async_get_entry(router.entry_id)
    await setup_sensors(hass, entry, sensors.add)
    sensor = next(entity for entity in sensors.entities if str(entity.unique_id).endswith("Messages vocaux non lus"))
    platform = make_platform(hass, "sensor")
    await platform.async_add_entities([sensor])
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        await router._update_voicemails()
        await router._update_voicemails()
    assert router.voicemail_supported is False
    assert router.voicemail_available is True
    assert router.voicemail_error == "invalid_request"
    assert ("get", "/api_version") in script.paths
    assert ("get", "/api/v10/call/voicemail/") in script.paths
    version_calls = [item for item in script.paths if item[1] == "/api_version"]
    assert len(version_calls) == 1
    warnings = [
        record for record in caplog.records
        if record.levelno >= logging.WARNING and record.name.startswith(_LOG)
    ]
    assert warnings == []
    infos = [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]
    assert any("invalid_request" in message and "HttpRequestError" in message for message in infos)
    assert all(re.search(r"\d", message) is None for message in infos if "Messagerie" in message)
    assert SECRET not in caplog.text
    assert MESSAGE not in caplog.text
    sensor.async_write_ha_state()
    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state == "0"
    assert state.attributes["voicemail_supported"] is False
    assert state.attributes["voicemail_available"] is True
    assert state.attributes["voicemail_error"] == "invalid_request"
    from homeassistant.helpers import entity_registry as er
    row = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{router.mac} Messages vocaux non lus", config_entry=entry
    )
    async_register_voicemail_websocket_api(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/voicemails", "entity_id": row.entity_id})
    listed = await client.receive_json()
    assert listed["success"] is True
    assert listed["result"]["supported"] is False
    assert listed["result"]["available"] is True
    assert listed["result"]["messages"] == []
    assert SECRET not in str(listed)
    from custom_components.freebox_homexa.diagnostics import async_get_config_entry_diagnostics
    exported = await async_get_config_entry_diagnostics(hass, entry)
    assert exported["voicemail"]["supported"] is False
    assert exported["voicemail"]["error"] == "invalid_request"
    assert SECRET not in str(exported["voicemail"])
    assert MESSAGE not in str(exported["voicemail"])
    await platform.async_reset()


class NotFound:
    status = 404


async def test_http_404_then_advertised_version_is_not_supported(hass, home_context):
    router, _node = home_context

    class Gone(VersionScript):
        async def get(self, path: str) -> object:
            self.paths.append(("get", path))
            if path == "/api_version":
                return {"api_version": "8.0", "api_base_url": "/api/"}
            if path == "call/voicemail/":
                return NotFound()
            if path == "/api/v8/call/voicemail/":
                raise http_error("unsupported")
            raise AssertionError(path)

    script = Gone(fail_relative=True)
    router._api.call._access = script
    load(hass, router)
    await router._update_voicemails()
    assert router.voicemail_supported is False
    assert router.voicemail_available is True
    assert router.voicemail_error == "not_found"
    assert ("get", "/api/v8/call/voicemail/") in script.paths


async def test_real_voicemail_failure_is_visible_once(hass, hass_ws_client, home_context, caplog):
    router, _node = home_context
    script = bind(router)
    script.error = http_error("internal_error")
    script.error_on = "voicemail"
    load(hass, router)
    sensors = Collector()
    entry = hass.config_entries.async_get_entry(router.entry_id)
    await setup_sensors(hass, entry, sensors.add)
    sensor = next(entity for entity in sensors.entities if str(entity.unique_id).endswith("Messages vocaux non lus"))
    platform = make_platform(hass, "sensor")
    await platform.async_add_entities([sensor])
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        await router._update_voicemails()
        await router._update_voicemails()
    warnings = [
        record for record in caplog.records
        if record.levelno == logging.WARNING and record.name.startswith(_LOG) and "Messagerie" in record.getMessage()
    ]
    debugs = [
        record for record in caplog.records
        if record.levelno == logging.DEBUG and "momentanément" in record.getMessage()
    ]
    assert warnings == []
    assert debugs and "HttpRequestError" in debugs[0].getMessage()
    assert re.search(r"\d", debugs[0].getMessage()) is None
    assert SECRET not in debugs[0].getMessage()
    assert router.voicemail_available is True
    assert router.voicemail_loading is True
    assert router.voicemail_error == "internal_error"
    assert not any(item[1] == "/api_version" for item in script.paths)
    sensor.async_write_ha_state()
    assert hass.states.get(sensor.entity_id).state == "0"
    assert hass.states.get(sensor.entity_id).attributes["voicemail_loading"] is True
    from homeassistant.helpers import entity_registry as er
    row = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{router.mac} Messages vocaux non lus", config_entry=entry
    )
    async_register_voicemail_websocket_api(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/voicemails", "entity_id": row.entity_id})
    listed = await client.receive_json()
    assert listed["result"]["available"] is True
    assert listed["result"]["loading"] is True
    assert listed["result"]["error"] == "internal_error"
    assert listed["result"]["messages"] == []
    assert SECRET not in str(listed)
    router.voicemail_failure_since = time.monotonic() - 600
    router.voicemail_last_attempt = None
    from custom_components.freebox_homexa.voicemail import cancel_voicemail_retry
    cancel_voicemail_retry(router)
    await router._update_voicemails()
    assert router.voicemail_available is False
    assert router.voicemail_loading is False
    sensor.async_write_ha_state()
    assert hass.states.get(sensor.entity_id).state == "unavailable"
    await platform.async_reset()


async def test_au_and_alaw_are_transcoded_and_failures_do_not_log_ids(hass, caplog):
    from custom_components.freebox_homexa.voicemail_audio import async_wav_to_mp3

    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="synthetic-ffmpeg")
    seen: list[tuple[str, ...]] = []

    class Process:
        returncode = 0

        async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
            return b"ID3-mpeg", b""

    async def fake_exec(*args, **kwargs):
        seen.append(tuple(str(arg) for arg in args))
        return Process()

    with caplog.at_level(logging.DEBUG, logger=_LOG), patch(
        "custom_components.freebox_homexa.voicemail_audio.asyncio.create_subprocess_exec",
        new=fake_exec,
    ):
        assert await async_wav_to_mp3(hass, alaw_wav()) == b"ID3-mpeg"
        assert await async_wav_to_mp3(hass, au_snd()) == b"ID3-mpeg"
        ulaw = bytearray(alaw_wav())
        ulaw[20] = 7
        assert await async_wav_to_mp3(hass, bytes(ulaw)) == b"ID3-mpeg"
    assert seen[0][seen[0].index("-f") + 1] == "wav"
    assert seen[1][seen[1].index("-f") + 1] == "au"
    assert seen[2][seen[2].index("-f") + 1] == "wav"
    assert all("libmp3lame" in command for command in seen)

    class Bad:
        returncode = 1

        async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
            return b"", b""

    with caplog.at_level(logging.DEBUG, logger=_LOG), patch(
        "custom_components.freebox_homexa.voicemail_audio.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=Bad()),
    ):
        with pytest.raises(HomeAssistantError):
            await async_wav_to_mp3(hass, alaw_wav())
    warnings = [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]
    assert any("RIFF" in message and "ffmpeg" in message for message in warnings)
    assert SECRET not in caplog.text
    assert MESSAGE not in caplog.text


async def test_percent_dot_is_retried_after_404_and_audio_404_keeps_the_list(hass, home_context):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    script.messages = [message()]
    await router._update_voicemails()
    assert router.voicemail_api_prefix == ""

    class DotScript:
        def __init__(self) -> None:
            self.paths: list[str] = []

        async def get(self, path: str) -> object:
            self.paths.append(path)
            if path == "/api_version":
                raise AssertionError(path)
            if path.endswith("/audio_file") and "%2E" in path:
                return b"RIFF-ok"
            if "voicemail" in path:
                return NotFound()
            raise AssertionError(path)

        async def put(self, path: str, payload: object = None) -> None:
            self.paths.append(path)

        async def delete(self, path: str, payload: object = None) -> None:
            self.paths.append(path)

    dots = DotScript()
    router._api.call._access = dots
    from custom_components.freebox_homexa.voicemail import async_voicemail_audio

    heard = tokens_of(router).issue(MESSAGE)
    assert await async_voicemail_audio(router, heard) == b"RIFF-ok"
    assert any(path.endswith(".au/audio_file") and "%2E" not in path for path in dots.paths)
    assert any("%2Eau/audio_file" in path for path in dots.paths)
    assert router.voicemail_encode_dot is True
    assert router.voicemail_supported is True
    assert len(router.voicemails) == 1
    dots.paths.clear()
    assert await async_voicemail_audio(router, heard) == b"RIFF-ok"
    assert dots.paths == [f"call/voicemail/{MESSAGE.replace('.', '%2E')}/audio_file"]
    dots.paths.clear()

    class AlwaysMissing(DotScript):
        async def get(self, path: str) -> object:
            self.paths.append(path)
            if "audio_file" in path:
                return NotFound()
            raise AssertionError(path)

    missing = AlwaysMissing()
    router._api.call._access = missing
    with pytest.raises(Exception):
        await async_voicemail_audio(router, heard)
    assert router.voicemail_supported is True
    assert len(router.voicemails) == 1
    assert not any(path == "/api_version" for path in missing.paths)


async def test_v6_list_survives_a_later_404_and_an_omitted_result(hass, home_context, caplog):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    script.messages = [message()]
    await router._update_voicemails()
    assert router.voicemail_supported is True
    assert router.voicemail_api_prefix == ""
    script.messages = None
    await router._update_voicemails()
    assert len(router.voicemails) == 1
    script.messages = [message()]
    script.status = 404
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        await router._update_voicemails()
    assert router.voicemail_supported is True
    assert router.voicemail_available is True
    assert len(router.voicemails) == 1
    assert not any(item[1] == "/api_version" for item in script.paths)
    assert SECRET not in caplog.text
    assert MESSAGE not in caplog.text


async def test_websocket_list_matches_the_sensor_and_stays_available(hass, hass_ws_client, home_context):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    script.messages = [message()]
    await router._update_voicemails()
    sensors = Collector()
    entry = hass.config_entries.async_get_entry(router.entry_id)
    await setup_sensors(hass, entry, sensors.add)
    sensor = next(entity for entity in sensors.entities if str(entity.unique_id).endswith("Messages vocaux non lus"))
    platform = make_platform(hass, "sensor")
    await platform.async_add_entities([sensor])
    state = hass.states.get(sensor.entity_id)
    assert state is not None and state.state == "1"
    assert state.attributes["total"] == 1
    assert state.attributes["voicemail_available"] is True
    assert state.attributes["voicemail_supported"] is True
    token = state.attributes["messages"][0]["id"]
    assert re.fullmatch(r"[0-9a-f]{64}", token)
    assert SECRET not in str(state.attributes)
    assert MESSAGE not in str(state.attributes)
    from homeassistant.helpers import entity_registry as er

    row = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{router.mac} Messages vocaux non lus", config_entry=entry
    )
    async_register_voicemail_websocket_api(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/voicemails", "entity_id": row.entity_id})
    listed = await client.receive_json()
    assert listed["success"] is True
    assert listed["result"]["available"] is True
    assert listed["result"]["supported"] is True
    assert listed["result"]["total"] == 1
    assert listed["result"]["messages"][0]["id"] == token
    assert SECRET not in str(listed)
    assert MESSAGE not in str(listed)
    await client.send_json_auto_id({
        "type": "freebox_homexa/voicemails",
        "action": "audio_url",
        "entity_id": row.entity_id,
        "message_id": token,
    })
    audio = await client.receive_json()
    assert "codec=mp3" in audio["result"]["url"]
    script.error = OSError("synthetic")
    script.error_on = "voicemail"
    await router._update_voicemails()
    assert router.voicemail_available is True
    assert len(router.voicemails) == 1
    sensor.async_write_ha_state()
    assert hass.states.get(sensor.entity_id).state == "1"
    await platform.async_reset()


async def test_missed_call_and_voicemail_events_name_the_contact(hass, home_context, caplog):
    from custom_components.freebox_homexa.calls_ws import MISSED_CALL_EVENT
    from custom_components.freebox_homexa.const import CONF_EVENT_INCLUDE_NUMBER

    router, _node = home_context
    script = bind(router)
    load(hass, router)
    entry = hass.config_entries.async_get_entry(router.entry_id)
    missed: list[dict[str, object]] = []
    voices: list[dict[str, object]] = []
    hass.bus.async_listen(MISSED_CALL_EVENT, lambda event: missed.append(dict(event.data)))
    hass.bus.async_listen(NEW_VOICEMAIL_EVENT, lambda event: voices.append(dict(event.data)))
    router.call_list = [{
        "id": 7,
        "type": "missed",
        "name": SECRET,
        "number": SECRET,
        "datetime": 1671111695,
        "new": True,
    }]
    from custom_components.freebox_homexa.calls_ws import announce_missed_calls

    with caplog.at_level(logging.DEBUG, logger=_LOG):
        announce_missed_calls(router)
        announce_missed_calls(router)
    await hass.async_block_till_done()
    assert missed == []
    router.call_list.append({
        "id": 8,
        "type": "missed",
        "name": "Martin",
        "number": SECRET,
        "datetime": 1671111800,
        "new": True,
    })
    router.call_list.append({
        "id": 9,
        "type": "missed",
        "name": "",
        "number": "0699999999",
        "datetime": 1671111900,
        "new": True,
    })
    announce_missed_calls(router)
    await hass.async_block_till_done()
    by_caller = {item["caller"]: item for item in missed}
    assert by_caller["Martin"]["name"] == "Martin"
    assert "number" not in by_caller["Martin"]
    assert by_caller["Inconnu"]["caller"] == "Inconnu"
    assert "number" not in by_caller["Inconnu"]
    assert SECRET not in str(missed)
    assert "0699999999" not in str(missed)
    assert SECRET not in caplog.text
    updated = hass.config_entries.async_update_entry(entry, options={CONF_EVENT_INCLUDE_NUMBER: True})
    from custom_components.freebox_homexa.calls_ws import events_include_number
    assert updated is True
    assert events_include_number(router) is True
    router.call_list.append({
        "id": 10,
        "type": "missed",
        "name": "",
        "number": "0688888888",
        "datetime": 1671112000,
    })
    announce_missed_calls(router)
    await hass.async_block_till_done()
    numbered = next(item for item in missed if item.get("number") == "0688888888")
    assert numbered["caller"] == "0688888888"
    assert numbered["name"] == "Inconnu"
    script.messages = [message(ident="plain.au")]
    await router._update_voicemails()
    await hass.async_block_till_done()
    script.messages = [message(ident="plain.au"), message()]
    router.call_list.append({
        "id": 11,
        "type": "accepted",
        "name": "Nadia",
        "number": SECRET,
        "datetime": 1671111695,
    })
    await router._update_voicemails()
    await hass.async_block_till_done()
    assert voices and voices[0]["caller"] == "Nadia"
    assert voices[0]["name"] == "Nadia"
    assert voices[0]["number"] == SECRET
    assert MESSAGE not in str(voices[0])
    assert SECRET not in caplog.text


async def test_transient_voicemail_error_stays_available_and_retries(hass, home_context, caplog):
    from datetime import timedelta

    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.freebox_homexa.calls_ws import announce_missed_calls
    from custom_components.freebox_homexa.voicemail import VOICEMAIL_UNAVAILABLE_AFTER
    from homeassistant.util import dt as dt_util

    router, _node = home_context
    script = bind(router)
    load(hass, router)
    script.messages = [message()]
    await router._update_voicemails()
    assert router.voicemail_stale is False
    script.error = http_error("internal_error")
    script.error_on = "voicemail"
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        await router._update_voicemails()
        await router._update_voicemails()
    assert router.voicemail_available is True
    assert router.voicemail_stale is False
    assert router.voicemail_error is None
    assert router.voicemail_loading is False
    assert len(router.voicemails) == 1
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "momentanément" in record.getMessage()
    ]
    debugs = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.DEBUG and "momentanément" in record.getMessage()
    ]
    assert warnings == []
    assert debugs and "internal_error" in debugs[0]
    assert SECRET not in caplog.text
    assert MESSAGE not in caplog.text
    router.voicemail_failure_since = time.monotonic() - VOICEMAIL_UNAVAILABLE_AFTER
    router.voicemail_last_attempt = None
    from custom_components.freebox_homexa.voicemail import cancel_voicemail_retry
    cancel_voicemail_retry(router)
    await router._update_voicemails()
    assert router.voicemail_available is False
    assert router.voicemail_stale is True
    assert router.voicemail_error == "internal_error"
    assert len(router.voicemails) == 1
    script.error = None
    script.messages = [message(), message(ident="fresh.au")]
    cancel_voicemail_retry(router)
    router.voicemail_failure_since = None
    router.voicemail_last_attempt = None
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        await router._update_voicemails()
    assert router.voicemail_available is True
    assert router.voicemail_stale is False
    assert router.voicemail_error is None
    assert len(router.voicemails) == 2
    recovered = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "de nouveau disponible" in record.getMessage()
    ]
    assert len(recovered) == 1
    assert SECRET not in recovered[0] and MESSAGE not in recovered[0]

    script.error = TimeoutError("synthetic")
    script.error_on = "voicemail"
    router.voicemail_last_attempt = None
    before = dt_util.utcnow()
    await router._update_voicemails()
    assert router.voicemail_stale is False
    assert router.voicemail_error is None
    assert router.voicemail_available is True
    async_fire_time_changed(hass, before + timedelta(seconds=15))
    await hass.async_block_till_done()
    assert sum(1 for item in script.paths if item[0] == "get" and item[1] == "call/voicemail/") >= 2
    script.error = None
    await router._update_voicemails()
    script.paths.clear()
    router.call_list = [{"id": 1, "type": "missed", "name": "Martin", "number": SECRET, "datetime": 10}]
    announce_missed_calls(router)
    await hass.async_block_till_done()
    assert script.paths == []
    router.call_list.append({
        "id": 2, "type": "missed", "name": "Nadia", "number": SECRET, "datetime": 20,
    })
    announce_missed_calls(router)
    await hass.async_block_till_done()
    assert ("get", "call/voicemail/") in script.paths
    assert SECRET not in caplog.text


async def test_write_retries_advertised_version_and_transient_error(hass, home_context, caplog):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    script.messages = [message()]
    await router._update_voicemails()
    public = tokens_of(router).issue(MESSAGE)

    class Versioned(Script):
        async def put(self, path: str, payload: object = None) -> None:
            self.paths.append(("put", path, payload))
            if path.startswith("/api/v8/"):
                return None
            raise http_error("invalid_request")

        async def get(self, path: str) -> object:
            self.paths.append(("get", path))
            if path == "/api_version":
                return {"api_version": "8.0", "api_base_url": "/api/"}
            if path == "call/voicemail/":
                return self.messages
            raise AssertionError(path)

    versioned = Versioned()
    versioned.messages = [message(read=True)]
    router._api.call._access = versioned
    from custom_components.freebox_homexa.voicemail import async_mark_voicemail_read
    with caplog.at_level(logging.DEBUG, logger=_LOG):
        await async_mark_voicemail_read(router, public)
    assert any(path[1].startswith("/api/v8/call/voicemail/") for path in versioned.paths if path[0] == "put")
    assert SECRET not in caplog.text and MESSAGE not in caplog.text
    assert all(item.read for item in router.voicemails)

    class Flaky(Script):
        def __init__(self) -> None:
            super().__init__()
            self.puts = 0

        async def delete(self, path: str, payload: object = None) -> None:
            self.paths.append(("delete", path))
            self.puts += 1
            if self.puts < 2:
                raise http_error("internal_error")

        async def get(self, path: str) -> object:
            self.paths.append(("get", path))
            if "voicemail" in path and "audio" not in path and path.endswith("/"):
                return []
            return await super().get(path)

    flaky = Flaky()
    router._api.call._access = flaky
    router.voicemail_last_attempt = None
    from custom_components.freebox_homexa.voicemail import async_delete_voicemail
    await async_delete_voicemail(router, public)
    assert flaky.puts == 2
    assert router.voicemails == []


async def test_play_keeps_going_when_mark_read_fails(hass, home_context, caplog):
    router, _node = home_context
    script = bind(router)
    load(hass, router)
    assert await async_setup_component(hass, "http", {"http": {}})
    script.messages = [message()]
    await router._update_voicemails()
    played: list[dict[str, object]] = []

    async def play(call) -> None:
        played.append(dict(call.data))

    hass.services.async_register("media_player", "play_media", play)
    hass.states.async_set("media_player.box", "idle", {"friendly_name": "Salon"})
    script.error = http_error("internal_error")
    script.error_on = "voicemail"
    with patch(
        "custom_components.freebox_homexa.voicemail_audio.get_url",
        return_value="http://homeassistant.local:8123",
    ), caplog.at_level(logging.DEBUG, logger=_LOG):
        await async_play_on_player(hass, router, tokens_of(router).issue(MESSAGE), "media_player.box")
    assert played and played[0]["media_content_type"] == "audio/mpeg"
    assert "codec=mp3" in str(played[0]["media_content_id"])
    assert any("marquage lu reporté" in record.getMessage() for record in caplog.records)
    assert SECRET not in caplog.text and MESSAGE not in caplog.text
    from custom_components.freebox_homexa.voicemail import cancel_voicemail_retry
    cancel_voicemail_retry(router)
    from homeassistant.helpers import entity_registry as er
    registry = er.async_get(hass)
    player = registry.async_get_or_create(
        "media_player", DOMAIN, "player-3", suggested_object_id="freebox_player_3"
    )
    hass.states.async_set(player.entity_id, "idle")
    from custom_components.freebox_homexa.voicemail_audio import playback_content_type
    assert playback_content_type(hass, player.entity_id) == "music"
    assert playback_content_type(hass, "media_player.box") == "audio/mpeg"


async def async_delete_voicemail_direct(router) -> None:
    from custom_components.freebox_homexa.voicemail import async_delete_voicemail, tokens_of
    await async_delete_voicemail(router, tokens_of(router).issue(MESSAGE))
