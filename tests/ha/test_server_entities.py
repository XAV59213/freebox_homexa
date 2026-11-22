"""Websocket freebox_homexa/server_entities : registre, pas les noms affichés."""
import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from unittest.mock import AsyncMock

from custom_components.freebox_homexa.binary_sensor import (
    RAID_SENSORS,
    FreeboxRaidDegradedSensor,
    FreeboxWifiApSensor,
)
from custom_components.freebox_homexa.button import BUTTON_DESCRIPTIONS, FreeboxButton
from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.device_tracker import FreeboxDevice
from custom_components.freebox_homexa.lan_group_sensors import FreeboxLanGroupClientsSensor
from custom_components.freebox_homexa.router import FreeboxRouter
from custom_components.freebox_homexa.sensor import (
    CALL_SENSORS,
    CONNECTION_SENSORS,
    DISK_PARTITION_SENSORS,
    FreeboxCallSensor,
    FreeboxDiskSensor,
    FreeboxSensor,
    fan_sensor_description,
    temperature_sensor_description,
)
from custom_components.freebox_homexa.server_ws import (
    _blank,
    _keyed,
    _named,
    _put,
    _sort_lists,
    _text,
    async_register_server_websocket_api,
    entity_role,
    server_entities_for_entry,
    websocket_server_entities,
)
from custom_components.freebox_homexa.switch import SWITCH_DESCRIPTIONS, FreeboxSwitch
from custom_components.freebox_homexa.wifi_ap_sensors import (
    FreeboxRepeaterCountSensor,
    FreeboxWifiClientCountSensor,
    FreeboxWifiClientListSensor,
    FreeboxWifiTotalClientSensor,
)
from test_home_platforms import home_context


def _index(view, role):
    group, key = role.split(".", 1)
    return view[group][key]


