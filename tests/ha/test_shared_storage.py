"""Actual HA Store failures are observable before destructive unload/reload steps."""
from unittest.mock import AsyncMock, Mock, patch
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.storage import Store
from homeassistant.util.file import WriteError
from custom_components.freebox_homexa import async_unload_entry
from custom_components.freebox_homexa.services import _save_config, async_setup_services
from test_lifecycle import entry_for


@pytest.mark.parametrize("action", ["save", "unload", "reboot"])
async def test_shared_store_swallowed_write_failure_then_recovery(hass, action):
    store = Store(hass, 1, "homexa_synthetic_shared_config")
    await store.async_save({"previous": True})
    wanted = {"previous": True, "new": {"synthetic": True}}
    hass.data["freebox_homexa"] = {"store": store, "config": wanted}
    entry = entry_for(hass)
    router = Mock(close=AsyncMock(), reboot=AsyncMock(), closing=False)
    entry.runtime_data = router
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    async_setup_services(hass)
    async def invoke():
        if action == "save":
            await _save_config(hass)
        elif action == "unload":
            await async_unload_entry(hass, entry)
        else:
            await hass.services.async_call("freebox_homexa", "reboot", {}, blocking=True)
    with patch.object(hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)) as unload:
        with patch.object(store, "_async_write_data", new=AsyncMock(side_effect=WriteError("synthetic storage failure"))):
            with pytest.raises(HomeAssistantError) as caught:
                await invoke()
        assert caught.value.translation_key == "storage_write_failed"
        assert await store.async_load() == {"previous": True}
        assert router.closing is False
        router.close.assert_not_awaited()
        unload.assert_not_awaited()
        # Storage is checked before either teardown or any reboot command.
        router.reboot.assert_not_awaited()
        await invoke()
        assert await store.async_load() == wanted
        assert router.close.await_count == int(action == "unload")
    entry._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)
