"""Real HA + installed SDK transport mocks: legacy identities and sandbox contract."""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from freebox_api.api.home import Home
from homeassistant.components.camera.const import CameraEntityFeature
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryHider

from test_home_platforms import home_context, make_platform
from custom_components.freebox_homexa.base_class import FreeboxBaseClass
from custom_components.freebox_homexa.camera import FreeboxCamera
from custom_components.freebox_homexa.const import DUMMY, DOMAIN, VALUE_NOT_SET
from custom_components.freebox_homexa.sensor import FreeboxDiskSensor


@pytest.mark.parametrize('category,inherit,model,manufacturer', [
    ('pir', '', 'F-HAPIR01A', 'Free SAS'), ('camera', '', 'F-HACAM01A', 'Free SAS'),
    ('dws', '', 'F-HADWS01A', 'Free SAS'), ('kfb', '', 'F-HAKFB01A', 'Free SAS'),
    ('alarm', '', 'F-MSEC07A', 'Free SAS'), ('other', 'node::rts', 'RTS', 'Somfy'),
    ('other', 'node::ios', 'IOcontrol', 'Somfy'), ('other', '', '', 'Free SAS'),
])
async def test_legacy_module_import_and_identity_contract(hass, home_context, category, inherit, model, manufacturer):
    router, _ = home_context
    node = {'id': 42, 'label': '  Legacy  ', 'category': category,
            'type': {'inherit': inherit}, 'props': {'FwVersion': '1.0'}}
    entity = FreeboxBaseClass(hass, router, node)
    assert DUMMY is False  # historical source default, not invented by a test stub
    assert entity._unique_id == router.mac + '-node_42'
    info = entity.device_info
    assert info['identifiers'] == {(DOMAIN, '42')}
    assert info['model'] == model and info['manufacturer'] == manufacturer
    assert info['name'] == 'Legacy'
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(config_entry_id=router.entry_id, **info)
    registry.async_update_device(device.id, name_by_user='My legacy device')
    again = registry.async_get_or_create(config_entry_id=router.entry_id, **entity.device_info)
    assert again.id == device.id and again.name_by_user == 'My legacy device'
    assert registry.async_get_device_by_identifier((DOMAIN, '42'), router.entry_id) is again
    entity._is_device = False
    assert entity.device_info is None


@pytest.mark.parametrize('dummy,node_id,skip', [(False, 42, False), (False, 1001, False),
                                               (True, 42, False), (True, 1001, True)])
async def test_legacy_dummy_and_exact_public_sdk_payload(hass, home_context, dummy, node_id, skip):
    router, _ = home_context
    transport = Mock(get=AsyncMock(return_value={'value': 7}), put=AsyncMock())
    router._api.home = Home(transport)
    entity = FreeboxBaseClass(hass, router, {'id': node_id, 'label': 'Legacy', 'category': 'pir'},
                             {'label': 'Sub', 'name': 'endpoint'})
    assert entity._unique_id == f'{router.mac}-node_{node_id}-endpoint'
    payload = {'value': None}
    with patch('custom_components.freebox_homexa.base_class.DUMMY', dummy):
        assert await entity.set_home_endpoint_value(3, payload) is True
        assert await entity.get_home_endpoint_value(3) == (VALUE_NOT_SET if skip else 7)
        assert await entity.set_home_endpoint_value(VALUE_NOT_SET, payload) is skip
        assert await entity.get_home_endpoint_value(VALUE_NOT_SET) == VALUE_NOT_SET
    if skip:
        transport.get.assert_not_awaited()
        transport.put.assert_not_awaited()
    else:
        transport.put.assert_awaited_once_with(f'home/endpoints/{node_id}/3', payload)
        assert transport.put.await_args.args[1] is payload
        transport.get.assert_awaited_once_with(f'home/endpoints/{node_id}/3')
    endpoints = [{'id': 3, 'name': 'state', 'ep_type': 'signal', 'value': 7}]
    assert entity.get_command_id(endpoints, 'signal', 'state') == 3
    assert entity.get_node_value(endpoints, 'signal', 'state') == 7
    assert entity.get_command_id(endpoints, 'slot', 'absent') == VALUE_NOT_SET
    assert entity.get_node_value(endpoints, 'slot', 'absent') == VALUE_NOT_SET


@pytest.mark.parametrize('reply,expected', [({}, VALUE_NOT_SET), ({'value': None}, None)])
async def test_legacy_missing_endpoint_value_preserved(hass, home_context, reply, expected):
    router, _ = home_context
    router._api.home = Home(Mock(get=AsyncMock(return_value=reply)))
    entity = FreeboxBaseClass(hass, router, {'id': 42, 'label': 'Legacy', 'category': 'pir'})
    assert await entity.get_home_endpoint_value(3) == expected


