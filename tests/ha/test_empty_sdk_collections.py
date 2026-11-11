"""Empty Freebox collections omit result; freebox-api then returns None.

None is an empty list. A call-log failure must not take the other sensors down.
"""
from copy import deepcopy

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.router import FreeboxRouter
from test_dynamic_discovery import forwarded_empty
from test_home_platforms import home_context  # noqa: F401  # fixture required by forwarded_empty


COLLECTIONS = (
    "calls", "disks", "raids", "home", "hosts", "bss", "ap", "stations", "players",
)


def _disk():
    return {
        "id": 1, "model": "Test disk",
        "partitions": [{"id": 1, "label": "Disque", "total_bytes": 100, "free_bytes": 40}],
    }


def _prime(router):
    api = router._api
    api.system.get_config.return_value = {
        "sensors": [{"name": "temp_cpu", "value": 42}],
        "uptime_val": 120, "serial": "SYNTHETIC",
    }
    api.connection.get_status.return_value = {
        "rate_down": 8000, "rate_up": 1000, "ipv4": "192.0.2.10", "ipv6": None, "media": "ftth",
    }
    api.call.get_calls_log.return_value = []
    api.storage.get_disks.return_value = [_disk()]
    api.storage.get_raids.return_value = [{"id": 4, "name": "Test RAID", "degraded": False}]
    api.lan.get_hosts_list.return_value = []
    api.wifi.get_global_config.return_value = {"enabled": True}
    api.wifi.get_bss.return_value = []
    api.wifi.get_ap_list.return_value = [
        {"id": 1, "name": "Freebox", "status": {"state": "active"}},
    ]
    api.wifi.get_station_list.return_value = []
    api.wifi._access.get.return_value = []
    api.player.get_players.return_value = []


def _state(hass, unique_id, domain="sensor"):
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id, unique_id
    state = hass.states.get(entity_id)
    assert state is not None
    return state


def _assert_server_sensors(hass, router):
    mac = router.mac
    assert router.sensors_available and router.calls_available and router.disks_available
    for name in (
        "Vitesse de téléchargement Freebox",
        "Vitesse de téléversement Freebox",
        "IP Externe Freebox",
        "Temps de fonctionnement Freebox",
        "Appels manqués Freebox",
        "Derniers appels Freebox",
        "Freebox temp_cpu",
    ):
        assert _state(hass, f"{mac} {name}").state != "unavailable"
    assert _state(hass, f"{mac} Appels manqués Freebox").state == "0"
    assert _state(hass, f"{mac} Derniers appels Freebox").state == "0"
    disk = _state(hass, f"{mac} partition_free_space 1 1")
    assert disk.state != "unavailable"
    assert "40" in disk.state


