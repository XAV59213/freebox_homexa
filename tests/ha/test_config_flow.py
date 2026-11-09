"""Config flow through HA's real flow manager, with the Freebox network mocked."""
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = 'freebox_homexa'
HOST = 'freebox.test'
MAC = '00:00:00:00:00:01'
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


async def finish_recovered_flow(hass, api, result):
    """After an asserted link error, fix its cause and complete that same HA flow."""
    api.open.side_effect = None
    api.system.get_config.side_effect = None
    api.player.get_players.side_effect = None
    with patch("custom_components.freebox_homexa.config_flow.get_api", return_value=api), \
         patch("custom_components.freebox_homexa.config_flow.get_hosts_list_if_supported", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.config_flow.Store.async_save", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "lan_options"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MAC
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
        assert result['result'].unique_id == MAC
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
    await finish_recovered_flow(hass, api, result)

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
    await finish_recovered_flow(hass, api, result)

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
    assert entry.unique_id == MAC
    assert entry.data['host'] == HOST
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
    await finish_recovered_flow(hass, api, result)

from types import SimpleNamespace
from homeassistant.config_entries import SOURCE_ZEROCONF, SOURCE_RECONFIGURE


async def test_discovery_suggests_host_and_duplicate_aborts(hass, api):
    info = SimpleNamespace(properties={'api_domain': 'freebox.test', 'https_port': '443'}, host='local.test', port=80)
    api.open.side_effect = TimeoutError()
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api), \
         patch('custom_components.freebox_homexa.config_flow.Store.async_load', return_value=None):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_ZEROCONF}, data=info)
    assert result['step_id'] == 'user'
    defaults = result['data_schema']({})
    assert defaults['host'] == 'freebox.test'
    assert defaults['port'] == 443
    hass.config_entries.flow.async_abort(result['flow_id'])
    entry = MockConfigEntry(domain=DOMAIN, unique_id='freebox.test', data={'host': 'freebox.test'},
                            options={'home_poll_interval': 15})
    entry.add_to_hass(hass)
    api.open.side_effect = None
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_ZEROCONF}, data=info)
    assert result['type'] == FlowResultType.ABORT
    assert result['reason'] == 'already_configured'
    assert entry.unique_id == MAC
    assert entry.data['host'] == 'freebox.test'
    assert entry.options['home_poll_interval'] == 15


async def test_discovery_updates_address_of_known_freebox(hass, api):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=MAC,
        data={'host': 'old.test', 'port': 80, 'remote_code': 'synthetic'},
        options={'home_poll_interval': 15},
    )
    entry.add_to_hass(hass)
    info = SimpleNamespace(properties={'api_domain': 'new.freebox.test', 'https_port': '80'}, host='192.0.2.10', port=80)
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api), \
         patch('custom_components.freebox_homexa.async_setup_entry', return_value=True):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_ZEROCONF}, data=info)
        await hass.async_block_till_done()
    assert result['type'] == FlowResultType.ABORT
    assert result['reason'] == 'already_configured'
    assert entry.unique_id == MAC
    assert entry.data['host'] == 'new.freebox.test'
    assert entry.data['remote_code'] == 'synthetic'
    assert entry.options['home_poll_interval'] == 15


async def test_reauth_rejects_a_different_freebox(hass, api):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data={'host': HOST, 'port': 80, 'remote_code': 'synthetic'})
    entry.add_to_hass(hass)
    api.system.get_config.return_value = {'mac': 'aa:bb:cc:dd:ee:ff'}
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={
            'source': SOURCE_REAUTH, 'entry_id': entry.entry_id,
        }, data=entry.data)
        result = await hass.config_entries.flow.async_configure(result['flow_id'], {})
    assert result['type'] == FlowResultType.ABORT
    assert result['reason'] == 'wrong_account'
    assert entry.unique_id == MAC
    assert entry.data['remote_code'] == 'synthetic'
    assert entry.data['host'] == HOST


async def test_reconfigure_rejects_a_different_freebox(hass, api):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MAC, data={'host': HOST, 'port': 80, 'remote_code': 'synthetic'})
    entry.add_to_hass(hass)
    api.system.get_config.return_value = {'mac': '00:00:00:00:00:02'}
    with patch('custom_components.freebox_homexa.config_flow.get_api', return_value=api):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_RECONFIGURE, 'entry_id': entry.entry_id})
        assert result['step_id'] == 'reconfigure'
        result = await hass.config_entries.flow.async_configure(result['flow_id'], {'host': 'new.test', 'port': 80})
    assert result['type'] == FlowResultType.ABORT
    assert result['reason'] == 'wrong_account'
    assert entry.data['host'] == HOST
    assert entry.data['remote_code'] == 'synthetic'
    assert entry.unique_id == MAC
    api.close.assert_awaited()