async def test_legacy_invalid_endpoint_envelope_fails_without_state_invention(hass, home_context):
    router, _ = home_context
    router._api.home = Home(Mock(get=AsyncMock(return_value=[])))
    entity = FreeboxBaseClass(hass, router, {'id': 42, 'label': 'Legacy', 'category': 'pir'})
    with pytest.raises(ValueError, match='Invalid Home endpoint response'):
        await entity.get_home_endpoint_value(3)


async def test_camera_delegate_preserves_native_registry_identity_and_user_choices(hass, home_context):
    router, node = home_context
    node = {**node, 'category': 'camera'}
    registry = er.async_get(hass)
    platform = make_platform(hass, 'camera')
    entry = hass.config_entries.async_get_entry(router.entry_id)
    platform.config_entry = entry
    hass.config_entries.async_update_entry(entry, options={'remote_codes': {'saved': 'synthetic'}, 'legacy_preference': True})
    saved_options = dict(entry.options)
    devices = dr.async_get(hass)
    original_device = None
    entity_id = None
    try:
        for reload_number in range(2):
            camera = FreeboxCamera(hass, router, node)
            assert camera.name is None
            assert camera.supported_features == CameraEntityFeature.STREAM
            assert camera.unique_id == f'{router.mac}-node_42'
            await platform.async_add_entities([camera])
            await hass.async_block_till_done()
            row = registry.async_get(camera.entity_id)
            if reload_number == 0:
                entity_id = camera.entity_id
                original_device = row.device_id
                assert original_device is not None
                assert devices.async_get(original_device).identifiers == {(DOMAIN, 42)}
                devices.async_update_device(original_device, name_by_user='My camera device')
                registry.async_update_entity(entity_id, name='My camera', icon='mdi:shield-home',
                                             hidden_by=RegistryEntryHider.USER)
            else:
                assert camera.entity_id == entity_id and row.device_id == original_device
                assert row.name == 'My camera' and row.icon == 'mdi:shield-home'
                assert row.hidden_by is RegistryEntryHider.USER
                assert devices.async_get(row.device_id).name_by_user == 'My camera device'
            assert entry.options == saved_options
            assert camera._ffmpeg.name == node['label'].strip()
            assert len([r for r in registry.entities.values() if r.platform == DOMAIN]) == 1
            await platform.async_reset()
    finally:
        await platform.async_reset()
    router._api.home.set_home_endpoint_value.assert_not_called()


async def test_disk_native_registry_keeps_integer_and_user_name(hass, home_context):
    router, _ = home_context
    disk = {'id': 7, 'model': 'Synthetic disk'}
    partition = {'id': 2, 'label': 'Saved partition'}
    registry = dr.async_get(hass)
    legacy = registry.async_get_or_create(
        config_entry_id=router.entry_id, identifiers={(DOMAIN, 7)}, name='Disque 7',
    )
    registry.async_update_device(legacy.id, name_by_user='My disk')
    entity = FreeboxDiskSensor(router, disk, partition, SensorEntityDescription(key='free'))
    again = registry.async_get_or_create(config_entry_id=router.entry_id, **entity.device_info)
    assert entity.unique_id == f'{router.mac} free 7 2'
    assert legacy.id == again.id and again.name_by_user == 'My disk'
    assert again.identifiers == {(DOMAIN, '7')}


@pytest.mark.parametrize('disk,partition', [({'id': '7', 'model': 'Disk'}, {'id': 2, 'label': 'P'}),
    ({'id': 7, 'model': 'Disk'}, {'id': '2', 'label': 'P'}),
    ({'id': 7, 'model': 42}, {'id': 2, 'label': 'P'})])
async def test_invalid_disk_contract_does_not_coerce_identity(hass, home_context, disk, partition):
    router, _ = home_context
    with pytest.raises(ValueError, match='Invalid SDK disk'):
        FreeboxDiskSensor(router, disk, partition, SensorEntityDescription(key='free'))


async def test_restored_legacy_constructor_does_not_log_node_credentials(hass, home_context, caplog):
    import logging
    router, _ = home_context
    with caplog.at_level(logging.DEBUG, logger='custom_components.freebox_homexa.base_class'):
        FreeboxBaseClass(hass, router, {'id': 42, 'label': 'Synthetic private label', 'category': 'camera',
            'props': {'FwVersion': '1.0', 'Pass': 'SYNTHETIC_PRIVATE_PASSWORD',
                      'Stream': 'rtsp://test:SYNTHETIC_PRIVATE_PASSWORD@camera.test/live'}})
    assert 'SYNTHETIC_PRIVATE_PASSWORD' not in caplog.text
    assert 'rtsp://' not in caplog.text
    assert 'Synthetic private label' not in caplog.text
    created = FreeboxBaseClass(hass, router, {'id': 42, 'label': 'Synthetic', 'category': 'camera', 'props': {}})
    assert created.device_info is not None
    assert created.device_info['identifiers'] == {(DOMAIN, '42')}
