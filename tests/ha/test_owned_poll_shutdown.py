"""Router shutdown is serialized and retries only after an explicit later close."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from test_home_platforms import home_context


async def test_concurrent_close_calls_public_sdk_once(hass, home_context):
    router, _ = home_context
    started, release = asyncio.Event(), asyncio.Event()
    async def delayed_close():
        started.set()
        await release.wait()
    router._api.close.side_effect = delayed_close
    first = asyncio.create_task(router.close())
    await started.wait()
    second = asyncio.create_task(router.close())
    release.set()
    await asyncio.gather(first, second)
    await router.close()
    router._api.close.assert_awaited_once()
    assert router.closing


async def test_failed_public_close_is_not_reported_as_closed_and_is_retryable(hass, home_context):
    router, _ = home_context
    router._api.close.side_effect = [OSError("synthetic SDK close failure"), None]
    with pytest.raises(OSError):
        await router.close()
    assert router.closing
    assert not router._closed
    await router.close()
    assert router._closed
    assert router._api.close.await_count == 2
    rejected = AsyncMock()
    await router.async_poll(rejected)
    rejected.assert_not_called()


async def test_not_open_keeps_historical_suppression_without_closure_ack(hass, home_context):
    from freebox_api.exceptions import NotOpenError
    router, _ = home_context
    router._api.close.side_effect = NotOpenError("synthetic not-open")
    await router.close()
    assert not router._closed
    await router.close()
    assert router._api.close.await_count == 2
