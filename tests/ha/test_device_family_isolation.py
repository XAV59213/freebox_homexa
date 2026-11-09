"""Two Freebox entries keep their devices apart. No identifier is rewritten.

The FFmpeg helper receives a stream configuration, not the registry DeviceInfo.
Serial and hardware version are omitted when the payload does not provide them.
"""
from copy import deepcopy
from unittest.mock import AsyncMock, Mock

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_homexa.camera import FreeboxCamera
from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.media_player import player_device_info
from custom_components.freebox_homexa.router import FreeboxRouter
from custom_components.freebox_homexa.sensor import FreeboxDiskSensor, FreeboxWifiSignalSensor
from custom_components.freebox_homexa.tnt_sensor import TNT_DEVICE_INFO


def _router(hass, host, mac):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": host})
    entry.add_to_hass(hass)
    router = FreeboxRouter(
        hass, entry, AsyncMock(),
        {"mac": mac, "model_info": {"pretty_name": host, "name": "server"}, "firmware_version": "4.9.0"},
    )
    entry.runtime_data = router
    return entry, router


async def test_two_servers_keep_shared_integer_and_service_devices_apart(hass):
    devices = dr.async_get(hass)
    first_entry, first = _router(hass, "first.test", "00:00:00:00:00:0a")
    second_entry, second = _router(hass, "second.test", "00:00:00:00:00:0b")
    hass.data["ffmpeg"] = Mock()
    node = {
        "id": 42, "label": "Camera salon", "category": "camera", "status": "active",
        "type": {"endpoints": []}, "show_endpoints": [],
        "props": {"Pass": "SYNTHETIC", "Stream": "rtsp://test:SYNTHETIC@camera.test/live", "FwVersion": "1.2"},
    }
    camera_first = FreeboxCamera(hass, first, deepcopy(node))
    camera_second = FreeboxCamera(hass, second, deepcopy(node))
    assert camera_first.device_info["identifiers"] == {(DOMAIN, 42)}
    assert "input" not in camera_first.device_info
    assert camera_first._ffmpeg._input.startswith("rtsp://")
    assert camera_first.unique_id != camera_second.unique_id
    assert camera_first.device_info["sw_version"] == "1.2"
    assert "serial_number" not in camera_first.device_info
    assert "hw_version" not in camera_first.device_info

    home_first = devices.async_get_or_create(config_entry_id=first_entry.entry_id, **camera_first.device_info)
    home_second = devices.async_get_or_create(config_entry_id=second_entry.entry_id, **camera_second.device_info)
    devices.async_update_device(home_first.id, name_by_user="Ma camera")
    assert home_first.id != home_second.id
    assert devices.async_get(home_first.id).name_by_user == "Ma camera"
    assert devices.async_get(home_second.id).name_by_user is None
    assert devices.async_get_device_by_identifier((DOMAIN, 42), first_entry.entry_id).id == home_first.id
    assert devices.async_get_device_by_identifier((DOMAIN, 42), second_entry.entry_id).id == home_second.id

    disk = {"id": 7, "model": "Synthetic", "firmware": "9"}
    partition = {"id": 2, "label": "Data"}
    disk_first = FreeboxDiskSensor(first, disk, partition, SensorEntityDescription(key="free"))
    disk_second = FreeboxDiskSensor(second, disk, partition, SensorEntityDescription(key="free"))
    assert disk_first.device_info["identifiers"] == {(DOMAIN, "7")}
    assert "serial_number" not in disk_first.device_info
    stored_first = devices.async_get_or_create(config_entry_id=first_entry.entry_id, **disk_first.device_info)
    stored_second = devices.async_get_or_create(config_entry_id=second_entry.entry_id, **disk_second.device_info)
    devices.async_update_device(stored_first.id, name_by_user="Mon disque")
    assert stored_first.id != stored_second.id
    assert (DOMAIN, "7") in devices.async_get(stored_first.id).identifiers
    assert devices.async_get(stored_first.id).name_by_user == "Mon disque"
    assert devices.async_get(stored_second.id).name_by_user is None

    player_first = player_device_info(first, {"id": 3, "device_name": "Salon", "mac": "aa:bb:cc:dd:ee:01", "device_model": "Pop"})
    player_second = player_device_info(second, {"id": 3, "device_name": "Salon", "mac": "aa:bb:cc:dd:ee:02", "device_model": "Pop"})
    assert "serial_number" not in player_first
    assert "sw_version" not in player_first
    registered_first = devices.async_get_or_create(config_entry_id=first_entry.entry_id, **player_first)
    registered_second = devices.async_get_or_create(config_entry_id=second_entry.entry_id, **player_second)
    assert registered_first.id != registered_second.id
    assert devices.async_get_device_by_identifier((DOMAIN, "player_3"), first_entry.entry_id).id == registered_first.id
    assert devices.async_get_device_by_identifier((DOMAIN, "player_3"), second_entry.entry_id).id == registered_second.id

    guide_first = devices.async_get_or_create(config_entry_id=first_entry.entry_id, **TNT_DEVICE_INFO)
    guide_second = devices.async_get_or_create(config_entry_id=second_entry.entry_id, **TNT_DEVICE_INFO)
    assert guide_first.id != guide_second.id
    assert guide_first.entry_type == dr.DeviceEntryType.SERVICE

    phone = {"l2ident": {"id": "aa:bb:cc:dd:ee:10"}, "primary_name": "Pixel", "vendor_name": "Google", "model": " Pixel "}
    signal = FreeboxWifiSignalSensor(first, phone, True)
    assert signal.device_info["model"] == "Pixel"
    assert signal.device_info["connections"] == {(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:10")}
    plain = dict(phone)
    plain["model"] = None
    assert "model" not in FreeboxWifiSignalSensor(first, plain, True).device_info

    assert devices.async_get(home_first.id) is not None
    assert devices.async_get(home_second.id) is not None
