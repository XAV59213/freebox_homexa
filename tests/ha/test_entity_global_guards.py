"""Global constructor availability/endpoint boundaries, independent of network I/O."""
import pytest
from test_entity_inventory import build_inventory
from test_home_platforms import home_context
from custom_components.freebox_homexa.entity import FreeboxHomeEntity


@pytest.mark.parametrize("closing", [False, True])
async def test_all_freebox_backed_families_hide_untrusted_values(hass, home_context, closing):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    objects, coordinator = build_inventory(hass, router, node, entry)
    try:
        for _, entity in objects:
            entity.hass = hass
        before = {variant: entity.available for variant, entity in objects}
        router.closing = closing
        router.reachable = closing  # offline OR closing, separately
        for variant, entity in objects:
            if variant in ("tnt", "inversion"):
                # XMLTV is independent of Freebox OS; inversion edits a local file.
                assert entity.available == before[variant], variant
            else:
                assert entity.available is False, variant
        router.closing = False
        router.reachable = True
        assert {variant: entity.available for variant, entity in objects} == before
        router._api.home.set_home_endpoint_value.assert_not_called()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("endpoint_id,expected", [(9, 9), (None, None), (True, None), ("9", None), (9.5, None)])
async def test_command_id_accepts_only_real_integer_ids(hass, home_context, endpoint_id, expected):
    router, node = home_context
    entity = FreeboxHomeEntity(hass, router, node)
    assert entity.get_command_id([{"name": "trigger", "ep_type": "signal", "id": endpoint_id}], "signal", "trigger") == expected
    assert entity.get_command_id([], "signal", "missing") is None
    router._api.home.set_home_endpoint_value.assert_not_called()