async def test_roles_follow_live_unique_ids_not_names(hass, home_context):
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    entry.mock_state(hass, ConfigEntryState.LOADED)
    router.wifi_aps = {
        "gateway": {"kind": "gateway", "name": "Box", "online": True, "state": "active"},
        "rep": {"kind": "repeater", "mac": "aa:bb:cc:dd:ee:10", "name": "Cave", "online": True, "state": "active"},
    }
    disk = {"id": 1, "model": "Synthetic"}
    partition = {"id": 2, "label": "Data"}
    router.disks[1] = {**disk, "partitions": {2: partition}}
    built = [
        ("sensor", FreeboxSensor(router, CONNECTION_SENSORS[0]), "connection.rate_down"),
        ("sensor", FreeboxSensor(router, CONNECTION_SENSORS[1]), "connection.rate_up"),
        ("sensor", FreeboxSensor(router, CONNECTION_SENSORS[2]), "connection.ipv4"),
        ("sensor", FreeboxSensor(router, CONNECTION_SENSORS[3]), "system.uptime"),
        ("sensor", FreeboxSensor(router, temperature_sensor_description("temp_cpu")), "health.temperatures"),
        ("sensor", FreeboxSensor(router, fan_sensor_description("1")), "health.fans"),
        ("sensor", FreeboxDiskSensor(router, disk, partition, DISK_PARTITION_SENSORS[0]), "health.disks"),
        ("sensor", FreeboxCallSensor(router, CALL_SENSORS[0]), "calls.missed"),
        ("binary_sensor", FreeboxRaidDegradedSensor(router, {"id": 3, "degraded": False}, RAID_SENSORS[0]), "health.raid"),
        ("binary_sensor", FreeboxWifiApSensor(router, "gateway", router.wifi_aps["gateway"]), "network.access_points"),
        ("binary_sensor", FreeboxWifiApSensor(router, "rep", router.wifi_aps["rep"]), "network.access_points"),
        ("sensor", FreeboxWifiClientCountSensor(router, "gateway"), "network.wifi_clients"),
        ("sensor", FreeboxWifiClientCountSensor(router, "rep"), "network.wifi_clients"),
        ("sensor", FreeboxWifiTotalClientSensor(router), "network.wifi_clients"),
        ("sensor", FreeboxWifiClientListSensor(router, "gateway"), None),
        ("sensor", FreeboxRepeaterCountSensor(router), "network.repeater_count"),
        ("sensor", FreeboxLanGroupClientsSensor(router, "lan_wired", {"lan_wired"}), "network.lan_groups"),
        ("switch", FreeboxSwitch(router, SWITCH_DESCRIPTIONS[0]), "network.wifi"),
        ("button", FreeboxButton(router, BUTTON_DESCRIPTIONS[0]), "actions.reboot"),
        ("device_tracker", FreeboxDevice(router, {
            "l2ident": {"id": router.mac}, "primary_name": "Box", "attrs": {},
        }, False), "connection.attributes"),
    ]
    registry = er.async_get(hass)
    hidden = None
    ignored = None
    for index, (domain, entity, role) in enumerate(built):
        assert entity_role(router.mac, domain, entity.unique_id) == role
        row = registry.async_get_or_create(
            domain, DOMAIN, entity.unique_id, config_entry=entry,
            suggested_object_id=f"srv_{index}",
        )
        registry.async_update_entity(row.entity_id, name=f"Renommé {index}")
        if role == "connection.rate_down":
            hidden = row.entity_id
        if role is None:
            ignored = row.entity_id
    decoy = registry.async_get_or_create(
        "sensor", DOMAIN, "not-the-rate", config_entry=entry, suggested_object_id="vitesse_de_telechargement",
    )
    registry.async_update_entity(decoy.entity_id, name="Vitesse de téléchargement Freebox")
    assert entity_role(router.mac, "sensor", f"{router.mac}_wifi_client_list_gateway") is None
    assert entity_role(router.mac, "button", f"{router.mac}_player_1_key_ok") is None
    assert entity_role(router.mac, "sensor", "Vitesse de téléchargement Freebox") is None
    devices = dr.async_get(hass)
    devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, router.mac)},
        name="Freebox Pop", model="fbxgw9", sw_version="4.9.9", manufacturer="Freebox SAS",
    )
    options = dict(entry.options)
    view = server_entities_for_entry(hass, entry, lambda entity_id: entity_id != hidden)
    assert view["system"]["pretty_name"] == "Freebox Pop"
    assert view["system"]["model"] == "fbxgw9"
    assert view["system"]["firmware"] == "4.9.9"
    assert _index(view, "connection.rate_down") is None
    assert decoy.entity_id != _index(view, "connection.rate_up")
    assert _index(view, "connection.rate_up").startswith("sensor.")
    assert len(_index(view, "health.fans")) == 1
    assert len(_index(view, "network.wifi_clients")) == 3
    assert ignored not in _index(view, "network.wifi_clients")
    assert _index(view, "network.wifi").startswith("switch.")
    assert _index(view, "actions.reboot").startswith("button.")
    assert entry.options == options
    full = server_entities_for_entry(hass, entry, lambda entity_id: True)
    assert full["connection"]["rate_down"].startswith("sensor.")
    assert "Renommé" not in str(full)


