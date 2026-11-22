"""Ventilateurs system.fans : mesures synthétiques, aucun appareil réel."""
import logging

from freebox_api.api.system import System
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers import entity_registry as er

from custom_components.freebox_homexa.sensor import (
    CONNECTION_SENSORS,
    FreeboxSensor,
    fan_sensor_description,
    temperature_sensor_description,
)
from test_dynamic_discovery import forwarded_empty, owned
from test_home_platforms import home_context


def _system(router, payload):
    access = Mock(get=AsyncMock(return_value=payload))
    router._api.system = System(access)
    router._api.connection.get_status.return_value = {"rate_down": 8000, "rate_up": 1000}
    router._api.call.get_calls_log.return_value = []
    router._api.storage.get_disks.return_value = []
    router._api.storage.get_raids.return_value = []
    return access


async def test_fan_readings_keep_temperatures_rates_and_options(hass, home_context, caplog):
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    options = dict(entry.options)
    payload = {
        "serial": "SYNTHETIC",
        "uptime_val": 10,
        "sensors": [{"name": "temp_cpu", "value": 32}, {"name": "fan_cpu", "value": 40}],
        "fans": [
            {"id": "cpu", "name": "Ventilateur CPU", "value": 1400},
            {"id": "off", "value": 0},
            {"id": "bad", "value": True},
            {"id": "neg", "value": -3},
            {"id": "flt", "value": 900.2},
            {"id": "txt", "value": "1400"},
            {"id": "inf", "value": float("inf")},
            {"id": " ", "value": 1},
            {"id": "", "value": 1},
            {"id": 3, "value": 5},
            {"id": "x" * 65, "value": 5},
            {"value": 5},
            "nope",
        ],
    }
    _system(router, payload)
    with caplog.at_level(logging.DEBUG):
        await router.update_sensors()
    assert router.sensors_available
    assert router.sensors_temperature["temp_cpu"] == 32
    assert router.sensors_fans == {
        "fan_cpu": 1400, "fan_off": 0, "fan_bad": None, "fan_neg": None, "fan_flt": 900, "fan_txt": None, "fan_inf": None,
    }
    # La température homonyme reste prioritaire dans le relevé historique.
    assert router.sensors["fan_cpu"] == 40
    assert router.sensors["temp_cpu"] == 32
    assert router.sensors["rate_down"] == 8000
    fan = FreeboxSensor(router, fan_sensor_description("cpu"))
    fan.async_update_state()
    assert fan.unique_id == f"{router.mac} fan_cpu"
    assert fan.native_value == 1400
    stopped = FreeboxSensor(router, fan_sensor_description("off"))
    stopped.async_update_state()
    assert stopped.native_value == 0
    unknown = FreeboxSensor(router, fan_sensor_description("bad"))
    unknown.async_update_state()
    assert unknown.native_value is None
    temperature = FreeboxSensor(router, temperature_sensor_description("temp_cpu"))
    assert temperature.unique_id == f"{router.mac} Freebox temp_cpu"
    rate = FreeboxSensor(router, CONNECTION_SENSORS[0])
    assert rate.unique_id == f"{router.mac} {CONNECTION_SENSORS[0].name}"
    payload["fans"] = None
    await router.update_sensors()
    assert router.sensors_fans == {}
    fan.async_update_state()
    assert fan.native_value is None
    assert temperature.unique_id == f"{router.mac} Freebox temp_cpu"
    payload["fans"] = "illisible"
    with caplog.at_level(logging.INFO):
        await router.update_sensors()
    assert router.sensors_available
    assert router.sensors_temperature["temp_cpu"] == 32
    assert router.sensors_fans == {}
    assert "Liste de ventilateurs Freebox illisible" in caplog.text
    assert entry.options == options
    assert "1400" not in caplog.text


async def test_fan_sensors_are_created_like_temperatures(hass, forwarded_empty):
    router, entry, _, _, _ = forwarded_empty
    config = router._api.system.get_config.return_value
    config["sensors"] = [{"name": "temp_cpu", "value": 36}]
    config["fans"] = [{"id": "1", "value": 1200}, {"id": "2", "value": 800}]
    router._api.connection.get_status.return_value = {}
    router._api.call.get_calls_log.return_value = []
    router._api.storage.get_disks.return_value = []
    router._api.storage.get_raids.return_value = []
    options = dict(entry.options)
    before = {entity_id: row.unique_id for entity_id, row in owned(hass, entry).items()}
    await router.update_sensors()
    await hass.async_block_till_done()
    added = {entity_id: row for entity_id, row in owned(hass, entry).items() if entity_id not in before}
    assert {row.unique_id for row in added.values()} == {
        f"{router.mac} Freebox temp_cpu", f"{router.mac} fan_1", f"{router.mac} fan_2",
    }
    registry = er.async_get(hass)
    fan_id = registry.async_get_entity_id("sensor", "freebox_homexa", f"{router.mac} fan_1")
    assert hass.states.get(fan_id).state == "1200"
    config["fans"][0]["value"] = 1300
    await router.update_sensors()
    await hass.async_block_till_done()
    current = owned(hass, entry)
    assert {entity_id: row.unique_id for entity_id, row in current.items() if entity_id in before} == before
    assert registry.async_get(fan_id).unique_id == f"{router.mac} fan_1"
    assert hass.states.get(fan_id).state == "1300"
    config["fans"] = [{"id": "2", "value": 800}]
    await router.update_sensors()
    await hass.async_block_till_done()
    assert registry.async_get(fan_id).entity_id == fan_id
    assert hass.states.get(fan_id).state == "unknown"
    assert len(owned(hass, entry)) == len(before) + 3
    assert entry.options == options
