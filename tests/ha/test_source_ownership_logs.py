"""Actual HA entity ownership, SDK fallback, and finite source transitions."""
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from freebox_api.api.player import Player
from freebox_api.api.home import Home
from homeassistant.helpers.entity_platform import EntityPlatform
from datetime import timedelta

from custom_components.freebox_homexa.button import FreeboxPlayerAppButton, FreeboxPlayerRemoteButton
from custom_components.freebox_homexa.media_player import FreeboxPlayerMediaPlayer
from custom_components.freebox_homexa.remote import FreeboxRemote
from custom_components.freebox_homexa.entity import FreeboxHomeEntity
from custom_components.freebox_homexa.const import CONF_REMOTE_CODES
from custom_components.freebox_homexa.tnt_coordinator import ProgrammeTntFrCoordinator
from test_player_platforms import player_context
from test_home_platforms import make_platform, home_context


def buttons(router, entry, player):
    return [FreeboxPlayerAppButton(router, player, 'youtube', 'YouTube', 'mdi:youtube', 'app://synthetic', True),
            FreeboxPlayerRemoteButton(router, player, entry, 'power', 'Power', 'mdi:power', True)]


async def test_buttons_only_one_read_failure_recovery_and_release(hass, player_context, caplog):
    router, entry, player = player_context
    transport = Mock(get=AsyncMock(return_value={'power_state': 'running'}), post=AsyncMock(), put=AsyncMock())
    router._api.player = Player(transport)
    entities = buttons(router, entry, player)
    platform = make_platform(hass, 'button')
    with caplog.at_level(logging.INFO):
        try:
            await platform.async_add_entities(entities)
            assert router._player_button_readers['1'][0] == 2
            await router.update_player_buttons()
            await hass.async_block_till_done()
            assert transport.get.await_count == 1
            assert all(e.available for e in entities)
            ids = [e.entity_id for e in entities]
            transport.get.side_effect = TimeoutError('SYNTHETIC_SECRET')
            for _ in range(3):
                await router.update_player_buttons()
            await hass.async_block_till_done()
            assert all(hass.states.get(e.entity_id).state == 'unavailable' for e in entities)
            assert caplog.text.count('Player indisponible') == 1
            assert 'SYNTHETIC_SECRET' not in caplog.text
            assert transport.get.await_count == 13  # four existing fallbacks, not per button
            transport.get.side_effect = None
            transport.get.return_value = {}  # valid unknown, still reachable
            await router.update_player_buttons()
            await hass.async_block_till_done()
            assert all(e.available for e in entities)
            assert ids == [e.entity_id for e in entities]
            assert caplog.text.count('Player de nouveau disponible') == 1
        finally:
            await platform.async_reset()
    assert not router._player_button_readers
    count = transport.get.await_count
    await router.update_player_buttons()
    assert transport.get.await_count == count
    transport.post.assert_not_called()
    transport.put.assert_not_called()


async def test_media_provider_no_duplicate_fallback_and_ownership_release(hass, player_context):
    router, entry, player = player_context
    transport = Mock(get=AsyncMock(return_value={'power_state': 'standby'}))
    router._api.player = Player(transport)
    media = FreeboxPlayerMediaPlayer(router, player, entry)
    mp = make_platform(hass, 'media_player')
    bp = make_platform(hass, 'button')
    try:
        await bp.async_add_entities(buttons(router, entry, player))
        await mp.async_add_entities([media], update_before_add=True)
        count = transport.get.await_count
        assert router.player_status_providers == {'1'}
        await router.update_player_buttons()
        assert transport.get.await_count == count
        await mp.async_reset()
        assert not router.player_status_providers
        await router.update_player_buttons()
        assert transport.get.await_count == count + 1
    finally:
        await mp.async_reset()
        await bp.async_reset()


