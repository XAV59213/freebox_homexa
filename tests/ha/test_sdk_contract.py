"""Installed public SDK contract; synthetic transports, no network or token file."""
import inspect
from unittest.mock import AsyncMock, Mock, patch

import pytest
from freebox_api.aiofreepybox import Freepybox
from freebox_api.access import Access


def test_current_sdk_network_interface_is_async():
    for kind, methods in [(Freepybox, ['open', 'close', 'get_permissions']),
                           (Access, ['get', 'post', 'put', 'delete', 'get_permissions'])]:
        for name in methods:
            assert inspect.iscoroutinefunction(getattr(kind, name)), (kind, name)


def test_sdk_has_no_public_session_injection_parameter():
    assert not {'session', 'websession', 'web_session', 'client_session'} & set(inspect.signature(Freepybox).parameters)


async def test_sdk_131_public_close_cannot_finish_after_failed_open():
    """Known upstream limitation, NOT a successful cleanup guarantee."""
    api = Freepybox({'app_id': 'test', 'app_name': 'test', 'app_version': 'test', 'device_name': 'test'}, 'unused-synthetic-file')
    session = Mock(close=AsyncMock())
    with patch.object(api, '_create_ssl_context', return_value=Mock()), \
         patch('freebox_api.aiofreepybox.TCPConnector'), \
         patch('freebox_api.aiofreepybox.ClientSession', return_value=session), \
         patch.object(api, '_get_freebox_access', new=AsyncMock(side_effect=TimeoutError('synthetic failure'))):
        with pytest.raises(TimeoutError):
            await api.open('freebox.test', 80)
        with pytest.raises(AttributeError, match='_access'):
            await api.close()
    session.close.assert_not_awaited()
