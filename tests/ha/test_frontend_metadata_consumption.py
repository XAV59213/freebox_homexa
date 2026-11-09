"""Exercise HA's real translation lifecycle and registry/frontend serialization."""
import json
from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.cover import CoverEntity
from homeassistant.components.camera import Camera
from homeassistant.components.calendar import CalendarEntity
from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.remote import RemoteEntity
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity
from custom_components.freebox_homexa.media_player import FreeboxPlayerMediaPlayer
from test_entity_inventory import build_inventory
from test_entity_naming_defaults import platform_for
from test_home_platforms import home_context
from test_player_platforms import player_context

DOMAINS = [(SensorEntity, 'sensor'), (BinarySensorEntity, 'binary_sensor'),
    (ButtonEntity, 'button'), (SwitchEntity, 'switch'), (CoverEntity, 'cover'),
    (Camera, 'camera'), (CalendarEntity, 'calendar'), (MediaPlayerEntity, 'media_player'),
    (RemoteEntity, 'remote'), (ScannerEntity, 'device_tracker'),
    (AlarmControlPanelEntity, 'alarm_control_panel')]


@pytest.mark.parametrize('language', ['fr', 'en'])
async def test_every_fixed_label_consumed_by_real_entity_platform(hass, home_context, language):
    hass.config.language = language
    router, node = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    objects, coordinator = build_inventory(hass, router, node, entry)
    registry = er.async_get(hass)
    consumed = {}
    try:
        for variant, entity in objects:
            domain = next(domain for cls, domain in DOMAINS if isinstance(entity, cls))
            # Include normally disabled diagnostics/remote buttons without changing their defaults.
            previous = registry.async_get_or_create(domain, 'freebox_homexa', entity.unique_id,
                config_entry=entry, suggested_object_id='original_' + variant, disabled_by=None)
            platform = platform_for(hass, entry, domain)
            await platform.platform_data.async_load_translations()
            try:
                await platform.async_add_entities([entity])
                assert entity.entity_id == previous.entity_id
                assert registry.async_get(entity.entity_id).unique_id == previous.unique_id
                key = entity.translation_key
                if variant == "battery":
                    consumed["battery"] = entity.name  # Native translated battery device-class name.
                if key is None or key.startswith('device_') or variant == 'temperature':
                    continue  # Primary/provided names and icon-only keys are not fixed labels.
                translation_path = f'component.freebox_homexa.entity.{domain}.{key}.name'
                template = platform.platform_data.platform_translations[translation_path]
                expected = template.format(**entity.translation_placeholders)
                assert entity.name == expected, (language, variant, entity.name, expected)
                assert registry.async_get(entity.entity_id).original_name == expected
                consumed[key] = expected
                registry.async_update_entity(entity.entity_id, name='Mon libellé', icon='mdi:heart')
                await hass.async_block_till_done()
                assert hass.states.get(entity.entity_id).attributes['friendly_name'] == 'Mon libellé'
                assert registry.async_get(entity.entity_id).icon == 'mdi:heart'
            finally:
                await platform.async_reset()
        assert len(consumed) == 69
        assert consumed['battery'] == ('Batterie' if language == 'fr' else 'Battery')
        assert consumed['rate_down'] == ('Vitesse de téléchargement' if language == 'fr' else 'Download speed')
        assert consumed['partition_free_space'] == ('Synthetic espace libre' if language == 'fr' else 'Synthetic free space')
        assert consumed['wifi_signal_named'] == ('Synthetic Signal Wi-Fi' if language == 'fr' else 'Synthetic Wi-Fi signal')
        assert consumed['tnt_channel'] == 'TF1'
        router._api.home.set_home_endpoint_value.assert_not_called()
        router._api.player._access.put.assert_not_called()
        router._api.remote.send_key.assert_not_called()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize('initial', ['TV', 'YouTube'])
