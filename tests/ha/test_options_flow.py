"""Options through HA's manager, preserving unrelated settings and reload once."""
from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = 'freebox_homexa'


async def test_general_options_preserve_other_pages(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test', 'port': 80},
                            options={'tnt_channels': ['TF1'], 'reminder_profiles': []})
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)) as reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result['type'] == FlowResultType.MENU
        assert 'general' in result['menu_options']
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': 'general'})
        assert result['step_id'] == 'general'
        result = await hass.config_entries.options.async_configure(result['flow_id'], {})
        await hass.async_block_till_done()
        assert result['type'] == FlowResultType.CREATE_ENTRY
        assert entry.options['tnt_channels'] == ['TF1']
        assert entry.options['reminder_profiles'] == []
        reload.assert_awaited_once_with(entry.entry_id)


async def test_empty_groups_abort_without_mutation(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test'})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': 'groups'})
    assert result['type'] == FlowResultType.ABORT
    assert result['reason'] == 'no_devices'
    assert not entry.options


async def test_profiles_add_edit_remove_validation_and_preserve_other_options(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test'},
                            options={'tnt_channels': ['TF1.fr'], 'reminder_profiles': [{'name': 'Existing'}]})
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)) as reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': 'profiles'})
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'action': 'add'})
        for name, expected in [(' ', 'no_name'), ('Existing', 'duplicate_name')]:
            result = await hass.config_entries.options.async_configure(result['flow_id'], {'name': name})
            assert result['errors'] == {'base': expected}
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'name': 'New', 'announce_volume': 0.5})
        assert result['step_id'] == 'profiles'
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'action': 'edit:New'})
        assert result['step_id'] == 'add_profile'
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'name': 'Renamed', 'announce_volume': 0.25})
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'action': 'remove:Renamed'})
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'action': 'done'})
        await hass.async_block_till_done()
        assert result['type'] == FlowResultType.CREATE_ENTRY
        assert entry.options['tnt_channels'] == ['TF1.fr']
        assert entry.options['reminder_profiles'] == [{'name': 'Existing'}]
        reload.assert_not_awaited()  # Final options unchanged: HA avoids a needless reload.


async def test_tnt_options_empty_refused_then_preserves_other_options(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test'}, options={'home_poll_interval': 20})
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': 'tnt'})
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'tnt_channels_france': [], 'tnt_channels_belgique': []})
        assert result['errors'] == {'base': 'no_channels'}
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'tnt_channels_france': ['TF1.fr'], 'tnt_channels_belgique': []})
        await hass.async_block_till_done()
        assert result['type'] == FlowResultType.CREATE_ENTRY
        assert entry.options['tnt_channels'] == ['TF1.fr']
        assert entry.options['home_poll_interval'] == 20


from types import SimpleNamespace
import pytest


@pytest.mark.parametrize('page,attribute,option', [
    ('groups', 'grouped_devices', 'device_group_overrides'),
    ('types', 'lan_client_types', 'device_type_overrides'),
])
async def test_device_classification_pages_keep_other_options(hass, page, attribute, option):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test'}, options={'home_poll_interval': 20})
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(**{attribute: {'test-client': ('Test client', '')}}, repeater_names=lambda: {})
    with patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': page})
        assert result['step_id'] == page
        label = next(iter(result['data_schema'].schema)).schema
        result = await hass.config_entries.options.async_configure(result['flow_id'], {label: 'auto'})
        await hass.async_block_till_done()
        assert result['type'] == FlowResultType.CREATE_ENTRY
        assert entry.options[option] == {}
        assert entry.options['home_poll_interval'] == 20


@pytest.mark.parametrize('players', [[], [{'id': 1, 'name': 'Test Player'}], None])
async def test_general_preserves_codes_for_players_not_listed(hass, players):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test'}, options={
        'remote_codes': {'2': 'synthetic-test-code'}, 'remote_code_2': 'synthetic-test-code',
        'tnt_channels': ['TF1.fr'],
    })
    entry.add_to_hass(hass)
    api = AsyncMock()
    api.player.get_players.return_value = players
    if players is None:
        api.player.get_players.side_effect = TimeoutError('synthetic offline')
    entry.runtime_data = SimpleNamespace(_api=api)
    with patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': 'general'})
        result = await hass.config_entries.options.async_configure(result['flow_id'], {})
        await hass.async_block_till_done()
    assert entry.options['remote_codes']['2'] == 'synthetic-test-code'
    assert entry.options['remote_code_2'] == 'synthetic-test-code'
    assert entry.options['tnt_channels'] == ['TF1.fr']


