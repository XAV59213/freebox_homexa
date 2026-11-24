"""HA 2026.11: device trackers must not create a new device on every setup.

Mocks only. No Freebox, no network, no real device.
"""
from datetime import timedelta
from unittest.mock import patch

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.device_groups import (
    async_cleanup_lan_client_devices_once,
    async_remove_lan_client_devices,
)
from custom_components.freebox_homexa.device_tracker import FreeboxDevice
from test_home_platforms import home_context, make_platform

MAC = "aa:bb:cc:dd:ee:10"
FOREIGN_MAC = "aa:bb:cc:dd:ee:11"
OFF_MAC = "aa:bb:cc:dd:ee:12"
STABLE_MAC = "aa:bb:cc:dd:ee:13"
DISABLED_MAC = "aa:bb:cc:dd:ee:14"
NAMED_MAC = "aa:bb:cc:dd:ee:15"


def _host(mac: str, name: str) -> dict[str, str]:
    return {"l2ident": {"id": mac}, "primary_name": name}


def _described(entity: FreeboxDevice) -> object:
    """Device info HA will read, or the stored one when 2026.10 hides the property."""
    info = entity.device_info
    if info is not None:
        return info
    return entity._attr_device_info


def _connection(mac: str) -> set[tuple[str, str]]:
    return {(CONNECTION_NETWORK_MAC, mac)}