async def test_server_entities_websocket_filters_entries(hass, hass_ws_client, home_context, hass_read_only_access_token):
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    entry.mock_state(hass, ConfigEntryState.LOADED)
    other_entry = MockConfigEntry(domain=DOMAIN, data={"host": "other.test"})
    other_entry.add_to_hass(hass)
    other = FreeboxRouter(hass, other_entry, AsyncMock(), {
        "mac": "00:00:00:00:00:09",
        "model_info": {"pretty_name": "Second", "name": "second"},
        "firmware_version": "1.0.0",
    })
    other_entry.runtime_data = other
    other_entry.mock_state(hass, ConfigEntryState.LOADED)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{router.mac} fan_1", config_entry=entry, suggested_object_id="fan_one",
    )
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{other.mac} fan_9", config_entry=other_entry, suggested_object_id="fan_two",
    )
    async_register_server_websocket_api(hass)
    async_register_server_websocket_api(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/server_entities"})
    response = await client.receive_json()
    assert response["success"] is True
    by_id = {item["entry_id"]: item for item in response["result"]["entries"]}
    assert set(by_id) == {entry.entry_id, other_entry.entry_id}
    assert by_id[other_entry.entry_id]["system"]["pretty_name"] == "Second"
    assert by_id[other_entry.entry_id]["system"]["model"] == "second"
    assert by_id[other_entry.entry_id]["system"]["firmware"] == "1.0.0"
    assert by_id[entry.entry_id]["health"]["fans"]
    assert by_id[other_entry.entry_id]["health"]["fans"] != by_id[entry.entry_id]["health"]["fans"]
    await client.send_json_auto_id({"type": "freebox_homexa/server_entities", "entry_id": other_entry.entry_id})
    one = await client.receive_json()
    assert [item["entry_id"] for item in one["result"]["entries"]] == [other_entry.entry_id]
    limited = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await limited.send_json_auto_id({"type": "freebox_homexa/server_entities", "entry_id": entry.entry_id})
    assert (await limited.receive_json())["success"] is True


@pytest.mark.parametrize("fields", [
    {"entry_id": ""}, {"entry_id": "   "}, {"entry_id": 4}, {"extra": True},
])
async def test_server_entities_rejects_invalid_envelopes(hass, hass_ws_client, fields):
    client = await hass_ws_client(hass)
    async_register_server_websocket_api(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/server_entities", **fields})
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] == "invalid_format"


def test_view_helpers_skip_bad_shapes_and_duplicate_ids():
    class Item:
        def __init__(self, key: str, name: object) -> None:
            self.key = key
            self.name = name

    assert _text(None) is None
    assert _text("  ") is None
    assert _text(" Pop ") == "Pop"
    assert _named([Item("other", "x"), Item("rate", 1), Item("rate", "Nom")], "rate") == "Nom"
    with pytest.raises(ValueError):
        _named([Item("nope", "x")], "missing")
    assert _keyed([Item("a", None), Item("partition_free_space", "libre")], "partition_free_space") == "partition_free_space"
    with pytest.raises(ValueError):
        _keyed([], "missing")
    view = _blank("entry")
    _put(view, "health.fans", "sensor.b")
    _put(view, "health.fans", "sensor.a")
    _put(view, "health.fans", "sensor.a")
    _put(view, "calls.missed", "sensor.m")
    _put(view, "calls.missed", "sensor.other")
    _sort_lists(view)
    assert view["health"]["fans"] == ["sensor.a", "sensor.b"]
    assert view["calls"]["missed"] == "sensor.m"
    _put({"health": []}, "health.fans", "sensor.a")
    _put({"health": {"fans": "nope"}}, "health.fans", "sensor.a")
    broken = _blank("entry")
    broken["health"] = []
    _sort_lists(broken)
    broken = _blank("entry")
    health = broken["health"]
    assert isinstance(health, dict)
    health["fans"] = "nope"
    _sort_lists(broken)
    assert entity_role("", "sensor", "fan_1") is None
    with pytest.raises(vol.Invalid):
        websocket_server_entities(None, None, {"id": "bad", "type": "freebox_homexa/server_entities"})


async def test_register_skips_a_non_dict_store(hass):
    hass.data[DOMAIN] = []
    async_register_server_websocket_api(hass)


async def test_server_entities_unknown_or_unidentified_entry(hass, hass_ws_client, home_context):
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    entry.mock_state(hass, ConfigEntryState.LOADED)
    client = await hass_ws_client(hass)
    async_register_server_websocket_api(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/server_entities", "entry_id": "missing"})
    assert (await client.receive_json())["error"]["code"] == "not_found"
    router.mac = ""
    await client.send_json_auto_id({"type": "freebox_homexa/server_entities", "entry_id": entry.entry_id})
    assert (await client.receive_json())["error"]["code"] == "not_found"
    await client.send_json_auto_id({"type": "freebox_homexa/server_entities"})
    listed = await client.receive_json()
    assert listed["success"] is True
    assert listed["result"]["entries"] == []
