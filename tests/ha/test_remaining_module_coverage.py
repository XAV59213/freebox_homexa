"""Synthetic LAN, Wi-Fi, registry and TMDB cases for the four modules under 95% lines.

No live device, no network, no identity migration of an existing installation.
A MAC owned by another integration is not moved. A group that still has a
child or an entity is not removed.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from unittest.mock import AsyncMock, patch

import pytest
from freebox_api.exceptions import HttpRequestError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_homexa.const import DOMAIN
from custom_components.freebox_homexa.device_groups import (
    GROUP_AUTO,
    GROUP_CAMERAS,
    GROUP_LAN_WIFI,
    GROUP_LAN_WIRED,
    GROUP_PLAYER,
    LINK_REPEATER,
    LINK_WIFI,
    LINK_WIRED,
    NET_AMAZON,
    NET_CAMERAS,
    NET_COMPUTERS,
    NET_CONSOLES,
    NET_IOT,
    NET_MEDIA,
    NET_NETWORK,
    NET_OTHER,
    NET_PHONES,
    NET_PRINTERS,
    NET_SERVERS,
    NET_VIRTUAL,
    async_clean_repeater_connections,
    async_detach_top_level_devices,
    async_get_group_device,
    async_get_lan_group_device,
    async_get_lan_type_device,
    async_merge_repeater_devices,
    async_remove_lan_client_devices,
    async_remove_merged_node_devices,
    classify_lan_client,
    group_identifier,
    group_label,
    has_ethernet_evidence,
    has_wifi_evidence,
    home_node_name,
    is_network_client,
    is_server_client,
    is_server_name,
    is_specific_repeater_name,
    is_virtual_client,
    lan_client_link,
    lan_client_name,
    lan_client_type,
    link_group,
    migrate_group,
    migrate_overrides,
    migrate_repeater_merges,
    next_lan_link,
    repeater_registry_devices,
    suggested_area,
    to_service,
    ul_twin,
    user_names,
    _repeater_idents,
)
from custom_components.freebox_homexa.router import (
    extract_wifi_details,
    get_api,
    is_freebox_repeater,
    resolve_token_file,
)
from custom_components.freebox_homexa.tnt_coordinator import Programme
from custom_components.freebox_homexa.tnt_tmdb import (
    TMDB_SEARCH_MOVIE_URL,
    TMDB_SEARCH_TV_URL,
    TmdbResolver,
)
from custom_components.freebox_homexa.wifi_ap import (
    annotate_wifi_parents,
    build_wifi_aps,
    eui64_mac,
    gateway_wifi_state,
    group_repeater_macs,
    is_free_mac,
    normalize_mac,
    repeater_own_macs,
)
from test_home_platforms import home_context


def host(**kwargs):
    base = {"l2ident": {"id": "aa:bb:cc:dd:ee:10"}, "primary_name": "Appareil", "vendor_name": ""}
    base.update(kwargs)
    return base


def test_lan_classification_links_and_names():
    assert to_service("unknown-legacy") == "server"
    assert migrate_group("cameras") is None
    assert migrate_group("net_phones") == "server"
    assert migrate_group("media") == "player"
    cases = {
        "amazon": ({"vendor_name": "Amazon", "host_type": "multimedia_device", "primary_name": "Echo"}, NET_AMAZON),
        "phone": ({"host_type": "smartphone", "primary_name": "Pixel"}, NET_PHONES),
        "wled": ({"vendor_name": "Espressif", "primary_name": "wled-salon"}, NET_IOT),
        "apple-tv-name": ({"vendor_name": "Apple", "primary_name": "Apple TV Salon"}, NET_MEDIA),
        "samsung-tv": ({"vendor_name": "Samsung", "primary_name": "TV Salon"}, NET_MEDIA),
        "samsung-phone": ({"vendor_name": "Samsung", "primary_name": "Galaxy"}, NET_PHONES),
        "hikvision": ({"vendor_name": "Hikvision", "primary_name": "Cam"}, GROUP_CAMERAS),
        "echo-name": ({"vendor_name": "Unknown", "primary_name": "echo-dot"}, NET_AMAZON),
        "other": ({"vendor_name": "Acme", "primary_name": "Boite"}, NET_OTHER),
    }
    for name, (payload, expected) in cases.items():
        assert classify_lan_client(host(**payload)) == expected, name
    virtual = host(l2ident={"id": "52:54:00:11:22:33"}, primary_name="vm-guest")
    assert is_virtual_client(virtual) is True
    assert is_virtual_client(host(primary_name="docker-web")) is True
    assert is_virtual_client(host(primary_name="Telephone")) is False
    assert is_server_name(host(primary_name="nas1")) is True
    assert is_server_name(host(primary_name="srv02")) is True
    assert is_server_client(host(host_type="nas", primary_name="Boite")) is True
    assert is_server_client(host(vendor_name="Synology", primary_name="Boite")) is True
    assert is_network_client(host(host_type="networking_device", vendor_name="Cisco")) is True
    assert is_network_client(host(vendor_name="Ubiquiti", primary_name="AP")) is True
    assert is_network_client(host(primary_name="pfsense")) is True
    assert lan_client_type(host(primary_name="pve-host")) == NET_SERVERS
    assert lan_client_type(host(l2ident={"id": "BC:24:11:00:00:01"}, primary_name="ct-mail")) == NET_VIRTUAL
    assert lan_client_type(host(host_type="nas", primary_name="Stockage")) == NET_SERVERS
    assert lan_client_type(host(vendor_name="Cisco", host_type="networking_device", primary_name="Switch")) == NET_NETWORK
    assert lan_client_type(host(vendor_name="Realtek", primary_name="Tv chambre")) == NET_MEDIA
    assert lan_client_type(host(host_type="ip_camera", primary_name="Entree")) == NET_CAMERAS
    assert lan_client_type(host(host_type="freebox_player", primary_name="Salon")) == NET_MEDIA
    assert lan_client_type(host(host_type="printer", primary_name="Bureau")) == NET_PRINTERS
    assert lan_client_type(host(host_type="vg_console", primary_name="Jeux")) == NET_CONSOLES
    assert lan_client_type(host(host_type="laptop", primary_name="Travail")) == NET_COMPUTERS
    assert lan_client_type(host(vendor_name="Acme", primary_name="Boite")) == NET_OTHER
    assert lan_client_name(host(primary_name="wlan0", names=[{"name": "Bureau"}], default_name="Unknown")) == "Bureau"
    assert lan_client_name(host(primary_name="", vendor_name="Acme", l2ident={"id": "aa:bb:cc:dd:ee:1a"})).startswith("Acme")
    assert lan_client_name(host(primary_name="", vendor_name="", l2ident={"id": "aa:bb:cc:dd:ee:1b"})).startswith("Appareil")
    assert home_node_name({"label": "unknown device", "id": 3, "category": "kiz"}, "Prise") == "Prise 3"
    assert suggested_area("Volet du salon") == "Salon"
    assert suggested_area("Capteur de la grange") == "Grange"
    assert suggested_area("Volet roulant de la porte") is None
    assert suggested_area(None) is None
    assert is_specific_repeater_name("Repeteur Wifi Freebox Garage") is True
    assert is_specific_repeater_name("Repeteur Wifi Freebox") is False
    assert is_specific_repeater_name("#2") is False
    assert ul_twin("2066CF4B4969") == "2266CF4B4969"
    assert ul_twin("court") == ""
    assert ul_twin("ZZ66CF4B4969") == ""
    wired = host(access_point={"connectivity_type": "ethernet"})
    wifi = host(access_point={"connectivity_type": "wifi", "wifi_information": {"ssid": "free"}})
    repeater = host(access_point={"type": "repeater", "mac": "20:66:CF:4B:49:69"}, wifi={"connectivity": "wifi"})
    assert has_ethernet_evidence(wired) is True
    assert has_ethernet_evidence(host(access_point="bad")) is False
    assert has_wifi_evidence(wifi) is True
    assert has_wifi_evidence(host(wifi="nope")) is False
    assert has_wifi_evidence(host(_wifi_station={"signal": -40})) is True
    assert lan_client_link(host(wifi_parent={"kind": "repeater", "ap_id": "20:66:CF:4B:49:69"})) == f"{LINK_REPEATER}20:66:CF:4B:49:69"
    assert lan_client_link(host(wifi_parent={"kind": "gateway"})) == LINK_WIFI
    assert lan_client_link(wired) == LINK_WIRED
    assert lan_client_link(repeater, repeater_of=lambda mac: "20:66:CF:4B:49:69") == f"{LINK_REPEATER}20:66:CF:4B:49:69"
    assert lan_client_link(repeater) == LINK_WIFI
    assert lan_client_link(host(active=True)) == LINK_WIRED
    assert lan_client_link(host(active=False, access_point="bad")) is None
    assert link_group(LINK_WIRED) == GROUP_LAN_WIRED
    assert link_group(LINK_WIFI) == GROUP_LAN_WIFI
    assert link_group(f"{LINK_REPEATER}aa") == GROUP_LAN_WIFI
    assert link_group(None) is None
    assert next_lan_link("wifi", None, True, None) == ("wifi", None)
    assert next_lan_link(None, "wifi", True, None) == ("wifi", None)
    assert next_lan_link("wifi", "wired", False, None) == ("wifi", None)
    assert next_lan_link("wifi", "wired", True, None)[1] == ("wired", 1)
    assert next_lan_link("wifi", "wired", True, ("wired", 1)) == ("wired", None)
    assert group_label(None) == ""
    assert "Serveurs" in group_label("lan_wired_net_servers")
    assert "Grange" in group_label(f"{LINK_REPEATER}aa", {"aa": "Grange"})
    assert group_label("net_phones") == "Téléphones et tablettes"
    assert group_label("media") == "Freebox Player"


async def test_group_registry_keeps_children_and_merges_only_own_repeaters(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"})
    entry.add_to_hass(hass)
    mac = "00:00:00:00:00:21"
    devices = dr.async_get(hass)
    placeholder = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "placeholder")}, name="Tmp")
    home = async_get_group_device(hass, entry.entry_id, mac, "home")
    devices.async_update_device(home, name="Ancien", via_device_id=placeholder.id)
    again = async_get_group_device(hass, entry.entry_id, mac, "home")
    assert again == home
    assert devices.async_get(home).via_device_id is None
    server = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, mac)}, name="Server")
    wired = async_get_lan_group_device(hass, entry.entry_id, mac, GROUP_LAN_WIRED, server.id)
    renamed = async_get_lan_group_device(hass, entry.entry_id, mac, GROUP_LAN_WIRED, server.id)
    assert renamed == wired
    subtype = async_get_lan_type_device(hass, entry.entry_id, mac, GROUP_LAN_WIRED, NET_SERVERS, wired)
    assert devices.async_get(subtype).via_device_id == wired
    child = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "child")}, name="Enfant")
    devices.async_update_device(child.id, via_device_id=wired, name_by_user="Mon enfant")
    assert async_remove_merged_node_devices(hass, entry, {mac}) == 0
    player = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "player_9")}, name="Player", via_device_id=home,
    )
    devices.async_update_device(player.id, name_by_user="Mon player")
    async_detach_top_level_devices(hass, entry, [(DOMAIN, "player_9")])
    assert devices.async_get(player.id).via_device_id is None
    assert devices.async_get(player.id).name_by_user == "Mon player"
    assert devices.async_get(child.id).via_device_id == wired
    foreign = MockConfigEntry(domain="shelly", data={})
    foreign.add_to_hass(hass)
    shelly = devices.async_get_or_create(
        config_entry_id=foreign.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:77")},
        name="Shelly",
    )
    devices.async_update_device(shelly.id, name_by_user="Ma prise")
    exclusive = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:78")},
        name="Client",
    )
    removed = async_remove_lan_client_devices(hass, entry, mac)
    assert devices.async_get(shelly.id).name_by_user == "Ma prise"
    assert devices.async_get(exclusive.id) is None
    assert removed == 1
    canon = "20:66:CF:4B:49:69"
    keeper = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"repeater_{canon}")},
        connections={(dr.CONNECTION_NETWORK_MAC, canon)},
        name="Repeteur #2",
    )
    devices.async_update_device(keeper.id, name_by_user="Mon garage")
    duplicate = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "22:66:CF:4B:49:69")},
        name="Repeteur Wifi Freebox Garage",
    )
    registry = er.async_get(hass)
    registry.async_get_or_create("sensor", DOMAIN, f"{mac}_repeater_22:66:CF:4B:49:69", config_entry=entry, device_id=duplicate.id)
    moved = registry.async_get_or_create("sensor", DOMAIN, f"{mac}_kept_signal", config_entry=entry, device_id=duplicate.id)
    kid = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "rep-child")}, name="Fils")
    devices.async_update_device(kid.id, via_device_id=duplicate.id)
    count = async_merge_repeater_devices(
        hass, entry, mac,
        {canon: {"name": "Garage", "macs": [canon, "22:66:CF:4B:49:69"]}},
        rejected_macs=["4E:C4:E5:8E:62:A7"],
        lan_macs={"4E:C4:E5:8E:62:A7"},
    )
    assert count >= 1
    assert devices.async_get(keeper.id).name_by_user == "Mon garage"
    assert registry.async_get(moved.entity_id).device_id == keeper.id
    assert devices.async_get(kid.id).via_device_id == keeper.id
    stray = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "repeater_4EC4E58E62A7")},
        connections={(dr.CONNECTION_NETWORK_MAC, "4E:C4:E5:8E:62:A7")},
        name="Telephone",
    )
    async_merge_repeater_devices(
        hass, entry, mac, {canon: {"macs": [canon]}},
        rejected_macs=["4E:C4:E5:8E:62:A7"], lan_macs={"4E:C4:E5:8E:62:A7"},
    )
    assert (DOMAIN, "repeater_4EC4E58E62A7") not in devices.async_get(stray.id).identifiers
    random_phone = "02:11:22:33:44:55"
    devices.async_update_device(
        keeper.id,
        new_connections={
            (dr.CONNECTION_NETWORK_MAC, canon),
            (dr.CONNECTION_NETWORK_MAC, random_phone),
        },
    )
    changed = async_clean_repeater_connections(
        hass, entry.entry_id, mac, {canon: {"macs": [canon]}},
    )
    assert changed >= 1
    left = {c[1].upper() for c in devices.async_get(keeper.id).connections}
    assert random_phone not in left


def test_wifi_grouping_states_and_inventory():
    router = "00:07:CB:00:00:01"
    assert is_freebox_repeater(host(primary_name="Repeteur Wifi", l2ident={"id": "20:66:CF:4B:49:69"}), router) is True
    assert is_freebox_repeater(host(host_type="freebox_wifi", vendor_name="Free", l2ident={"id": "20:66:CF:00:00:02"}), router) is True
    assert is_freebox_repeater(host(l2ident={"id": router}), router) is False
    assert is_free_mac("2066CF4B4969") is True
    assert is_free_mac("2266CF4B4969") is True
    assert is_free_mac("short") is False
    assert is_free_mac("ZZ66CF4B4969") is False
    slaac = "fe80::2266:cfff:fe4b:4969"
    assert eui64_mac(slaac) == "2066CF4B4969"
    assert eui64_mac("not-an-ip") == ""
    assert eui64_mac("192.0.2.1") == ""
    assert eui64_mac("fe80::1") == ""
    main = "2066CF4B4969"
    twin = "2266CF4B4969"
    hosts = {
        main: host(primary_name="Repeteur Garage", l2ident={"id": "20:66:CF:4B:49:69"},
                   l3connectivities=[{"addr": "192.0.2.20"}, {"addr": slaac}]),
        twin: host(primary_name="Repeteur", l2ident={"id": "22:66:CF:4B:49:69"},
                   l3connectivities=[{"addr": "192.0.2.20"}]),
    }
    aliases, why = group_repeater_macs(
        hosts,
        {twin: "uid-garage", "2266CFC692D2": "uid-chambre"},
        [{"id": 2, "main_mac": "20:66:CF:4B:49:69", "backhaul": [{"mac": "8C:97:EA:55:BB:B6"}],
          "fronthaul": [{"bssid": "22:66:CF:4B:49:90"}]}],
        {"4EC4E58E62A7": "20:66:CF:4B:49:69"},
    )
    assert aliases[main] == aliases[twin]
    assert any(aliases.values())
    assert why
    random_host = {"DEADBEEF0001": host(primary_name="Repeteur bidon", l2ident={"id": "DE:AD:BE:EF:00:01"})}
    rejected_aliases, rejected_why = group_repeater_macs(random_host, {})
    assert rejected_aliases == {}
    assert rejected_why["_rejected"]
    online, state = gateway_wifi_state([{"id": 1, "state": "active"}], None, True, 0)
    assert (online, state) == (True, "active")
    assert gateway_wifi_state(None, None, False, 0) == (False, "disabled")
    assert gateway_wifi_state([{"state": "weird"}], None, True, 0) == (True, "enabled")
    assert gateway_wifi_state([{"state": "scanning"}], [{"state": "disabled"}], None, 0)[0] is False
    assert gateway_wifi_state(None, None, None, 2) == (True, "active")
    assert gateway_wifi_state(None, None, None, 0) == (None, "unknown")
    devices = {
        "aa:bb:cc:dd:ee:01": host(primary_name="Phone", active=True, l2ident={"id": "aa:bb:cc:dd:ee:01"},
                                  access_point={"type": "gateway", "connectivity_type": "wifi", "mac": router},
                                  wifi={"wifi_signal_dbm": -40, "wifi_ssid": "free"}),
        "20:66:CF:4B:49:69": host(primary_name="Repeteur Wifi Freebox Garage", l2ident={"id": "20:66:CF:4B:49:69"},
                                  vendor_name="Free"),
        "aa:bb:cc:dd:ee:02": host(primary_name="Switch", attrs={"x": 1}, l2ident={"id": "aa:bb:cc:dd:ee:02"}),
        "aa:bb:cc:dd:ee:03": host(primary_name="Fil", l2ident={"id": "aa:bb:cc:dd:ee:03"},
                                  access_point={"type": "gateway", "connectivity_type": "ethernet"}),
    }
    aps, repeaters = build_wifi_aps(
        router_mac=router, router_name="Freebox", router_model="server", devices=devices,
        radio_status=[{"id": 1, "state": "active"}], wifi_enabled=True,
        api_repeaters=[{"main_mac": "20:66:CF:4B:49:69", "name": "Garage", "backhaul": [], "fronthaul": []}],
    )
    assert aps["gateway"]["online"] is True
    assert any(repeaters.values()) or aps["gateway"]["client_count"] >= 1
    annotate_wifi_parents(devices, {"gateway": {"kind": "gateway", "id": "gateway", "name": "Wi-Fi", "clients": [{"mac": "aa:bb:cc:dd:ee:01"}, {"mac": ""}]}}, router)
    assert devices["aa:bb:cc:dd:ee:01"]["wifi_parent"]["kind"] == "gateway"
    own, extra = repeater_own_macs(main, [main, "4EC4E58E62A7"], hosts, None, set())
    assert main in own
    assert "4EC4E58E62A7" in extra


async def test_router_wifi_token_and_parent_edges(hass, home_context):
    router, _node = home_context
    assert is_freebox_repeater({"l2ident": {"id": ""}, "primary_name": "Repeteur"}, router.mac) is False
    assert is_freebox_repeater({"l2ident": {"id": "20:66:CF:00:00:09"}, "primary_name": "Repeteur", "vendor_name": "Free", "host_type": "freebox_wifi"}, router.mac) is True
    details = extract_wifi_details({
        "access_point": {"mac": "20:66:CF:00:00:01", "type": "repeater", "wifi_information": {
            "signal": "bad", "ssid": "free", "band": "5g", "bssid": "22:66:CF:00:00:01",
            "standard": "ax", "phy_rx_rate": 100, "phy_tx_rate": 80}},
        "_wifi_station": {"signal": -55, "_ap_name": "Garage"},
    })
    assert details["wifi_ssid"] == "free"
    assert details["ap_name"] == "Garage"
    assert "wifi_signal_dbm" not in details or isinstance(details.get("wifi_signal_dbm"), int)
    numeric = extract_wifi_details({"access_point": {"wifi_information": {"signal": "-48"}, "connectivity_type": "wifi"}})
    assert numeric["wifi_signal_dbm"] == -48
    token = get_api
    storage = hass.config.path(".storage")
    from pathlib import Path
    blocked = Path(storage) / "freebox_homexa"
    if blocked.exists():
        import shutil
        shutil.rmtree(blocked) if blocked.is_dir() else blocked.unlink()
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_text("not a directory", encoding="utf-8")
    api = await token(hass, "Freebox Test")
    assert api is not None
    token_file = Path(storage) / "freebox_homexa" / "freebox-test.conf"
    token_file.write_text('{"app_token": "synthetic", "app_id": "hass", "app_name": "Home Assistant", "device_name": "box"}', encoding="utf-8")
    reused = await token(hass, "Freebox Test")
    assert reused is not None
    empty = Path(storage) / "freebox_homexa" / "empty.conf"
    empty.write_text("{", encoding="utf-8")
    await token(hass, "empty")
    devices = dr.async_get(hass)
    entry = hass.config_entries.async_get_entry(router.entry_id)
    server = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, router.mac)}, name="Server")
    router.device_id = server.id
    router.group_overrides["disk:1"] = GROUP_LAN_WIFI
    parent = router.parent_for("disk:1", "Disque", "server")
    assert parent
    assert router.lan_link_parent_id(None) is None
    assert router.lan_link_parent_id("repeater:20:66:CF:4B:49:69")
    router.devices["aa:bb:cc:dd:ee:30"] = host(primary_name="Phone", l2ident={"id": "aa:bb:cc:dd:ee:30"})
    assert router.lan_client_type("aa:bb:cc:dd:ee:99", "Inconnu")
    router._api.wifi.get_global_config = AsyncMock(return_value={"enabled": True})
    router._api.wifi.get_bss = AsyncMock(return_value=[{"id": 1, "status": {"state": "active"}, "config": {"ssid": "free"}}, "skip"])
    router._api.wifi.get_ap_list = AsyncMock(return_value=[
        {"id": 1, "name": "Freebox", "status": {"state": "active"}},
        {"id": None, "status": "bad"},
        "skip",
    ])
    router._api.wifi.get_station_list = AsyncMock(side_effect=[
        [{"mac": "", "host": {"l2ident": {"id": "aa:bb:cc:dd:ee:30"}}, "signal": -40}],
        HttpRequestError("synthetic"),
    ])
    await router._fetch_wifi_global_state()
    await router._enrich_wifi_stations()
    assert router.wifi_global_enabled is True
    router._api.wifi.get_bss = AsyncMock(side_effect=RuntimeError("synthetic bss"))
    await router._fetch_wifi_global_state()
    router.closing = True
    router.update_device_trackers = AsyncMock(side_effect=RuntimeError("synthetic"))
    router.update_sensors = AsyncMock()
    await router.update_all(datetime.now(timezone.utc))
    router.closing = False
    router.reachable = False
    router.update_device_trackers = AsyncMock()
    await router.update_all(datetime.now(timezone.utc))
    assert router.reachable is True


async def test_tmdb_matching_and_mocked_search(hass):
    resolver = TmdbResolver(hass, "synthetic-key", AsyncMock())
    now = datetime.now(timezone.utc)
    soon = Programme(now, now + timedelta(hours=1), "Koh-Lanta *2024", None, None, "Serie", None, None, "2024")
    far = Programme(now + timedelta(days=5), now + timedelta(days=5, hours=1), "Magazine societe", None, None, "Magazine", None, None)
    movie = Programme(now, now + timedelta(hours=2), "Le Prenom, deuxieme partie", None, None, "Film", None, None, "2012")
    empty = Programme(now - timedelta(hours=2), now - timedelta(hours=1), "", None, None, None, None, None)
    assert resolver.key(soon)[0] == "Koh-Lanta *2024"
    resolver._tmdb_poster_cache[resolver.key(soon)] = None
    resolver._tmdb_failure_counts[("gone", None, None)] = 1
    resolver.prune([soon, empty])
    assert ("gone", None, None) not in resolver._tmdb_failure_counts
    cleaned = [
        resolver._clean_search_query(title)
        for title in (
            "Koh-Lanta - S29E01 *2024",
            "Serie saison 2",
            "Film - S01E02",
            "Quotidien - saison 3",
            "Emission S2",
            "Amour, gloire et beaute (9709) (n°9709)",
            "Cuisines des terroirs (La Macedoine) (n°311)",
            "Le bateau (version realisateur)",
            "Quotidien, deuxieme partie",
            "Deja propre",
        )
    ]
    assert any(year == "2024" for _title, year in cleaned)
    assert resolver._titles_match("koh lanta", "koh lanta") is True
    assert resolver._titles_match("koh lanta s29", "koh lanta") is True
    assert resolver._titles_match("lucifer", "luciferina") is False
    assert resolver._titles_match("meteo", "miss meteo") is False
    assert "coeur" in resolver._normalize_title("LIVE: La Villa des Cœurs Brisés")
    assert resolver._extract_year_from_xmltv_date("20241107") == "2024"
    assert resolver._extract_year_from_xmltv_date(None) is None
    assert resolver._extract_year_from_xmltv_date("nope") is None
    assert resolver._truncate_at_first_separator("Nomade des mers, les escales")
    assert resolver._truncate_at_first_separator("Amour") is None
    assert resolver._is_movie_category("Film") is True
    assert resolver._is_movie_category(None) is False
    assert resolver._is_non_fiction_category("Magazine de societe") is True
    assert resolver._is_non_fiction_category("Serie") is False

    class Response:
        def __init__(self, status, payload):
            self.status = status
            self.payload = payload
        async def json(self):
            return self.payload
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return False

    class Session:
        def __init__(self, routes):
            self.routes = list(routes)
            self.calls = []
        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params))
            status, payload = self.routes.pop(0)
            return Response(status, payload)

    poster = {"results": [
        {"name": "Autre", "poster_path": "/low.jpg", "vote_count": 1, "vote_average": 2, "id": 1},
        {"name": "Koh-Lanta", "poster_path": "/high.jpg", "vote_count": 50, "vote_average": 7.5, "id": 9},
        {"title": "Luciferina", "original_title": "Koh-Lanta", "poster_path": "/orig.jpg", "vote_count": 3, "id": 3},
    ]}
    session = Session([(200, poster), (200, {"results": []}), (401, {}), (429, {}), (500, {}), (404, {})])
    resolver._session = session
    match = await resolver._tmdb_search(TMDB_SEARCH_TV_URL, "Koh-Lanta", "2024")
    assert match.poster == "/high.jpg"
    assert match.votes == 50
    none = await resolver._tmdb_search(TMDB_SEARCH_MOVIE_URL, "Inconnu", "2012")
    assert none is None
    with pytest.raises(Exception):
        await resolver._tmdb_search(TMDB_SEARCH_TV_URL, "Auth", None)
    with pytest.raises(Exception):
        await resolver._tmdb_search(TMDB_SEARCH_TV_URL, "Rate", None)
    with pytest.raises(Exception):
        await resolver._tmdb_search(TMDB_SEARCH_TV_URL, "Server", None)
    assert await resolver._tmdb_search(TMDB_SEARCH_TV_URL, "Missing", None) is None
    year_params = [params for url, params in session.calls if params and params.get("first_air_date_year")]
    assert year_params

    class Repeat:
        def __init__(self):
            self.calls = []
        def get(self, url, params=None, timeout=None):
            self.calls.append(url)
            payload = {"results": [{"title": params["query"], "name": params["query"], "poster_path": "/p.jpg", "vote_count": 4, "vote_average": 6, "id": 8}]}
            if params["query"] in {"C a vous", "Inconnu"}:
                payload = {"results": []}
            return Response(200, payload)
    resolver._session = Repeat()
    film = await resolver._lookup_tmdb_poster("Le Prenom, deuxieme partie", "Film", "20121107")
    magazine = await resolver._lookup_tmdb_poster("C a vous", "Magazine", None)
    plain = await resolver._lookup_tmdb_poster("Deja propre", None, None)
    failed = TmdbResolver(hass, "synthetic-key", AsyncMock())
    class Boom:
        def get(self, url, params=None, timeout=None):
            raise RuntimeError("synthetic tmdb")
    failed._session = Boom()
    await failed._resolve_tmdb_posters({("Rate limite", "Serie", None): None})
    resolver.schedule([soon, far, movie, empty, None], now)
    await hass.async_block_till_done()
    assert film and film.poster.startswith("http")
    assert magazine is None
    assert plain and plain.poster.startswith("http")
    assert failed._tmdb_failure_counts


def test_repeater_grouping_edges_and_unknown_wifi_state():
    """Jumeaux, BSSID, EUI-64 et refus de fusionner deux répéteurs qui ont chacun une MAC principale."""
    router = "00:07:CB:00:00:01"
    assert is_freebox_repeater(
        host(primary_name="Telephone", host_type="smartphone", vendor_name="Samsung", l2ident={"id": "AA:BB:CC:DD:EE:01"}),
        router,
    ) is False
    assert eui64_mac("gggg::1") == ""
    assert classify_lan_client(host(vendor_name="Samsung", primary_name="QE65", host_type="")) == NET_PHONES
    assert user_names(host(primary_name="Samsung", vendor_name="Samsung")) == ""
    assert has_wifi_evidence(host(access_point={"wifi_information": {"ssid": "free"}})) is True
    assert lan_client_name(host(primary_name="wlan0", names=[{"name": "unknown"}], default_name="Serveur salon")) == "Serveur salon"
    assert home_node_name({"label": "Volet cuisine", "id": 3}, None) == "Volet cuisine"
    assert is_specific_repeater_name("unknown") is False
    assert migrate_group(GROUP_AUTO) is None
    assert migrate_group(None) is None
    assert migrate_overrides({"aa": GROUP_AUTO, "bb": "net_phones", "cc": "n'existe pas"}) == {"bb": "server"}
    assert migrate_repeater_merges("nope") == {}
    assert migrate_repeater_merges({"2266CF4B4969": "2066CF4B4969"})["22:66:CF:4B:49:69"] == "20:66:CF:4B:49:69"
    class _Odd:
        identifiers = ["pas-un-tuple", (DOMAIN, 12), (DOMAIN, "repeater_2066CF4B4969")]
    assert _repeater_idents(_Odd()) == ["repeater_2066CF4B4969"]

    garage = "2066CF111111"
    garage_twin = "2266CF111111"
    cave = "2066CF222222"
    cave_twin = "2266CF222222"
    other_main = "2066CF333333"
    # Le jumeau de la cave partage l'IP d'un AUTRE répéteur : la fusion automatique est refusée.
    hosts = {
        garage: host(primary_name="Repeteur Wifi Freebox Garage", l2ident={"id": "20:66:CF:11:11:11"},
                     l3connectivities=[{"addr": "fe80::2266:cfff:fe11:1111"}, {"addr": "2001:db8::2266:cfff:fe11:1111"}]),
        garage_twin: host(primary_name="Repeteur", l2ident={"id": "22:66:CF:11:11:11"}),
        cave: host(primary_name="Repeteur Wifi Freebox Cave", l2ident={"id": "20:66:CF:22:22:22"}),
        cave_twin: host(primary_name="Repeteur", l2ident={"id": "22:66:CF:22:22:22"},
                        l3connectivities=[{"addr": "192.0.2.50"}]),
        other_main: host(primary_name="Repeteur Wifi Freebox Chambre", l2ident={"id": "20:66:CF:33:33:33"},
                         l3connectivities=[{"addr": "192.0.2.50"}]),
    }
    aliases, why = group_repeater_macs(
        hosts,
        {garage_twin: "uid-garage", "2266CF9999BB": "uid-garage", "8C97EA0000AA": "uid-partage", "8C97EA0000BB": "uid-partage"},
        [
            {"id": 1},
            {"id": 2, "main_mac": "20:66:CF:11:11:11", "fronthaul": [{"bssid": "22:66:CF:99:99:BB"}]},
        ],
    )
    assert aliases[garage] == aliases[garage_twin]
    # Le jumeau a déjà été réuni par IP à un autre répéteur : on ne fusionne pas les deux MAC principales.
    assert aliases[cave] != aliases[other_main]
    assert aliases[cave_twin] == aliases[other_main]
    assert why
    own, extra = repeater_own_macs("DEADBEEF0001", ["4EC4E58E62A7"], {}, None, set())
    assert own == ["DEADBEEF0001"]
    assert extra == ["4EC4E58E62A7"]
    states = gateway_wifi_state(["pas-un-etat", {"id": 1, "state": "exotic-radio"}], None, True, 0)
    assert states[0] is True
    missing = {}
    annotate_wifi_parents(
        missing,
        {"gateway": {"kind": "gateway", "clients": [{"mac": "aa:bb:cc:dd:ee:99"}]}},
        router,
    )
    assert missing == {}
    devices = {
        "20:66:CF:11:11:11": host(primary_name="Repeteur Wifi Freebox Garage", l2ident={"id": "20:66:CF:11:11:11"}, vendor_name="Free"),
        "aa:bb:cc:dd:ee:01": host(
            primary_name="Telephone", active=True, l2ident={"id": "aa:bb:cc:dd:ee:01"},
            access_point={"type": "repeater", "mac": "4E:C4:E5:8E:62:A7", "connectivity_type": "wifi"},
        ),
    }
    _aps, repeaters = build_wifi_aps(
        router_mac=router, router_name="Freebox", router_model="server", devices=devices,
        api_repeaters=[{"main_mac": "20:66:CF:11:11:11", "name": "Garage"}],
        manual_links={"4E:C4:E5:8E:62:A7": "20:66:CF:11:11:11"},
    )
    payload = next(iter(repeaters.values()))
    # Lien manuel : la MAC choisie reste une MAC du répéteur, le client Wi-Fi est compté à part.
    assert "4E:C4:E5:8E:62:A7" in payload["macs"]
    assert payload["client_count"] == 1
    assert payload["name"] == "Garage"


async def test_repeater_registry_keeps_names_and_drops_only_duplicates(hass):
    """Fusion : nom choisi conservé, entité d'alias retirée, jumeau sans identifiant Homexa supprimé."""
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "freebox.test"})
    entry.add_to_hass(hass)
    router_mac = "00:07:CB:AA:00:21"
    canon = "20:66:CF:4B:49:69"
    twin = "22:66:CF:4B:49:69"
    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    keeper = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"repeater_{canon}")},
        connections={(dr.CONNECTION_NETWORK_MAC, canon)},
        name="Repeteur #2",
    )
    named = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "repeater_22:66:CF:55:55:55")},
        name="Doublon",
    )
    devices.async_update_device(named.id, name_by_user="Mon cellier")
    alias = registry.async_get_or_create(
        "sensor", DOMAIN, f"{router_mac}_wifi_clients_{twin}", config_entry=entry, device_id=keeper.id,
    )
    bssid = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "repeater_22:66:CF:C6:92:D4")},
        name="Interface",
    )
    orphan = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "node-absent")}, name="Ancien noeud",
    )
    registry.async_get_or_create("sensor", DOMAIN, "node-absent-temp", config_entry=entry, device_id=orphan.id)
    assert async_remove_merged_node_devices(hass, entry, {"inconnu", "node-absent"}) == 0
    assert devices.async_get(orphan.id) is not None
    box = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, router_mac)},
        name="Freebox",
    )
    merged = async_merge_repeater_devices(
        hass, entry, router_mac,
        {
            canon: {"name": "Repeteur #3", "macs": [canon, twin, "22:66:CF:C6:92:D2"]},
            "20:66:CF:55:55:55": {"macs": ["20:66:CF:55:55:55"]},
            "20:66:CF:00:00:99": {"macs": ["20:66:CF:00:00:99"]},
        },
    )
    assert merged >= 1
    assert devices.async_get(named.id).name_by_user == "Mon cellier"
    assert registry.async_get(alias.entity_id) is None
    assert devices.async_get(bssid.id) is None or (DOMAIN, "repeater_22:66:CF:C6:92:D4") not in devices.async_get(bssid.id).identifiers
    stored_router = next(c[1] for c in devices.async_get(box.id).connections)
    removed = async_remove_lan_client_devices(hass, entry, stored_router)
    assert devices.async_get(box.id) is not None
    assert removed == 0
    twin_only = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, twin)},
        name="Jumeau",
    )
    signal = registry.async_get_or_create("sensor", DOMAIN, f"{router_mac}_twin_signal", config_entry=entry, device_id=twin_only.id)
    child = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "enfant-jumeau")}, name="Enfant")
    devices.async_update_device(child.id, via_device_id=twin_only.id)
    zigbee = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("zigbee", "aa")},
        name="Zigbee",
    )
    mixed = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "8C:97:EA:00:00:01"), (dr.CONNECTION_NETWORK_MAC, "02:00:00:00:00:01")},
        name="Melange",
    )
    stranger = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "02:00:00:00:00:02")},
        name="Inconnu",
    )
    changed = async_clean_repeater_connections(
        hass, entry.entry_id, router_mac, {canon: {"macs": [canon, twin, "8C:97:EA:00:00:01"]}},
    )
    assert changed >= 1
    assert registry.async_get(signal.entity_id).device_id == keeper.id
    assert devices.async_get(child.id).via_device_id == keeper.id
    assert devices.async_get(twin_only.id) is None
    assert devices.async_get(zigbee.id) is not None
    assert devices.async_get(mixed.id) is not None
    assert devices.async_get(stranger.id) is not None
    listed = repeater_registry_devices(hass, entry)
    assert any(item["name_by_user"] == "Mon cellier" for item in listed)