async def test_tracker_device_info_three_cases(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    devices = dr.async_get(hass)
    saved_options = dict(entry.options)

    enabled = FreeboxDevice(router, _host(MAC, "Telephone"), True)
    enabled_info = _described(enabled)
    assert enabled_info["connections"] == _connection(MAC)
    assert "identifiers" not in enabled_info
    assert enabled.unique_id == MAC

    absent = FreeboxDevice(router, _host(OFF_MAC, "Tablette"), False)
    absent_info = _described(absent)
    assert "connections" not in absent_info
    assert "identifiers" not in absent_info

    foreign_entry = MockConfigEntry(domain="shelly", data={})
    foreign_entry.add_to_hass(hass)
    foreign = devices.async_get_or_create(
        config_entry_id=foreign_entry.entry_id,
        connections=_connection(FOREIGN_MAC),
        name="Shelly",
    )
    devices.async_update_device(foreign.id, name_by_user="Ma prise")
    linked = FreeboxDevice(router, _host(FOREIGN_MAC, "Shelly"), False)
    assert _described(linked)["connections"] == _connection(FOREIGN_MAC)
    assert devices.async_get(foreign.id).name_by_user == "Ma prise"
    assert devices.async_get(foreign.id).config_entry_id == foreign_entry.entry_id

    server = FreeboxDevice(
        router,
        {"l2ident": {"id": router.mac}, "primary_name": "Freebox", "attrs": {"role": "server"}},
        False,
    )
    assert (DOMAIN, router.mac) in _described(server)["identifiers"]

    canon = "2066CF4B4969"
    router.repeaters[canon] = {"name": "Cave", "macs": ["20:66:cf:4b:49:69"], "model": "RP01"}
    router.repeater_aliases[canon] = canon
    repeater = FreeboxDevice(router, _host("20:66:cf:4b:49:69", "Cave"), True)
    assert (DOMAIN, "repeater_2066CF4B4969") in _described(repeater)["identifiers"]
    assert entry.options == saved_options


async def test_option_off_creates_no_client_device(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    saved_options = dict(entry.options)
    tracker = FreeboxDevice(router, _host(OFF_MAC, "Tablette"), False)
    platform = make_platform(hass, "device_tracker")
    platform.config_entry = entry
    try:
        er.async_get(hass).async_get_or_create(
            "device_tracker", DOMAIN, tracker.unique_id,
            config_entry=entry, disabled_by=None,
        )
        await platform.async_add_entities([tracker])
        await hass.async_block_till_done()
        devices = dr.async_get(hass)
        assert devices.async_get_devices(connections=_connection(OFF_MAC)) == []
        row = er.async_get(hass).async_get(tracker.entity_id)
        assert row is not None
        assert row.device_id is None
        assert row.unique_id == OFF_MAC
        assert row.entity_id == tracker.entity_id
        assert entry.options == saved_options
    finally:
        await platform.async_reset()


async def test_second_setup_moves_no_entity_and_schedules_no_reload(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    saved_options = dict(entry.options)
    host = _host(STABLE_MAC, "Ordinateur")
    router.devices[STABLE_MAC] = host
    router.create_lan_devices = True
    schedule_path = "homeassistant.config_entries.ConfigEntries.async_schedule_reload"

    with patch(schedule_path) as schedule:
        first = FreeboxDevice(router, host, True)
        exposes_device_info = first.device_info is not None
        er.async_get(hass).async_get_or_create(
            "device_tracker", DOMAIN, first.unique_id,
            config_entry=entry, disabled_by=None,
        )
        platform = make_platform(hass, "device_tracker")
        platform.config_entry = entry
        try:
            await platform.async_add_entities([first])
            await hass.async_block_till_done()
            row = er.async_get(hass).async_get(first.entity_id)
            assert row is not None and row.device_id is not None
            entity_id, unique_id, device_id = row.entity_id, row.unique_id, row.device_id
            await platform.async_reset()

            registry = er.async_get(hass)
            moves: list[str] = []
            original = registry.async_update_entity

            def spy(entity_id_arg, **kwargs):
                current = registry.async_get(entity_id_arg)
                new_device = kwargs.get("device_id", current.device_id if current else None)
                if "device_id" in kwargs and current is not None and new_device != current.device_id:
                    moves.append(entity_id_arg)
                return original(entity_id_arg, **kwargs)

            registry.async_update_entity = spy
            try:
                second = FreeboxDevice(router, host, True)
                again_platform = make_platform(hass, "device_tracker")
                again_platform.config_entry = entry
                await again_platform.async_add_entities([second])
                await hass.async_block_till_done()
                again = er.async_get(hass).async_get(entity_id)
                assert again is not None
                assert again.entity_id == entity_id
                assert again.unique_id == unique_id
                assert again.device_id == device_id
                if exposes_device_info:
                    assert moves == []
                assert entry.options == saved_options
                async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
                await hass.async_block_till_done()
                schedule.assert_not_called()
            finally:
                registry.async_update_entity = original
                await again_platform.async_reset()
        finally:
            await platform.async_reset()


async def test_disabled_client_device_does_not_reload(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    saved_options = dict(entry.options)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections=_connection(DISABLED_MAC),
        name="Client",
    )
    devices.async_update_device(device.id, disabled_by=dr.DeviceEntryDisabler.USER)
    host = _host(DISABLED_MAC, "Client")
    tracker = FreeboxDevice(router, host, False)
    exposes_device_info = tracker.device_info is not None
    assert _described(tracker)["connections"] == _connection(DISABLED_MAC)
    assert async_remove_lan_client_devices(hass, entry, router.mac) == 0
    assert devices.async_get(device.id) is not None
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "device_tracker", DOMAIN, tracker.unique_id,
        config_entry=entry, device_id=device.id, disabled_by=None,
    )

    schedule_path = "homeassistant.config_entries.ConfigEntries.async_schedule_reload"
    with patch(schedule_path) as schedule:
        platform = make_platform(hass, "device_tracker")
        platform.config_entry = entry
        try:
            await platform.async_add_entities([tracker])
            await hass.async_block_till_done()
            entity_id = registry.async_get_entity_id("device_tracker", DOMAIN, DISABLED_MAC)
            assert entity_id is not None
            row = registry.async_get(entity_id)
            assert row is not None
            assert row.unique_id == DISABLED_MAC
            if exposes_device_info:
                assert row.device_id == device.id
                assert row.disabled_by == er.RegistryEntryDisabler.DEVICE
            await platform.async_reset()

            again_platform = make_platform(hass, "device_tracker")
            again_platform.config_entry = entry
            await again_platform.async_add_entities([FreeboxDevice(router, host, False)])
            await hass.async_block_till_done()
            again = registry.async_get(entity_id)
            assert again is not None
            assert again.entity_id == entity_id
            assert again.unique_id == row.unique_id
            assert again.device_id == row.device_id
            assert again.disabled_by == row.disabled_by
            assert entry.options == saved_options
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
            await hass.async_block_till_done()
            schedule.assert_not_called()
            assert devices.async_get(device.id) is not None
        finally:
            await platform.async_reset()


async def test_cleanup_detaches_entities_once_and_keeps_customized_devices(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    plain = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections=_connection(OFF_MAC),
        name="Auto",
    )
    kept_entity = registry.async_get_or_create(
        "device_tracker", DOMAIN, OFF_MAC, config_entry=entry, device_id=plain.id,
    )
    named = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections=_connection(NAMED_MAC),
        name="Nomme",
    )
    devices.async_update_device(named.id, name_by_user="Mon telephone")
    from homeassistant.helpers import area_registry as ar

    area = ar.async_get(hass).async_create("Salon")
    placed = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections=_connection("aa:bb:cc:dd:ee:16"),
        name="Place",
    )
    devices.async_update_device(placed.id, area_id=area.id)
    other = MockConfigEntry(domain="other", data={})
    other.add_to_hass(hass)
    shared_entity_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections=_connection("aa:bb:cc:dd:ee:17"),
        name="Partage",
    )
    registry.async_get_or_create(
        "sensor", "other", "synthetic-other", config_entry=other, device_id=shared_entity_device.id,
    )

    removed = async_cleanup_lan_client_devices_once(hass, entry, router.mac, False)
    assert removed == 1
    assert devices.async_get(plain.id) is None
    assert registry.async_get(kept_entity.entity_id) is not None
    assert registry.async_get(kept_entity.entity_id).device_id is None
    assert registry.async_get(kept_entity.entity_id).entity_id == kept_entity.entity_id
    assert registry.async_get(kept_entity.entity_id).unique_id == OFF_MAC
    assert devices.async_get(named.id) is not None
    assert devices.async_get(placed.id) is not None
    assert devices.async_get(shared_entity_device.id) is not None

    recreated = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections=_connection("aa:bb:cc:dd:ee:18"),
        name="Recree",
    )
    assert async_cleanup_lan_client_devices_once(hass, entry, router.mac, False) == 0
    assert devices.async_get(recreated.id) is not None
    assert async_cleanup_lan_client_devices_once(hass, entry, router.mac, True) == 0
    assert async_cleanup_lan_client_devices_once(hass, entry, router.mac, False) == 1
    assert devices.async_get(recreated.id) is None
