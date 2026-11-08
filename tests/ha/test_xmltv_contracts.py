"""Actual XML parser/time-slot and public HTTP contracts, synthetic guide only."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import xml.etree.ElementTree as ET
import pytest
from custom_components.freebox_homexa.tnt_coordinator import (
    _parse_xmltv, _parse_xmltv_datetime, Programme, ProgrammeTntFrCoordinator)
from custom_components.freebox_homexa.tnt_const import XMLTV_URL


def test_incremental_xmltv_sort_filter_metadata_and_utf8_chunk_boundary():
    description = "é" * 40000
    xml = f'''<tv><channel id="TF1.fr"><display-name>Chaîne synthétique</display-name><icon src="https://example.invalid/icon.png"/></channel>
    <channel id="ignored"><display-name>Ignored</display-name></channel>
    <programme channel="TF1.fr" start="20261107130000 +0100" stop="20261107140000 +0100"><title>Second</title><desc>{description}</desc><sub-title>Sub</sub-title><category>Film</category><date>2026</date><rating><value>10</value></rating><icon src="https://example.invalid/program.png"/></programme>
    <programme channel="TF1.fr" start="20261107120000 +0100" stop="20261107130000 +0100"><title>First</title></programme>
    <programme channel="TF1.fr" start="invalid" stop="20261107130000 +0100"><title>Invalid</title></programme>
    <programme channel="TF1.fr" start="20261107140000 +0100" stop="20261107150000 +0100"/>
    <programme channel="ignored" start="20261107120000 +0100" stop="20261107130000 +0100"><title>Ignored</title></programme></tv>'''
    programmes, metadata = _parse_xmltv(xml.encode(), ["TF1.fr", "missing"])
    assert [p.title for p in programmes["TF1.fr"]] == ["First", "Second"]
    assert programmes["missing"] == []
    assert metadata == {"TF1.fr": {"name": "Chaîne synthétique", "icon": "https://example.invalid/icon.png"}}
    second = programmes["TF1.fr"][1]
    assert second.desc == description
    data = second.as_dict()
    assert data["poster"] == data["icon"] == "https://example.invalid/program.png"
    assert data["start"] == "2026-11-07T13:00:00+01:00"
    assert data["rating"] == "10" and data["date"] == "2026"
    assert second.subtitle == "Sub"
    assert second.category == "Film"
    assert _parse_xmltv_datetime(None) is None
    assert _parse_xmltv_datetime("invalid") is None
    with pytest.raises(ET.ParseError):
        _parse_xmltv(b"<tv><programme>", ["TF1.fr"])


async def test_real_http_fetch_parse_and_broadcast_day_slots(hass, aioclient_mock):
    tz = timezone(timedelta(hours=1))
    now = datetime(2026, 11, 7, 21, 30, tzinfo=tz)
    coordinator = ProgrammeTntFrCoordinator(hass, ["TF1.fr"])
    xml = b'<tv><channel id="TF1.fr"><display-name>Synthetic</display-name></channel><programme channel="TF1.fr" start="20261107210000 +0100" stop="20261107233000 +0100"><title>Prime</title></programme><programme channel="TF1.fr" start="20261107233000 +0100" stop="20261108020000 +0100"><title>Late</title></programme></tv>'
    aioclient_mock.get(XMLTV_URL, content=xml)
    try:
        with patch("custom_components.freebox_homexa.tnt_coordinator.dt_util.now", return_value=now):
            result = await coordinator._async_update_data()
            assert result["TF1.fr"]["current"]["title"] == "Prime"
            assert result["TF1.fr"]["next"]["title"] == "Late"
            assert result["TF1.fr"]["prime_time"]["title"] == "Prime"
            assert result["TF1.fr"]["second_part"]["title"] == "Late"
            assert len(coordinator.get_programmes_for_day("TF1.fr", "2026-11-07")) == 2
            assert coordinator.get_programmes_for_day("unknown") is None
            assert coordinator.get_programmes_for_day("TF1.fr", "invalid") is None
            assert coordinator._programme_dict(None) is None
            assert list(coordinator._all_programmes()) == coordinator._programmes_by_channel["TF1.fr"]
            await coordinator._async_update_data()
        assert aioclient_mock.call_count == 1
        after_midnight = datetime(2026, 11, 8, 1, 0, tzinfo=tz)
        with patch("custom_components.freebox_homexa.tnt_coordinator.dt_util.now", return_value=after_midnight):
            assert len(coordinator.get_programmes_for_day("TF1.fr")) == 2
        before = datetime(2026, 11, 7, 20, 0, tzinfo=tz)
        slots = coordinator._pick_slots("TF1.fr", before)
        assert slots[0] is None and slots[1] is None
        assert slots[2].title == "Prime"
    finally:
        await coordinator.async_shutdown()
