"""User-confirmed stale-device removal, and proof the condition/trigger exemptions apply.

No device is deleted by the callback. Integer identifiers and chosen names stay.
No live device, no identity migration, no repeater/ change.
"""
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_homexa import async_remove_config_entry_device
from custom_components.freebox_homexa.const import DOMAIN, PLATFORMS
from custom_components.freebox_homexa.device_groups import config_entry_device_removable
from test_home_platforms import home_context

PACKAGE = Path(__file__).resolve().parents[2] / "custom_components" / "freebox_homexa"


def test_condition_and_trigger_rules_do_not_apply():
    """The official exception is absence of those platforms, not missing documentation."""
    names = {path.name for path in PACKAGE.iterdir()}
    assert "conditions.yaml" not in names
    assert "triggers.yaml" not in names
    assert {platform.value for platform in PLATFORMS}.isdisjoint({"event", "device_automation"})
    source = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py"))
    assert "async_get_conditions" not in source
    assert "async_get_triggers" not in source
    assert "conditions.yaml" not in source
    assert "triggers.yaml" not in source


async def test_user_may_delete_only_a_device_proven_absent(hass, home_context):
    router, _node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    devices = dr.async_get(hass)

    info = router.device_info
    assert info["identifiers"] == {(DOMAIN, router.mac)}
    assert "serial_number" not in info
    router._attrs["serial"] = "  FBX-SYNTH  "
    assert router.device_info["serial_number"] == "FBX-SYNTH"
    assert router.device_info["identifiers"] == {(DOMAIN, router.mac)}
    router._attrs["serial"] = 7
    assert "serial_number" not in router.device_info

    disk = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, 7)},
        name="Disque 7",
    )
    devices.async_update_device(disk.id, name_by_user="Mon disque")
    home = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, 42)},
        name="Volet",
    )
    devices.async_update_device(home.id, name_by_user="Mon volet")
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(disk.id)) is False
    assert (DOMAIN, 7) in devices.async_get(disk.id).identifiers
    assert devices.async_get(disk.id).name_by_user == "Mon disque"

    router._api.storage.get_disks = AsyncMock(return_value=[
        {"id": 7, "model": "synth", "firmware": "1", "partitions": []},
    ])
    await router._update_disks_sensors()
    assert router.disks_snapshot_known is True
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(disk.id)) is False
    router.home_snapshot_known = True
    router.home_devices = {42: {"id": 42}}
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(home.id)) is False
    gone = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, 99)},
        name="Ancien",
    )
    devices.async_update_device(gone.id, name_by_user="A garder tant que je ne confirme pas")
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(gone.id)) is True
    assert devices.async_get(gone.id).name_by_user == "A garder tant que je ne confirme pas"
    assert (DOMAIN, 99) in devices.async_get(gone.id).identifiers

    router._api.storage.get_disks = AsyncMock(side_effect=RuntimeError("synthetic"))
    await router._update_disks_sensors()
    assert router.disks_snapshot_known is False
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(gone.id)) is False

    box = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, router.mac)},
        connections={(dr.CONNECTION_NETWORK_MAC, router.mac)},
        name="Server",
    )
    group = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{router.mac}_group_home")},
        name="Maison",
    )
    guide = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "programme_tnt_fr")},
        name="TNT",
    )
    player = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "player_3")},
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:03")},
        name="Player",
    )
    devices.async_update_device(player.id, name_by_user="Mon player")
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(box.id)) is False
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(group.id)) is False
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(guide.id)) is False
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(player.id)) is False
    router.players_initialized = True
    router.players = [{"id": 3, "mac": "aa:bb:cc:dd:ee:03"}, "ignore"]
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(player.id)) is False
    assert devices.async_get(player.id).name_by_user == "Mon player"
    other = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "player_9")},
        name="Ancien player",
    )
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(other.id)) is True
    assert devices.async_get(other.id) is not None

    client = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:40")},
        name="Telephone",
    )
    devices.async_update_device(client.id, name_by_user="Mon telephone")
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(client.id)) is False
    router.lan_snapshot_known = True
    router.devices = {"aa:bb:cc:dd:ee:40": {"l2ident": {"id": "aa:bb:cc:dd:ee:40"}}}
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(client.id)) is False
    router.devices = {}
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(client.id)) is True
    assert devices.async_get(client.id).name_by_user == "Mon telephone"

    repeater = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "repeater_20:66:CF:4B:49:69")},
        name="Cave",
    )
    router.lan_snapshot_known = False
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(repeater.id)) is False
    router.lan_snapshot_known = True
    router.repeaters = {"20:66:CF:4B:49:69": {"macs": ["20:66:CF:4B:49:69"]}}
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(repeater.id)) is False
    router.repeaters = {}
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(repeater.id)) is True
    assert devices.async_get(repeater.id) is not None

    foreign = MockConfigEntry(domain="shelly", data={})
    foreign.add_to_hass(hass)
    shelly = devices.async_get_or_create(
        config_entry_id=foreign.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:77")},
        name="Shelly",
    )
    devices.async_update_device(shelly.id, name_by_user="Ma prise")
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(shelly.id)) is False
    assert devices.async_get(shelly.id).name_by_user == "Ma prise"

    router.closing = False
    router.home_devices = {"42": {"id": "42"}}
    router.home_snapshot_known = True
    router.disks_snapshot_known = True
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(home.id)) is False
    zigbee = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("zigbee", "aa")},
        name="Sans MAC",
    )
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(zigbee.id)) is False
    mystery = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "pas-un-appareil")},
        name="Inclassable",
    )
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(mystery.id)) is False
    router.repeater_aliases = {"20:66:CF:11:22:33": "2066CF112233"}
    router.repeaters = {"autre": "pas-un-dict", "cave": {"macs": ["20:66:CF:4B:49:69"]}}
    router.lan_snapshot_known = True
    assert await async_remove_config_entry_device(hass, entry, devices.async_get(repeater.id)) is False
    class _EmptyMac:
        identifiers = ()
        connections = ((dr.CONNECTION_NETWORK_MAC, ""),)

    assert config_entry_device_removable(router, _EmptyMac()) is False
    router.home_devices = None
    assert config_entry_device_removable(router, devices.async_get(gone.id)) is True
    assert devices.async_get(gone.id) is not None
    router.home_devices = {42: {"id": 42}}

    router.closing = True
    assert config_entry_device_removable(router, devices.async_get(gone.id)) is False
    assert config_entry_device_removable(None, devices.async_get(gone.id)) is False
    assert config_entry_device_removable(router, None) is False

    with patch(
        "custom_components.freebox_homexa.router.get_hosts_list_if_supported",
        new=AsyncMock(return_value=(True, [])),
    ):
        await router.update_device_trackers()
    assert router.lan_snapshot_known is True
    with patch(
        "custom_components.freebox_homexa.router.get_hosts_list_if_supported",
        new=AsyncMock(side_effect=RuntimeError("synthetic lan")),
    ):
        try:
            await router.update_device_trackers()
        except RuntimeError:
            pass
    assert router.lan_snapshot_known is False
