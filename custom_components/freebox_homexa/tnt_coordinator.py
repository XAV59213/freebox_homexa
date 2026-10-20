"""XMLTV coordinator adapted from cyclope205/programme-tnt-fr (MIT)."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .tnt_tmdb import TmdbMatch, TmdbResolver
from .tnt_const import (
    DAY_RESET,
    FETCH_MIN_INTERVAL_MINUTES,
    LATE_NIGHT_START,
    PRIME_TIME_START,
    ALL_CHANNELS,
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


def _parse_xmltv(xml_text: str, channels: list[str]) -> tuple[dict, dict]:
    """Parse XMLTV off the event loop."""
    root = ET.fromstring(xml_text)
    wanted = set(channels)
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
                date=(node.findtext("date") or "").strip() or None,
            )
        )
    for cid in programmes:
        programmes[cid].sort(key=lambda item: item.start)
    return programmes, meta


class Programme:
    def __init__(
        self, start, stop, title, subtitle, desc, category, icon, rating, date=None
    ) -> None:
        self.start = start
        self.stop = stop
        self.title = title
        self.subtitle = subtitle
        self.desc = desc
        self.category = category
        self.icon = icon
        self.rating = rating
        self.date = date

    def as_dict(self, match: TmdbMatch | None = None) -> dict:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "description": self.desc,
            "category": self.category,
            "icon": self.icon,
            "poster": match.poster if match else self.icon,
            "tmdb_id": match.tmdb_id if match else None,
            "tmdb_media_type": match.media_type if match else None,
            "tmdb_rating": match.rating if match else 0,
            "tmdb_votes": match.votes if match else 0,
            "rating": self.rating,
            "date": self.date,
            "start": self.start.isoformat() if self.start else None,
            "stop": self.stop.isoformat() if self.stop else None,
        }


class ProgrammeTntFrCoordinator(DataUpdateCoordinator):
    def __init__(
        self, hass: HomeAssistant, channels: list[str], tmdb_api_key: str | None = None
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="programme_tnt_fr",
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._channels = channels
        # Clé TMDB personnelle de l'utilisateur (jamais de clé par défaut)
        self._tmdb_api_key = tmdb_api_key
        self._tmdb: TmdbResolver | None = (
            TmdbResolver(hass, tmdb_api_key, self.async_request_refresh)
            if tmdb_api_key
            else None
        )
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
            if self._tmdb is not None:
                self._tmdb.prune(self._all_programmes())

        if self._tmdb is not None:
            self._tmdb.schedule(self._all_programmes(), now)

        result: dict[str, dict] = {}
        for channel_id in self._channels:
            current, prime_time, second_part = self._pick_slots(channel_id, now)
            meta = self._channels_meta.get(channel_id, {})
            result[channel_id] = {
                "channel_id": channel_id,
                "channel_name": meta.get("name", ALL_CHANNELS.get(channel_id, channel_id)),
                "channel_icon": meta.get("icon"),
                "current": self._programme_dict(current),
                "prime_time": self._programme_dict(prime_time),
                "second_part": self._programme_dict(second_part),
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
            self._programme_dict(programme)
            for programme in programmes
            if programme.start and programme.start.date() == day
        ]

    def _all_programmes(self):
        for channel_id in self._channels:
            yield from self._programmes_by_channel.get(channel_id, [])

    def _programme_dict(self, programme: Programme | None) -> dict | None:
        if programme is None:
            return None
        match = self._tmdb.get(programme) if self._tmdb is not None else None
        return programme.as_dict(match)

    async def _fetch_and_parse(self) -> None:
        async with self._session.get(XMLTV_URL, timeout=60) as resp:
            resp.raise_for_status()
            xml_text = await resp.text()
        programmes, meta = await self.hass.async_add_executor_job(
            _parse_xmltv, xml_text, self._channels
        )
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
