"""Global constructor metadata inventory, not a claim of hardware validation."""
import importlib
import inspect
import json
import os
from pathlib import Path

from homeassistant.helpers.entity import Entity
from custom_components.freebox_homexa import sensor as s, binary_sensor as b, button as btn
from custom_components.freebox_homexa import wifi_ap_sensors as w, lan_group_sensors as lan
from custom_components.freebox_homexa import cover, switch, camera, remote, media_player, calendar, device_tracker, alarm_control_panel
from custom_components.freebox_homexa.tnt_coordinator import ProgrammeTntFrCoordinator
from custom_components.freebox_homexa.tnt_sensor import HomexaTntSensor
from test_home_platforms import home_context

SNAPSHOT = Path(__file__).parents[1] / "fixtures" / "quality_scale_entity_inventory.json"
MODULES = (s, b, btn, w, lan, cover, switch, camera, remote, media_player, calendar, device_tracker, alarm_control_panel,
           importlib.import_module("custom_components.freebox_homexa.tnt_sensor"))


def build_inventory(hass, router, node, entry):
    objects = []
    extra = [{"id": 20 + i, "name": name, "label": name, "ep_type": kind, "value": False}
             for i, (name, kind) in enumerate([("trigger", "signal"), ("cover", "signal"),
                 ("trigger", "slot"), ("alarm1", "slot"), ("alarm2", "slot"), ("off", "slot")])]
    node = {**node, "show_endpoints": node["show_endpoints"] + extra,
            "type": {"endpoints": node["type"]["endpoints"] + extra}}
    def add(variant, entity):
        objects.append((variant, entity))
    for description in s.CONNECTION_SENSORS:
        add("connection/" + description.key, s.FreeboxSensor(router, description))
    add("temperature", s.FreeboxSensor(router, s.temperature_sensor_description("temp_cpu")))
    for description in s.CALL_SENSORS:
        add("calls/" + description.key, s.FreeboxCallSensor(router, description))
    add("call-log", s.FreeboxCallLogSensor(router, s.CALL_LOG_SENSOR))
    disk = {"id": 1, "model": "Synthetic disk"}
    partition = {"id": 1, "label": "Synthetic", "total_bytes": 100, "free_bytes": 50}
    for description in s.DISK_PARTITION_SENSORS:
        add("disk/" + description.key, s.FreeboxDiskSensor(router, disk, partition, description))
    battery = {"id": 10, "name": "battery", "label": "Battery", "value": 90, "ep_type": "signal"}
    add("battery", s.FreeboxBatterySensor(hass, router, node, battery))
    client = {"l2ident": {"id": "00:00:00:00:10:01"}, "primary_name": "Synthetic", "host_type": "computer",
        "wifi": {"wifi_signal_dbm": -40}, "active": True}
    router.devices[client["l2ident"]["id"]] = client
    for create_devices in (False, True):
        add("wifi-signal/devices=" + str(create_devices), s.FreeboxWifiSignalSensor(router, client, create_devices))
        add("tracker/devices=" + str(create_devices), device_tracker.FreeboxDevice(router, client, create_devices))
    for category, cls in (("pir", b.FreeboxPirSensor), ("dws", b.FreeboxDwsSensor)):
        add(category, cls(hass, router, {**node, "category": category}))
    add("tamper", b.FreeboxCoverSensor(hass, router, node))
    for description in b.RAID_SENSORS:
        add("raid/" + description.key, b.FreeboxRaidDegradedSensor(router, {"id": 1, "name": "Synthetic", "degraded": False}, description))
    router.wifi_aps = {"gateway": {"kind": "gateway", "name": "Synthetic", "online": True, "state": "active"},
        "repeater": {"kind": "repeater", "mac": "00:00:00:00:20:01", "name": "Synthetic", "online": True, "state": "active"}}
    for ap_id, ap in router.wifi_aps.items():
        add("ap/" + ap_id, b.FreeboxWifiApSensor(router, ap_id, ap))
        add("ap-count/" + ap_id, w.FreeboxWifiClientCountSensor(router, ap_id))
        add("ap-list/" + ap_id, w.FreeboxWifiClientListSensor(router, ap_id))
    add("repeater-count", w.FreeboxRepeaterCountSensor(router))
    add("total-wifi-clients", w.FreeboxWifiTotalClientSensor(router))
    add("wired-group", lan.FreeboxLanGroupClientsSensor(router, "lan_wired", {"lan_wired"}))
    for description in btn.BUTTON_DESCRIPTIONS:
        add("server-button/" + description.key, btn.FreeboxButton(router, description))
    player = {"id": 1, "name": "Synthetic Player", "api_available": True}
    for key, name, icon, enabled in btn.PLAYER_REMOTE_BUTTONS:
        add("remote-button/" + key, btn.FreeboxPlayerRemoteButton(router, player, entry, key, name, icon, enabled))
    for key, name, icon, url, enabled in btn.PLAYER_APP_BUTTONS:
        add("app-button/" + key, btn.FreeboxPlayerAppButton(router, player, key, name, icon, url, enabled))
    add("basic-shutter", cover.FreeboxBasicShutter(hass, router, node))
    for category, label in (("shutter", "Synthetic"), ("opener", "Synthetic garage"), ("opener", "Synthetic portail")):
        add("cover/" + label + category, cover.FreeboxShutter(hass, router, {**node, "category": category, "label": label}))
    for description in switch.SWITCH_DESCRIPTIONS:
        add("switch/" + description.key, switch.FreeboxSwitch(router, description))
    add("inversion", switch.FreeboxShutterInvertSwitchEntity(hass, router, node))
    add("camera", camera.FreeboxCamera(hass, router, {**node, "category": "camera"}))
    add("alarm", alarm_control_panel.FreeboxAlarm(hass, router, {**node, "category": "alarm"}))
    add("remote", remote.FreeboxRemote(router, player, entry))
    for model in ("devialet", "mini4k", "generic"):
        add("player/" + model, media_player.FreeboxPlayerMediaPlayer(router, {**player, "device_name": model}, entry))
    add("calendar", calendar.FreeboxTvGuideCalendar(router))
    coordinator = ProgrammeTntFrCoordinator(hass, ["TF1.fr"], config_entry=entry)
    coordinator.async_set_updated_data({})
    add("tnt", HomexaTntSensor(coordinator, "TF1.fr", "synthetic", router))
    return objects, coordinator


