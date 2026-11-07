"""Real HA registry data plus explicit legacy API/owner views, never real devices.

The facades exercise old provider shapes; they do NOT claim an older HA runtime
was installed. All backing entries, ownership and removal use the actual registry.
"""
from types import SimpleNamespace

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_homexa import registry_compat as compat
from custom_components.freebox_homexa.const import DOMAIN
from test_home_platforms import home_context


class LegacyEntryView:
    def __init__(self, native):
        self.native = native

    @property
    def config_entries(self):
        return {self.native.config_entry_id}

    def __getattr__(self, name):
        if name == "config_entry_id":
            raise AttributeError(name)
        return getattr(self.native, name)


class LegacyRegistryView:
    def __init__(self, native):
        self.native = native

    def async_get_device(self, **kwargs):
        device = self.native.async_get_device(**kwargs)
        return LegacyEntryView(device) if device is not None else None


async def test_native_and_legacy_owner_lookup_preserves_scope_names_connections(hass):
    registry = dr.async_get(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN, data={})
    other.add_to_hass(hass)
    identifier = (DOMAIN, "synthetic-owner")
    connection = (dr.CONNECTION_NETWORK_MAC, "02:00:00:00:00:01")
    device = registry.async_get_or_create(config_entry_id=entry.entry_id,
        identifiers={identifier}, connections={connection}, name="Source name")
    device = registry.async_update_device(device.id, name_by_user="My custom device")
    before = registry.async_get(device.id)
    for backend in (registry, LegacyRegistryView(registry)):
        found = compat.get_device_by_identifier(backend, identifier, entry.entry_id)
        assert compat.registry_device_id(found) == device.id
        assert compat.device_entry_id(found) == entry.entry_id
        assert compat.device_owned_by(found, entry.entry_id)
        assert compat.device_entries(found) == {entry.entry_id}
        assert compat.get_device_by_identifier(backend, identifier, other.entry_id) is None
        assert compat.get_device_by_connection(backend, connection, entry.entry_id).id == device.id
        assert compat.get_device_by_connection(backend, connection, other.entry_id) is None
        assert compat.foreign_device_with_connection(backend, connection, other.entry_id).id == device.id
        assert compat.foreign_device_with_connection(backend, connection, entry.entry_id) is None
        assert registry.async_get(device.id) == before
    compat.remove_device(registry, device.id)
    assert registry.async_get(device.id) is None


async def test_unknown_lookup_without_child_api_is_not_a_foreign_or_new_identity(hass):
    registry = dr.async_get(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    backend = SimpleNamespace(async_get_device_by_identifier=registry.async_get_device_by_identifier)
    assert compat.get_device_by_identifier(backend, (DOMAIN, "missing"), entry.entry_id) is None
    assert compat.get_device_by_identifier(LegacyRegistryView(registry), (DOMAIN, "missing"), entry.entry_id) is None
    assert compat.get_device_by_connection(LegacyRegistryView(registry),
        (dr.CONNECTION_NETWORK_MAC, "02:00:00:00:00:02"), entry.entry_id) is None


def test_opaque_or_malformed_registry_id_is_never_stringified():
    assert compat.registry_device_id(object()) is None
    assert compat.registry_device_id(SimpleNamespace(id=23)) is None
    assert compat.device_entry_id(object()) is None
    assert compat.device_entries(object()) == set()
    assert compat.device_entry_id(SimpleNamespace(config_entry_id=23)) is None
    assert compat.device_entries(SimpleNamespace(config_entry_id=23)) == set()
    assert compat.device_entry_id(SimpleNamespace(config_entries=[23, "legacy-entry"])) == "legacy-entry"
    assert compat.device_entries(SimpleNamespace(config_entries=[23, "legacy-entry"])) == {"legacy-entry"}
    assert not compat.device_owned_by(SimpleNamespace(config_entry_id=23), "23")
    assert compat.device_entry_id(SimpleNamespace(config_entries=[])) is None
    assert compat.shared_with_other_entries(SimpleNamespace(config_entry_id=23), "23")
    assert compat.shared_with_other_entries(SimpleNamespace(config_entries=[23, "own"]), "own")
    assert compat.shared_with_other_entries(SimpleNamespace(config_entries=23), "own")
    assert not compat.shared_with_other_entries(None, "own")

    class Orphan:
        config_entry_id = None
        @property
        def config_entries(self):
            raise AssertionError("must not read deprecated ownership for modern orphan")
    assert compat.device_entry_id(Orphan()) is None
    assert compat.device_entries(Orphan()) == set()


async def test_router_parent_ids_are_native_registry_ids_not_converted_identifiers(hass, home_context):
    router, _ = home_context
    registry = dr.async_get(hass)
    physical = "02:00:00:00:00:03"
    device = registry.async_get_or_create(config_entry_id=router.entry_id,
        identifiers={(DOMAIN, physical)}, name="Synthetic parent")
    device = registry.async_update_device(device.id, name_by_user="Keep my name")
    before = registry.async_get(device.id)
    assert router.via_device_id_for(physical) == device.id
    assert registry.async_get(device.id) == before


async def test_real_sdk_bad_lan_record_retains_cache_and_only_real_read_recovers(hass, home_context):
    from test_source_permission_repairs import sdk_context
    import pytest
    router, _ = home_context
    mode, payloads, transport = sdk_context(router, "lan/browser/pub")
    mode["error"] = None
    before = dict(router.devices)
    payloads["lan/browser/pub"] = ["not a host record"]
    with pytest.raises(ValueError, match="Invalid LAN host record"):
        await router.update_device_trackers()
    assert not router.lan_available
    assert router.devices == before
    payloads["lan/browser/pub"] = []
    await router.update_device_trackers()
    assert router.lan_available
    transport.post.assert_not_called()
    transport.put.assert_not_called()
    transport.delete.assert_not_called()


async def test_legacy_provider_bad_id_cannot_reparent_or_poison_native_lan_cache(hass, home_context):
    from unittest.mock import Mock, patch
    router, _ = home_context
    mac = "02:00:00:00:00:04"
    router.create_lan_devices = True
    router.devices[mac] = {"l2ident": {"id": mac}, "primary_name": "Synthetic client"}
    bad = SimpleNamespace(id=23, config_entry_id=router.entry_id)
    registry = dr.async_get(hass)
    before = list(dr.async_entries_for_config_entry(registry, router.entry_id))
    with patch.object(router, "_lan_client_device", return_value=bad), \
         patch.object(router, "lan_client_parent", new=Mock()) as parent, \
         patch.object(registry, "async_update_device", wraps=registry.async_update_device) as update:
        assert router.ensure_lan_client_device(mac) is None
        parent.assert_not_called()
        update.assert_not_called()
    assert mac.replace(":", "").lower() not in router.lan_device_ids
    assert list(dr.async_entries_for_config_entry(registry, router.entry_id)) == before
