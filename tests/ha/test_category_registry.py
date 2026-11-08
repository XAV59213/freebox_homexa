"""Category updates must retain user registry preferences and stable identity."""
import logging
from datetime import timedelta
import pytest
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform
from test_entity_inventory import build_inventory
from test_home_platforms import home_context


@pytest.mark.parametrize("variant", ["connection/ipv4", "connection/uptime", "temperature", "calls/missed",
    "disk/partition_free_space", "battery", "inversion", "ap/gateway"])
async def test_category_metadata_preserves_user_registry_settings(hass, home_context, variant):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    objects, coordinator = build_inventory(hass, router, node, entry)
    entity = next(entity for key, entity in objects if key == variant)
    domain = "switch" if variant == "inversion" else "binary_sensor" if variant.startswith("ap/") else "sensor"
    category = EntityCategory.CONFIG if variant == "inversion" else EntityCategory.DIAGNOSTIC
    registry = er.async_get(hass)
    original = registry.async_get_or_create(domain, "freebox_homexa", entity.unique_id, config_entry=entry,
        suggested_object_id="synthetic_existing",
        disabled_by=er.RegistryEntryDisabler.USER, hidden_by=er.RegistryEntryHider.USER)
    registry.async_update_entity(original.entity_id, name="Nom utilisateur")
    uid, entity_id = original.unique_id, original.entity_id
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
        platform_name="freebox_homexa", platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
    platform.config_entry = entry
    try:
        await platform.async_add_entities([entity])
        current = registry.async_get(entity_id)
        assert current.unique_id == uid
        assert current.entity_id == entity_id
        assert current.name == "Nom utilisateur"
        assert current.disabled_by is er.RegistryEntryDisabler.USER
        assert current.hidden_by is er.RegistryEntryHider.USER
        assert current.entity_category is category
        assert not platform.entities  # opting out remains effective
        router._api.home.set_home_endpoint_value.assert_not_called()
        router._api.remote.send_key.assert_not_called()
    finally:
        await platform.async_reset()
        await coordinator.async_shutdown()


async def test_global_metadata_update_preserves_all_user_registry_choices(hass, home_context):
    """Every inventoried constructor goes through real registry/platform logic."""
    from homeassistant.components import (alarm_control_panel, binary_sensor, button,
        calendar, camera, cover, device_tracker, media_player, remote, sensor, switch)
    from homeassistant.util import slugify
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    objects, coordinator = build_inventory(hass, router, node, entry)
    registry = er.async_get(hass)
    domains = [("alarm_control_panel", alarm_control_panel.AlarmControlPanelEntity),
        ("binary_sensor", binary_sensor.BinarySensorEntity), ("button", button.ButtonEntity),
        ("calendar", calendar.CalendarEntity), ("camera", camera.Camera),
        ("cover", cover.CoverEntity), ("device_tracker", device_tracker.ScannerEntity),
        ("media_player", media_player.MediaPlayerEntity), ("remote", remote.RemoteEntity),
        ("sensor", sensor.SensorEntity), ("switch", switch.SwitchEntity)]
    try:
        for variant, entity in objects:
            domain = next(domain for domain, cls in domains if isinstance(entity, cls))
            original = registry.async_get_or_create(domain, "freebox_homexa", entity.unique_id,
                config_entry=entry, suggested_object_id="legacy_" + slugify(variant),
                disabled_by=er.RegistryEntryDisabler.USER, hidden_by=er.RegistryEntryHider.USER)
            registry.async_update_entity(original.entity_id, name="Nom personnalisé")
            platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
                platform_name="freebox_homexa", platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
            platform.config_entry = entry
            try:
                await platform.async_add_entities([entity])
                current = registry.async_get(original.entity_id)
                assert current.unique_id == original.unique_id, variant
                assert current.name == "Nom personnalisé", variant
                assert current.disabled_by is er.RegistryEntryDisabler.USER, variant
                assert current.hidden_by is er.RegistryEntryHider.USER, variant
                assert entity.has_entity_name is True, variant
                assert not platform.entities, variant
            finally:
                await platform.async_reset()
        router._api.home.set_home_endpoint_value.assert_not_called()
        router._api.remote.send_key.assert_not_called()
    finally:
        await coordinator.async_shutdown()