@pytest.mark.parametrize('customized', [False, True])
async def test_dynamic_icons_follow_source_frontend_cache_preferences_and_reload(hass, player_context, initial, customized):
    router, entry, player = player_context
    get = router._api.player._access.get
    entity = FreeboxPlayerMediaPlayer(router, player, entry)
    registry = er.async_get(hass)
    original = registry.async_get_or_create('media_player', 'freebox_homexa', entity.unique_id,
        config_entry=entry, suggested_object_id='historical_player')
    if customized:
        original = registry.async_update_entity(original.entity_id, name='Mon cinéma', icon='mdi:heart',
            hidden_by=er.RegistryEntryHider.USER)
        original = registry.async_update_entity_options(original.entity_id, 'conversation', {'should_expose': False})
    stable = lambda row: (row.entity_id, row.unique_id, row.name, row.icon, row.hidden_by, row.disabled_by, row.options)
    original_preferences = stable(original)
    icons = (await async_get_icons(hass, 'entity', ['freebox_homexa']))['freebox_homexa']['media_player']
    events = []
    unsubscribe = hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, events.append)
    platform = platform_for(hass, entry, 'media_player')
    await platform.platform_data.async_load_translations()
    def status(source, power='running'):
        return {'source': 'tv:1' if source == 'TV' else source, 'power_state': power, 'volume': 20}
    get.return_value = status(initial)
    try:
        await platform.async_add_entities([entity], update_before_add=True)
        await hass.async_block_till_done()
        for source, expected in [('YouTube', 'player_youtube'), ('YouTube', 'player_youtube'),
                ('Netflix', 'player_netflix'), ('TV', None), ('other', None), ('YouTube', 'player_youtube'),
                ('off', None)]:
            before = registry.async_get(entity.entity_id)
            # Materialize the SAME cached frontend representation before changing source.
            assert json.loads(before.display_json_repr).get('tk') == before.translation_key
            events.clear()
            get.return_value = status(source, 'off' if source == 'off' else 'running')
            await entity.async_update()
            entity.async_write_ha_state()
            await hass.async_block_till_done()
            row = registry.async_get(entity.entity_id)
            payload = json.loads(row.display_json_repr)
            assert entity.translation_key == row.translation_key == payload.get('tk') == expected
            assert entity.icon is None  # The frontend metadata, not a Python MDI override, supplies the icon.
            assert stable(row) == original_preferences
            assert payload.get('ic') == ('mdi:heart' if customized else None)
            own_events = [event for event in events if event.data.get('entity_id') == entity.entity_id]
            assert len(own_events) == int(before.translation_key != expected)
            if own_events:
                assert set(own_events[0].data['changes']) == {'translation_key'}
            if expected:
                assert icons[expected]['default'] == ('mdi:youtube' if source == 'YouTube' else 'mdi:netflix')
        await platform.async_reset()
        entity = FreeboxPlayerMediaPlayer(router, player, entry)
        get.return_value = status('Netflix')
        await platform.async_add_entities([entity], update_before_add=True)
        await hass.async_block_till_done()
        assert entity.entity_id == original.entity_id
        assert stable(registry.async_get(entity.entity_id)) == original_preferences
        assert json.loads(registry.async_get(entity.entity_id).display_json_repr)['tk'] == 'player_netflix'
        router._api.player._access.put.assert_not_called()
        router._api.player._access.post.assert_not_called()
        router._api.remote.send_key.assert_not_called()
    finally:
        unsubscribe()
        await platform.async_reset()


@pytest.mark.parametrize('failure', [None, b'', TimeoutError('synthetic'), ValueError('synthetic')])
async def test_video_health_distinct_from_home_control_recovers_without_probe(hass, home_context, failure):
    from custom_components.freebox_homexa.camera import FreeboxCamera
    from custom_components.freebox_homexa.entity import FreeboxHomeEntity
    router, node = home_context
    node = {**node, 'category': 'camera'}
    router.home_devices[node['id']] = node
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entity = FreeboxCamera(hass, router, node)
    platform = platform_for(hass, entry, 'camera')
    frame = AsyncMock(return_value=b'synthetic-frame')
    try:
        await platform.async_add_entities([entity])
        assert entity.extra_state_attributes['video_available'] is None
        with patch('homeassistant.components.ffmpeg.camera.FFmpegCamera.async_camera_image', frame):
            assert await entity.async_camera_image() == b'synthetic-frame'
            assert entity.extra_state_attributes['video_available'] is True
            frame.return_value = failure if isinstance(failure, bytes) else None
            frame.side_effect = failure if isinstance(failure, Exception) else None
            for _ in range(2):
                if isinstance(failure, Exception):
                    with pytest.raises(type(failure)):
                        await entity.async_camera_image()
                else:
                    assert await entity.async_camera_image() == failure
                assert entity.available  # A failed secondary image is not failed Home control/status.
                assert hass.states.get(entity.entity_id).attributes['video_available'] is False
            # A healthy Home poll never pretends to prove video recovery.
            await FreeboxHomeEntity.async_update_signal(entity)
            assert entity.available and entity.extra_state_attributes['video_available'] is False
            frame.side_effect = None
            frame.return_value = b'recovered-frame'
            assert await entity.async_camera_image() == b'recovered-frame'
            assert hass.states.get(entity.entity_id).attributes['video_available'] is True
            assert frame.await_count == 4  # Foreground requests only, no timer, probe or retry.
        router.home_available = False
        entity.async_write_ha_state()
        assert hass.states.get(entity.entity_id).state == 'unavailable'
        router._api.home.set_home_endpoint_value.assert_not_called()
    finally:
        await platform.async_reset()