@pytest.mark.parametrize("collection", COLLECTIONS)
async def test_none_collection_keeps_sensors_and_discovers_disks(hass, forwarded_empty, collection, caplog):
    """An omitted Freebox result stays a successful empty collection."""
    router, _entry, seed, _snapshot, transport = forwarded_empty
    _prime(router)
    api = router._api
    if collection == "calls":
        api.call.get_calls_log.return_value = None
    elif collection == "disks":
        api.storage.get_disks.return_value = None
    elif collection == "raids":
        api.storage.get_raids.return_value = None
    elif collection == "hosts":
        api.lan.get_hosts_list.return_value = None
    elif collection == "bss":
        api.wifi.get_bss.return_value = None
    elif collection == "ap":
        api.wifi.get_ap_list.return_value = None
    elif collection == "stations":
        api.wifi.get_station_list.return_value = None
    elif collection == "players":
        api.player.get_players.return_value = None
    elif collection == "home":
        async def read(path):
            if path == "home/nodes":
                return None
            return {"value": False}
        transport.get.side_effect = read
        router.home_devices[seed["id"]] = deepcopy(seed)

    if collection in {"hosts", "bss", "ap", "stations"}:
        await router.update_device_trackers()
        await hass.async_block_till_done()
    if collection == "home":
        await FreeboxRouter.update_home_devices(router)
        await hass.async_block_till_done()
        assert router.home_available and router.home_snapshot_known
        assert router.home_devices == {}
    if collection == "players":
        await router.async_update_players()
        assert router.players == [] and router.players_initialized
        assert "Inventaire Player indisponible" not in caplog.text
        assert router._source_states[("player_inventory", router.entry_id)] is True
    if collection == "disks":
        await router.update_sensors()
        await hass.async_block_till_done()
        assert router.disks == {} and router.disks_available and router.sensors_available
        assert _state(hass, f"{router.mac} Freebox temp_cpu").state != "unavailable"
        api.storage.get_disks.return_value = [_disk()]

    await router.update_sensors()
    await hass.async_block_till_done()
    _assert_server_sensors(hass, router)

    if collection == "calls":
        assert router.call_list == []
    elif collection == "raids":
        assert router.raids_available and router.raids == {}
    elif collection == "hosts":
        assert router.lan_available and router.supports_hosts
    elif collection == "bss":
        assert "bss" not in router.wifi_api_errors
        assert router.wifi_bss_status == []
    elif collection == "ap":
        assert "ap" not in router.wifi_api_errors and router.wifi_stations_available
        assert router.wifi_radio_status == []
    elif collection == "stations":
        assert router.wifi_stations_available
        assert "stations" not in router.wifi_api_errors
    if collection in {"hosts", "bss", "ap", "stations"}:
        gateway = _state(hass, f"{router.mac}_wifi_ap_gateway", "binary_sensor")
        assert gateway.state != "unavailable"

    disk_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{router.mac} partition_free_space 1 1")
    rate_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{router.mac} Vitesse de téléchargement Freebox")
    before = {
        entity_id: er.async_get(hass).async_get(entity_id).unique_id
        for entity_id in (disk_id, rate_id)
    }
    await router.update_sensors()
    await hass.async_block_till_done()
    for entity_id, unique_id in before.items():
        current = er.async_get(hass).async_get(entity_id)
        assert current.entity_id == entity_id and current.unique_id == unique_id
        assert hass.states.get(entity_id).state != "unavailable"


async def test_call_log_error_hides_only_call_sensors(hass, forwarded_empty, caplog):
    """A call-log failure leaves temperatures, rates and disks available."""
    router, _entry, _seed, _snapshot, _transport = forwarded_empty
    _prime(router)
    secret = {"type": "missed", "new": True, "name": "Alice", "number": "0102030405"}
    router.call_list = [secret]
    async_dispatcher_send(hass, router.signal_sensor_update)
    await hass.async_block_till_done()
    missed = _state(hass, f"{router.mac} Appels manqués Freebox")
    calls = _state(hass, f"{router.mac} Derniers appels Freebox")
    assert missed.state == "1"
    assert "Alice" not in missed.state and "0102030405" not in str(missed.attributes)
    assert "Alice" not in calls.state and "0102030405" not in str(calls.attributes)
    identities = {
        entity_id: er.async_get(hass).async_get(entity_id).unique_id
        for entity_id in (missed.entity_id, calls.entity_id)
    }

    router._api.call.get_calls_log.side_effect = RuntimeError("synthetic call log")
    with caplog.at_level("INFO"):
        await router.update_sensors()
        await hass.async_block_till_done()
        await router.update_sensors()
        await hass.async_block_till_done()

    assert router.sensors_available and router.disks_available
    assert router.calls_available is False
    assert router.call_list == [secret]
    assert _state(hass, f"{router.mac} Appels manqués Freebox").state == "unavailable"
    assert _state(hass, f"{router.mac} Derniers appels Freebox").state == "unavailable"
    for name in (
        "Vitesse de téléchargement Freebox",
        "Vitesse de téléversement Freebox",
        "IP Externe Freebox",
        "Temps de fonctionnement Freebox",
        "Freebox temp_cpu",
    ):
        assert _state(hass, f"{router.mac} {name}").state != "unavailable"
    disk = _state(hass, f"{router.mac} partition_free_space 1 1")
    assert disk.state != "unavailable"
    assert "Capteurs Freebox indisponibles" not in caplog.text
    assert caplog.text.count("Journal d'appels Freebox indisponible") == 1
    assert "0102030405" not in caplog.text and "Alice" not in caplog.text
    for entity_id, unique_id in identities.items():
        current = er.async_get(hass).async_get(entity_id)
        assert current.entity_id == entity_id and current.unique_id == unique_id
