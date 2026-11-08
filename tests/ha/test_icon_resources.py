"""Real HA frontend icon resources, independent of custom dashboards."""
from homeassistant.helpers.icon import async_get_icons
from test_home_platforms import home_context
from test_entity_inventory import build_inventory


async def test_fixed_icons_loaded_by_ha_for_all_inventory_variants(hass, home_context):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    objects, coordinator = build_inventory(hass, router, node, entry)
    try:
        resources = (await async_get_icons(hass, 'entity', ['freebox_homexa']))['freebox_homexa']
        checked = []
        for variant, entity in objects:
            entity.hass = hass
            domain = type(entity).__module__.rsplit('.', 1)[-1]
            if domain in {'wifi_ap_sensors', 'lan_group_sensors', 'tnt_sensor'}:
                domain = 'sensor'
            key = entity.translation_key
            if key in resources.get(domain, {}):
                assert resources[domain][key]['default'].startswith('mdi:')
                assert entity.icon is None, variant  # no fixed icon in each state update
                checked.append(variant)
            elif key:
                # Keys with no own icon legitimately use device-class/default icons.
                assert entity.icon is None, variant
        assert len(checked) >= 60
        assert resources['button']['player_app_youtube']['default'] == 'mdi:youtube'
        assert resources['button']['remote_key_home']['default'] == 'mdi:home'
        assert resources['sensor']['tnt_channel']['default'] == 'mdi:television-classic'
        assert resources['device_tracker']['device_unknown']['default'] == 'mdi:help-network'
        from custom_components.freebox_homexa.const import DEVICE_ICONS
        for kind, icon in DEVICE_ICONS.items():
            assert resources['device_tracker']['device_' + kind]['default'] == icon
    finally:
        await coordinator.async_shutdown()


async def test_icon_metadata_preserves_custom_registry_icon_name_and_identity(hass, home_context):
    from homeassistant.helpers import entity_registry as er
    from custom_components.freebox_homexa.button import FreeboxPlayerAppButton
    from test_home_platforms import make_platform
    router, _ = home_context
    entity = FreeboxPlayerAppButton(router, {'id': 1}, 'youtube', 'YouTube', 'mdi:youtube', 'app://synthetic', True)
    registry = er.async_get(hass)
    existing = registry.async_get_or_create('button', 'freebox_homexa', entity.unique_id, suggested_object_id='existing_icon')
    registry.async_update_entity(existing.entity_id, icon='mdi:heart', name='User choice')
    platform = make_platform(hass, 'button')
    try:
        await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        state = hass.states.get(existing.entity_id)
        assert entity.entity_id == existing.entity_id
        assert registry.async_get(existing.entity_id).unique_id == entity.unique_id
        assert state.attributes['icon'] == 'mdi:heart'
        assert state.attributes['friendly_name'] == 'User choice'
        assert registry.async_get(existing.entity_id).translation_key == 'player_app_youtube'
        assert entity.icon is None
    finally:
        await platform.async_reset()