@pytest.mark.parametrize('position', [None, True, -1, 101, 25.5])
async def test_cover_real_signature_rejects_invalid_position_before_transport(hass, home_context, position):
    from custom_components.freebox_homexa.cover import FreeboxShutter
    from homeassistant.exceptions import ServiceValidationError
    router, node = home_context
    entity = FreeboxShutter(hass, router, node)
    with pytest.raises(ServiceValidationError):
        if position is None:
            await entity.async_set_cover_position()
        else:
            await entity.async_set_cover_position(position=position)
    router._api.home.set_home_endpoint_value.assert_not_called()


@pytest.mark.parametrize('channels,expected', [
    (None, None), (['TF1.fr', 'unknown', 42], ['TF1.fr']),
    (('TF1.fr',), ['TF1.fr']), (True, TypeError), ('TF1.fr', []),
])
def test_selected_channels_narrows_real_option_values(channels, expected):
    from custom_components.freebox_homexa.tnt_const import selected_channels, DEFAULT_CHANNELS, CONF_TNT_CHANNELS
    if expected is TypeError:
        with pytest.raises(TypeError):
            selected_channels({CONF_TNT_CHANNELS: channels})
    else:
        assert selected_channels({CONF_TNT_CHANNELS: channels}) == (list(DEFAULT_CHANNELS) if expected is None else expected)


@pytest.mark.parametrize('current', ['malformed', {'title': 42, 'icon': False}, None])
async def test_tnt_unknown_metadata_is_not_an_invented_title_or_artwork(hass, home_context, current):
    from custom_components.freebox_homexa.tnt_coordinator import ProgrammeTntFrCoordinator
    from custom_components.freebox_homexa.tnt_sensor import HomexaTntSensor
    router, _ = home_context
    entry = hass.config_entries.async_get_entry(router.entry_id)
    coordinator = ProgrammeTntFrCoordinator(hass, ['TF1.fr'], config_entry=entry)
    try:
        coordinator.async_set_updated_data({'TF1.fr': {'current': current, 'channel_icon': False}})
        entity = HomexaTntSensor(coordinator, 'TF1.fr', 'synthetic', router)
        assert entity.native_value is None
        assert entity.entity_picture is None
        assert entity.extra_state_attributes['channel_name'] == 'TF1'
        coordinator.async_set_updated_data({'TF1.fr': {'current': {'title': 'Source title', 'icon': '/source.png'}}})
        assert entity.native_value == 'Source title'
        assert entity.entity_picture == '/source.png'
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize('shutdown', ['removed', 'closing'])
async def test_late_frame_after_platform_removal_cannot_recreate_state(hass, home_context, shutdown):
    from asyncio import Event
    from custom_components.freebox_homexa.camera import FreeboxCamera
    router, node = home_context
    node = {**node, 'category': 'camera'}
    router.home_devices[node['id']] = node
    entry = hass.config_entries.async_get_entry(router.entry_id)
    entity = FreeboxCamera(hass, router, node)
    platform = platform_for(hass, entry, 'camera')
    started, release = Event(), Event()
    async def frame(self, width=None, height=None):
        started.set()
        await release.wait()
        return b'late-frame'
    try:
        await platform.async_add_entities([entity])
        with patch('homeassistant.components.ffmpeg.camera.FFmpegCamera.async_camera_image', frame):
            task = hass.async_create_task(entity.async_camera_image())
            await started.wait()
            if shutdown == 'removed':
                await platform.async_reset()
            else:
                router.closing = True
            previous = hass.states.get(entity.entity_id)
            release.set()
            assert await task == b'late-frame'
            await hass.async_block_till_done()
            assert hass.states.get(entity.entity_id) is previous
            assert entity.extra_state_attributes['video_available'] is None
    finally:
        release.set()
        await platform.async_reset()
