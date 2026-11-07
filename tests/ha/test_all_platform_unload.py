"""Simultaneous owned HA entity platforms, actual hooks/listeners/registry.

The integration's forward/unload platform dispatcher is substituted with this
explicit set of real platforms; device discovery/network remain out of scope.
"""
import asyncio
from unittest.mock import patch
from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform
from custom_components.freebox_homexa import async_unload_entry
from custom_components.freebox_homexa.const import DOMAIN, PLATFORMS
from custom_components.freebox_homexa.sensor import FreeboxSensor
from custom_components.freebox_homexa.binary_sensor import FreeboxWifiApSensor
from custom_components.freebox_homexa.device_tracker import FreeboxDevice
from custom_components.freebox_homexa.calendar import FreeboxTvGuideCalendar
from custom_components.freebox_homexa.cover import FreeboxShutter
from custom_components.freebox_homexa.camera import FreeboxCamera
from custom_components.freebox_homexa.tnt_coordinator import ProgrammeTntFrCoordinator
from custom_components.freebox_homexa.tnt_sensor import HomexaTntSensor
from custom_components.freebox_homexa.tnt_setup import TNT_COORDINATORS_KEY
from test_action_errors import build_entity
from test_home_platforms import home_context


async def test_eleven_owned_platforms_and_tnt_unload_together(hass, home_context):
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entry.runtime_data = router
    router.wifi_aps = {"gateway": {"kind": "gateway", "name": "Test", "online": True, "state": "active"}}
    client = {"l2ident": {"id": "00:00:00:00:10:01"}, "primary_name": "Test client", "active": True, "host_type": "computer"}
    router.devices[client["l2ident"]["id"]] = client
    tracker = FreeboxDevice(router, client, False)
    er.async_get(hass).async_get_or_create("device_tracker", DOMAIN, tracker.unique_id,
        config_entry=entry, disabled_by=None)
    entities = {
        "alarm_control_panel": build_entity(hass, router, node, entry, "alarm")[0],
        "binary_sensor": FreeboxWifiApSensor(router, "gateway", router.wifi_aps["gateway"]),
        "button": build_entity(hass, router, node, entry, "server_button")[0],
        "calendar": FreeboxTvGuideCalendar(router), "camera": FreeboxCamera(hass, router, node),
        "cover": FreeboxShutter(hass, router, node), "device_tracker": tracker,
        "media_player": build_entity(hass, router, node, entry, "media")[0],
        "remote": build_entity(hass, router, node, entry, "remote")[0],
        "sensor": FreeboxSensor(router, SensorEntityDescription(key="uptime", name="Test uptime")),
        "switch": build_entity(hass, router, node, entry, "wifi")[0],
    }
    assert set(entities) == set(PLATFORMS)
    coordinator = ProgrammeTntFrCoordinator(hass, ["TF1.fr"], config_entry=entry)
    coordinator.async_set_updated_data({"TF1.fr": {"current": {"title": "Synthetic programme"}}})
    tnt = HomexaTntSensor(coordinator, "TF1.fr", "synthetic")
    hass.data.setdefault(DOMAIN, {})[TNT_COORDINATORS_KEY] = {entry.entry_id: coordinator}
    platforms = []
    try:
        for domain, entity in entities.items():
            platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
                platform_name=DOMAIN, platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
            platform.config_entry = entry
            platforms.append(platform)
            await platform.async_add_entities([entity] + ([tnt] if domain == "sensor" else []))
        await hass.async_block_till_done()
        assert all(platform.entities for platform in platforms)
        assert all(entity.registry_entry.config_entry_id == entry.entry_id for entity in entities.values())
        alarm = entities["alarm_control_panel"]
        alarm._start_arming_watcher()
        assert alarm._unsub_watcher is not None
        assert coordinator._listeners
        async def unload_platforms(owner, domains):
            assert owner is entry
            assert set(domains) == set(PLATFORMS)
            await asyncio.gather(*(platform.async_reset() for platform in platforms))
            return True
        with patch.object(hass.config_entries, "async_unload_platforms", side_effect=unload_platforms):
            assert await async_unload_entry(hass, entry)
        await entry._async_process_on_unload(hass)
        assert all(not platform.entities for platform in platforms)
        assert alarm._unsub_watcher is None
        assert not coordinator._listeners
        assert entry.entry_id not in hass.data[DOMAIN][TNT_COORDINATORS_KEY]
        for signal in (router.signal_device_update, router.signal_sensor_update, router.signal_home_device_update):
            assert not hass.data.get("dispatcher", {}).get(signal)
        router._api.close.assert_awaited_once()
        router._api.remote.send_key.assert_not_called()
        router._api.home.set_home_endpoint_value.assert_not_called()
    finally:
        await asyncio.gather(*(platform.async_reset() for platform in platforms))
        await entry._async_process_on_unload(hass)
