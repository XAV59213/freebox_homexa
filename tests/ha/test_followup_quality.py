"""Migrations and proven-absent device removal. No real Freebox."""
from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.helpers import entity_registry as er

from custom_components.freebox_homexa.binary_sensor import FreeboxRaidDegradedSensor, migrate_raid_unique_ids
from custom_components.freebox_homexa.const import DOMAIN
from test_home_platforms import home_context


async def test_raid_rename_keeps_the_entity_id(hass, home_context):
    router, _ = home_context
    registry = er.async_get(hass)
    old_unique_id = f"{router.mac}_raid_degraded_Ancien nom_4"
    original = registry.async_get_or_create(
        "binary_sensor", DOMAIN, old_unique_id, suggested_object_id="mon_raid",
        config_entry=hass.config_entries.async_get_entry(router.entry_id),
    )
    registry.async_update_entity(original.entity_id, name="Mon RAID")
    migrate_raid_unique_ids(hass, router.entry_id, router.mac)
    current = registry.async_get(original.entity_id)
    assert current is not None
    assert current.entity_id == original.entity_id
    assert current.name == "Mon RAID"
    assert current.unique_id == f"{router.mac}_raid_degraded_4"
    sensor = FreeboxRaidDegradedSensor(
        router, {"id": 4, "name": "Nouveau libellé", "degraded": False},
        BinarySensorEntityDescription(key="raid_degraded"),
    )
    assert sensor.unique_id == current.unique_id
