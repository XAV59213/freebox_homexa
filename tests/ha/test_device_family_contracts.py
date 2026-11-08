"""Each active entity family attaches to one demonstrated device contract.

Families that call the same constructor are not retested one by one.
Optional serial and hardware fields stay absent when the payload has none.
The historical manufacturer Inconnu is kept.
"""
from copy import deepcopy

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType

from custom_components.freebox_homexa.alarm_control_panel import FreeboxAlarm
from custom_components.freebox_homexa.binary_sensor import FreeboxPirSensor, FreeboxWifiApSensor
from custom_components.freebox_homexa.button import BUTTON_DESCRIPTIONS, FreeboxButton, FreeboxPlayerRemoteButton
from custom_components.freebox_homexa.calendar import FreeboxTvGuideCalendar
from custom_components.freebox_homexa.camera import FreeboxCamera
from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.cover import FreeboxBasicShutter
from custom_components.freebox_homexa.device_groups import GROUP_HOME, GROUP_LAN_WIFI, group_identifier
from custom_components.freebox_homexa.device_tracker import FreeboxDevice
from custom_components.freebox_homexa.lan_group_sensors import FreeboxLanGroupClientsSensor
from custom_components.freebox_homexa.remote import FreeboxRemote
from custom_components.freebox_homexa.sensor import FreeboxDiskSensor, FreeboxSensor, FreeboxWifiSignalSensor
from custom_components.freebox_homexa.switch import FreeboxShutterInvertSwitchEntity
from custom_components.freebox_homexa.tnt_sensor import TNT_DEVICE_INFO
from test_home_platforms import home_context


async def test_entity_families_share_seven_device_contracts(hass, home_context):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    devices = dr.async_get(hass)
    server = devices.async_get_or_create(config_entry_id=entry.entry_id, **router.device_info)
    devices.async_update_device(server.id, name_by_user="Mon serveur")
    router.device_id = server.id
    assert server.entry_type is None
    assert (DOMAIN, router.mac) in server.identifiers
    assert router.device_info["connections"] == {(dr.CONNECTION_NETWORK_MAC, router.mac)}
    assert "hw_version" not in router.device_info

    sensor = FreeboxSensor(router, SensorEntityDescription(key="rate_down", name="Débit descendant"))
    button = FreeboxButton(router, BUTTON_DESCRIPTIONS[0])
    gateway = FreeboxWifiApSensor(router, "gateway", {"kind": "gateway", "name": "Wi-Fi"})
    assert sensor.device_info == button.device_info == gateway.device_info
    assert devices.async_get(server.id).name_by_user == "Mon serveur"

    shutter = FreeboxBasicShutter(hass, router, node)
    camera_node = deepcopy(node)
    camera_node["category"] = "camera"
    camera = FreeboxCamera(hass, router, camera_node)
    pir = FreeboxPirSensor(hass, router, node)
    invert = FreeboxShutterInvertSwitchEntity(hass, router, node)
    assert shutter.device_info["identifiers"] == camera.device_info["identifiers"] == {(DOMAIN, 42)}
    assert pir.device_info["identifiers"] == invert.device_info["identifiers"]
    assert "input" not in camera.device_info
    assert camera._ffmpeg._input.startswith("rtsp://")
    assert shutter.device_info["sw_version"] is None
    versioned = deepcopy(node)
    versioned["props"] = {**node["props"], "FwVersion": "1.2"}
    assert FreeboxBasicShutter(hass, router, versioned).device_info["sw_version"] == "1.2"
    assert "serial_number" not in shutter.device_info
    home = devices.async_get(shutter.device_info["via_device_id"])
    assert home.identifiers == {group_identifier(router.mac, GROUP_HOME)}
    assert home.entry_type == DeviceEntryType.SERVICE

    alarm = FreeboxAlarm(hass, router, {
        "id": 8, "label": "Alarme", "category": "alarm", "status": "active",
        "type": {"endpoints": []}, "show_endpoints": [], "props": {},
    })
    assert alarm.device_info["identifiers"] == {group_identifier(router.mac, GROUP_HOME)}
    assert devices.async_get(home.id).entry_type == DeviceEntryType.SERVICE
    assert devices.async_get(home.id).name_by_user is None

    disk = FreeboxDiskSensor(
        router, {"id": 7, "model": "Synthetic"}, {"id": 2, "label": "Data"},
        SensorEntityDescription(key="free"),
    )
    assert disk.device_info["identifiers"] == {(DOMAIN, 7)}
    assert "serial_number" not in disk.device_info
    assert "hw_version" not in disk.device_info
    stored = devices.async_get_or_create(config_entry_id=entry.entry_id, **disk.device_info)
    devices.async_update_device(stored.id, name_by_user="Mon disque")
    assert (DOMAIN, 7) in devices.async_get(stored.id).identifiers
    assert devices.async_get(stored.id).name_by_user == "Mon disque"
    assert stored.via_device_id == server.id

    player = {"id": 3, "device_name": "Salon", "mac": "aa:bb:cc:dd:ee:01", "device_model": "Pop"}
    remote = FreeboxRemote(router, player, entry)
    key = FreeboxPlayerRemoteButton(router, player, entry, "home", "Home", "mdi:home", True)
    assert remote.device_info["identifiers"] == key.device_info["identifiers"] == {(DOMAIN, "player_3")}
    assert "via_device_id" not in remote.device_info
    assert "sw_version" not in remote.device_info
    player_device = devices.async_get_or_create(config_entry_id=entry.entry_id, **remote.device_info)
    assert player_device.via_device_id is None

    router.repeaters["2066CF4B4969"] = {"name": "Cave", "macs": ["20:66:CF:4B:49:69"], "model": "RP01"}
    router.repeater_aliases["2066CF4B4969"] = "2066CF4B4969"
    repeater = FreeboxWifiApSensor(router, "cave", {
        "kind": "repeater", "mac": "20:66:CF:4B:49:69", "name": "Cave", "model": "RP01",
    })
    assert (DOMAIN, "repeater_2066CF4B4969") in repeater.device_info["identifiers"]
    parent = devices.async_get(repeater.device_info["via_device_id"])
    assert parent.identifiers == {group_identifier(router.mac, GROUP_LAN_WIFI)}
    assert parent.entry_type == DeviceEntryType.SERVICE

    phone = {"l2ident": {"id": "aa:bb:cc:dd:ee:10"}, "primary_name": "Telephone"}
    signal = FreeboxWifiSignalSensor(router, phone, True)
    assert signal.device_info["manufacturer"] == "Inconnu"
    assert "model" not in signal.device_info
    tracker = FreeboxDevice(router, phone, True)
    assert tracker.device_info is None

    calendar = FreeboxTvGuideCalendar(router)
    assert calendar.device_info["identifiers"] == TNT_DEVICE_INFO["identifiers"]
    assert calendar.device_info["entry_type"] == DeviceEntryType.SERVICE
    guide = devices.async_get_or_create(config_entry_id=entry.entry_id, **TNT_DEVICE_INFO)
    assert guide.entry_type == DeviceEntryType.SERVICE

    group = FreeboxLanGroupClientsSensor(router, GROUP_LAN_WIFI, set())
    assert group.device_info["entry_type"] == DeviceEntryType.SERVICE
    assert group.device_info["identifiers"] == {group_identifier(router.mac, GROUP_LAN_WIFI)}
    assert devices.async_get(server.id).name_by_user == "Mon serveur"
    assert devices.async_get(stored.id).name_by_user == "Mon disque"