async def test_all_active_entity_families_have_reviewable_metadata_inventory(hass, home_context):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    objects, coordinator = build_inventory(hass, router, node, entry)
    try:
        declared = {cls for module in MODULES for cls in vars(module).values()
            if inspect.isclass(cls) and cls.__module__ == module.__name__ and issubclass(cls, Entity)}
        # Shared parent is not directly created by discovery; its concrete PIR/DWS/tamper descendants are.
        declared.remove(b.FreeboxHomeBinarySensor)
        assert {type(entity) for _, entity in objects} == declared
        records = []
        for variant, entity in objects:
            entity.hass = hass
            assert entity.unique_id
            records.append({"class": type(entity).__name__, "variant": variant,
                "category": entity.entity_category, "device_class": getattr(entity, "device_class", None),
                "enabled_default": entity.entity_registry_enabled_default, "has_entity_name": entity.has_entity_name,
                "translation_key": entity.translation_key, "unit": getattr(entity, "native_unit_of_measurement", None)})
        records.sort(key=lambda record: (record["class"], record["variant"]))
        if os.environ.get("HOMEXA_UPDATE_ENTITY_INVENTORY") == "1":
            SNAPSHOT.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
        assert records == json.loads(SNAPSHOT.read_text())
        router._api.home.set_home_endpoint_value.assert_not_called()
        router._api.remote.send_key.assert_not_called()
    finally:
        await coordinator.async_shutdown()
