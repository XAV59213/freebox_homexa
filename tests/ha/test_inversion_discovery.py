"""Registry order/rename/removal must not change inversion semantics or IDs."""
import pytest
from homeassistant.helpers.entity_registry import async_get
from custom_components.freebox_homexa.cover import FreeboxShutter
from test_home_platforms import home_context


@pytest.mark.parametrize("before", [False, True])
async def test_inversion_lookup_is_independent_of_discovery_order(hass, home_context, before):
    router, node = home_context
    registry = async_get(hass)
    uid = f"{router.mac}-node_{node['id']}"
    def register():
        return registry.async_get_or_create("switch", "freebox_homexa", f"{uid}_InvertSwitch", suggested_object_id="synthetic_inversion")
    if before:
        inversion = register()
        hass.states.async_set(inversion.entity_id, "on")
    entity = FreeboxShutter(hass, router, node)
    assert entity.unique_id == uid
    if not before:
        assert entity.current_cover_position == 25
        inversion = register()
        hass.states.async_set(inversion.entity_id, "on")
    assert entity.current_cover_position == 75
    hass.states.async_set(inversion.entity_id, "off")
    assert entity.current_cover_position == 25
    hass.states.async_set(inversion.entity_id, "unavailable")
    assert entity.current_cover_position is None
    renamed = registry.async_update_entity(inversion.entity_id, new_entity_id="switch.renamed_synthetic")
    hass.states.async_set(renamed.entity_id, "on")
    assert entity.current_cover_position == 75
    registry.async_remove(renamed.entity_id)
    assert entity.current_cover_position == 25
    assert entity.unique_id == uid
    router.home.set_home_endpoint_value.assert_not_called()
