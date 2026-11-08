"""Calendar parsing and HA lifecycle, with synthetic SDK responses only."""
from datetime import datetime, timedelta, UTC
import logging
from unittest.mock import AsyncMock
import pytest
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.freebox_homexa.calendar import FreeboxTvGuideCalendar, _as_datetime, _program_to_event
from custom_components.freebox_homexa.router import FreeboxRouter

@pytest.mark.parametrize("value", [None, "invalid", {}, float("inf"), 10**100])
def test_invalid_dates_are_ignored(value):
    assert _as_datetime(value) is None

@pytest.mark.parametrize("milliseconds", [False, True])
def test_timestamp_units(milliseconds):
    stamp = 1800000000
    assert _as_datetime(stamp * (1000 if milliseconds else 1)) == datetime.fromtimestamp(stamp, UTC)

@pytest.mark.parametrize("program", [{}, {"title": "Test"}, {"title": "Test", "start": "invalid"}])
def test_incomplete_event_is_ignored(program):
    assert _program_to_event(program, "Test channel") is None

@pytest.mark.parametrize("duration", [None, "invalid", -1, 1200])
def test_event_duration_fallback(duration):
    start = datetime(2026, 11, 7, 12, tzinfo=UTC)
    event = _program_to_event({"title": "Test", "start": start, "duration": duration}, "Test channel")
    assert event.summary == "Test channel: Test"
    assert event.end - start == timedelta(seconds=1200 if duration == 1200 else 1800)

async def test_real_calendar_platform_load_update_and_remove(hass):
    entry = MockConfigEntry(domain="freebox_homexa", data={"host": "freebox.test"})
    entry.add_to_hass(hass)
    api = AsyncMock()
    router = FreeboxRouter(hass, entry, api, {"mac": "00:00:00:00:00:02", "model_info": {"name": "Test", "pretty_name": "Test"}, "firmware_version": "4.9.0"})
    now = dt_util.now()
    api.tv.get_tv_channels.return_value = {"test": {"name": "Test channel"}}
    api.tv.get_tv_programs_by_date.return_value = [None, {},
        {"id": 1, "uuid": "test", "title": "Test programme", "start": now - timedelta(minutes=5), "duration": 3600}]
    entity = FreeboxTvGuideCalendar(router)
    uid = entity.unique_id
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain="calendar",
        platform_name="freebox_homexa", platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
    try:
        await platform.async_add_entities([entity], update_before_add=True)
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == "on"
        assert entity.event.summary == "Test channel: Test programme"
        assert entity.unique_id == uid
        api.tv.get_tv_programs_by_date.side_effect = TimeoutError
        await entity.async_update()
        assert entity.event is None
        api.tv.get_tv_programs_by_date.side_effect = None
        await entity.async_update()
        assert entity.event is not None
        api.tv.get_tv_programs_by_date.assert_awaited()
    finally:
        await platform.async_reset()
    assert not platform.entities
