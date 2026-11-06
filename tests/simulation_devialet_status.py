"""Tests hors HA du vrai async_update, avec dépendances HA minimales.

Fixture : extrait réduit du payload Devialet de D-Kalck (post 10), sans
MAC, UID, IP, URL de flux ni horodatages personnels :
https://community.jeedom.com/t/petit-soucis-depuis-mis-a-jour-01-01-2024/118286/10
Les variantes pause/arrêt/format plat sont des cas de test synthétiques,
pas des captures supplémentaires d'un appareil.
Lancer : python3 -B tests/simulation_devialet_status.py
"""
import asyncio
from copy import deepcopy
from enum import IntFlag, StrEnum, auto
import importlib.util
import json
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


class State(StrEnum):
    OFF = 'off'
    ON = 'on'
    IDLE = 'idle'
    PLAYING = 'playing'
    PAUSED = 'paused'


class Feature(IntFlag):
    VOLUME_SET = auto()
    VOLUME_MUTE = auto()
    VOLUME_STEP = auto()
    PLAY = auto()
    PAUSE = auto()
    STOP = auto()
    NEXT_TRACK = auto()
    PREVIOUS_TRACK = auto()
    TURN_ON = auto()
    TURN_OFF = auto()
    SELECT_SOURCE = auto()
    PLAY_MEDIA = auto()


module('homeassistant')
module('homeassistant.components')
module('homeassistant.components.media_player', MediaPlayerDeviceClass=types.SimpleNamespace(TV='tv'),
       MediaPlayerEntity=type('Entity', (), {}), MediaPlayerEntityFeature=Feature, MediaPlayerState=State)
module('homeassistant.config_entries', ConfigEntry=object)
module('homeassistant.core', HomeAssistant=object)
module('homeassistant.helpers')
module('homeassistant.helpers.device_registry', DeviceInfo=dict)
module('homeassistant.helpers.entity_platform', AddEntitiesCallback=object)
pkg = module('freebox_homexa')
pkg.__path__ = [str(ROOT / 'custom_components/freebox_homexa')]
module('freebox_homexa.const', DOMAIN='freebox_homexa', option_remote_code=lambda *a: None)
module('freebox_homexa.availability', FreeboxReachableMixin=type('Mixin', (), {}))
module('freebox_homexa.player_remote', async_schedule_player_api_retry=AsyncMock(), filter_ready_players=lambda *a: [])
module('freebox_homexa.router', FreeboxConfigEntry=object, FreeboxRouter=object)
# Stub guide TNT : l'artwork est testé à part ; ici on contrôle le retour.
_artwork = {'url': None}

def _stub_tnt_artwork_url(hass, *, channel_name=None, channel_number=None):
    return _artwork['url']

module('freebox_homexa.tv_guide', tnt_artwork_url=_stub_tnt_artwork_url)
spec = importlib.util.spec_from_file_location('freebox_homexa.media_player', ROOT / 'custom_components/freebox_homexa/media_player.py')
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)
FIXTURE = json.loads((ROOT / 'tests/fixtures/devialet_tv_status.json').read_text())


