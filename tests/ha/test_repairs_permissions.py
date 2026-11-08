"""Native issue registry and actual SDK denial/recovery, never real I/O."""
from unittest.mock import AsyncMock, Mock

import pytest
from freebox_api.api.home import Home
from freebox_api.exceptions import InsufficientPermissionsError
from homeassistant.helpers import issue_registry as ir
from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.repairs import home_permission_issue_id
from test_home_platforms import home_context


async def test_actionable_home_denial_preserves_ignore_until_proven_recovery(hass, home_context):
    router, node = home_context
    transport = Mock(get=AsyncMock(side_effect=InsufficientPermissionsError('SYNTHETIC secret')), post=AsyncMock(), put=AsyncMock())
    router._api.home = Home(transport)
    registry = ir.async_get(hass)
    issue_id = home_permission_issue_id(router.entry_id)
    await router.update_home_devices()
    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None and issue.translation_key == 'home_permissions'
    assert issue.is_persistent and not issue.is_fixable
    assert not router.home_granted
    assert issue.translation_placeholders is None and issue.data is None
    registry.async_ignore(DOMAIN, issue_id, True)
    ignored = registry.async_get_issue(DOMAIN, issue_id)
    # A transient error on retry is NOT recovery and does not clear the ignored issue.
    router.home_granted = True
    transport.get.side_effect = TimeoutError()
    await router.update_home_devices()
    assert registry.async_get_issue(DOMAIN, issue_id) == ignored
    router.home_granted = True
    transport.get.side_effect = InsufficientPermissionsError('SYNTHETIC secret')
    await router.update_home_devices()
    assert registry.async_get_issue(DOMAIN, issue_id).dismissed_version == ignored.dismissed_version
    router.home_granted = True
    transport.get.side_effect = None
    transport.get.return_value = [node]
    await router.update_home_devices()
    assert registry.async_get_issue(DOMAIN, issue_id) is None
    transport.post.assert_not_called()
    transport.put.assert_not_called()


@pytest.mark.parametrize('failure', [TimeoutError(), ValueError('synthetic invalid response')])
async def test_transient_home_outage_is_not_a_repair(hass, home_context, failure):
    router, _ = home_context
    router._api.home = Home(Mock(get=AsyncMock(side_effect=failure)))
    await router.update_home_devices()
    assert ir.async_get(hass).async_get_issue(DOMAIN, home_permission_issue_id(router.entry_id)) is None
    assert router.home_granted


@pytest.mark.parametrize('language,word', [('fr', 'Accès Home'), ('en', 'Home access')])
async def test_native_issue_translations_are_consumed(hass, home_context, language, word):
    from homeassistant.helpers.translation import async_get_translations
    translations = await async_get_translations(hass, language, 'issues', {DOMAIN})
    prefix = f'component.{DOMAIN}.issues.home_permissions'
    assert word in translations[f'{prefix}.title']
    description = translations[f'{prefix}.description']
    assert 'Freebox OS' in description and 'Homexa' in description
    assert ('Rechargez' in description) if language == 'fr' else ('reload' in description)