async def test_router_lan_clients_keep_foreign_macs_and_user_names(hass, home_context):
    """Parents filaire / répéteur, jeton local, et aucun déplacement d'une MAC étrangère."""
    router, _node = home_context
    devices = dr.async_get(hass)
    entry = hass.config_entries.async_get_entry(router.entry_id)
    server = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, router.mac)}, name="Server",
    )
    router.device_id = server.id
    storage = Path(hass.config.path(".storage"))
    blocked = storage / "freebox_homexa"
    if blocked.exists():
        shutil.rmtree(blocked) if blocked.is_dir() else blocked.unlink()
    backup = storage / "freebox_homexa.bak"
    if backup.exists():
        shutil.rmtree(backup) if backup.is_dir() else backup.unlink()
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_text("not a directory", encoding="utf-8")
    backup.mkdir()
    with pytest.raises(Exception):
        await get_api(hass, "boite")
    if blocked.exists():
        shutil.rmtree(blocked) if blocked.is_dir() else blocked.unlink()
    if backup.exists():
        shutil.rmtree(backup) if backup.is_dir() else backup.unlink()
    assert resolve_token_file(hass, "Freebox Test").name.endswith(".conf")
    token_file = resolve_token_file(hass, "Freebox Test")
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(
        '{"app_token": "synthetic-token", "app_id": "hass", "app_name": "Home Assistant", "app_version": "2026.10.4", "device_name": "box"}',
        encoding="utf-8",
    )
    described = await get_api(hass, "Freebox Test")
    assert described is not None
    bare = resolve_token_file(hass, "bare-token")
    bare.write_text('{"app_id": "hass"}', encoding="utf-8")
    await get_api(hass, "bare-token")

    canon = "20:66:CF:11:22:33"
    router.repeaters = {
        canon: {"name": "Cave", "macs": [canon], "ap_aliases": ["4E:C4:E5:8E:62:A7"], "serial": "SN-SYNTH", "model": "RP01"},
    }
    router.devices = {
        canon: host(primary_name="Repeteur Wifi Freebox Cave", vendor_name="Free", l2ident={"id": canon}),
    }
    router.api_repeaters = [{"main_mac": canon, "name": "Cave", "sn": "SN-SYNTH"}]
    router.repeater_merges = {}
    router.wifi_radio_status = []
    router.wifi_bss_status = []
    router.wifi_global_enabled = True
    info = router.repeater_device_info(canon, "Cave")
    assert info["serial_number"] == "SN-SYNTH"
    assert info["name"] == "Cave"
    router._refresh_repeaters()
    refreshed = next(iter(router.repeaters.values()))
    assert refreshed["serial"] == "SN-SYNTH"
    assert refreshed["name"] == "Cave"

    router._api.wifi.get_ap_list = AsyncMock(return_value=[
        {"id": 1, "name": "Freebox", "status": {"state": "active"}},
    ])
    router._api.wifi.get_station_list = AsyncMock(return_value=[{"mac": "", "host": {}, "signal": None}])
    await router._enrich_wifi_stations()
    assert router.via_device_id_for(router.mac) == router.device_id
    assert "repeater:" in (router._auto_value("repeater:20:66:CF:11:22:33", None) or "")
    assert router.repeater_names()

    rep = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"repeater_{canon}")},
        connections={(dr.CONNECTION_NETWORK_MAC, canon)},
        name="Cave",
    )
    devices.async_update_device(rep.id, name_by_user="Ma cave")
    parent = router.lan_link_parent_id(f"{LINK_REPEATER}{canon}")
    assert parent == rep.id
    assert router.lan_link_parent_id("inconnu") is None

    wired = router.group_device_id(GROUP_LAN_WIRED)
    phone = "aa:bb:cc:dd:ee:41"
    phone_dev = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, phone)},
        name="Telephone",
    )
    devices.async_update_device(phone_dev.id, via_device_id=wired, name_by_user="Mon telephone")
    router.devices[phone] = host(primary_name="Telephone", l2ident={"id": phone}, active=True,
                                  access_point={"connectivity_type": "ethernet"})
    assert router._link_from_registry(phone) == LINK_WIRED
    owned = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "player_edge")},
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:42")},
        name="Player",
    )
    devices.async_update_device(owned.id, via_device_id=wired, name_by_user="Mon player")
    assert router._link_from_registry("aa:bb:cc:dd:ee:42") is None
    subtype = router.lan_group_parent_id(GROUP_LAN_WIRED, NET_SERVERS)
    server_client = "aa:bb:cc:dd:ee:46"
    server_dev = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, server_client)},
        name="Nas",
    )
    devices.async_update_device(server_dev.id, via_device_id=subtype)
    router.devices[server_client] = host(primary_name="nas", l2ident={"id": server_client})
    assert router._link_from_registry(server_client) == LINK_WIRED
    wifi_phone = "aa:bb:cc:dd:ee:47"
    wifi_dev = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, wifi_phone)},
        name="Mobile",
    )
    devices.async_update_device(wifi_dev.id, via_device_id=rep.id, name_by_user="Mon mobile")
    router.devices[wifi_phone] = host(primary_name="Mobile", l2ident={"id": wifi_phone})
    router.repeaters = {canon: {"name": "Cave", "macs": [canon]}}
    assert router._link_from_registry(wifi_phone) == f"{LINK_REPEATER}{canon}"

    changing = "aa:bb:cc:dd:ee:43"
    router.devices[changing] = host(
        primary_name="Tablette", active=True, l2ident={"id": changing},
        access_point={"type": "repeater", "mac": canon, "connectivity_type": "wifi"},
    )
    router.lan_links[normalize_mac(changing)] = LINK_WIRED
    router.repeater_aliases[normalize_mac(canon)] = canon
    router._update_lan_links()
    assert router._lan_link_pending.get(normalize_mac(changing))
    router._update_lan_links()
    assert router.lan_links[normalize_mac(changing)].startswith(LINK_REPEATER)

    class _Idents:
        def __init__(self, identifiers):
            self.identifiers = identifiers
    router.repeater_aliases = {normalize_mac(canon): canon}
    stale = router._stale_repeater_idents(_Idents([("other", "x"), (DOMAIN, 12), (DOMAIN, "repeater_DEADBEEF0001"), (DOMAIN, f"repeater_{canon}")]))
    assert (DOMAIN, "repeater_DEADBEEF0001") in stale
    assert router._is_current_repeater_device(_Idents([(DOMAIN, f"repeater_{canon}")])) is True

    client_mac = "aa:bb:cc:dd:ee:44"
    devices.async_update_device(
        rep.id,
        new_connections={(dr.CONNECTION_NETWORK_MAC, canon), (dr.CONNECTION_NETWORK_MAC, client_mac)},
    )
    router.devices[client_mac] = host(primary_name="Invite", l2ident={"id": client_mac})
    assert router._lan_client_device(devices, client_mac) is None
    assert (dr.CONNECTION_NETWORK_MAC, client_mac) not in devices.async_get(rep.id).connections
    stale_mac = "aa:bb:cc:dd:ee:45"
    stale_dev = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "repeater_AABBCCDDEE45"), (DOMAIN, "disk_edge")},
        connections={(dr.CONNECTION_NETWORK_MAC, stale_mac)},
        name="Ancien faux repeteur",
    )
    devices.async_update_device(stale_dev.id, name_by_user="A garder")
    router.devices[stale_mac] = host(primary_name="Ancien", l2ident={"id": stale_mac})
    assert router._lan_client_device(devices, stale_mac) is None
    assert (DOMAIN, "repeater_AABBCCDDEE45") not in devices.async_get(stale_dev.id).identifiers
    assert devices.async_get(stale_dev.id).name_by_user == "A garder"

    router.create_lan_devices = False
    assert router.ensure_lan_client_device(phone) is None
    router.create_lan_devices = True
    assert router.ensure_lan_client_device("absent") is None
    foreign = MockConfigEntry(domain="shelly", data={})
    foreign.add_to_hass(hass)
    shelly_mac = "aa:bb:cc:dd:ee:77"
    shelly = devices.async_get_or_create(
        config_entry_id=foreign.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, shelly_mac)},
        name="Shelly",
    )
    devices.async_update_device(shelly.id, name_by_user="Ma prise")
    router.devices[shelly_mac] = host(primary_name="Shelly", l2ident={"id": shelly_mac})
    router.tracked_lan_macs.add(normalize_mac(shelly_mac))
    assert router.ensure_lan_client_device(shelly_mac) is None
    assert devices.async_get(shelly.id).name_by_user == "Ma prise"
    fresh = "aa:bb:cc:dd:ee:48"
    router.devices[fresh] = host(primary_name="Portable", l2ident={"id": fresh}, active=True,
                                  access_point={"connectivity_type": "ethernet"})
    router.tracked_lan_macs.add(normalize_mac(fresh))
    router.lan_links[normalize_mac(fresh)] = LINK_WIRED
    created = router.ensure_lan_client_device(fresh)
    assert created
    assert devices.async_get(created).name_by_user is None
    assert router.lan_client_placements.get(normalize_mac(fresh))
    assert router.lan_group_members(GROUP_LAN_WIRED)
    assert router._placement_of(None) is None
    router.repeater_device_ids[canon] = rep.id
    assert router._placement_of(rep.id) == f"{LINK_REPEATER}{canon}"

    router.repeaters = None
    router._sync_lan_client_parents()
    router.repeaters = {}

    with patch.object(router, "_update_lan_links", side_effect=RuntimeError("classement synthetique")):
        with patch(
            "custom_components.freebox_homexa.router.get_hosts_list_if_supported",
            new=AsyncMock(return_value=(True, [])),
        ):
            await router.update_device_trackers()
    # Un groupe qui a encore un enfant reste ; un groupe vide est retiré.
    assert GROUP_LAN_WIRED in router.group_device_ids
    empty = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "groupe-vide")}, name="Vide",
    )
    router.group_device_ids["lan_wifi_net_printers"] = empty.id
    router._prune_empty_lan_groups()
    assert "lan_wifi_net_printers" not in router.group_device_ids
    assert devices.async_get(empty.id) is None
    assert GROUP_LAN_WIRED in router.group_device_ids

    async def _closing():
        router.closing = True
        raise RuntimeError("closed")

    router.closing = False
    router.reachable = True
    router.update_device_trackers = _closing
    await router.update_all(datetime.now(timezone.utc))
    assert router.reachable is True
    router.closing = False
    router.home_granted = True
    router.home_available = True

    async def _home_closed():
        router.closing = True
        raise RuntimeError("closed")

    router.home.get_home_nodes = _home_closed
    await router.update_home_devices()
    assert router.home_available is True
