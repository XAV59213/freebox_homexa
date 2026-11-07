"""Real camera/cover/switch lifecycle and SDK contracts; no media/network process."""
from datetime import timedelta
import logging
from unittest.mock import AsyncMock, Mock, patch
import pytest
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.freebox_homexa.router import FreeboxRouter
from custom_components.freebox_homexa.cover import FreeboxBasicShutter, FreeboxShutter
from custom_components.freebox_homexa.switch import FreeboxSwitch, FreeboxShutterInvertSwitchEntity, SWITCH_DESCRIPTIONS
from custom_components.freebox_homexa.camera import FreeboxCamera

@pytest.fixture
def home_context(hass):
    entry = MockConfigEntry(domain="freebox_homexa", data={"host": "freebox.test"})
    entry.add_to_hass(hass)
    api = AsyncMock()
    router = FreeboxRouter(hass, entry, api, {"mac": "00:00:00:00:00:03",
        "model_info": {"pretty_name": "Test", "name": "test"}, "firmware_version": "4.9.0"})
    endpoints = [{"id": i, "name": name, "ep_type": kind, "value": value}
        for i, (name, kind, value) in enumerate([
            ("up", "slot", None), ("down", "slot", None), ("stop", "slot", None),
            ("state", "signal", False), ("position_set", "slot", None),
            ("position_set", "signal", 25), ("detection", "slot", None),
            ("detection", "signal", False)])]
    node = {"id": 42, "label": "Test Home", "category": "shutter", "status": "active",
        "type": {"endpoints": endpoints}, "show_endpoints": endpoints,
        "props": {"Pass": "SYNTHETIC", "Stream": "rtsp://test:SYNTHETIC@camera.test/live"}}
    router.home_devices[42] = node
    router.home.get_home_endpoint_value.return_value = {"value": False}
    router.wifi.get_global_config.return_value = {"enabled": True}
    hass.data["ffmpeg"] = Mock()
    return router, node


def make_platform(hass, domain):
    return EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
        platform_name="freebox_homexa", platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)

@pytest.mark.parametrize("kind", ["basic", "position", "wifi", "invert", "camera"])
async def test_home_platform_state_reachability_and_removal(hass, home_context, kind):
    router, node = home_context
    domain = "cover" if kind in {"basic", "position"} else "camera" if kind == "camera" else "switch"
    constructors = {"basic": lambda: FreeboxBasicShutter(hass, router, node),
        "position": lambda: FreeboxShutter(hass, router, node),
        "wifi": lambda: FreeboxSwitch(router, SWITCH_DESCRIPTIONS[0]),
        "invert": lambda: FreeboxShutterInvertSwitchEntity(hass, router, node),
        "camera": lambda: FreeboxCamera(hass, router, {**node, "category": "camera"})}
    entity = constructors[kind]()
    uid = entity.unique_id
    platform = make_platform(hass, domain)
    try:
        await platform.async_add_entities([entity], update_before_add=True)
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id) is not None
        assert entity.unique_id == uid
        router.reachable = False
        entity.async_write_ha_state()
        assert hass.states.get(entity.entity_id).state == ("off" if kind == "invert" else "unavailable")
        router.reachable = True
        entity.async_write_ha_state()
        assert hass.states.get(entity.entity_id).state != "unavailable"
        await platform.async_reset()
        assert not platform.entities
        assert not hass.data.get("dispatcher", {}).get(router.signal_home_device_update)
        router.home.set_home_endpoint_value.assert_not_called()
        router.wifi.set_global_config.assert_not_called()
    finally:
        await platform.async_reset()

async def test_position_unknown_is_unknown_even_with_inversion(hass, home_context):
    router, node = home_context
    entity = FreeboxShutter(hass, router, node)
    entity.hass = hass
    from homeassistant.helpers.entity_registry import async_get
    entity._invert_entity_id = async_get(hass).async_get_or_create(
        "switch", "freebox_homexa", f"{entity.unique_id}_InvertSwitch",
        suggested_object_id="test_inversion").entity_id
    hass.states.async_set(entity._invert_entity_id, "on")
    entity._current_cover_position = None
    assert entity.current_cover_position is None
    assert entity.is_closed is None

