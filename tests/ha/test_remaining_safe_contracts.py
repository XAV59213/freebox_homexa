"""Safe local contracts still short of the official per-module bar.

Real HA registry, services and entity platforms. SDK transport stays mocked.
No identity migration, no repeater/ change, and no device command is treated
as success. Preexisting user settings are compared by value; Home Assistant
may add sensor.suggested_display_precision without that being data loss.
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientError
from freebox_api.exceptions import NotOpenError
from homeassistant.components.cover import CoverState
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.freebox_homexa import async_migrate_entry, async_setup
from custom_components.freebox_homexa.alarm_control_panel import FreeboxAlarm
from custom_components.freebox_homexa.binary_sensor import (
    FreeboxCoverSensor,
    FreeboxHomeBinarySensor,
    FreeboxPirSensor,
)
from custom_components.freebox_homexa.camera import FreeboxCamera
from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.cover import FreeboxBasicShutter, FreeboxShutter
from custom_components.freebox_homexa.device_groups import (
    GROUP_HOME,
    GROUP_LAN_WIFI,
    GROUP_PLAYER,
    async_get_group_device,
    async_get_lan_group_device,
    async_remove_lan_client_devices,
    async_remove_unused_group_devices,
    group_identifier,
)
from custom_components.freebox_homexa.device_tracker import FreeboxDevice, add_entities
from custom_components.freebox_homexa.entity import FreeboxHomeEntity
from custom_components.freebox_homexa.errors import (
    api_error_code,
    is_permission_denied,
    is_shutdown_error,
    poll_log_level,
)
from custom_components.freebox_homexa.media_player import FreeboxPlayerMediaPlayer
from custom_components.freebox_homexa.router import normalize_mac
from custom_components.freebox_homexa.sensor import (
    FreeboxDiskSensor,
    FreeboxSensor,
    FreeboxWifiSignalSensor,
    async_setup_entry as async_setup_sensors,
)
from custom_components.freebox_homexa.services import async_setup_services
from custom_components.freebox_homexa.tnt_setup import (
    TNT_COORDINATORS_KEY,
    async_setup_bundled_tnt,
    async_unload_bundled_tnt,
)
from test_home_platforms import home_context, make_platform
from test_player_platforms import player_context
from test_websocket_contracts import calls_context


def _preserved(before: dict, after: dict) -> None:
    """User settings captured before the action are still present with the same values."""
    for domain, value in before.items():
        assert after[domain] == value


def _alarm_node(node: dict) -> dict:
    endpoints = [
        {"id": 1, "name": "alarm1", "ep_type": "slot", "value": None},
        {"id": 2, "name": "alarm2", "ep_type": "slot", "value": None},
        {"id": 3, "name": "off", "ep_type": "slot", "value": None},
        {"id": 4, "name": "state", "ep_type": "signal", "value": "idle"},
        {"id": 5, "name": "trigger", "ep_type": "slot", "value": None},
        {"id": 6, "name": "pin", "ep_type": "signal", "value": "0000"},
        {"id": 7, "name": "label", "ep_type": "signal", "value": "salon"},
    ]
    return {
        **node,
        "id": 77,
        "label": "Alarme",
        "category": "alarm",
        "type": {"endpoints": endpoints},
        "show_endpoints": endpoints,
    }


async def test_alarm_idle_stops_watcher_and_rejects_malformed_metadata(hass, home_context):
    router, node = home_context
    alarm = FreeboxAlarm(hass, router, _alarm_node(node))
    alarm.hass = hass
    router.home.set_home_endpoint_value.return_value = True
    router.home.get_home_endpoint_value.return_value = {"value": "alarm2_arming"}
    try:
        with patch("custom_components.freebox_homexa.alarm_control_panel.asyncio.sleep", new=AsyncMock()):
            await alarm.async_alarm_arm_home()
        assert alarm._unsub_watcher is not None
        router.home.get_home_endpoint_value.return_value = {"value": "idle"}
        await alarm.async_update()
        assert alarm._freebox_alarm_state == "idle"
        assert alarm._unsub_watcher is None
        router.home.set_home_endpoint_value.assert_awaited()
    finally:
        if alarm._unsub_watcher is not None:
            alarm._unsub_watcher()
    with pytest.raises(TypeError):
        alarm.update_parameters({**_alarm_node(node), "label": 1})
    with pytest.raises(TypeError):
        alarm.update_parameters({**_alarm_node(node), "show_endpoints": "nope"})
    with pytest.raises(TypeError):
        alarm.update_parameters({**_alarm_node(node), "show_endpoints": ["nope"]})
    with pytest.raises(TypeError):
        alarm.update_parameters({
            **_alarm_node(node),
            "show_endpoints": [{"ep_type": "signal", "name": 1, "value": True}],
        })


async def test_binary_sensor_invalid_identity_and_update_failure(hass, home_context, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    router, node = home_context
    broken = {**node, "id": None, "category": "pir"}
    with pytest.raises(ValueError):
        FreeboxHomeBinarySensor(hass, router, broken)
    with pytest.raises(ValueError):
        FreeboxCoverSensor(hass, router, broken)
    endpoints = list(node["type"]["endpoints"]) + [
        {"id": 9, "name": "trigger", "ep_type": "signal", "value": True}
    ]
    pir_node = {**node, "category": "pir", "type": {"endpoints": endpoints}, "show_endpoints": endpoints}
    router.home_devices[42] = pir_node
    sensor = FreeboxPirSensor(hass, router, pir_node)
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.synthetic_pir"

    async def broken_read(_command_id):
        raise RuntimeError("synthetic")

    sensor.get_home_endpoint_value = broken_read
    await sensor.async_update_signal()
    assert sensor._attr_is_on is None
    assert "Échec de la mise à jour du capteur" in caplog.text
    caplog.clear()
    router.closing = True
    sensor._attr_is_on = True
    await sensor.async_update_signal()
    assert sensor._attr_is_on is True
    assert "interrompue" in caplog.text
    assert "Échec de la mise à jour du capteur" not in caplog.text
    router.closing = False
    router.home.set_home_endpoint_value.assert_not_called()


async def test_camera_image_errors_and_update_do_not_leak_or_command(hass, home_context, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    router, node = home_context
    camera_node = {**node, "category": "camera", "label": "Camera"}
    router.home_devices[42] = camera_node
    camera = FreeboxCamera(hass, router, camera_node)
    camera.hass = hass
    platform = make_platform(hass, "camera")
    try:
        await platform.async_add_entities([camera])
        with patch("homeassistant.components.ffmpeg.camera.async_get_image", new=AsyncMock(side_effect=RuntimeError("synthetic"))) as image:
            with pytest.raises(RuntimeError, match="synthetic"):
                await camera.async_camera_image(160, 120)
            assert image.await_count == 1
        assert camera._video_available is False
        assert camera.extra_state_attributes["video_available"] is False
        with patch("homeassistant.components.ffmpeg.camera.async_get_image", new=AsyncMock(return_value=b"")):
            assert await camera.async_camera_image() is b""
        assert camera._video_available is False
        with patch("homeassistant.components.ffmpeg.camera.async_get_image", new=AsyncMock(return_value=None)):
            assert await camera.async_camera_image() is None
        assert camera._video_available is False
        with patch("homeassistant.components.ffmpeg.camera.async_get_image", new=AsyncMock(return_value=b"frame")):
            assert await camera.async_camera_image() == b"frame"
        assert camera._video_available is True
        camera._stop_video_observer()
        with patch.object(camera, "async_write_ha_state") as write, \
             patch("homeassistant.components.ffmpeg.camera.async_get_image", new=AsyncMock(return_value=b"late")):
            assert await camera.async_camera_image() == b"late"
            write.assert_not_called()
        assert camera._video_available is True
        router.closing = True
        with patch.object(camera, "async_write_ha_state") as write, \
             patch("homeassistant.components.ffmpeg.camera.async_get_image", new=AsyncMock(return_value=b"closed")):
            assert await camera.async_camera_image() == b"closed"
            write.assert_not_called()
        router.closing = False
        router.home_devices[42] = {**camera_node, "label": 5}
        await camera.async_update_signal()
        assert camera._attr_available is False
        assert "Mise à jour caméra impossible" in caplog.text
        caplog.clear()
        router.closing = True
        camera._attr_available = True
        await camera.async_update_signal()
        assert camera._attr_available is True
        assert "interrompue" in caplog.text
        assert "Mise à jour caméra impossible" not in caplog.text
        router.home.set_home_endpoint_value.assert_not_called()
        called = [str(call) for call in router._api.mock_calls]
        assert not any("repeater/" in item for item in called)
    finally:
        router.closing = False
        await platform.async_reset()


async def test_cover_unknown_closed_and_position_errors_skip_commands(hass, home_context):
    router, node = home_context
    endpoints = [item for item in node["show_endpoints"] if item["name"] != "state"]
    bare = {**node, "show_endpoints": endpoints, "type": {"endpoints": endpoints}}
    basic = FreeboxBasicShutter(hass, router, bare)
    assert basic._command_state is None
    await basic.async_update()
    assert basic._state is None
    assert basic.is_closed is None
    basic._state = CoverState.CLOSED
    assert basic.is_closed is True
    assert basic.convert_state(None) is None
    assert basic.convert_state(True) == CoverState.CLOSED
    shutter = FreeboxShutter(hass, router, node)
    shutter._node = {**node, "show_endpoints": 5}
    router.closing = True
    previous = shutter.current_cover_position
    await shutter.async_update()
    assert shutter.current_cover_position == previous
    router.closing = False
    router.reachable = False
    await shutter.async_update()
    assert shutter.current_cover_position is None
    router.reachable = True
    router.home.set_home_endpoint_value.assert_not_called()


async def test_home_entity_legacy_models_command_and_metadata_errors(hass, home_context):
    router, node = home_context
    rts = {
        "id": 5,
        "label": "unknown device",
        "category": "kiz",
        "type": {"inherit": "node::rts", "endpoints": []},
        "show_endpoints": [],
    }
    entity = FreeboxHomeEntity(hass, router, rts)
    assert entity._manufacturer == "Somfy"
    assert "5" in entity._device_name
    ios = {**rts, "id": 6, "label": "Store", "type": {"inherit": "node::ios", "endpoints": []}}
    assert FreeboxHomeEntity(hass, router, ios)._manufacturer == "Somfy"
    assert entity.get_node_value([], "signal", "state") is None

    async def hang(*_args, **_kwargs):
        await asyncio.Future()

    router.home.set_home_endpoint_value.side_effect = hang
    assert await entity.set_home_endpoint_value(1, True) is False
    router.closing = True
    assert await entity.get_home_endpoint_value(1) is None
    router.home.set_home_endpoint_value.side_effect = NotOpenError("closed")
    assert await entity.set_home_endpoint_value(1, True) is False
    router.closing = False
    router.home.set_home_endpoint_value.side_effect = RuntimeError("synthetic")
    assert await entity.set_home_endpoint_value(1, True) is False
    router.home_devices[42] = {**node, "label": 5}
    home = FreeboxHomeEntity(hass, router, node)
    platform = make_platform(hass, "switch")
    try:
        await platform.async_add_entities([home])
        await home.async_update_signal()
        assert home._attr_available is False
        router.closing = True
        home._attr_available = True
        await home.async_update_signal()
        assert home._attr_available is True
    finally:
        router.closing = False
        router.home.set_home_endpoint_value.side_effect = None
        await platform.async_reset()


def test_shutdown_permission_and_log_classification():
    class Router:
        closing = False
        reachable = True

    router = Router()
    assert is_shutdown_error(RuntimeError("other"), router) is False
    router.closing = True
    assert is_shutdown_error(ValueError("synthetic"), router) is True
    router.closing = False
    assert is_shutdown_error(NotOpenError("closed"), router) is True
    assert is_shutdown_error(ClientError("Session is closed"), router) is True
    assert is_shutdown_error(RuntimeError("Connector is closed"), router) is True
    assert is_shutdown_error(RuntimeError("still open"), router) is False
    router.reachable = False
    assert poll_log_level(router) == 10
    router.reachable = True
    assert poll_log_level(router) == 40
    assert api_error_code(RuntimeError("Request failed (APIResponse: {not json})")) is None
    assert api_error_code(RuntimeError('Request failed (APIResponse: ["nope"])')) is None
    denied = RuntimeError('Request failed (APIResponse: {"error_code": "insufficient_rights"})')
    assert api_error_code(denied) == "insufficient_rights"
    assert is_permission_denied(denied) is True


async def test_calls_entity_without_read_permission_is_unauthorized(hass, hass_ws_client, calls_context):
    from homeassistant.auth.models import Credentials
    from pytest_homeassistant_custom_component.common import CLIENT_ID, MockUser
    from custom_components.freebox_homexa.calls_ws import async_register_calls_websocket_api

    user = MockUser(name="No entity rights").add_to_hass(hass)
    user.mock_policy({})
    credential = Credentials(
        id="mock-norights-credential-id",
        auth_provider_type="homeassistant",
        auth_provider_id=None,
        data={"username": "norights"},
        is_new=False,
    )
    user.credentials.append(credential)
    refresh = await hass.auth.async_create_refresh_token(user, CLIENT_ID, credential=credential)
    token = hass.auth.async_create_access_token(refresh)
    client = await hass_ws_client(hass, access_token=token)
    async_register_calls_websocket_api(hass)
    entity_id = calls_context[2][0].entity_id
    await client.send_json_auto_id({"type": "freebox_homexa/calls", "entity_id": entity_id})
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] == "unauthorized"
    assert "Synthetic A" not in str(response)
    assert "000001" not in str(response)


async def test_tnt_refresh_failure_still_keeps_the_coordinator(hass):
    from homeassistant.helpers.update_coordinator import UpdateFailed
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={"tnt_channels": ["TF1.fr"]})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.freebox_homexa.tnt_coordinator.ProgrammeTntFrCoordinator.async_config_entry_first_refresh",
        new=AsyncMock(side_effect=UpdateFailed("synthetic")),
    ):
        coordinator = await async_setup_bundled_tnt(hass, entry)
    assert coordinator is not None
    assert hass.data["freebox_homexa"][TNT_COORDINATORS_KEY][entry.entry_id] is coordinator
    async_unload_bundled_tnt(hass, entry)


async def test_setup_survives_reminder_failure_and_refuses_future_entry_version(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    with patch(
        "custom_components.freebox_homexa.async_setup_reminders",
        new=AsyncMock(side_effect=RuntimeError("synthetic")),
    ):
        assert await async_setup(hass, {}) is True
    assert hass.services.has_service(DOMAIN, "reboot")
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, version=2)
    entry.add_to_hass(hass)
    before = dict(entry.options)
    assert await async_migrate_entry(hass, entry) is False
    assert entry.options == before


async def test_sensor_disk_absence_wifi_parent_and_user_precision(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    devices = dr.async_get(hass)
    server = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, router.mac)},
        name="Freebox Server",
    )
    devices.async_update_device(server.id, name_by_user="Mon serveur")
    router.device_id = server.id
    disk = {"id": 7, "model": "Synthetic", "firmware": "1", "partitions": {
        3: {"id": 3, "label": "Data", "total_bytes": 100, "free_bytes": 40},
    }}
    description = SensorEntityDescription(
        key="partition_free_space", name="espace libre", entity_category=EntityCategory.DIAGNOSTIC,
    )
    disk_sensor = FreeboxDiskSensor(router, disk, disk["partitions"][3], description)
    assert disk_sensor.device_info["identifiers"] == {(DOMAIN, "7")}
    platform = make_platform(hass, "sensor")
    platform.config_entry = entry
    registry = er.async_get(hass)
    try:
        await platform.async_add_entities([disk_sensor])
        device = devices.async_get(disk_sensor.registry_entry.device_id)
        assert device is not None
        assert any(ident == (DOMAIN, "7") for ident in device.identifiers)
        devices.async_update_device(device.id, name_by_user="Mon disque")
        registry.async_update_entity_options(disk_sensor.entity_id, "conversation", {"should_expose": False})
        registry.async_update_entity_options(disk_sensor.entity_id, "sensor", {"suggested_display_precision": 2})
        preexisting = dict(registry.async_get(disk_sensor.entity_id).options)
        router.disks.clear()
        disk_sensor.async_update_state()
        assert disk_sensor.native_value is None
        router.disks[7] = {"id": 7, "partitions": {}}
        disk_sensor.async_update_state()
        assert disk_sensor.native_value is None
        disk_sensor.async_write_ha_state()
        _preserved(preexisting, registry.async_get(disk_sensor.entity_id).options)
        again = devices.async_get(device.id)
        assert again.id == device.id
        assert again.name_by_user == "Mon disque"
        assert any(ident == (DOMAIN, "7") for ident in again.identifiers)
        plain = FreeboxSensor(router, SensorEntityDescription(key="custom_plain", name="Debit salon"))
        assert isinstance(plain.name, str)
        unnamed = FreeboxSensor(router, SensorEntityDescription(key="custom_none", name=None))
        assert unnamed.name is None
        phone = "aa:bb:cc:dd:ee:10"
        repeater = "aa:bb:cc:dd:ee:20"
        canon = normalize_mac(repeater)
        router.repeater_aliases[canon] = canon
        router.repeaters[canon] = {"name": "Repeteur", "macs": [repeater], "model": "F-RP01A"}
        router.devices[phone] = {
            "l2ident": {"id": phone}, "primary_name": "Telephone", "vendor_name": "Test",
            "active": True, "wifi": {"wifi_signal_dbm": -40, "connectivity": "wifi"},
        }
        router.devices[repeater] = {
            "l2ident": {"id": repeater}, "primary_name": "Repeteur", "vendor_name": "Free",
            "active": True, "wifi": {"wifi_signal_dbm": -30, "connectivity": "wifi"},
        }
        router.lan_links[normalize_mac(phone)] = "wifi"
        phone_sensor = FreeboxWifiSignalSensor(router, router.devices[phone], True)
        assert phone_sensor.device_info["via_device_id"]
        repeater_sensor = FreeboxWifiSignalSensor(router, router.devices[repeater], True)
        assert (DOMAIN, f"repeater_{canon}") in repeater_sensor.device_info["identifiers"]
        added = []

        def collect(entities, update_before_add=False):
            added.extend(entities)

        hass.data.setdefault(DOMAIN, {})
        await async_setup_sensors(hass, entry, collect)
        wifi = [entity for entity in added if isinstance(entity, FreeboxWifiSignalSensor)]
        assert {entity.unique_id for entity in wifi} >= {
            f"{router.mac}_{phone}_wifi_signal",
            f"{router.mac}_{repeater}_wifi_signal",
        }
        router.home.set_home_endpoint_value.assert_not_called()
        assert not any("repeater/" in str(call) for call in router._api.mock_calls)
        assert devices.async_get(server.id).name_by_user == "Mon serveur"
    finally:
        await platform.async_reset()


async def test_device_tracker_links_lan_client_without_moving_foreign_mac(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    devices = dr.async_get(hass)
    server = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, router.mac)}, name="Freebox Server",
    )
    router.device_id = server.id
    router.create_lan_devices = True
    phone = "aa:bb:cc:dd:ee:30"
    box = "aa:bb:cc:dd:ee:31"
    foreign_mac = "aa:bb:cc:dd:ee:32"
    router.devices[phone] = {
        "l2ident": {"id": phone}, "primary_name": "Telephone", "active": True,
        "last_time_reachable": 1_700_000_000, "last_activity": 1_700_000_100,
        "wifi": {"wifi_signal_dbm": -48}, "wifi_parent": {"name": "Salon", "kind": "repeater"},
    }
    router.devices[box] = {"l2ident": {"id": box}, "primary_name": "Box", "attrs": {"role": "server"}}
    router.devices[foreign_mac] = {
        "l2ident": {"id": foreign_mac}, "primary_name": "Shelly", "active": True,
    }
    skipped = []
    add_entities(router, lambda entities, update: skipped.extend(entities), set(), False, True)
    assert [entity.mac_address for entity in skipped] == [box]
    other = hass.config_entries.async_entries("other")
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    foreign_entry = MockConfigEntry(domain="shelly", data={})
    foreign_entry.add_to_hass(hass)
    foreign = devices.async_get_or_create(
        config_entry_id=foreign_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, foreign_mac)},
        name="Shelly",
    )
    devices.async_update_device(foreign.id, name_by_user="Ma prise")
    created = []
    add_entities(router, lambda entities, update: created.extend(entities), set(), True, True)
    tracker = next(entity for entity in created if entity.mac_address == phone)
    tracker.async_update_state()
    state = tracker.extra_state_attributes
    assert state["connecte_sur"] == "Salon"
    assert state["ap_kind"] == "repeater"
    assert datetime.fromisoformat(state["last_time_reachable"])
    saved = router.devices.pop(phone)
    tracker.async_update_state()
    assert tracker.extra_state_attributes == {}
    assert tracker.is_connected is False
    router.devices[phone] = saved
    # Known MAC enables the tracker; without a platform config entry the
    # scanner does not claim the device, so Homexa's own link runs.
    phone_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, phone)},
        name="Telephone",
    )
    devices.async_update_device(phone_device.id, name_by_user="Mon telephone")
    platform = make_platform(hass, "device_tracker")
    try:
        await platform.async_add_entities([tracker])
        await hass.async_block_till_done()
        norm = normalize_mac(phone)
        assert norm in router.tracked_lan_macs
        assert router.lan_device_ids[norm] == phone_device.id
        assert er.async_get(hass).async_get(tracker.entity_id).device_id == phone_device.id
        assert devices.async_get(phone_device.id).name_by_user == "Mon telephone"
        assert router.ensure_lan_client_device(foreign_mac) is None
        assert devices.async_get(foreign.id).name_by_user == "Ma prise"
        assert devices.async_get(foreign.id).config_entry_id == foreign_entry.entry_id
    finally:
        await platform.async_reset()
    assert normalize_mac(phone) not in router.tracked_lan_macs


async def test_player_group_is_established_before_parent_and_settings_stay(hass, player_context):
    router, entry, player = player_context
    devices = dr.async_get(hass)
    server = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, router.mac)}, name="Freebox Server",
    )
    router.device_id = server.id
    media = FreeboxPlayerMediaPlayer(router, {**player, "device_name": "Salon", "mac": "aa:bb:cc:dd:ee:40"}, entry)
    platform = make_platform(hass, "media_player")
    platform.config_entry = entry
    registry = er.async_get(hass)
    try:
        await platform.async_add_entities([media])
        await hass.async_block_till_done()
        player_device = devices.async_get(media.registry_entry.device_id)
        assert player_device is not None
        assert (DOMAIN, "player_1") in player_device.identifiers
        devices.async_update_device(player_device.id, name_by_user="Mon Player")
        registry.async_update_entity_options(media.entity_id, "conversation", {"should_expose": False})
        preexisting = dict(registry.async_get(media.entity_id).options)
        # Parent lookup for the Player service uses the device created above.
        router.group_overrides["node:42"] = GROUP_PLAYER
        home = FreeboxHomeEntity(hass, router, {
            "id": 42, "label": "Prise", "category": "switch",
            "type": {"endpoints": []}, "show_endpoints": [],
        })
        assert home.device_info["via_device_id"] == player_device.id
        assert home.device_info["identifiers"] == {(DOMAIN, 42)}
        assert home.device_info["via_device_id"] != server.id
        media.async_write_ha_state()
        _preserved(preexisting, registry.async_get(media.entity_id).options)
        kept = devices.async_get(player_device.id)
        assert kept.id == player_device.id
        assert kept.name_by_user == "Mon Player"
        assert (DOMAIN, "player_1") in kept.identifiers
        router._api.remote.send_key.assert_not_called()
        router._api.player._access.post.assert_not_called()
    finally:
        await platform.async_reset()


async def test_stale_cleanup_keeps_named_devices_children_and_foreign_macs(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    server = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, router.mac)}, name="Freebox Server",
    )
    devices.async_update_device(server.id, name_by_user="Mon serveur")
    router.device_id = server.id
    home_id = async_get_group_device(hass, entry.entry_id, router.mac, GROUP_HOME)
    devices.async_update_device(home_id, name_by_user="Ma maison")
    wifi_id = async_get_lan_group_device(hass, entry.entry_id, router.mac, GROUP_LAN_WIFI, server.id)
    child = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "child-synthetic")},
        name="Enfant",
    )
    devices.async_update_device(child.id, via_device_id=wifi_id, name_by_user="Mon enfant")
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{router.mac}-kept-home",
        config_entry=entry, device_id=home_id, suggested_object_id="kept_home",
    )
    kept_entity = registry.async_get_entity_id("sensor", DOMAIN, f"{router.mac}-kept-home")
    registry.async_update_entity_options(kept_entity, "sensor", {"suggested_display_precision": 1})
    registry.async_update_entity_options(kept_entity, "conversation", {"should_expose": True})
    preexisting = dict(registry.async_get(kept_entity).options)
    empty = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={group_identifier(router.mac, "security")},
        name="Ancien groupe",
    )
    disk = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, 7)}, name="Disque 7",
    )
    devices.async_update_device(disk.id, name_by_user="Mon disque")
    removed = async_remove_unused_group_devices(hass, entry, router.mac, set())
    assert devices.async_get(empty.id) is None
    assert "Ancien groupe" in removed
    assert devices.async_get(home_id).name_by_user == "Ma maison"
    assert devices.async_get(wifi_id) is not None
    assert devices.async_get(child.id).name_by_user == "Mon enfant"
    assert devices.async_get(child.id).via_device_id == wifi_id
    _preserved(preexisting, registry.async_get(kept_entity).options)
    assert any(ident == (DOMAIN, 7) for ident in devices.async_get(disk.id).identifiers)
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    foreign_entry = MockConfigEntry(domain="shelly", data={})
    foreign_entry.add_to_hass(hass)
    foreign = devices.async_get_or_create(
        config_entry_id=foreign_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:50")},
        name="Shelly",
    )
    devices.async_update_device(foreign.id, name_by_user="Ma prise")
    exclusive = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:51")},
        name="Client seul",
    )
    removed_clients = async_remove_lan_client_devices(hass, entry, router.mac)
    assert devices.async_get(foreign.id).name_by_user == "Ma prise"
    assert devices.async_get(server.id).name_by_user == "Mon serveur"
    assert devices.async_get(disk.id).name_by_user == "Mon disque"
    assert any(ident == (DOMAIN, 7) for ident in devices.async_get(disk.id).identifiers)
    assert devices.async_get(exclusive.id) is None
    assert removed_clients == 1
    assert not any("repeater/" in str(call) for call in router._api.mock_calls)


async def test_remote_validation_uses_player_device_without_sending_keys(hass, player_context):
    router, entry, _player = player_context
    entry.runtime_data = router
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    async_setup_services(hass)
    devices = dr.async_get(hass)
    server = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, router.mac)}, name="Freebox Server",
    )
    player = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "player_9")}, name="Player",
    )
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    other = MockConfigEntry(domain="other", data={})
    other.add_to_hass(hass)
    foreign = devices.async_get_or_create(
        config_entry_id=other.entry_id, identifiers={("other", "x")}, name="Autre",
    )

    async def rejected(data, key):
        with pytest.raises(ServiceValidationError) as exc:
            await hass.services.async_call(DOMAIN, "remote", data, blocking=True)
        assert exc.value.translation_key == key

    await rejected({"code": "home", "player_id": "abc"}, "remote_invalid_player")
    await rejected({"code": ""}, "remote_empty_command")
    await rejected({"code": "nope"}, "remote_invalid_key")
    router._api.player.get_players.side_effect = RuntimeError("synthetic")
    await rejected({"code": "home"}, "remote_no_player")
    router._api.player.get_players.side_effect = None
    router._api.player.get_players.return_value = [{"id": 1}, {"id": 2}]
    await rejected({"code": "home", "device_id": "missing-device"}, "remote_multiple_players")
    router._api.player.get_players.return_value = []
    await rejected({"code": "home", "device_id": player.id}, "remote_code_missing")
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call(DOMAIN, "reload", {"device_id": foreign.id}, blocking=True)
    assert exc.value.translation_key == "entry_not_loaded"
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)) as reload:
        await hass.services.async_call(
            DOMAIN, "reload", {"device_id": [server.id, "missing-device"]}, blocking=True,
        )
    reload.assert_awaited()
    hass.config_entries.async_update_entry(entry, options={"remote_code": "synthetic-code"})
    router._api.player.get_players.return_value = [{"id": 9}]
    router._api.remote.send_key.return_value = False
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            DOMAIN, "remote", {"code": "home", "device_id": player.id}, blocking=True,
        )
    assert exc.value.translation_key == "command_unconfirmed"
    router._api.remote.send_key.assert_awaited()
    router._api.player._access.post.assert_not_called()
    entry._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)
