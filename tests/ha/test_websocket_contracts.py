"""Authenticated HA websocket envelopes and privacy, with no device network."""
from datetime import datetime, timedelta, UTC

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from test_home_platforms import home_context
from custom_components.freebox_homexa.calls_ws import async_register_calls_websocket_api, format_calls
from custom_components.freebox_homexa.tnt_ws import async_register_homexa_websocket_api
from custom_components.freebox_homexa.tnt_coordinator import ProgrammeTntFrCoordinator, Programme


@pytest.fixture
def calls_context(hass, home_context):
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    entry.mock_state(hass, ConfigEntryState.LOADED)
    router.call_list = [
        {"name": "Synthetic A", "number": "000001", "datetime": 1700000000, "type": "missed", "new": True},
        {"number": "000002", "datetime": 1700000100, "type": "accepted", "new": False},
        {"name": "Old", "datetime": 1699999900, "type": "missed", "new": False},
    ]
    registry = er.async_get(hass)
    entities = [registry.async_get_or_create("sensor", "freebox_homexa", "synthetic " + suffix,
        config_entry=entry) for suffix in ("Derniers appels Freebox", "Appels manqués Freebox", "Other")]
    return router, entry, entities


async def test_calls_defaults_limits_missed_and_no_state_contact_leak(hass, hass_ws_client, calls_context):
    router, entry, entities = calls_context
    client = await hass_ws_client(hass)
    async_register_calls_websocket_api(hass)
    before_options = dict(entry.options)
    for fields, expected in [({}, 3), ({"entity_id": entities[0].entity_id, "limit": 1}, 1),
                             ({"entity_id": entities[1].entity_id}, 1)]:
        await client.send_json_auto_id({"type": "freebox_homexa/calls", **fields})
        response = await client.receive_json()
        assert response["success"] is True
        assert len(response["result"]["calls"]) == expected
    assert response["result"]["calls"][0]["name"] == "Synthetic A"
    assert entry.options == before_options
    assert hass.states.async_all() == []
    router._api.open.assert_not_called()
    router._api.call.get_calls_log.assert_not_called()


@pytest.mark.parametrize("fields", [{"limit": 0}, {"limit": 31}, {"limit": "3"},
    {"entity_id": 42}, {"extra": True}])
async def test_calls_rejects_invalid_envelopes(hass, hass_ws_client, fields):
    client = await hass_ws_client(hass)
    async_register_calls_websocket_api(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/calls", **fields})
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] == "invalid_format"


@pytest.mark.parametrize("index,code", [(2, "invalid_format"), (None, "not_found")])
async def test_calls_rejects_foreign_sensor_and_absent_entity(hass, hass_ws_client, calls_context, index, code):
    client = await hass_ws_client(hass)
    async_register_calls_websocket_api(hass)
    entity = calls_context[2][index].entity_id if index is not None else "sensor.absent"
    await client.send_json_auto_id({"type": "freebox_homexa/calls", "entity_id": entity})
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] == code


async def test_calls_nonadmin_fallback_forbidden_but_entity_permissions_apply(
        hass, hass_ws_client, hass_read_only_access_token, calls_context):
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    async_register_calls_websocket_api(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/calls"})
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] == "unauthorized"
    await client.send_json_auto_id({"type": "freebox_homexa/calls", "entity_id": calls_context[2][0].entity_id})
    response = await client.receive_json()
    assert response["success"] is True


async def test_calls_ambiguous_entries_do_not_guess(hass, hass_ws_client, calls_context):
    other = MockConfigEntry(domain="freebox_homexa", data={})
    other.add_to_hass(hass)
    other.runtime_data = calls_context[0]
    other.mock_state(hass, ConfigEntryState.LOADED)
    client = await hass_ws_client(hass)
    async_register_calls_websocket_api(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/calls"})
    response = await client.receive_json()
    assert response["error"]["code"] == "not_found"


@pytest.mark.parametrize("fields", [{}, {"channels": "TF1.fr"}, {"channels": [42]},
    {"channels": [], "date": 42}, {"channels": [], "unexpected": True}])
async def test_programmes_required_payload_and_types_use_native_invalid_format(hass, hass_ws_client, fields):
    client = await hass_ws_client(hass)
    async_register_homexa_websocket_api(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/tnt_programmes", **fields})
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] == "invalid_format"


async def test_tnt_cached_programmes_multi_entry_first_match_and_profiles(hass, hass_ws_client):
    start = datetime(2026, 11, 7, 19, tzinfo=UTC)
    first = ProgrammeTntFrCoordinator(hass, ["TF1.fr"])
    second = ProgrammeTntFrCoordinator(hass, ["TF1.fr", "France2.fr"])
    for coordinator, channel, title in [(first, "TF1.fr", "First"), (second, "TF1.fr", "Second"),
                                         (second, "France2.fr", "Other")]:
        coordinator._programmes_by_channel[channel] = [Programme(start, start + timedelta(hours=1),
            title, None, None, None, None, None)]
    hass.data["freebox_homexa"] = {"tnt_coordinators": {"one": first, "two": second, "invalid": object()}}
    for profiles in [[{"name": "Alice"}, {"name": ""}, {"name": 42}, "invalid"],
                     [{"name": "Alice"}, {"name": "Bob"}]]:
        entry = MockConfigEntry(domain="freebox_homexa", data={}, options={"reminder_profiles": profiles})
        entry.add_to_hass(hass)
    client = await hass_ws_client(hass)
    async_register_homexa_websocket_api(hass)
    await client.send_json_auto_id({"type": "freebox_homexa/tnt_programmes",
        "channels": ["TF1.fr", "France2.fr", "Absent", "TF1.fr"], "date": "2026-11-07"})
    response = await client.receive_json()
    assert response["success"] is True
    programmes = response["result"]["programmes"]
    assert list(programmes) == ["TF1.fr", "France2.fr"]
    assert programmes["TF1.fr"][0]["title"] == "First"
    await client.send_json_auto_id({"type": "freebox_homexa/tnt_reminder_profiles"})
    assert (await client.receive_json())["result"] == {"profiles": ["Alice", "Bob"]}
    await client.send_json_auto_id({"type": "freebox_homexa/tnt_version"})
    assert (await client.receive_json())["result"]["channel_order"]


def test_call_formatter_preserves_defaults_and_rejects_invalid_timestamp():
    assert format_calls(None) == []
    assert format_calls([{}]) == [{"name": "Inconnu", "number": "", "type": "", "datetime": None,
        "duration": 0, "new": False}]
    with pytest.raises(ValueError, match="Invalid call timestamp"):
        format_calls([{"datetime": "not a timestamp"}])