async def run():
    access = types.SimpleNamespace(get=AsyncMock())
    router = types.SimpleNamespace(mac='00:00:00:00:00:00', player_identifiers=set(),
                                   _api=types.SimpleNamespace(player=types.SimpleNamespace(_access=access)))
    entity = mp.FreeboxPlayerMediaPlayer(router, {'id':17, 'device_model':'fbx7hd-delta', 'api_version':'11.0'}, object())
    entity.hass = object()  # suffisant pour déclencher le lookup artwork

    async def update(status):
        async def get(path):
            return deepcopy(status) if path.endswith('status/') else {'volume':30, 'mute':False}
        access.get.side_effect = get
        await entity.async_update()

    await update(FIXTURE)
    assert entity._attr_state == State.PLAYING
    assert entity._attr_media_title == entity._attr_media_channel == 'M6'
    assert entity.extra_state_attributes['channel_number'] == 6
    assert entity._attr_source == 'TV'
    assert router.player_diagnostic_schemas[17]['outcome'] == 'received'
    assert entity._attr_volume_level == .3
    access.get.assert_any_await('player/17/api/v11/status/')

    paused = deepcopy(FIXTURE)
    paused['player']['state']['playback_state'] = 'paused'
    await update(paused)
    assert entity._attr_state == State.PAUSED

    # Flat format remains preferred, even when nested data is also present.
    flat = {**FIXTURE, 'playback_state':'paused', 'title':'Titre plat', 'uri':'tv:?channel=8', 'volume':45}
    await update(flat)
    assert entity._attr_state == State.PAUSED and entity._attr_media_title == 'Titre plat'
    assert entity._attr_volume_level == .45
    revolution = {'power_state':'running', 'foreground_app':{'package':'fr.freebox.tv', 'cur_url':'tv://?channel=8'},
                  'player':{'state':{'playback_state':'playing'}}}
    await update(revolution)
    assert entity._attr_state == State.PLAYING and entity._attr_source == 'TV'
    assert entity._attr_media_title is None and entity._attr_media_channel is None
    assert entity.extra_state_attributes['channel_number'] is None

    for status in ({}, {'power_state':'running'}, {'foreground_app':None, 'player':None},
                   {'foreground_app':{'context':{'channel':[]}}, 'player':{'state':[]}, 'cur_info':[]}):
        await update(status)
        assert entity._attr_media_title is None and entity._attr_media_channel is None
        assert entity._attr_source is None and entity.extra_state_attributes['channel_number'] is None

    for power in ('standby', 'off', 'stopped'):
        await update({**FIXTURE, 'power_state':power})
        assert entity._attr_state == State.OFF
        assert entity._attr_media_title is None and entity._attr_media_channel is None
        assert entity._attr_source is None and entity.extra_state_attributes['channel_number'] is None

    await update({'power_state':'running', 'foreground_app':{'package':'com.netflix.mediaplayer'}})
    assert entity._attr_source == 'Netflix' and entity._attr_media_title == 'Netflix'
    assert entity._attr_media_image_url == 'https://upload.wikimedia.org/wikipedia/commons/f/ff/Netflix-new-icon.png'
    assert entity._attr_icon == 'mdi:netflix'
    # YouTube sans métadonnées : repli UX, pas un titre de vidéo inventé.
    await update({'power_state':'running', 'foreground_app':{'package':'com.google.android.youtube.tv'}})
    assert entity._attr_source == 'YouTube' and entity._attr_media_title == 'YouTube'
    assert entity._attr_media_image_url == 'https://brands.home-assistant.io/youtube/icon.png'
    await update({'power_state':'running', 'foreground_app':{'cur_url':'https://www.youtube.com/watch?v=abc'}})
    assert entity._attr_source == 'YouTube' and entity._attr_media_title == 'YouTube'
    # Un vrai titre reste prioritaire sur le repli d'application.
    await update({'power_state':'running', 'title':'Vidéo réelle',
                 'foreground_app':{'package':'com.google.android.youtube.tv'}})
    assert entity._attr_source == 'YouTube' and entity._attr_media_title == 'Vidéo réelle'
    # Chaîne TV non écrasée par un package YouTube fantôme.
    await update({**FIXTURE, 'foreground_app':{
        'package':'fr.freebox.tv',
        'context':{'channel':{'channelName':'BFM TV', 'channelNumber':15}}}})
    assert entity._attr_source == 'TV' and entity._attr_media_title == 'BFM TV'
    assert entity._attr_media_channel == 'BFM TV'
    # Sans données TNT (stub None) : pas d'image inventée.
    assert getattr(entity, '_attr_media_image_url', None) is None
    _artwork['url'] = 'https://image.tmdb.org/t/p/w500/bfm-poster.jpg'
    await update({**FIXTURE, 'foreground_app':{
        'package':'fr.freebox.tv',
        'context':{'channel':{'channelName':'BFM TV', 'channelNumber':15}}}})
    assert entity._attr_media_image_url == 'https://image.tmdb.org/t/p/w500/bfm-poster.jpg'
    # YouTube/Netflix : logos publics officiels (pas de miniature vidéo inventée).
    await update({'power_state':'running', 'foreground_app':{'package':'com.google.android.youtube.tv'}})
    assert entity._attr_source == 'YouTube'
    assert entity._attr_media_image_url == 'https://brands.home-assistant.io/youtube/icon.png'
    assert entity._attr_icon == 'mdi:youtube'
    await update({'power_state':'running', 'foreground_app':{'package':'com.netflix.mediaplayer'}})
    assert entity._attr_source == 'Netflix'
    assert entity._attr_media_image_url == 'https://upload.wikimedia.org/wikipedia/commons/f/ff/Netflix-new-icon.png'
    assert entity._attr_icon == 'mdi:netflix'
    # BFM + TNT reste prioritaire sur les icônes app.
    await update({**FIXTURE, 'foreground_app':{
        'package':'fr.freebox.tv',
        'context':{'channel':{'channelName':'BFM TV', 'channelNumber':15}}}})
    assert entity._attr_media_image_url == 'https://image.tmdb.org/t/p/w500/bfm-poster.jpg'
    assert entity._attr_icon is None
    # Veille : image effacée.
    _artwork['url'] = 'https://image.tmdb.org/t/p/w500/bfm-poster.jpg'
    await update({**FIXTURE, 'foreground_app':{
        'package':'fr.freebox.tv',
        'context':{'channel':{'channelName':'BFM TV', 'channelNumber':15}}}})
    assert entity._attr_media_image_url
    await update({'power_state':'standby'})
    assert entity._attr_state == State.OFF and entity._attr_media_image_url is None
    assert entity._attr_icon is None
    _artwork['url'] = None
    # URLs artwork app alignées sur les constantes du module.
    assert mp.APP_ARTWORK_URLS['YouTube'] == 'https://brands.home-assistant.io/youtube/icon.png'
    assert mp.APP_ARTWORK_URLS['Netflix'] == 'https://upload.wikimedia.org/wikipedia/commons/f/ff/Netflix-new-icon.png'
    # Après YouTube, l'arrêt efface le repli.
    await update({'power_state':'running', 'foreground_app':{'package':'fr.freebox.youtube'}})
    assert entity._attr_media_title == 'YouTube'
    await update({'power_state':'standby', 'foreground_app':{'package':'fr.freebox.youtube'}})
    assert entity._attr_state == State.OFF and entity._attr_media_title is None
    await update({'title':'Titre existant', 'playback_state':'playing'})
    assert entity._attr_media_title == 'Titre existant' and entity._attr_state == State.PLAYING
    await update({'cur_info':{'title':'Autre titre'}, 'power_state':'running'})
    assert entity._attr_media_title == 'Autre titre'
    await update({'power_state':'standby'})
    assert entity._attr_state == State.OFF and entity._attr_media_title is None

    access.get.side_effect = RuntimeError('offline')
    await entity.async_update()  # API failure must not raise.
    assert router.player_diagnostic_schemas[17]['outcome'] == 'unavailable'
    assert router.player_diagnostic_schemas[17]['timing_samples'] == []
    print('OK : Devialet TV, pause, plat, YouTube/Netflix repli UX, artwork TNT, BFM prioritaire, arrêt, erreur API')


asyncio.run(run())