async def test_position_missing_clears_old_measurement(hass, home_context):
    router, node = home_context
    entity = FreeboxShutter(hass, router, node)
    assert entity.current_cover_position == 25
    node["show_endpoints"] = []
    await entity.async_update()
    assert entity.current_cover_position is None

async def test_inverted_set_keeps_raw_coordinate_contract(hass, home_context):
    router, node = home_context
    entity = FreeboxShutter(hass, router, node)
    entity.hass = hass
    from homeassistant.helpers.entity_registry import async_get
    entity._invert_entity_id = async_get(hass).async_get_or_create(
        "switch", "freebox_homexa", f"{entity.unique_id}_InvertSwitch",
        suggested_object_id="test_inversion").entity_id
    hass.states.async_set(entity._invert_entity_id, "on")
    await entity.async_set_cover_position(30)
    router.home.set_home_endpoint_value.assert_awaited_once_with(42, 4, {"value": 70})
    assert entity.current_cover_position == 30

async def test_camera_signal_replaces_node_for_availability(hass, home_context):
    router, node = home_context
    entity = FreeboxCamera(hass, router, node)
    platform = make_platform(hass, "camera")
    try:
        await platform.async_add_entities([entity])
        router.home_devices[42] = {**node, "status": "unreachable"}
        async_dispatcher_send(hass, router.signal_home_device_update)
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == "unavailable"
        router.home_devices[42] = node
        async_dispatcher_send(hass, router.signal_home_device_update)
        await hass.async_block_till_done()
        assert entity.available
    finally:
        await platform.async_reset()

async def test_inversion_storage_roundtrip_and_failed_write(hass, home_context, tmp_path):
    router, node = home_context
    entity = FreeboxShutterInvertSwitchEntity(hass, router, node)
    entity._path = tmp_path / "inversion.conf"
    platform = make_platform(hass, "switch")
    try:
        await platform.async_add_entities([entity], update_before_add=True)
        await entity.async_turn_on()
        assert entity.is_on is True
        assert entity._path.read_text() == "1"
        with patch.object(entity, "_write", side_effect=OSError("synthetic")):
            with pytest.raises(HomeAssistantError) as exc:
                await entity.async_turn_off()
            assert exc.value.translation_key == "command_failed"
        assert entity.is_on is True
        await entity.async_turn_off()
        assert entity._path.read_text() == "0"
    finally:
        await platform.async_reset()

from homeassistant.exceptions import HomeAssistantError

@pytest.mark.parametrize("kind,action", [("basic", "async_open_cover"), ("basic", "async_close_cover"),
    ("position", "async_set_cover_position"), ("camera", "async_enable_motion_detection"),
    ("camera", "async_disable_motion_detection")])
async def test_failed_sdk_command_is_translated_and_not_optimistic(hass, home_context, kind, action):
    router, node = home_context
    entity = {"basic": FreeboxBasicShutter, "position": FreeboxShutter, "camera": FreeboxCamera}[kind](hass, router, node)
    entity.hass = hass
    before = entity._state if kind == "basic" else entity._current_cover_position if kind == "position" else entity._attr_motion_detection_enabled
    router.home.set_home_endpoint_value.side_effect = TimeoutError
    with pytest.raises(HomeAssistantError) as exc:
        await getattr(entity, action)(**({"position": 75} if kind == "position" else {}))
    assert exc.value.translation_domain == "freebox_homexa"
    assert exc.value.translation_key == "command_failed"
    after = entity._state if kind == "basic" else entity._current_cover_position if kind == "position" else entity._attr_motion_detection_enabled
    assert before == after

async def test_wifi_failure_and_recovery_preserve_contract(hass, home_context):
    router, _ = home_context
    entity = FreeboxSwitch(router, SWITCH_DESCRIPTIONS[0])
    await entity.async_update()
    assert entity.is_on is True
    router.wifi.get_global_config.side_effect = TimeoutError
    await entity.async_update()
    assert entity.is_on is None
    router.wifi.get_global_config.side_effect = None
    router.wifi.get_global_config.return_value = {"enabled": False}
    await entity.async_update()
    assert entity.is_on is False
    await entity.async_turn_on()
    router.wifi.set_global_config.assert_awaited_once_with({"enabled": True})

