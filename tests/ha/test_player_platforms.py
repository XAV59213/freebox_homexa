"""Real HA Player entities; network and all commands mocked."""
from datetime import timedelta
import logging
from unittest.mock import AsyncMock
import pytest
from homeassistant.helpers.entity_platform import EntityPlatform
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.freebox_homexa.router import FreeboxRouter
from custom_components.freebox_homexa.remote import FreeboxRemote
from custom_components.freebox_homexa.media_player import FreeboxPlayerMediaPlayer

@pytest.fixture
def player_context(hass):
    entry = MockConfigEntry(domain="freebox_homexa", data={"host": "freebox.test"})
    entry.add_to_hass(hass)
    router = FreeboxRouter(hass, entry, AsyncMock(), {
        "mac": "00:00:00:00:00:01", "model_info": {"pretty_name": "Test", "name": "test"},
        "firmware_version": "4.9.0"})
    return router, entry, {"id": 1, "reachable": True, "name": "Test Player", "api_version": "v6"}

@pytest.mark.parametrize("power,expected", [("running", True), ("on", True),
    ("standby", False), ("stopped", False), ("off", False), ("unexpected", None)])
async def test_remote_power(player_context, power, expected):
    router, entry, player = player_context
    router._api.player.get_player_status.return_value = {"power_state": power}
    entity = FreeboxRemote(router, player, entry)
    await entity.async_update()
    assert entity.is_on is expected
    router._api.remote.send_key.assert_not_called()

@pytest.mark.parametrize("domain", ["remote", "media_player"])
async def test_real_platform_failure_recovery_removal(hass, player_context, domain):
    router, entry, player = player_context
    get = router._api.player.get_player_status if domain == "remote" else router._api.player._access.get
    get.return_value = {"power_state": "running", "volume": 20, "mute": False}
    entity = (FreeboxRemote if domain == "remote" else FreeboxPlayerMediaPlayer)(router, player, entry)
    uid = entity.unique_id
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
        platform_name="freebox_homexa", platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
    try:
        await platform.async_add_entities([entity], update_before_add=True)
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == "on"
        get.side_effect = TimeoutError
        await entity.async_update()
        entity.async_write_ha_state()
        assert hass.states.get(entity.entity_id).state in {"unknown", "unavailable"}
        get.side_effect = None
        get.return_value = {"power_state": "standby", "volume": 0, "mute": True}
        await entity.async_update()
        entity.async_write_ha_state()
        assert hass.states.get(entity.entity_id).state == "off"
        assert entity.unique_id == uid
        router._api.remote.send_key.assert_not_called()
        router._api.player._access.put.assert_not_called()
        router._api.player._access.post.assert_not_called()
    finally:
        await platform.async_reset()
    assert not platform.entities

@pytest.mark.parametrize("value", [None, True, "65", float("nan"), float("inf")])
async def test_unknown_volume_clears_old_state(player_context, value):
    router, entry, player = player_context
    entity = FreeboxPlayerMediaPlayer(router, player, entry)
    get = router._api.player._access.get
    get.return_value = {"power_state": "running", "volume": 20, "mute": True}
    await entity.async_update()
    assert entity.volume_level == .2
    assert entity.is_volume_muted is True
    async def response(path):
        if path.endswith("status/"):
            return {"power_state": "running", "volume": value}
        raise TimeoutError
    get.side_effect = response
    await entity.async_update()
    assert entity.volume_level is None
    assert entity.is_volume_muted is None

from custom_components.freebox_homexa.button import (
    BUTTON_DESCRIPTIONS, PLAYER_REMOTE_BUTTONS, PLAYER_APP_BUTTONS,
    FreeboxButton, FreeboxPlayerRemoteButton, FreeboxPlayerAppButton,
)

@pytest.mark.parametrize("description", BUTTON_DESCRIPTIONS, ids=lambda d: d.key)
async def test_server_button_metadata(player_context, description):
    router, _, _ = player_context
    entity = FreeboxButton(router, description)
    assert entity.unique_id == f"{router.mac} {description.name}"
    assert entity.has_entity_name
    assert entity.translation_key == description.key
    assert entity.entity_category == description.entity_category
    assert entity.device_class == description.device_class
    router._api.assert_not_called()

@pytest.mark.parametrize("definition", PLAYER_REMOTE_BUTTONS, ids=lambda d: d[0])
async def test_remote_button_identity_and_defaults(player_context, definition):
    router, entry, player = player_context
    key, name, icon, enabled = definition
    entity = FreeboxPlayerRemoteButton(router, player, entry, *definition)
    renamed = FreeboxPlayerRemoteButton(router, {**player, "name": "Renamed"}, entry, key, "Renamed", icon, enabled)
    assert entity.unique_id == renamed.unique_id == f"{router.mac}_player_1_key_{key}"
    assert entity.has_entity_name
    assert entity.translation_key == f"remote_key_{key}"
    assert entity.entity_registry_enabled_default == enabled
    router._api.remote.send_key.assert_not_called()

@pytest.mark.parametrize("definition", PLAYER_APP_BUTTONS, ids=lambda d: d[0])
async def test_app_button_identity_and_defaults(player_context, definition):
    router, _, player = player_context
    key, name, icon, url, enabled = definition
    entity = FreeboxPlayerAppButton(router, player, *definition)
    renamed = FreeboxPlayerAppButton(router, {**player, "name": "Renamed"}, key, "Renamed", icon, url, enabled)
    assert entity.unique_id == renamed.unique_id == f"{router.mac}_player_1_app_{key}"
    assert entity.has_entity_name
    assert entity.translation_key == f"player_app_{key}"
    assert entity.entity_registry_enabled_default == enabled
    router._api.player._access.post.assert_not_called()


@pytest.mark.parametrize("kind", ["server", "remote", "app"])
async def test_button_real_platform_lifecycle_no_automatic_action(hass, player_context, kind):
    router, entry, player = player_context
    entity = {"server": lambda: FreeboxButton(router, BUTTON_DESCRIPTIONS[0]),
        "remote": lambda: FreeboxPlayerRemoteButton(router, player, entry, *PLAYER_REMOTE_BUTTONS[0]),
        "app": lambda: FreeboxPlayerAppButton(router, player, *PLAYER_APP_BUTTONS[0])}[kind]()
    uid = entity.unique_id
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain="button",
        platform_name="freebox_homexa", platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
    try:
        await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        assert entity.registry_entry.unique_id == uid
        assert hass.states.get(entity.entity_id) is not None
        await platform.async_reset()
        assert not platform.entities
        router._api.remote.send_key.assert_not_called()
        router._api.player._access.post.assert_not_called()
        router._api.system.reboot.assert_not_called()
    finally:
        await platform.async_reset()
