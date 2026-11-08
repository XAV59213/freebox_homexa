"""Real HA paths for modules still under the 95% line threshold.

Device I/O stays mocked. These tests do not migrate identifiers, move a MAC
owned by another integration, or delete a group that still has an entity
or a child.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.freebox_homexa import async_setup_entry
from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.device_groups import group_identifier
from custom_components.freebox_homexa.frontend import HomexaCardView, JSModuleRegistration
from custom_components.freebox_homexa.player_remote import (
    PLAYER_API_RETRY_DELAYS,
    async_schedule_player_api_retry,
    filter_ready_players,
    player_display_name,
    player_id_from_identifiers,
)
from custom_components.freebox_homexa.tnt_reminders import (
    _ReminderManager,
    _UNSUB_KEY,
    _profile_targets,
    async_setup_reminders,
    async_unload_reminders,
)
from custom_components.freebox_homexa.tv_guide import (
    artwork_from_tnt_programs,
    channel_number,
    summarize_guide,
    tnt_artwork_url,
    tnt_programs,
    _slot_from_freebox,
)


def _config():
    return {
        "mac": "00:00:00:00:00:11",
        "model_info": {"pretty_name": "Test", "name": "test"},
        "firmware_version": "4.9.0",
    }


def _router():
    router = MagicMock()
    router.mac = "00:00:00:00:00:11"
    router.repeaters = {}
    router.devices = {}
    router.wifi_aps = {}
    router.player_identifiers = set()
    router.group_device_ids = {"unused": "gone"}
    router.used_groups = set()
    router.merged_node_ids = {8}
    router.update_all = AsyncMock()
    router.update_home_devices = AsyncMock()
    router.async_poll = AsyncMock(side_effect=RuntimeError("synthetic slow"))
    router.close = AsyncMock()
    return router


async def test_setup_migrates_groups_and_keeps_named_children(hass, caplog):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "freebox.test", "port": 80},
        options={"device_group_overrides": {"node:1": "security"}, "create_lan_devices": False},
    )
    entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    exclusive = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:61")},
        name="Client seul",
    )
    kept = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={group_identifier("00:00:00:00:00:11", "home")},
        name="Maison",
    )
    devices.async_update_device(kept.id, name_by_user="Ma maison")
    child = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "kept-child")},
        name="Enfant",
    )
    devices.async_update_device(child.id, via_device_id=kept.id, name_by_user="Mon enfant")
    empty = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={group_identifier("00:00:00:00:00:11", "security")},
        name="Ancien groupe",
    )
    merged = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, 8)},
        name="Ancienne alarme",
    )
    api = AsyncMock()
    api.system.get_config.return_value = _config()
    router = _router()
    intervals = []
    cleanup = {}

    with caplog.at_level("DEBUG"), \
         patch("custom_components.freebox_homexa.JSModuleRegistration.async_register", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.get_api", return_value=api), \
         patch("custom_components.freebox_homexa.FreeboxRouter", return_value=router), \
         patch("custom_components.freebox_homexa.async_merge_repeater_devices", return_value=1), \
         patch("custom_components.freebox_homexa.device_groups.repeater_registry_devices", return_value=[
             {"name_by_user": "Mon répéteur", "name": "Repeteur", "model": "F-RP01A", "identifiers": [], "entity_count": 0}
         ]), \
         patch("custom_components.freebox_homexa.async_setup_bundled_tnt", new=AsyncMock(side_effect=RuntimeError("synthetic tnt"))), \
         patch("custom_components.freebox_homexa.async_setup_reminders", new=AsyncMock(side_effect=RuntimeError("synthetic reminders"))), \
         patch("custom_components.freebox_homexa.async_track_time_interval", side_effect=lambda _hass, action, _interval: intervals.append(action) or (lambda: None)), \
         patch("custom_components.freebox_homexa.async_call_later", side_effect=lambda _hass, _delay, action: cleanup.setdefault("action", action) or (lambda: None)), \
         patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()):
        assert await async_setup_entry(hass, entry)
    assert entry.options["device_group_overrides"]["node:1"] == "home"
    assert devices.async_get(exclusive.id) is None
    assert "appareil(s) client réseau retiré(s)" in caplog.text
    assert "répéteur en double fusionné" in caplog.text
    assert "non fusionnés" in caplog.text
    assert "Guide TNT embarqué indisponible" in caplog.text
    assert "Rappels TNT indisponibles" in caplog.text
    await intervals[1](None)
    assert "Poll Home ignoré" in caplog.text
    cleanup["action"](None)
    assert devices.async_get(empty.id) is None
    assert devices.async_get(merged.id) is None
    assert devices.async_get(kept.id).name_by_user == "Ma maison"
    assert devices.async_get(child.id).name_by_user == "Mon enfant"
    assert devices.async_get(child.id).via_device_id == kept.id
    assert "unused" not in router.group_device_ids
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    router.close.assert_awaited()
    api.close.assert_not_awaited()


async def test_setup_reports_merge_and_summary_failures_and_closes_without_router(hass, caplog):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test", "port": 80})
    entry.add_to_hass(hass)
    api = AsyncMock()
    api.system.get_config.return_value = _config()
    router = _router()
    with caplog.at_level("DEBUG"), \
         patch("custom_components.freebox_homexa.JSModuleRegistration.async_register", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.get_api", return_value=api), \
         patch("custom_components.freebox_homexa.FreeboxRouter", return_value=router), \
         patch("custom_components.freebox_homexa.async_merge_repeater_devices", side_effect=RuntimeError("synthetic merge")), \
         patch("custom_components.freebox_homexa.device_groups.repeater_registry_devices", side_effect=RuntimeError("synthetic summary")), \
         patch("custom_components.freebox_homexa.async_setup_bundled_tnt", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.async_setup_reminders", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.async_track_time_interval", return_value=lambda: None), \
         patch("custom_components.freebox_homexa.async_call_later", return_value=lambda: None), \
         patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()):
        assert await async_setup_entry(hass, entry)
    assert "Fusion des répéteurs en double impossible" in caplog.text
    assert "Résumé des répéteurs impossible" in caplog.text
    fresh = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test", "port": 80})
    fresh.add_to_hass(hass)
    with patch("custom_components.freebox_homexa.JSModuleRegistration.async_register", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.get_api", return_value=api), \
         patch("custom_components.freebox_homexa.FreeboxRouter", side_effect=RuntimeError("synthetic router")):
        with pytest.raises(RuntimeError, match="synthetic router"):
            await async_setup_entry(hass, fresh)
    await fresh._async_process_on_unload(hass)
    api.close.assert_awaited()


async def test_player_retry_reload_stop_and_skip_messages(hass, caplog):
    assert player_id_from_identifiers([]) is None
    assert player_id_from_identifiers({(DOMAIN, "player_nope")}) is None
    assert player_display_name({}) == "Freebox Player"
    assert player_display_name({"id": 4}) == "Freebox Player 4"
    ready, skipped = filter_ready_players(
        [{"id": 1, "device_name": "Salon"}, {"api_available": False, "device_model": "fbx8am"}, "not-a-player", {"id": None, "name": "Pop"}],
        context="setup",
    )
    assert [player["id"] for player in ready] == [1]
    assert len(skipped) == 2
    assert "API Freebox OS est indisponible" in caplog.text
    assert "charge utile non dict" in caplog.text

    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"})
    entry.add_to_hass(hass)
    router = SimpleNamespace(
        _api=AsyncMock(), closing=False, player_identifiers={"player_1"}, _player_api_retry_scheduled=False,
    )
    router._api.player.get_players.side_effect = RuntimeError("synthetic")
    await async_schedule_player_api_retry(hass, entry, router)
    await async_schedule_player_api_retry(hass, entry, router)
    now = dt_util.utcnow()
    async_fire_time_changed(hass, now + timedelta(seconds=PLAYER_API_RETRY_DELAYS[0]))
    await hass.async_block_till_done()
    assert "Nouvelle tentative Player impossible" in caplog.text

    router.closing = True
    async_fire_time_changed(hass, now + timedelta(seconds=sum(PLAYER_API_RETRY_DELAYS)))
    await hass.async_block_till_done()
    hass.config_entries.async_reload = AsyncMock()
    router.closing = False
    router._player_api_retry_scheduled = False
    router._api.player.get_players.side_effect = None
    router._api.player.get_players.return_value = [{"id": 9, "device_name": "Chambre", "api_available": True}]
    await async_schedule_player_api_retry(hass, entry, router)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=PLAYER_API_RETRY_DELAYS[0] + 1))
    await hass.async_block_till_done()
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)

    quiet = SimpleNamespace(
        _api=AsyncMock(), closing=False, player_identifiers={"player_3"}, _player_api_retry_scheduled=False,
    )
    quiet._api.player.get_players.return_value = [{"id": 3, "name": "Deja connu"}]
    await async_schedule_player_api_retry(hass, entry, quiet)
    moment = dt_util.utcnow()
    for delay in (120, 300, 600):
        moment += timedelta(seconds=delay)
        async_fire_time_changed(hass, moment)
        await hass.async_block_till_done()
    assert "après 3 tentatives" in caplog.text


def test_guide_matches_artwork_slots_without_network(hass):
    assert channel_number("nrj12") == 12
    assert channel_number(None) is None
    poster = "https://example.test/poster.jpg"
    icon = "http://example.test/icon.png"
    programs = [
        "ignore",
        {"channel_name": 5, "current": {"poster": "ftp://nope"}},
        {"channel_name": "TF1", "current": {"poster": poster, "icon": icon}, "channel_icon": icon},
        {"channel_name": "M6", "current": {"icon": icon}, "channel_icon": "not-a-url"},
    ]
    assert artwork_from_tnt_programs(programs, channel_name="tf1") == poster
    assert artwork_from_tnt_programs(programs, channel_number="6") == icon
    assert artwork_from_tnt_programs(programs, channel_number=True) is None
    assert artwork_from_tnt_programs([{"channel_name": "M6", "channel_icon": icon}], channel_number=6) == icon
    coordinator = SimpleNamespace(data={
        "nrj12": {"channel_name": "NRJ 12", "channel_icon": icon, "current": {"title": "Soir", "poster": poster},
                  "prime_time": {"title": "Prime"}, "second_part": "skip"},
        "dup": "skip",
        "empty": {"current": "nope"},
    })
    other = SimpleNamespace(data=["not-a-dict"])
    hass.data["freebox_homexa"] = {"tnt_coordinators": {"a": coordinator, "b": other, "c": coordinator}}
    found = tnt_programs(hass)
    assert len(found) == 1
    assert tnt_artwork_url(hass, channel_name="NRJ 12") == poster
    summary = summarize_guide(hass)
    assert summary["source"] == "tnt"
    assert summary["current"][0]["title"] == "Soir"
    assert summary["prime_time"][0]["title"] == "Prime"
    now = dt_util.now().replace(hour=20, minute=30, second=0, microsecond=0)
    late = {"_start": now.replace(hour=23), "channel": "Arte", "title": "Nuit"}
    prime = {"_start": now.replace(hour=21, minute=20), "_end": now.replace(hour=22), "channel": "Arte", "title": "Prime"}
    inside = {"_start": now - timedelta(minutes=30), "_end": now + timedelta(minutes=30), "channel": "Arte", "title": "Maintenant"}
    outside = {"_start": now.replace(hour=18), "channel": "Arte", "title": "Passe"}
    assert _slot_from_freebox({"channel": "Arte"}, now) == "current"
    assert _slot_from_freebox(late, now) == "second_part"
    assert _slot_from_freebox(prime, now) == "prime_time"
    assert _slot_from_freebox(inside, now) == "current"
    assert _slot_from_freebox(outside, now) == "current"
    hass.data["freebox_homexa"]["tnt_coordinators"] = {}
    freebox = summarize_guide(hass, [late, prime, inside, outside, {"title": "Sans heure"}])
    assert freebox["source"] == "freebox"
    assert {item["title"] for item in freebox["second_part"]} == {"Nuit"}
    assert {item["title"] for item in freebox["prime_time"]} == {"Prime"}


class _Resources:
    def __init__(self, items, *, fail_load=False, fail_items=False, fail_write=False):
        self.items = items
        self.loaded = False
        self.fail_load = fail_load
        self.fail_items = fail_items
        self.fail_write = fail_write
        self.updated = None
        self.created = None

    async def async_load(self):
        if self.fail_load:
            raise RuntimeError("synthetic load")
        self.loaded = True

    def async_items(self):
        if self.fail_items:
            raise RuntimeError("synthetic items")
        return list(self.items)

    async def async_update_item(self, item_id, data):
        if self.fail_write:
            raise RuntimeError("synthetic update")
        self.updated = (item_id, data)

    async def async_create_item(self, data):
        if self.fail_write:
            raise RuntimeError("synthetic create")
        self.created = data


async def test_frontend_serves_card_and_updates_only_its_resource(hass, caplog):
    caplog.set_level("DEBUG")
    from homeassistant.setup import async_setup_component
    assert await async_setup_component(hass, "http", {"http": {}})
    assert await async_setup_component(hass, "frontend", {})
    await hass.async_block_till_done()
    view = HomexaCardView()
    request = SimpleNamespace(app={"hass": hass})
    response = await view.get(request)
    assert response.status == 200
    assert response.content_type == "text/javascript"
    assert b"freebox" in response.body.lower() or b"customElements" in response.body or len(response.body) > 20

    waiting = JSModuleRegistration(hass)
    hass.set_state(CoreState.not_running)
    with caplog.at_level("DEBUG"):
        await waiting.async_register()
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert "ressources Lovelace indisponibles" not in caplog.text or waiting._retries >= 0

    resources = _Resources([{"id": "card", "url": "/freebox_homexa/freebox-homexa-card.js?v=old"}])
    hass.data["lovelace"] = {"resources": resources}
    registration = JSModuleRegistration(hass)
    hass.set_state(CoreState.running)
    await registration.async_register()
    assert resources.loaded is True
    assert resources.updated[0] == "card"
    assert resources.updated[1]["url"].startswith("/freebox_homexa/freebox-homexa-card.js?v=")
    await registration.async_register()

    fresh = _Resources([])
    hass.data["lovelace"] = SimpleNamespace(resources=fresh)
    created = JSModuleRegistration(hass)
    await created._async_register_lovelace_resources()
    assert fresh.created["res_type"] == "module"
    assert "Carte Lovelace Homexa enregistrée" in caplog.text

    broken = _Resources([], fail_load=True)
    hass.data["lovelace"] = {"resources": broken}
    failing = JSModuleRegistration(hass)
    await failing._async_register_lovelace_resources()
    assert failing._retries == 1
    broken.fail_load = False
    broken.fail_items = True
    await failing._retry_resources(None)
    assert failing._retries == 2
    broken.fail_items = False
    broken.fail_write = True
    await failing._async_register_lovelace_resources()
    assert "Échec d'enregistrement de la carte Lovelace" in caplog.text
    failing._retries = 12
    failing._schedule_retry("synthetic exhausted")
    assert "Carte Lovelace non enregistrée" in caplog.text
    absent = JSModuleRegistration(hass)
    absent._retries = 12
    hass.data.pop("lovelace", None)
    await absent._async_register_lovelace_resources()
    hass.data["lovelace"] = {"resources": _Resources([{"id": "card", "url": "/freebox_homexa/freebox-homexa-card.js?v=28.8.90"}])}
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()


async def test_reminder_voice_volume_and_failures_use_real_services(hass, caplog):
    notified = []

    async def notify(call):
        notified.append(call.data)
        if call.data["message"].startswith("BOOM"):
            raise RuntimeError("synthetic notify")

    async def volume(call):
        level = call.data["volume_level"]
        if level == 0.9:
            raise RuntimeError("synthetic volume")
        entity = call.data.get("entity_id", "media_player.salon")
        if isinstance(entity, list):
            entity = entity[0]
        hass.states.async_set(entity, "idle", {"volume_level": level})

    spoken = []

    async def speak(call):
        spoken.append(call.data["message"])
        if "FAIL" in call.data["message"]:
            raise RuntimeError("synthetic tts")

    hass.services.async_register("notify", "synthetic", notify)
    hass.services.async_register("notify", "alexa_media_echo", notify)
    hass.services.async_register("media_player", "volume_set", volume)
    hass.services.async_register("tts", "speak", speak)
    er.async_get(hass).async_get_or_create(
        "media_player", "alexa_media", "echo", suggested_object_id="echo",
    )
    store = Store(hass, 1, "homexa_synthetic_voice")
    manager = _ReminderManager(hass, store)
    hass.states.async_set("media_player.salon", "playing", {"volume_level": 0.2})
    hass.states.async_set("media_player.echo", "idle", {"volume_level": 0.3})
    base = {"channel_name": "NRJ 12", "program_title": "Soir", "start_time": "2030-01-01T20:00:00+01:00", "minutes_before": 5}
    try:
        with caplog.at_level("WARNING"), \
             patch("custom_components.freebox_homexa.tnt_reminders.asyncio.sleep", new=AsyncMock()), \
             patch.object(manager, "_resolve_targets", return_value=(["synthetic"], ["media_player.salon", "media_player.echo"], "tts.demo", 0.4)):
            await manager.async_handle_schedule(ServiceCall(hass, DOMAIN, "schedule_reminder", base))
            async_fire_time_changed(hass, datetime.fromisoformat("2030-01-01T19:55:00+01:00"))
            await hass.async_block_till_done()
        assert any(item["message"].startswith("Soir commence") for item in notified)
        assert spoken == ["Soir commence dans 5 min sur NRJ 12"]
        assert hass.states.get("media_player.salon").attributes["volume_level"] == 0.2

        with caplog.at_level("WARNING"), patch("custom_components.freebox_homexa.tnt_reminders.asyncio.sleep", new=AsyncMock()):
            hass.services.async_remove("tts", "speak")
            await manager._async_notify({
                "program_title": "Absent", "minutes_before": 5, "channel_name": "M6",
                "targets": ["missing_notify"], "media_player_targets": ["media_player.salon"],
                "tts_engine": "tts.demo", "announce_volume": None,
            })
            hass.services.async_remove("media_player", "volume_set")
            await manager._async_notify({
                "program_title": "Volume", "minutes_before": 5, "channel_name": "M6",
                "targets": [], "media_player_targets": ["media_player.salon"],
                "tts_engine": None, "announce_volume": 0.4,
            })
            await manager._async_notify({
                "program_title": "Silencieux", "minutes_before": 5, "channel_name": "M6",
                "targets": [], "media_player_targets": ["media_player.salon"],
                "tts_engine": None, "announce_volume": None,
            })
            await manager._async_notify({
                "program_title": "Vide", "minutes_before": 5, "channel_name": "M6",
                "targets": [], "media_player_targets": [],
            })
        assert "Echec de l'envoi du rappel" in caplog.text
        assert "Echec du reglage du volume" in caplog.text
        assert "Echec de l'annonce vocale" in caplog.text
        assert "Pas de moteur TTS" in caplog.text
        assert "aucun appareil de notification" in caplog.text
        with pytest.raises(ServiceValidationError):
            manager._schedule({"id": "bad", "fire_time": "not-a-time"})
        assert _profile_targets("notify.synthetic") == ["notify.synthetic"]
        entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={"reminder_profiles": [{"name": "Seul", "notify_target": "synthetic"}]})
        entry.add_to_hass(hass)
        assert manager._find_profile(None)["name"] == "Seul"
        assert manager._resolve_targets("inconnu") == ([], [], None, None)
        entry2 = MockConfigEntry(domain=DOMAIN, data={"host": "other.test"}, options={"reminder_profiles": "nope"})
        entry2.add_to_hass(hass)
        with pytest.raises(ServiceValidationError):
            manager._find_profile("Seul")
        await async_setup_reminders(hass)
        hass.data[_UNSUB_KEY] = {"synthetic": lambda: None}
        async_unload_reminders(hass)
        assert not hass.services.has_service(DOMAIN, "schedule_reminder")
        async_unload_reminders(hass)
    finally:
        for unsub in list(hass.data.get(_UNSUB_KEY, {}).values()):
            unsub()
        hass.data.pop(_UNSUB_KEY, None)
