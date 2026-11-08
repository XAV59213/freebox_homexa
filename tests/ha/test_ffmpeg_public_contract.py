"""Delegated real HA FFmpeg methods, subprocess/HTTP stream seams mocked."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiohttp import web
from homeassistant.components.ffmpeg import DATA_FFMPEG
from custom_components.freebox_homexa.camera import FreeboxCamera
from test_home_platforms import home_context


async def test_public_snapshot_and_stream_source_without_subprocess(hass, home_context):
    router, node = home_context
    camera = FreeboxCamera(hass, router, {**node, "category": "camera"})
    camera.hass = hass
    with patch("homeassistant.components.ffmpeg.camera.async_get_image", new=AsyncMock(return_value=b"synthetic jpeg")) as image:
        assert await camera.async_camera_image(320, 240) == b"synthetic jpeg"
        assert image.await_args.args[0] is hass
        assert image.await_args.args[1] == camera._input
        assert await camera.stream_source() == camera._input.split(" ")[-1]
    router._api.home.set_home_endpoint_value.assert_not_called()


@pytest.mark.parametrize("stage", ["success", "proxy_error", "proxy_cancel", "reader_error", "open_error"])
async def test_public_mjpeg_closes_after_open_but_not_on_open_failure(hass, home_context, stage):
    router, node = home_context
    hass.data[DATA_FFMPEG] = SimpleNamespace(binary="synthetic-ffmpeg", ffmpeg_stream_content_type="multipart/synthetic")
    camera = FreeboxCamera(hass, router, {**node, "category": "camera"})
    camera.hass = hass
    request = MagicMock(spec=web.Request)
    reader = object()
    stream = MagicMock(open_camera=AsyncMock(), get_reader=AsyncMock(return_value=reader), close=AsyncMock())
    response = web.StreamResponse()
    proxy = AsyncMock(return_value=response)
    started = asyncio.Event()
    failure = RuntimeError("synthetic stream failure")
    if stage == "open_error":
        stream.open_camera.side_effect = failure
    elif stage == "reader_error":
        stream.get_reader.side_effect = failure
    elif stage == "proxy_error":
        proxy.side_effect = failure
    elif stage == "proxy_cancel":
        async def blocked(*args):
            started.set()
            await asyncio.Future()
        proxy.side_effect = blocked
    with patch("homeassistant.components.ffmpeg.camera.CameraMjpeg", return_value=stream), \
         patch("homeassistant.components.ffmpeg.camera.async_aiohttp_proxy_stream", new=proxy):
        task = hass.async_create_background_task(camera.handle_async_mjpeg_stream(request), "synthetic stream")
        if stage == "proxy_cancel":
            await started.wait()
            task.cancel()
        if stage == "success":
            assert await task is response
        else:
            with pytest.raises(asyncio.CancelledError if stage == "proxy_cancel" else RuntimeError):
                await task
    stream.open_camera.assert_awaited_once()
    if stage == "open_error":
        # Public upstream implementation opens before its try/finally. This test
        # is characterization, NOT proof of cleanup after partial open failure.
        stream.close.assert_not_called()
    else:
        stream.close.assert_awaited_once()
    router._api.home.set_home_endpoint_value.assert_not_called()