async def test_general_can_explicitly_clear_visible_player_code(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test'}, options={
        'remote_codes': {'2': 'synthetic-test-code'}, 'remote_code_2': 'synthetic-test-code',
    })
    entry.add_to_hass(hass)
    api = AsyncMock()
    api.player.get_players.return_value = [{'id': 2, 'name': 'Test Player'}]
    entry.runtime_data = SimpleNamespace(_api=api)
    with patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': 'general'})
        await hass.config_entries.options.async_configure(result['flow_id'], {'remote_code_2': ''})
        await hass.async_block_till_done()
    assert entry.options['remote_codes'] == {}
    assert 'remote_code_2' not in entry.options


async def test_repeater_page_empty_aborts_without_changes(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={"home_poll_interval": 20})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "repeaters"})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_devices"
    assert entry.options == {"home_poll_interval": 20}


async def test_repeater_page_validates_registry_choices_and_preserves_options(hass):
    from homeassistant.helpers import device_registry as dr
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={"home_poll_interval": 20})
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    duplicate, target = "00:00:00:00:00:11", "00:00:00:00:00:12"
    for index, mac in enumerate((duplicate, target)):
        registry.async_get_or_create(config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"repeater_{mac}")}, name=f"Test repeater {index}")
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)) as reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "repeaters"})
        assert result["step_id"] == "repeaters"
        for data in ({"duplicate": duplicate}, {"duplicate": duplicate, "target": duplicate}):
            result = await hass.config_entries.options.async_configure(result["flow_id"], data)
            assert result["errors"] == {"base": "repeater_same"}
            assert entry.options == {"home_poll_interval": 20}
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"duplicate": duplicate, "target": target})
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.options["home_poll_interval"] == 20
        assert entry.options["repeater_merges"] == {duplicate: target}
        reload.assert_awaited_once_with(entry.entry_id)


async def test_repeater_page_clear_retains_other_settings(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={
        "home_poll_interval": 20, "repeater_merges": {"00:00:00:00:00:11": "00:00:00:00:00:12"}})
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "repeaters"})
        assert result["step_id"] == "repeaters"
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"clear": True})
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {"home_poll_interval": 20, "repeater_merges": {}}


@pytest.mark.parametrize("other_platform", ["test", "alexa_media"])
async def test_profile_conflict_then_distinct_targets_and_edit_defaults(hass, other_platform):
    from homeassistant.helpers import entity_registry as er
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={"home_poll_interval": 20})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    echo = registry.async_get_or_create("media_player", "alexa_media", "test-echo", suggested_object_id="test_echo")
    other = registry.async_get_or_create("media_player", other_platform, "test-other", suggested_object_id="test_other")
    slug = "alexa_media_" + echo.entity_id.split(".", 1)[1]
    notify = AsyncMock()
    hass.services.async_register("notify", slug, notify)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "profiles"})
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"action": "add"})
        data = {"name": "Test profile", "notify_target": [slug],
            "media_player_targets": [echo.entity_id], "tts_engine": "tts.test_engine"}
        result = await hass.config_entries.options.async_configure(result["flow_id"], data)
        assert result["errors"] == {"base": "device_conflict"}
        assert "reminder_profiles" not in entry.options
        data["media_player_targets"] = [other.entity_id]
        result = await hass.config_entries.options.async_configure(result["flow_id"], data)
        assert result["step_id"] == "profiles"
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"action": "edit:Test profile"})
        assert result["step_id"] == "add_profile"
        assert result["data_schema"]({"name": "Test profile"})["notify_target"] == [slug]
        result = await hass.config_entries.options.async_configure(result["flow_id"], data)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"action": "done"})
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["home_poll_interval"] == 20
    assert entry.options["reminder_profiles"][0]["media_player_targets"] == [other.entity_id]
    notify.assert_not_called()


@pytest.mark.parametrize("invalid", [None, "invalid", 999])
async def test_invalid_stored_poll_interval_uses_default_without_mutation(hass, invalid):
    from custom_components.freebox_homexa.const import DEFAULT_HOME_POLL_INTERVAL
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={"home_poll_interval": invalid})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "general"})
    assert result["data_schema"]({})["home_poll_interval"] == DEFAULT_HOME_POLL_INTERVAL
    assert entry.options["home_poll_interval"] == invalid