@pytest.mark.parametrize("cannot_unlink", [False, True])
async def test_invalid_token_cleanup_only_synthetic_file(hass, api, tmp_path, cannot_unlink):
    from unittest.mock import Mock
    token = tmp_path / "synthetic-token.json"
    token.write_text("synthetic test data, not a credential")
    path = Mock()
    path.unlink.side_effect = PermissionError("synthetic") if cannot_unlink else lambda **kw: token.unlink(**kw)
    api.open.side_effect = InvalidTokenError("synthetic invalid")
    with patch("custom_components.freebox_homexa.config_flow.get_api", return_value=api), \
         patch("custom_components.freebox_homexa.config_flow.resolve_token_file", return_value=path):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "invalid_token"}
    assert token.exists() == cannot_unlink
    path.unlink.assert_called_once_with(missing_ok=True)
    api.close.assert_awaited_once()
    await finish_recovered_flow(hass, api, result)

async def test_optional_player_failure_and_unknown_probe_error(hass, api):
    api.player.get_players.side_effect = TimeoutError
    with patch("custom_components.freebox_homexa.config_flow.get_api", return_value=api), \
         patch("custom_components.freebox_homexa.config_flow.get_hosts_list_if_supported", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.config_flow.Store.async_save", new=AsyncMock()):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "lan_options"
        hass.config_entries.flow.async_abort(result["flow_id"])
        api.system.get_config.side_effect = ValueError("synthetic invalid response")
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["errors"] == {"base": "unknown"}
    assert not hass.config_entries.async_entries(DOMAIN)
    assert api.close.await_count == 2
    await finish_recovered_flow(hass, api, result)

async def test_initial_codes_and_player_without_id(hass, api):
    api.player.get_players.return_value = [{"name": "Unavailable"}, {"id": 1, "name": "Test"}]
    with patch("custom_components.freebox_homexa.config_flow.get_api", return_value=api), \
         patch("custom_components.freebox_homexa.config_flow.get_hosts_list_if_supported", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.config_flow.Store.async_save", new=AsyncMock()), \
         patch("custom_components.freebox_homexa.async_setup_entry", return_value=True):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "remote_code": " synthetic-shared ", "remote_code_1": " synthetic-player "})
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MAC
    assert result["data"]["remote_code"] == "synthetic-shared"
    assert result["options"]["remote_codes"] == {"1": "synthetic-player"}


async def test_reconfigure_same_freebox_updates_port_and_adopts_mac(hass, api):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=HOST, data={"host": HOST, "port": 80, "remote_code": "synthetic"},
                            options={"home_poll_interval": 20})
    entry.add_to_hass(hass)
    with patch("custom_components.freebox_homexa.config_flow.get_api", return_value=api), \
         patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)) as reload:
        result = await hass.config_entries.flow.async_init(DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST, "port": 443})
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == MAC
    assert entry.data["port"] == 443
    assert entry.data["host"] == HOST
    assert entry.data["remote_code"] == "synthetic"
    assert entry.options["home_poll_interval"] == 20
    reload.assert_awaited_once_with(entry.entry_id)


async def test_reconfigure_rejects_existing_duplicate_identity_without_mutation(hass):
    """Legacy/restored duplicate entries are a real manager input, not a mocked step."""
    first = MockConfigEntry(domain=DOMAIN, unique_id='freebox.test',
        data={'host': 'freebox.test', 'port': 80}, options={'home_poll_interval': 20})
    duplicate = MockConfigEntry(domain=DOMAIN, unique_id='freebox.test',
        data={'host': 'freebox.test', 'port': 81}, options={'home_poll_interval': 30})
    first.add_to_hass(hass)
    duplicate.add_to_hass(hass)
    before = [(entry.entry_id, entry.unique_id, dict(entry.data), dict(entry.options)) for entry in (first, duplicate)]
    with patch('custom_components.freebox_homexa.config_flow.get_api', new_callable=AsyncMock) as get_api, \
         patch.object(hass.config_entries, 'async_reload', new_callable=AsyncMock) as reload:
        result = await hass.config_entries.flow.async_init(DOMAIN,
            context={'source': 'reconfigure', 'entry_id': first.entry_id})
        result = await hass.config_entries.flow.async_configure(result['flow_id'],
            {'host': 'freebox.test', 'port': 80})
        assert result['type'] == FlowResultType.ABORT
        assert result['reason'] == 'already_configured'
        assert [(entry.entry_id, entry.unique_id, dict(entry.data), dict(entry.options)) for entry in (first, duplicate)] == before
        get_api.assert_not_called()
        reload.assert_not_called()
