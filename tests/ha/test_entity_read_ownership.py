"""Typed read ownership, recovery and isolation without arbitrary clock delays."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from freebox_api.exceptions import NotOpenError
from custom_components.freebox_homexa.router import FreeboxRouter
from test_home_platforms import home_context


@pytest.mark.parametrize("failed", [False, True])
async def test_read_result_or_error_preserved_and_ownership_released(hass, home_context, failed):
    router, _ = home_context
    result = {"synthetic": True}
    read = AsyncMock(return_value=result, side_effect=OSError("synthetic failure") if failed else None)
    if failed:
        with pytest.raises(OSError):
            await router.async_read(read)
    else:
        assert await router.async_read(read) is result
    assert not router.read_tasks
    read.assert_awaited_once()


async def test_no_new_entity_read_started_while_closing(hass, home_context):
    router, _ = home_context
    await router.close()
    read = AsyncMock()
    with pytest.raises(NotOpenError):
        await router.async_read(read)
    read.assert_not_called()


async def test_one_router_close_does_not_cancel_another_entry_read(hass, home_context):
    first, _ = home_context
    entry = MockConfigEntry(domain="freebox_homexa", data={"host": "second.test"})
    entry.add_to_hass(hass)
    api = AsyncMock()
    second = FreeboxRouter(hass, entry, api, {"mac": "00:00:00:00:00:04",
        "model_info": {"pretty_name": "Test", "name": "test"}, "firmware_version": "4.9.0"})
    started, release = asyncio.Event(), asyncio.Event()
    async def read():
        started.set()
        await release.wait()
        return "synthetic result"
    task = asyncio.create_task(second.async_read(read))
    await started.wait()
    await first.close()
    assert not task.done()
    api.close.assert_not_called()
    release.set()
    assert await task == "synthetic result"
    assert not second.read_tasks
    await second.close()
