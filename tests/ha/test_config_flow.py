"""Config flow through HA's real flow manager, with the Freebox network mocked."""
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = 'freebox_homexa'
HOST = 'freebox.test'
pytestmark = pytest.mark.usefixtures('enable_custom')


@pytest.fixture
def api():
    api = AsyncMock()
    api.system.get_config.return_value = {'mac': '00:00:00:00:00:01'}
    api.player.get_players.return_value = []
    return api


async def start(hass):
    with patch('custom_components.freebox_homexa.config_flow.Store.async_load', return_value=None):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_USER})
    assert result['type'] == FlowResultType.FORM
    assert result['step_id'] == 'user'
    result = await hass.config_entries.flow.async_configure(result['flow_id'], {'host': HOST, 'port': 80})
    assert result['step_id'] == 'link'
    return result


async def test_success(hass, api):
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api), \
         patch('custom_components.freebox_homexa.config_flow.get_hosts_list_if_supported', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.config_flow.Store.async_save', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.async_setup_entry', return_value=True):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result['flow_id'], {})
        assert result['step_id'] == 'lan_options'
        api.close.assert_awaited_once()
        result = await hass.config_entries.flow.async_configure(result['flow_id'], {})
        assert result['type'] == FlowResultType.CREATE_ENTRY
        assert result['data']['host'] == HOST
        await hass.async_block_till_done()


@pytest.mark.parametrize('error', [TimeoutError(), aiohttp.ClientError(), OSError()])
async def test_network_failure_closes_and_no_entry(hass, api, error):
    api.open.side_effect = error
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result['flow_id'], {})
    assert result['errors'] == {'base': 'cannot_connect'}
    assert not hass.config_entries.async_entries(DOMAIN)
    api.close.assert_awaited_once()


async def test_duplicate_host(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=HOST, data={'host': HOST, 'port': 80})
    entry.add_to_hass(hass)
    with patch('custom_components.freebox_homexa.config_flow.Store.async_load', return_value=None):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result['flow_id'], {'host': HOST, 'port': 80})
    assert result['type'] == FlowResultType.ABORT
    assert result['reason'] == 'already_configured'


from freebox_api.exceptions import AuthorizationError, InvalidTokenError, InsufficientPermissionsError
from homeassistant.config_entries import SOURCE_REAUTH


@pytest.mark.parametrize('error,expected,cleanup', [
    (AuthorizationError('denied'), 'invalid_token', True),
    (AuthorizationError('timed out'), 'register_failed', False),
    (InvalidTokenError('invalid'), 'invalid_token', True),
    (InsufficientPermissionsError('denied'), 'cannot_connect', False),
])
async def test_auth_failure_no_entry(hass, api, error, expected, cleanup):
    api.open.side_effect = error
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api), \
         patch('custom_components.freebox_homexa.config_flow.FreeboxFlowHandler._cleanup_invalid_token', new=AsyncMock()) as clean:
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result['flow_id'], {})
    assert result['errors'] == {'base': expected}
    assert clean.await_count == int(cleanup)
    assert not hass.config_entries.async_entries(DOMAIN)
    api.close.assert_awaited_once()


async def test_reauth_success_reloads_existing_entry(hass, api):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=HOST, data={'host': HOST, 'port': 80})
    entry.add_to_hass(hass)
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api), \
         patch('custom_components.freebox_homexa.config_flow.get_hosts_list_if_supported', new=AsyncMock()), \
         patch('custom_components.freebox_homexa.config_flow.Store.async_save', new=AsyncMock()), \
         patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)) as reload:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={
            'source': SOURCE_REAUTH, 'entry_id': entry.entry_id,
        }, data=entry.data)
        assert result['step_id'] == 'reauth_confirm'
        result = await hass.config_entries.flow.async_configure(result['flow_id'], {})
        await hass.async_block_till_done()
        assert result['type'] == FlowResultType.ABORT
        assert result['reason'] == 'reauth_successful'
        reload.assert_awaited_once_with(entry.entry_id)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    api.close.assert_awaited_once()


async def test_failed_probe_no_entry(hass, api):
    api.system.get_config.side_effect = TimeoutError()
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result['flow_id'], {})
    assert result['errors'] == {'base': 'cannot_connect'}
    assert not hass.config_entries.async_entries(DOMAIN)
    api.close.assert_awaited_once()


from types import SimpleNamespace
from homeassistant.config_entries import SOURCE_ZEROCONF, SOURCE_RECONFIGURE


async def test_discovery_suggests_host_and_duplicate_aborts(hass):
    info = SimpleNamespace(properties={'api_domain': 'freebox.test', 'https_port': '443'}, host='local.test', port=80)
    with patch('custom_components.freebox_homexa.config_flow.Store.async_load', return_value=None):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_ZEROCONF}, data=info)
    assert result['step_id'] == 'user'
    defaults = result['data_schema']({})
    assert defaults['host'] == 'freebox.test'
    assert defaults['port'] == 443
    hass.config_entries.flow.async_abort(result['flow_id'])
    entry = MockConfigEntry(domain=DOMAIN, unique_id='freebox.test', data={'host': 'freebox.test'})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_ZEROCONF}, data=info)
    assert result['type'] == FlowResultType.ABORT
    assert result['reason'] == 'already_configured'


async def test_characterize_reconfigure_identity_boundary_without_migration(hass):
    """Current host identity rejects a host change; not an endorsement of the limitation."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=HOST, data={'host': HOST, 'port': 80})
    entry.add_to_hass(hass)
    with patch('custom_components.freebox_homexa.config_flow.get_api') as api:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_RECONFIGURE, 'entry_id': entry.entry_id})
        assert result['step_id'] == 'reconfigure'
        result = await hass.config_entries.flow.async_configure(result['flow_id'], {'host': 'new.test', 'port': 80})
        assert result['type'] == FlowResultType.ABORT
        assert result['reason'] == 'wrong_account'
        assert entry.data['host'] == HOST
        api.assert_not_called()
