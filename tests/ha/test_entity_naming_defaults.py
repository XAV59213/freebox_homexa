"""Real HA naming and default-enable behavior, no device commands."""
import logging
from datetime import timedelta
import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform
from custom_components.freebox_homexa.binary_sensor import FreeboxDwsSensor
from custom_components.freebox_homexa.entity import FreeboxHomeEntity
from custom_components.freebox_homexa.sensor import FreeboxBatterySensor, FreeboxWifiSignalSensor
from custom_components.freebox_homexa.registry_compat import get_device_by_identifier
from test_home_platforms import home_context


def platform_for(hass, entry, domain):
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
        platform_name="freebox_homexa", platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
    platform.config_entry = entry
    return platform


async def test_primary_secondary_names_follow_device_rename_not_user_entity_name(hass, home_context):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    node = {**node, "category": "dws", "label": "Porte synthétique"}
    router.home_devices[node["id"]] = node
    primary = FreeboxDwsSensor(hass, router, node)
    battery = FreeboxBatterySensor(hass, router, node, {"name": "battery", "label": "Batterie"})
    platforms = [platform_for(hass, entry, "binary_sensor"), platform_for(hass, entry, "sensor")]
    try:
        await platforms[0].async_add_entities([primary])
        await platforms[1].async_add_entities([battery])
        ids = [primary.entity_id, battery.entity_id]
        assert primary.name is None
        assert battery.name == "Batterie"
        assert hass.states.get(primary.entity_id).attributes["friendly_name"] == "Porte synthétique"
        assert hass.states.get(battery.entity_id).attributes["friendly_name"] == "Porte synthétique Batterie"
        registry = dr.async_get(hass)
        device = get_device_by_identifier(registry, ("freebox_homexa", node["id"]), router.entry_id)
        registry.async_update_device(device.id, name_by_user="Porte personnalisée")
        await hass.async_block_till_done()
        assert hass.states.get(primary.entity_id).attributes["friendly_name"] == "Porte personnalisée"
        assert hass.states.get(battery.entity_id).attributes["friendly_name"] == "Porte personnalisée Batterie"
        er.async_get(hass).async_update_entity(battery.entity_id, name="Pile personnalisée")
        await hass.async_block_till_done()
        router.home_devices[node["id"]] = {**node, "label": "Nouveau nom source"}
        await FreeboxHomeEntity.async_update_signal(primary)
        await FreeboxHomeEntity.async_update_signal(battery)
        await hass.async_block_till_done()
        assert registry.async_get(device.id).name == "Nouveau nom source"
        assert registry.async_get(device.id).name_by_user == "Porte personnalisée"
        assert hass.states.get(battery.entity_id).attributes["friendly_name"] == "Pile personnalisée"
        assert ids == [primary.entity_id, battery.entity_id]
        router._api.home.set_home_endpoint_value.assert_not_called()
    finally:
        for platform in platforms:
            await platform.async_reset()


@pytest.mark.parametrize("existing", ["new", "enabled", "disabled"])
async def test_rssi_default_only_applies_to_new_entities(hass, home_context, existing):
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    device = {"l2ident": {"id": "00:00:00:00:10:01"}, "primary_name": "Synthetic",
        "wifi": {"wifi_signal_dbm": -40}, "active": True}
    router.devices[device["l2ident"]["id"]] = device
    entity = FreeboxWifiSignalSensor(router, device, False)
    registry = er.async_get(hass)
    original = None
    if existing != "new":
        original = registry.async_get_or_create("sensor", "freebox_homexa", entity.unique_id,
            config_entry=entry, suggested_object_id="existing_signal",
            disabled_by=er.RegistryEntryDisabler.USER if existing == "disabled" else None)
    platform = platform_for(hass, entry, "sensor")
    try:
        await platform.async_add_entities([entity])
        registered = registry.async_get(entity.entity_id)
        expected = {"new": er.RegistryEntryDisabler.INTEGRATION,
                    "enabled": None, "disabled": er.RegistryEntryDisabler.USER}[existing]
        assert registered.disabled_by is expected
        assert (hass.states.get(entity.entity_id) is not None) == (existing == "enabled")
        if original is not None:
            assert registered.entity_id == original.entity_id
            assert registered.unique_id == original.unique_id
        router._api.wifi.get_station_list.assert_not_called()
    finally:
        await platform.async_reset()


async def test_display_changes_do_not_change_historical_unique_id_inputs(hass, home_context):
    from custom_components.freebox_homexa.sensor import FreeboxSensor, CONNECTION_SENSORS
    from custom_components.freebox_homexa.switch import FreeboxSwitch, SWITCH_DESCRIPTIONS
    router, _ = home_context
    sensor = FreeboxSensor(router, CONNECTION_SENSORS[0])
    switch = FreeboxSwitch(router, SWITCH_DESCRIPTIONS[0])
    assert sensor.unique_id == f"{router.mac} Vitesse de téléchargement Freebox"
    assert sensor.name == "Vitesse de téléchargement"
    assert switch.unique_id == f"{router.mac} Freebox WiFi"
    assert switch.name == "WiFi"


async def test_sensor_api_failure_hides_cache_then_recovers_missing_value_unknown(hass, home_context, caplog):
    from custom_components.freebox_homexa.sensor import FreeboxSensor, CONNECTION_SENSORS
    from freebox_api.exceptions import HttpRequestError
    router, _ = home_context
    api = router._api
    api.system.get_config.return_value = {"sensors": [], "uptime_val": 100, "serial": "SYNTHETIC"}
    api.connection.get_status.return_value = {"rate_down": 8000, "rate_up": 0, "ipv4": "192.0.2.1"}
    api.call.get_calls_log.return_value = []
    api.storage.get_disks.return_value = []
    router.supports_raid = False
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entity = FreeboxSensor(router, CONNECTION_SENSORS[0])
    platform = platform_for(hass, entry, "sensor")
    try:
        await router.update_sensors()
        await platform.async_add_entities([entity])
        assert entity.available and entity.native_value is not None
        api.system.get_config.side_effect = HttpRequestError("synthetic source offline")
        await router.update_sensors()
        await router.update_sensors()
        await hass.async_block_till_done()
        assert router.reachable  # a sensor-source failure is not a LAN failure
        assert hass.states.get(entity.entity_id).state == "unavailable"
        assert caplog.text.count("Capteurs Freebox indisponibles") == 1
        api.system.get_config.side_effect = None
        api.connection.get_status.return_value = {"rate_up": 0, "ipv4": "192.0.2.1"}
        await router.update_sensors()
        await hass.async_block_till_done()
        assert entity.available
        assert entity.native_value is None
        assert hass.states.get(entity.entity_id).state == "unknown"
        assert caplog.text.count("Capteurs Freebox de nouveau disponibles") == 1
        api.home.set_home_endpoint_value.assert_not_called()
    finally:
        await platform.async_reset()


@pytest.mark.parametrize("invalid", [False, "not numeric"])
async def test_non_numeric_connection_rates_are_unknown_not_zero(hass, home_context, invalid):
    router, _ = home_context
    api = router._api
    api.system.get_config.return_value = {"sensors": [], "uptime_val": 100, "serial": "SYNTHETIC"}
    api.connection.get_status.return_value = {"rate_down": invalid, "rate_up": 0}
    api.call.get_calls_log.return_value = []
    api.storage.get_disks.return_value = []
    router.supports_raid = False
    await router.update_sensors()
    assert router.sensors_available
    assert router.sensors_connection["rate_down"] is None
    assert router.sensors_connection["rate_up"] == 0
