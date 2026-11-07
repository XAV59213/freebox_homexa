"""Typed SDK boundaries execute the real installed SDK over synthetic transports."""
from datetime import timedelta
import logging
from unittest.mock import AsyncMock, Mock, patch

from freebox_api.api.system import System
from freebox_api.api.call import Call
from freebox_api.api.tv import Tv
from freebox_api.api.wifi import Wifi
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.util import dt as dt_util

from custom_components.freebox_homexa import async_setup_entry
from custom_components.freebox_homexa.calendar import FreeboxTvGuideCalendar
from custom_components.freebox_homexa.device_tracker import FreeboxDevice
from test_action_errors import build_entity
from test_home_platforms import home_context
from test_lifecycle import entry_for


def platform_for(hass, domain):
    return EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
        platform_name="freebox_homexa", platform=None,
        scan_interval=timedelta(seconds=30), entity_namespace=None)


@pytest.mark.parametrize("kind,method,path,body", [
    ("wifi", "async_turn_on", "wifi/config/", {"enabled": True}),
    ("wifi", "async_turn_off", "wifi/config/", {"enabled": False}),
    ("calls_button", "async_press", "call/log/mark_all_as_read/", None),
])
async def test_typed_actions_keep_actual_sdk_endpoint_body_error_and_recovery(
    hass, home_context, kind, method, path, body
):
    router, node = home_context
    transport = Mock(put=AsyncMock(), post=AsyncMock())
    router._api.wifi = Wifi(transport)
    router._api.call = Call(transport)
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entity, domain = build_entity(hass, router, node, entry, kind)
    platform = platform_for(hass, domain)
    operation = transport.post if body is None else transport.put
    try:
        await platform.async_add_entities([entity])
        identity = entity.unique_id
        operation.side_effect = TimeoutError("synthetic transport failure")
        with pytest.raises(HomeAssistantError):
            await getattr(entity, method)()
        operation.side_effect = None
        await getattr(entity, method)()
        args = (path,) if body is None else (path, body)
        assert operation.await_count == 2
        assert all(call.args == args for call in operation.await_args_list)
        assert entity.unique_id == identity
        (transport.put if body is None else transport.post).assert_not_awaited()
    finally:
        await platform.async_reset()


@pytest.mark.parametrize("shape", ["dictionary", "list", "invalid", "none", "empty"])
async def test_real_sdk_calendar_validates_raw_program_container_and_recovers(hass, home_context, shape):
    router, _ = home_context
    now = dt_util.now()
    program = {"id": 42, "uuid": "channel", "title": "Synthetic programme",
        "start": int((now - timedelta(minutes=5)).timestamp() * 1000), "duration": 3600}
    programs = {"42": program} if shape == "dictionary" else [program]
    if shape == "invalid":
        programs = "not a program collection"
    elif shape == "none":
        programs = None
    elif shape == "empty":
        programs = []
    async def get(path):
        if path == "tv/channels/":
            return {"channel": {"name": "Synthetic channel"}}
        assert path.startswith("tv/epg/by_time/")
        return programs
    transport = Mock(get=AsyncMock(side_effect=get))
    router._api.tv = Tv(transport)
    entity = FreeboxTvGuideCalendar(router)
    platform = platform_for(hass, "calendar")
    try:
        await platform.async_add_entities([entity])
        identity = entity.unique_id
        await entity.async_update()
        if shape in {"invalid", "none", "empty"}:
            assert entity.available is (shape == "empty")
            assert entity.event is None
            programs = [program]
            await entity.async_update()
        assert entity.available
        assert entity.event.summary == "Synthetic channel: Synthetic programme"
        assert entity.event.uid == "42"
        assert entity.unique_id == identity
        paths = [call.args[0] for call in transport.get.await_args_list]
        assert len(paths) == (4 if shape in {"invalid", "none", "empty"} else 2)
        assert paths[0] == "tv/channels/"
        assert all(path == "tv/channels/" or path.startswith("tv/epg/by_time/") for path in paths)
    finally:
        await platform.async_reset()


@pytest.mark.parametrize("mac", [23, None, b"AA:BB:CC:DD:EE:FF"])
def test_bad_mac_is_rejected_not_converted_into_new_identity(home_context, mac):
    router, _ = home_context
    with pytest.raises(ValueError, match="Invalid LAN MAC identifier"):
        FreeboxDevice(router, {"l2ident": {"id": mac}}, False)


def test_valid_mac_identifier_remains_exactly_unchanged(home_context):
    router, _ = home_context
    mac = "AA:BB:CC:DD:EE:FF"
    entity = FreeboxDevice(router, {"l2ident": {"id": mac, "type": "mac_address"},
        "primary_name": "Synthetic client", "host_type": "workstation"}, False)
    assert entity.mac_address == mac
    assert entity.unique_id == mac  # Native ScannerEntity identity, not _attr_unique_id.


@pytest.mark.parametrize("response", [[], {1: "invalid key"},
    {"mac": 23, "model_info": {"pretty_name": "Test"}},
    {"mac": "AA:BB:CC:DD:EE:FF", "model_info": {"pretty_name": 23}},
])
async def test_invalid_raw_system_configuration_closes_sdk_without_identity_conversion(hass, response):
    api = AsyncMock()
    transport = Mock(get=AsyncMock(return_value=response))
    api.system = System(transport)
    with patch("custom_components.freebox_homexa.JSModuleRegistration.async_register", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.Store.async_load", return_value={}), \
         patch("custom_components.freebox_homexa.get_api", return_value=api):
        with pytest.raises(ValueError, match="Invalid system"):
            await async_setup_entry(hass, entry_for(hass))
    api.close.assert_awaited_once()
    transport.get.assert_awaited_once_with("system/")