@pytest.mark.parametrize('code', [False, True])
async def test_fallback_known_standby_and_no_invented_first_off(hass, player_context, code):
    router, entry, player = player_context
    if code:
        hass.config_entries.async_update_entry(entry, options={CONF_REMOTE_CODES: {'1': 'SYNTHETIC'}})
    transport = Mock(get=AsyncMock(side_effect=TimeoutError()))
    router._api.player = Player(transport)
    remove = router.register_player_button(1, 'v8')
    try:
        await router.update_player_buttons()
        assert not router.player_status_available['1']  # code alone isn't a power observation
        transport.get.side_effect = None
        transport.get.return_value = {'power_state': 'standby', 'reachable': False}
        await router.update_player_buttons()
        assert router.player_status_available['1'] is code
        transport.get.side_effect = TimeoutError()
        await router.update_player_buttons()
        assert router.player_status_available['1'] is code
    finally:
        remove()


@pytest.mark.parametrize('kind', ['remote', 'media', 'endpoint'])
async def test_individual_sources_one_loss_one_recovery_no_private_payload(hass, player_context, home_context, caplog, kind):
    router, entry, player = player_context
    transport = Mock(get=AsyncMock(side_effect=TimeoutError('SYNTHETIC_PRIVATE')))
    if kind == 'endpoint':
        router, node = home_context
        router._api.home = Home(transport)
        entity = FreeboxHomeEntity(hass, router, node)
        async def update():
            await entity.get_home_endpoint_value(1)
        response = {'value': None}
        label = 'Lecture Home'
    else:
        router._api.player = Player(transport)
        entity = FreeboxRemote(router, player, entry) if kind == 'remote' else FreeboxPlayerMediaPlayer(router, player, entry)
        update = entity.async_update
        response = {'power_state': 'running'}
        label = 'Télécommande Player' if kind == 'remote' else 'Player'
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            await update()
        assert caplog.text.count(label + ' indisponible') == 1
        assert 'SYNTHETIC_PRIVATE' not in caplog.text
        transport.get.side_effect = None
        transport.get.return_value = response
        for _ in range(3):
            await update()
        assert caplog.text.count(label + ' de nouveau disponible') == 1


async def test_xmltv_coordinator_handles_own_single_failure_and_recovery(hass, caplog):
    coordinator = ProgrammeTntFrCoordinator(hass, ['C1'])
    with patch.object(coordinator, '_fetch_and_parse', AsyncMock(side_effect=TimeoutError('SYNTHETIC_PRIVATE'))) as fetch:
        with caplog.at_level(logging.INFO):
            for _ in range(3):
                await coordinator.async_refresh()
            assert not coordinator.last_update_success
            losses = [r for r in caplog.records if 'Error fetching' in r.message]
            assert len(losses) == 1
            assert 'SYNTHETIC_PRIVATE' not in caplog.text
            fetch.side_effect = None
            await coordinator.async_refresh()
            assert coordinator.last_update_success
            assert caplog.text.count('Fetching freebox_homexa_tnt data recovered') == 1


@pytest.mark.parametrize('source,label', [('sensors', 'Capteurs Freebox'), ('disks', 'Source disques Freebox'),
    ('raids', 'Source RAID Freebox'), ('home', 'Source Freebox Home')])
async def test_existing_central_source_transitions_remain_single(home_context, caplog, source, label):
    router, node = home_context
    if source == 'sensors':
        call = router._api.system.get_config
        update = router.update_sensors
        response = {'sensors': [], 'uptime_val': 10, 'serial': 'SYNTHETIC'}
        router._api.storage.get_disks.return_value = []
        router._api.storage.get_raids.return_value = []
        router._api.connection.get_status.return_value = {}
        router._api.call.get_calls_log.return_value = []
    elif source in {'disks', 'raids'}:
        call = getattr(router._api.storage, 'get_' + source)
        update = getattr(router, '_update_' + source + '_sensors')
        response = []
    else:
        call = router.home.get_home_nodes
        update = router.update_home_devices
        response = [node]
    with caplog.at_level(logging.INFO):
        call.side_effect = TimeoutError('SYNTHETIC_PRIVATE')
        for _ in range(3):
            await update()
        assert caplog.text.count(label + ' indisponible') == 1
        assert 'SYNTHETIC_PRIVATE' not in caplog.text
        call.side_effect = None
        call.return_value = response
        for _ in range(3):
            await update()
        assert caplog.text.count(label + ' de nouveau disponible') == 1


