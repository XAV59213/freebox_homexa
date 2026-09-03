"""XMLTV coordinator adapted from cyclope205/programme-tnt-fr (MIT)."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .tnt_const import (
    DAY_RESET,
    FETCH_MIN_INTERVAL_MINUTES,
    LATE_NIGHT_START,
    PRIME_TIME_START,
    TNT_CHANNELS,
    UPDATE_INTERVAL_MINUTES,
    XMLTV_URL,
)

_LOGGER = logging.getLogger(__name__)


def _parse_xmltv_datetime(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y%m%d%H%M%S %z")
    except ValueError:
        return None


class Programme:
    def __init__(self, start, stop, title, subtitle, desc, category, icon, rating) -> None:
        self.start = start
        self.stop = stop
        self.title = title
        self.subtitle = subtitle
        self.desc = desc
        self.category = category
        self.icon = icon
        self.rating = rating

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "description": self.desc,
            "category": self.category,
            "icon": self.icon,
            "poster": self.icon,
            "rating": self.rating,
            "start": self.start.isoformat() if self.start else None,
            "stop": self.stop.isoformat() if self.stop else None,
        }


class ProgrammeTntFrCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, channels: list[str], tmdb_api_key: str | None = None) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="programme_tnt_fr",
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._channels = channels
        self._session = async_get_clientsession(hass)
        self._programmes_by_channel: dict[str, list[Programme]] = {}
        self._channels_meta: dict[str, dict] = {}
        self._last_fetch = None

    async def _async_update_data(self) -> dict:
        now = dt_util.now()
        need_fetch = self._last_fetch is None or (now - self._last_fetch) >= timedelta(
            minutes=FETCH_MIN_INTERVAL_MINUTES
        )
        if need_fetch:
            try:
                await self._fetch_and_parse()
                self._last_fetch = now
            except Exception as err:
                if not self._programmes_by_channel:
                    raise UpdateFailed(f"Impossible de recuperer le flux XMLTV: {err}") from err
                _LOGGER.warning("XMLTV en cache : %s", err)

        result: dict[str, dict] = {}
        for channel_id in self._channels:
            current, prime_time, second_part = self._pick_slots(channel_id, now)
            meta = self._channels_meta.get(channel_id, {})
            result[channel_id] = {
                "channel_id": channel_id,
                "channel_name": meta.get("name", TNT_CHANNELS.get(channel_id, channel_id)),
                "channel_icon": meta.get("icon"),
                "current": current.as_dict() if current else None,
                "prime_time": prime_time.as_dict() if prime_time else None,
                "second_part": second_part.as_dict() if second_part else None,
            }
        return result

    def get_programmes_for_day(self, channel_id: str, date_str: str | None = None) -> list[dict] | None:
        programmes = self._programmes_by_channel.get(channel_id)
        if programmes is None:
            return None
        if date_str:
            try:
                day = datetime.fromisoformat(date_str).date()
            except ValueError:
                day = dt_util.now().date()
        else:
            day = dt_util.now().date()
        return [
            programme.as_dict()
            for programme in programmes
            if programme.start and programme.start.date() == day
        ]

    async def _fetch_and_parse(self) -> None:
        async with self._session.get(XMLTV_URL, timeout=60) as resp:
            resp.raise_for_status()
            xml_text = await resp.text()
        root = ET.fromstring(xml_text)
        wanted = set(self._channels)
        meta: dict[str, dict] = {}
        for channel in root.findall("channel"):
            cid = channel.get("id")
            if cid not in wanted:
                continue
            display = channel.findtext("display-name") or cid
            icon_el = channel.find("icon")
            meta[cid] = {"name": display, "icon": icon_el.get("src") if icon_el is not None else None}
        programmes: dict[str, list[Programme]] = {cid: [] for cid in wanted}
        for node in root.findall("programme"):
            cid = node.get("channel")
            if cid not in wanted:
                continue
            start = _parse_xmltv_datetime(node.get("start"))
            stop = _parse_xmltv_datetime(node.get("stop"))
            title = node.findtext("title")
            if not start or not stop or not title:
                continue
            icon_el = node.find("icon")
            rating_el = node.find("rating/value")
            programmes[cid].append(
                Programme(
                    start=start,
                    stop=stop,
                    title=title,
                    subtitle=node.findtext("sub-title"),
                    desc=node.findtext("desc"),
                    category=node.findtext("category"),
                    icon=icon_el.get("src") if icon_el is not None else None,
                    rating=rating_el.text if rating_el is not None else None,
                )
            )
        for cid in programmes:
            programmes[cid].sort(key=lambda item: item.start)
        self._programmes_by_channel = programmes
        self._channels_meta = meta

    def _pick_slots(self, channel_id: str, now):
        items = self._programmes_by_channel.get(channel_id, [])
        current = next((item for item in items if item.start <= now < item.stop), None)

        def _at(moment):
            target = now.replace(hour=moment.hour, minute=moment.minute, second=0, microsecond=0)
            if now.time() < DAY_RESET:
                target = target - timedelta(days=1)
            covering = next((item for item in items if item.start <= target < item.stop), None)
            if covering:
                return covering
            return next((item for item in items if item.start >= target), None)

        return current, _at(PRIME_TIME_START), _at(LATE_NIGHT_START)