async def test_camera_missing_detection_command_reports_failure(hass, home_context):
    router, node = home_context
    entity = FreeboxCamera(hass, router, node)
    entity._command_motion_detection = None
    with pytest.raises(HomeAssistantError):
        await entity.async_enable_motion_detection()
    router.home.set_home_endpoint_value.assert_not_called()


async def test_inversion_read_error_is_not_a_false_disabled_state(hass, home_context, tmp_path):
    router, node = home_context
    entity = FreeboxShutterInvertSwitchEntity(hass, router, node)
    entity._path = tmp_path / "inversion.conf"
    entity.hass = hass
    with patch("pathlib.Path.exists", side_effect=PermissionError("synthetic")):
        await entity.async_update()
    assert entity.is_on is None
    assert not entity.available
    entity._path.write_text("1")
    await entity.async_update()
    assert entity.is_on is True
    assert entity.available


async def test_unknown_inversion_prevents_an_ambiguous_command(hass, home_context):
    router, node = home_context
    entity = FreeboxShutter(hass, router, node)
    entity.hass = hass
    from homeassistant.helpers.entity_registry import async_get
    entity._invert_entity_id = async_get(hass).async_get_or_create(
        "switch", "freebox_homexa", f"{entity.unique_id}_InvertSwitch",
        suggested_object_id="test_inversion").entity_id
    hass.states.async_set(entity._invert_entity_id, "unavailable")
    assert entity.current_cover_position is None
    assert entity.is_closed is None
    with pytest.raises(HomeAssistantError) as exc:
        await entity.async_set_cover_position(30)
    assert exc.value.translation_key == "inversion_unavailable"
    router.home.set_home_endpoint_value.assert_not_called()


async def test_wifi_unavailable_on_failed_or_invalid_fetch_and_recovers(hass, home_context):
    router, _ = home_context
    entity = FreeboxSwitch(router, SWITCH_DESCRIPTIONS[0])
    for result in (None, []):
        router.wifi.get_global_config.return_value = result
        await entity.async_update()
        assert not entity.available
        assert entity.is_on is None
    for result in ({}, {"enabled": "false"}):
        router.wifi.get_global_config.return_value = result
        await entity.async_update()
        assert entity.available and entity.is_on is None
    router.wifi.get_global_config.return_value = {"enabled": False}
    await entity.async_update()
    assert entity.available
    assert entity.is_on is False


async def test_camera_disappears_repeatedly_and_recovers_without_new_identity(hass, home_context):
    router, node = home_context
    entity = FreeboxCamera(hass, router, node)
    uid = entity.unique_id
    platform = make_platform(hass, "camera")
    try:
        await platform.async_add_entities([entity])
        del router.home_devices[42]
        for _ in range(2):
            await entity.async_update_signal()
            assert hass.states.get(entity.entity_id).state == "unavailable"
        router.home_devices[42] = node
        await entity.async_update_signal()
        assert entity.available
        assert entity.unique_id == uid
    finally:
        await platform.async_reset()


@pytest.mark.parametrize("kind,command,value", [("basic", 0, None), ("position", 4, 30), ("camera", 6, True)])
@pytest.mark.parametrize("failed", [False, True])
async def test_real_sdk_home_contract_with_synthetic_transport(hass, home_context, kind, command, value, failed):
    from freebox_api.api.home import Home
    router, node = home_context
    access = AsyncMock()
    if failed:
        access.put.side_effect = TimeoutError("synthetic")
    router._api.home = Home(access)
    entity = {"basic": FreeboxBasicShutter, "position": FreeboxShutter, "camera": FreeboxCamera}[kind](hass, router, node)
    entity.hass = hass
    action = {"basic": entity.async_open_cover if kind == "basic" else None,
        "position": entity.async_set_cover_position if kind == "position" else None,
        "camera": entity.async_enable_motion_detection if kind == "camera" else None}[kind]
    if failed:
        with pytest.raises(HomeAssistantError) as exc:
            await action(**({"position": value} if kind == "position" else {}))
        assert exc.value.translation_key == "command_failed"
    else:
        await action(**({"position": value} if kind == "position" else {}))
    access.put.assert_awaited_once_with(f"home/endpoints/42/{command}", {"value": value})