@pytest.mark.parametrize('failure', [None, TimeoutError('SYNTHETIC_PRIVATE')])
async def test_inherited_ffmpeg_frame_failure_logs_once_and_recovers(hass, home_context, caplog, failure):
    from custom_components.freebox_homexa.camera import FreeboxCamera
    router, node = home_context
    camera = FreeboxCamera(hass, router, node)
    camera.hass = hass
    with patch('homeassistant.components.ffmpeg.camera.async_get_image', AsyncMock()) as image:
        with caplog.at_level(logging.INFO):
            if isinstance(failure, Exception):
                image.side_effect = failure
            else:
                image.return_value = failure
            for _ in range(3):
                if isinstance(failure, Exception):
                    with pytest.raises(TimeoutError):
                        await camera.async_camera_image(320, 240)
                else:
                    assert await camera.async_camera_image(320, 240) is None
            assert caplog.text.count('Image caméra indisponible') == 1
            assert 'SYNTHETIC_PRIVATE' not in caplog.text
            image.side_effect = None
            image.return_value = b'SYNTHETIC_IMAGE'
            assert await camera.async_camera_image(320, 240) == b'SYNTHETIC_IMAGE'
            assert caplog.text.count('Image caméra de nouveau disponible') == 1
            # Image channel is distinct from valid Home control/status. No cached frame returned.
            assert camera.available


async def test_wifi_config_bss_ap_stations_repeat_and_recover(home_context, caplog):
    router, _ = home_context
    wifi = router._api.wifi
    with caplog.at_level(logging.INFO):
        for method in [wifi.get_global_config, wifi.get_bss, wifi.get_ap_list]:
            method.side_effect = TimeoutError('SYNTHETIC_PRIVATE')
        for _ in range(3):
            await router._fetch_wifi_global_state()
            await router._enrich_wifi_stations()
        for label in ['API Freebox Wi-Fi config', 'API Freebox Wi-Fi bss', 'API Freebox Wi-Fi ap', 'Stations Wi-Fi']:
            assert caplog.text.count(label + ' indisponible') == 1
        assert 'SYNTHETIC_PRIVATE' not in caplog.text
        wifi.get_global_config.side_effect = None
        wifi.get_global_config.return_value = {}
        wifi.get_bss.side_effect = None
        wifi.get_bss.return_value = []
        wifi.get_ap_list.side_effect = None
        wifi.get_ap_list.return_value = [{'id': 1}]
        wifi.get_station_list.side_effect = TimeoutError('SYNTHETIC_PRIVATE')
        for _ in range(3):
            await router._fetch_wifi_global_state()
            await router._enrich_wifi_stations()
        # AP source recovered, stations still failed: no premature station recovery.
        assert caplog.text.count('Stations Wi-Fi de nouveau disponible') == 0
        wifi.get_station_list.side_effect = None
        wifi.get_station_list.return_value = []
        await router._enrich_wifi_stations()
        for label in ['API Freebox Wi-Fi config', 'API Freebox Wi-Fi bss', 'API Freebox Wi-Fi ap', 'Stations Wi-Fi']:
            assert caplog.text.count(label + ' de nouveau disponible') == 1


async def test_fallback_version_preference_and_inflight_close(hass, player_context):
    import asyncio
    router, entry, player = player_context
    entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def get(path):
        if '/v8/' not in path:
            raise TimeoutError('synthetic version')
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()
        return {'power_state': 'running'}
    transport = Mock(get=AsyncMock(side_effect=get))
    router._api.player = Player(transport)
    remove = router.register_player_button(1, 'v6')
    read = hass.async_create_background_task(router.update_player_buttons(), 'synthetic status')
    await entered.wait()
    close = hass.async_create_background_task(router.close(), 'synthetic close')
    try:
        # A deterministic hand-off, not a timing sleep.
        await cancelled.wait()
        assert router.closing
        router._api.close.assert_not_called()
        release.set()
        await read
        await close
        router._api.close.assert_awaited_once()
        assert router._player_button_readers['1'][2] == 'v8'
        assert transport.get.await_count == 2
    finally:
        release.set()
        remove()
        await read
        await close