@pytest.mark.parametrize("page,attribute,option", [
    ("groups", "grouped_devices", "device_group_overrides"),
    ("types", "lan_client_types", "device_type_overrides"),
])
async def test_duplicate_labels_and_absent_overrides_keep_stable_keys(hass, page, attribute, option):
    from custom_components.freebox_homexa.device_groups import group_choices, type_choices
    choices = group_choices() if page == "groups" else type_choices()
    selected = next(choice for choice in choices if choice != "auto")
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={
        "home_poll_interval": 20, option: {"absent": selected}})
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(**{attribute: {"client1": ("Repeated", ""), "client2": ("Repeated", "")}}, repeater_names=lambda: {})
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": page})
        labels = [marker.schema for marker in result["data_schema"].schema]
        assert len(set(labels)) == 3
        result = await hass.config_entries.options.async_configure(result["flow_id"], {label: selected for label in labels})
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[option] == {"absent": selected, "client1": selected, "client2": selected}
    assert entry.options["home_poll_interval"] == 20


async def test_types_empty_aborts(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "types"})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_devices"


async def test_general_shared_code_and_tnt_key_defaults_preserve_private_settings(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={
        "remote_code": "synthetic-shared", "tnt_tmdb_api_key": "synthetic-key", "tnt_channels": ["TF1.fr"]})
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "general"})
        assert result["data_schema"]({})["remote_code"] == "synthetic-shared"
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data["remote_code"] == "synthetic-shared"
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "tnt"})
        assert result["data_schema"]({})["tnt_tmdb_api_key"] == "synthetic-key"
        hass.config_entries.options.async_abort(result["flow_id"])
    assert entry.options["tnt_tmdb_api_key"] == "synthetic-key"


async def test_profile_edit_retains_unknown_metadata_and_other_profiles(hass):
    original = {"name": "Saved", "announce_volume": 0.4,
                "future_setting": {"stable_id": "unchanged", "history": ["old"]}}
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={
        "reminder_profiles": [original, {"name": "Other", "legacy_preference": True}],
        "home_poll_interval": 20, "remote_codes": {"player1": "synthetic"}})
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "profiles"})
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"action": "edit:Saved"})
        assert entry.options["reminder_profiles"][0] == original
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"name": "Saved", "announce_volume": 0.6})
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"action": "done"})
        await hass.async_block_till_done()
    assert entry.options["reminder_profiles"] == [{**original, "announce_volume": 0.6},
        {"name": "Other", "legacy_preference": True}]
    assert entry.options["remote_codes"] == {"player1": "synthetic"}
    assert entry.options["home_poll_interval"] == 20


@pytest.mark.parametrize("profiles", [{"not": "a list"}, [42], [{"name": 42}], [{"name": "Saved", 42: "bad key"}]])
async def test_invalid_saved_profiles_fail_closed_without_erasing_preferences(hass, profiles):
    import voluptuous as vol
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"}, options={
        "reminder_profiles": profiles, "remote_codes": {"player1": "synthetic"}})
    entry.add_to_hass(hass)
    before = dict(entry.options)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(vol.Invalid, match="Invalid saved reminder profile"):
        await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "profiles"})
    assert entry.options == before


async def test_profile_selector_rejects_malformed_input_then_recovers_via_native_manager(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={'host': 'freebox.test'}, options={'home_poll_interval': 20})
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'next_step_id': 'profiles'})
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'action': 'add'})
        from homeassistant.data_entry_flow import InvalidData
        with pytest.raises(InvalidData, match='notify_target'):
            await hass.config_entries.options.async_configure(result['flow_id'], {'name': 'New', 'notify_target': 42})
        assert entry.options == {'home_poll_interval': 20}
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'name': 'New', 'notify_target': []})
        assert result['step_id'] == 'profiles'
        result = await hass.config_entries.options.async_configure(result['flow_id'], {'action': 'done'})
        await hass.async_block_till_done()
        assert result['type'] == FlowResultType.CREATE_ENTRY
    assert entry.options == {'home_poll_interval': 20, 'reminder_profiles': [{'name': 'New'}]}
