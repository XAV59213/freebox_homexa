"""Calendrier Guide TV Freebox (EPG), enrichi si Programme TNT FR est présent."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .router import FreeboxRouter
from .tv_guide import summarize_guide

_LOGGER = logging.getLogger(__name__)
MAX_EVENTS = 80


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    async_add_entities([FreeboxTvGuideCalendar(router)], True)


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    try:
        ts = int(value)
        if ts > 10_000_000_000:
            ts = ts / 1000
        return dt_util.utc_from_timestamp(ts)
    except (TypeError, ValueError, OSError):
        return None


def _program_to_event(program: dict[str, Any], channel_name: str) -> CalendarEvent | None:
    title = program.get("title") or program.get("name") or program.get("subname")
    if not title:
        return None
    start = _as_datetime(program.get("date") or program.get("start") or program.get("start_time"))
    if start is None:
        return None
    duration = program.get("duration") or program.get("duration_sec") or 0
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 0
    end = _as_datetime(program.get("end") or program.get("end_time"))
    if end is None:
        end = start + timedelta(seconds=duration or 1800)
    if end <= start:
        end = start + timedelta(minutes=30)
    summary = f"{channel_name}: {title}" if channel_name else str(title)
    desc_parts = [
        part
        for part in (
            program.get("subname"),
            program.get("desc") or program.get("description"),
            program.get("category_name") or program.get("category"),
        )
        if part
    ]
    return CalendarEvent(
        start=start,
        end=end,
        summary=summary,
        description="\n".join(desc_parts) or None,
        uid=str(program.get("id") or f"{channel_name}-{int(start.timestamp())}"),
    )


class FreeboxTvGuideCalendar(CalendarEntity):
    """Programmes TV en cours et à venir."""

    _attr_has_entity_name = True
    _attr_name = "Guide TV"
    _attr_icon = "mdi:television-guide"

    def __init__(self, router: FreeboxRouter) -> None:
        self._router = router
        self._attr_unique_id = f"{router.mac}_tv_guide"
        self._attr_device_info = router.device_info
        self._event: CalendarEvent | None = None
        self._channels: dict[str, dict[str, Any]] = {}
        self._summary: dict[str, Any] = {}
        self._snippets: list[dict[str, Any]] = []

    @property
    def event(self) -> CalendarEvent | None:
        return self._event

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "guide_source": self._summary.get("source", "freebox"),
            "tnt_available": self._summary.get("tnt_available", False),
            "current": self._summary.get("current", []),
            "prime_time": self._summary.get("prime_time", []),
            "second_part": self._summary.get("second_part", []),
        }

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        self._snippets = []
        try:
            api_tv = self._router._api.tv
            channels = await api_tv.get_tv_channels() or {}
            if isinstance(channels, dict):
                self._channels = channels
            now_ts = int(dt_util.now().timestamp())
            programs = await api_tv.get_tv_programs_by_date(now_ts) or {}
            iterable = programs.values() if isinstance(programs, dict) else programs or []
            for program in iterable:
                if not isinstance(program, dict):
                    continue
                uuid = str(program.get("uuid") or program.get("channel_uuid") or "")
                channel = self._channels.get(uuid) or {}
                channel_name = (
                    channel.get("name")
                    or program.get("channel_name")
                    or program.get("subname")
                    or uuid
                )
                event = _program_to_event(program, str(channel_name))
                if event is None:
                    continue
                self._snippets.append(
                    {
                        "channel": channel_name,
                        "title": program.get("title") or program.get("name"),
                        "category": program.get("category_name") or program.get("category"),
                        "start": event.start,
                        "stop": event.end,
                        "_start": event.start,
                        "_end": event.end,
                    }
                )
                if event.end < start_date or event.start > end_date:
                    continue
                events.append(event)
                if len(events) >= MAX_EVENTS:
                    break
        except Exception as err:
            _LOGGER.warning("Impossible de lire le guide TV Freebox : %s", err)

        self._summary = summarize_guide(hass, self._snippets)
        events.sort(key=lambda item: item.start)
        now = dt_util.now()
        self._event = next((item for item in events if item.start <= now <= item.end), events[0] if events else None)
        return events

    async def async_update(self) -> None:
        now = dt_util.now()
        events = await self.async_get_events(self.hass, now - timedelta(minutes=10), now + timedelta(hours=3))
        self._event = next((item for item in events if item.start <= now <= item.end), events[0] if events else None)