async def test_node_unreachable_and_camera_disappearance_do_not_repeat(hass, home_context, caplog):
    from custom_components.freebox_homexa.camera import FreeboxCamera
    router, node = home_context
    camera = FreeboxCamera(hass, router, node)
    platform = make_platform(hass, 'camera')
    with caplog.at_level(logging.INFO):
        try:
            await platform.async_add_entities([camera])
            router.home.get_home_nodes.return_value = [dict(node, status='unreachable')]
            for _ in range(3):
                await router.update_home_devices()
            await hass.async_block_till_done()
            assert not camera.available
            assert caplog.text.count('Appareil Home indisponible') == 1
            router.home.get_home_nodes.return_value = [node]
            await router.update_home_devices()
            await hass.async_block_till_done()
            assert camera.available
            assert caplog.text.count('Appareil Home de nouveau disponible') == 1
            router.home.get_home_nodes.return_value = []
            for _ in range(3):
                await router.update_home_devices()
            await hass.async_block_till_done()
            assert caplog.text.count('Appareil Home indisponible') == 2
            router.home.get_home_nodes.return_value = [node]
            await router.update_home_devices()
            await hass.async_block_till_done()
            assert camera.available
            assert caplog.text.count('Appareil Home de nouveau disponible') == 2
        finally:
            await platform.async_reset()


async def test_central_lan_timeout_transition_has_no_host_or_payload(home_context, caplog):
    router, _ = home_context
    with caplog.at_level(logging.INFO), patch.object(router, 'update_sensors', AsyncMock()):
        router._api.lan.get_hosts_list.side_effect = TimeoutError('SYNTHETIC_PRIVATE')
        for _ in range(3):
            await router.update_all(now=object())
        assert not router.lan_available and not router.reachable
        assert caplog.text.count('Source LAN indisponible') == 1
        assert caplog.text.count('Freebox injoignable') == 1
        assert 'SYNTHETIC_PRIVATE' not in caplog.text
        assert 'freebox.test' not in caplog.text
        router._api.lan.get_hosts_list.side_effect = None
        router._api.lan.get_hosts_list.return_value = []
        router._api.wifi.get_global_config.return_value = {}
        router._api.wifi.get_bss.return_value = []
        router._api.wifi.get_ap_list.return_value = []
        with patch.object(router, '_fetch_api_repeaters', AsyncMock()):
            for _ in range(3):
                await router.update_all(now=object())
        assert router.lan_available and router.reachable
        assert caplog.text.count('Source LAN de nouveau disponible') == 1
        assert caplog.text.count('Freebox de nouveau joignable') == 1


async def test_wifi_switch_unknown_is_not_failed_source_and_logs_once(home_context, caplog):
    from custom_components.freebox_homexa.switch import FreeboxSwitch, SWITCH_DESCRIPTIONS
    router, _ = home_context
    entity = FreeboxSwitch(router, SWITCH_DESCRIPTIONS[0])
    with caplog.at_level(logging.INFO):
        router.wifi.get_global_config.side_effect = TimeoutError('SYNTHETIC_PRIVATE')
        for _ in range(3):
            await entity.async_update()
        assert not entity.available
        assert caplog.text.count('Interrupteur Wi-Fi indisponible') == 1
        router.wifi.get_global_config.side_effect = None
        router.wifi.get_global_config.return_value = {}
        for _ in range(3):
            await entity.async_update()
        assert entity.available and entity.is_on is None
        assert caplog.text.count('Interrupteur Wi-Fi de nouveau disponible') == 1
        assert 'SYNTHETIC_PRIVATE' not in caplog.text
        router.wifi.set_global_config.assert_not_called()
