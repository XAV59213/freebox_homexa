"""Simulation hors HA : séparation des clients réseau filaires / Wi-Fi (box ou répéteur).

Données réelles de l'utilisateur (3 répéteurs Free, firmware 2.9.3, backhaul Ethernet) :
  Grange        20:66:CF:4A:05:93  BSSID 22:66:CF:C9:A0:52 / 56
  Chambre fille 20:66:CF:4B:49:63  BSSID 22:66:CF:C6:92:D2 / D6
  Garage        20:66:CF:4B:49:69  BSSID 22:66:CF:96:92:D2 / D6
Hiérarchie attendue :
  Freebox Server
  ├─ Clients réseau filaires : clients Ethernet (box ou port d'un répéteur)
  └─ Clients Wi-Fi : clients du Wi-Fi de la box + Grange / Chambre fille / Garage
                     (chaque répéteur porte ses propres clients Wi-Fi)
Lancer depuis la racine du dépôt : python3 tests/simulation_clients_filaires_wifi.py
"""
import sys, types, itertools

# --- Bouchons Home Assistant / freebox_api ------------------------------------
for m in ["homeassistant", "homeassistant.config_entries", "homeassistant.core", "homeassistant.const",
          "homeassistant.helpers", "homeassistant.helpers.dispatcher", "homeassistant.util",
          "homeassistant.helpers.entity_registry", "freebox_api", "freebox_api.api", "freebox_api.api.call",
          "freebox_api.api.home", "freebox_api.api.wifi", "freebox_api.exceptions"]:
    sys.modules[m] = types.ModuleType(m)
ha = sys.modules
ha["homeassistant.config_entries"].ConfigEntry = object
ha["homeassistant.core"].HomeAssistant = object
ha["homeassistant.const"].CONF_HOST = "host"; ha["homeassistant.const"].CONF_PORT = "port"
ha["homeassistant.helpers.dispatcher"].async_dispatcher_send = lambda *a: None
ha["homeassistant.util"].slugify = lambda s: s
ha["freebox_api"].Freepybox = object
ha["freebox_api.api.call"].Call = object; ha["freebox_api.api.home"].Home = object; ha["freebox_api.api.wifi"].Wifi = object
ha["freebox_api.exceptions"].HttpRequestError = Exception; ha["freebox_api.exceptions"].NotOpenError = Exception


class Dev:
    def __init__(s, i, idents=(), conns=(), name=None, via=None):
        s.id = i; s.identifiers = set(idents); s.connections = set(conns); s.name = name
        s.via_device_id = via; s.config_entry_id = "E"


DEV = {}
ids = itertools.count()


class Reg:
    def async_get_device_by_identifier(s, ident, e):
        return next((d for d in DEV.values() if ident in d.identifiers and d.config_entry_id == e), None)

    def async_get_device_by_connection(s, c, e):
        return next((d for d in DEV.values() if c in d.connections and d.config_entry_id == e), None)

    def async_get_or_create(s, config_entry_id, identifiers, name, **kw):
        d = next((d for d in DEV.values() if d.identifiers & set(identifiers)), None)
        if d is None:
            d = Dev(f"dev{next(ids)}", identifiers, name=name); DEV[d.id] = d
        return d

    def async_update_device(s, i, **kw):
        d = DEV[i]
        for k, v in kw.items():
            setattr(d, k, v)
        UPDATES.append((d.name, kw))
        return d

    def async_remove_device(s, i):
        DEV.pop(i)


UPDATES = []
R = Reg()
dr = types.ModuleType("dr"); dr.async_get = lambda h: R; dr.CONNECTION_NETWORK_MAC = "mac"
dr.DeviceInfo = dict; dr.DeviceEntryType = types.SimpleNamespace(SERVICE="service")
dr.async_entries_for_config_entry = lambda r, e: [d for d in list(DEV.values()) if d.config_entry_id == e]
ha["homeassistant.helpers"].device_registry = dr; ha["homeassistant.helpers.device_registry"] = dr
er = ha["homeassistant.helpers.entity_registry"]; ha["homeassistant.helpers"].entity_registry = er
ENT = {}
er.async_get = lambda h: None
er.async_entries_for_device = lambda r, did, include_disabled_entities=True: [e for e, d in ENT.items() if d == did]

pkg = types.ModuleType("fh"); pkg.__path__ = []; sys.modules["fh"] = pkg
c = types.ModuleType("fh.const"); c.DOMAIN = "d"; c.REPEATER_MODEL = "F-RP01A"; c.FreeboxHomeCategory = type("C", (), {})
for k in ("API_VERSION", "APP_DESC", "CONNECTION_SENSORS_KEYS", "HOME_COMPATIBLE_CATEGORIES"):
    setattr(c, k, {})
sys.modules["fh.const"] = c


def load(name):
    m = types.ModuleType("fh." + name)
    src = open(f"custom_components/freebox_homexa/{name}.py").read().replace("from .", "from fh.")
    sys.modules["fh." + name] = m
    exec(src, m.__dict__)
    return m


load("registry_compat"); dg = load("device_groups"); wa = load("wifi_ap"); rt = load("router")

RM = "34:27:92:D9:E0:30"
TRUTH = {"Grange": ("20:66:CF:4A:05:93", "192.168.1.165", ["22:66:CF:C9:A0:52", "22:66:CF:C9:A0:56"]),
         "Chambre fille": ("20:66:CF:4B:49:63", "192.168.1.87", ["22:66:CF:C6:92:D2", "22:66:CF:C6:92:D6"]),
         "Garage": ("20:66:CF:4B:49:69", "192.168.1.66", ["22:66:CF:96:92:D2", "22:66:CF:96:92:D6"])}
API = [{"id": i, "name": n, "main_mac": m, "model": "fbxwmr-r2", "status": "running",
        "backhaul": [{"type": "eth", "mac": m}], "fronthaul": [{"bssid": b} for b in bss]}
       for i, (n, (m, _, bss)) in enumerate(TRUTH.items())]


def host(mac, name, ap=None, active=True, host_type="smartphone", signal=None):
    h = {"l2ident": {"id": mac, "type": "mac_address"}, "primary_name": name, "host_type": host_type,
         "vendor_name": "", "active": active}
    if ap is not None:
        h["access_point"] = ap
    return h


def wifi_ap(kind, mac, sig=-55):
    return {"type": kind, "mac": mac, "uid": f"uid-{mac}", "connectivity_type": "wifi",
            "wifi_information": {"signal": sig, "ssid": "Freebox", "band": "5g", "bssid": mac}}


def eth_ap(kind, mac):
    return {"type": kind, "mac": mac, "uid": f"uid-{mac}", "connectivity_type": "ethernet",
            "ethernet_information": {"speed": 1000, "duplex": "full", "link": "up"}}


def lan():
    hosts = {}
    for name, (mac, ip, _) in TRUTH.items():
        hosts[mac] = {"l2ident": {"id": mac}, "primary_name": name, "host_type": "networking_device",
                      "vendor_name": "Freebox SAS", "model": "fbxwmr-r2", "active": True,
                      "access_point": eth_ap("gateway", RM), "l3connectivities": [{"addr": ip}]}
    hosts["AA:00:00:00:00:01"] = host("AA:00:00:00:00:01", "PC-Bureau", eth_ap("gateway", RM), host_type="workstation")
    hosts["AA:00:00:00:00:02"] = host("AA:00:00:00:00:02", "NAS", eth_ap("gateway", RM), host_type="nas")
    hosts["AA:00:00:00:00:03"] = host("AA:00:00:00:00:03", "iPhone-Xav", wifi_ap("gateway", RM))
    hosts["AA:00:00:00:00:04"] = host("AA:00:00:00:00:04", "Echo-Salon", wifi_ap("gateway", RM))
    hosts["AA:00:00:00:00:05"] = host("AA:00:00:00:00:05", "Tel-Fille", wifi_ap("repeater", "22:66:CF:C6:92:D6"))
    hosts["AA:00:00:00:00:06"] = host("AA:00:00:00:00:06", "Shelly-Garage", wifi_ap("repeater", "22:66:CF:96:92:D2"))
    hosts["AA:00:00:00:00:07"] = host("AA:00:00:00:00:07", "Camera-Grange", wifi_ap("repeater", "22:66:CF:C9:A0:52"))
    # Branché sur le port Ethernet du répéteur Garage : client filaire.
    hosts["AA:00:00:00:00:08"] = host("AA:00:00:00:00:08", "TV-Garage", eth_ap("repeater", "20:66:CF:4B:49:69"))
    # Hors ligne depuis longtemps, sans access_point : non classé (reste sous le Freebox Server).
    hosts["AA:00:00:00:00:09"] = host("AA:00:00:00:00:09", "Vieux-PC", None, active=False)
    hosts[RM] = {"l2ident": {"id": RM}, "primary_name": "Freebox Server", "attrs": {}, "active": True}
    return hosts


entry = types.SimpleNamespace(entry_id="E", data={"host": "fbx"}, options={})
cfg = {"model_info": {"pretty_name": "Freebox v7", "name": "fbxgw7"}, "mac": RM, "firmware_version": "4.9"}


def make_router(options=None):
    entry.options = options or {}
    r = rt.FreeboxRouter(None, entry, None, cfg)
    srv = Dev("srv", [("d", RM)], [("mac", RM.lower())], "Freebox Server"); DEV[srv.id] = srv
    r.device_id = srv.id
    return r


def poll(r, hosts):
    for h in hosts.values():
        h.pop("wifi_parent", None)
        h["wifi"] = rt.extract_wifi_details(h)
    r.devices = hosts
    r.api_repeaters = API
    r._refresh_repeaters()
    r._update_lan_links()
    r._sync_lan_client_parents()


def register_entities(r, hosts):
    """Ajout des entités : répéteurs (DeviceInfo du routeur) puis clients (lan_client_parent)."""
    for canon, p in r.repeaters.items():
        info = r.repeater_device_info(canon, p["name"])
        d = R.async_get_or_create("E", info["identifiers"], info["name"])
        d.connections = set(info["connections"]); d.via_device_id = info.get("via_device_id")
    for mac, h in hosts.items():
        if h.get("attrs") is not None or r.is_repeater_host(h):
            continue
        d = R.async_get_device_by_connection(("mac", mac.lower()), "E")
        if d is None:
            d = Dev(f"dev{next(ids)}", (), [("mac", mac.lower())], dg.lan_client_name(h)); DEV[d.id] = d
        d.via_device_id = r.lan_client_parent(mac, d.name)


def parent_name(mac):
    d = R.async_get_device_by_connection(("mac", mac.lower()), "E")
    return DEV[d.via_device_id].name if d and d.via_device_id else None


def tree():
    out = {}
    for d in DEV.values():
        if d.via_device_id:
            out.setdefault(DEV[d.via_device_id].name, []).append(d.name)
    return {k: sorted(v) for k, v in out.items()}


# --- 1. Classement pur ----------------------------------------------------------
assert dg.lan_client_link({"access_point": eth_ap("gateway", RM)}) == dg.LINK_WIRED
assert dg.lan_client_link({"access_point": eth_ap("repeater", "20:66:CF:4B:49:69")}) == dg.LINK_WIRED
assert dg.lan_client_link({"access_point": wifi_ap("gateway", RM)}) == dg.LINK_WIFI
assert dg.lan_client_link({"access_point": wifi_ap("repeater", "22:66:CF:96:92:D2")},
                          lambda m: "20:66:CF:4B:49:69") == "repeater:20:66:CF:4B:49:69"
assert dg.lan_client_link({}) is None
# Un hôte Ethernet de la box n'est plus compté comme client Wi-Fi (« Appareils sur le Wi-Fi box »).
assert not wa._is_wifi_client(host("AA:00:00:00:00:01", "PC", eth_ap("gateway", RM)), RM)
assert wa._is_wifi_client(host("AA:00:00:00:00:03", "iPhone", wifi_ap("gateway", RM)), RM)
# Anti va-et-vient.
assert dg.next_lan_link(None, "wifi", True, None) == ("wifi", None)
assert dg.next_lan_link("wifi", None, False, None) == ("wifi", None)
assert dg.next_lan_link("wifi", "wired", False, None) == ("wifi", None)
assert dg.next_lan_link("wifi", "repeater:X", True, None) == ("wifi", ("repeater:X", 1))
assert dg.next_lan_link("wifi", "repeater:X", True, ("repeater:X", 1)) == ("repeater:X", None)
assert dg.next_lan_link("wifi", "wifi", True, ("repeater:X", 1)) == ("wifi", None)
print("OK : classement filaire / Wi-Fi")

# --- 2. Bout en bout avec les données réelles ---------------------------------
r = make_router()
hosts = lan()
poll(r, hosts)
assert len(r.repeaters) == 3, list(r.repeaters)
register_entities(r, hosts)
poll(r, hosts)
t = tree()
print("   hiérarchie :", t)
assert t["Freebox Server"] == ["Clients Wi-Fi", "Clients réseau filaires", "Vieux-PC"], t
assert t["Clients réseau filaires"] == ["NAS", "PC-Bureau", "TV-Garage"], t
assert t["Clients Wi-Fi"] == ["Chambre fille", "Echo-Salon", "Garage", "Grange", "iPhone-Xav"], t
assert t["Grange"] == ["Camera-Grange"] and t["Chambre fille"] == ["Tel-Fille"] and t["Garage"] == ["Shelly-Garage"], t
gw = r.wifi_aps["gateway"]
assert sorted(gw["client_names"]) == ["Echo-Salon", "iPhone-Xav"], gw["client_names"]  # plus de PC/NAS filaires
print("OK : hiérarchie Freebox Server > filaires / Wi-Fi > répéteurs")

# --- 3. Stabilité : hors ligne, itinérance, redémarrage -------------------------
hosts["AA:00:00:00:00:05"]["active"] = False
hosts["AA:00:00:00:00:05"].pop("access_point")  # Freebox ne dit plus rien
poll(r, hosts)
assert parent_name("AA:00:00:00:00:05") == "Chambre fille"
hosts["AA:00:00:00:00:05"]["access_point"] = eth_ap("gateway", RM)  # donnée périmée hors ligne
poll(r, hosts)
assert parent_name("AA:00:00:00:00:05") == "Chambre fille"
UPDATES.clear()
hosts["AA:00:00:00:00:03"]["access_point"] = wifi_ap("repeater", "22:66:CF:C9:A0:56")  # iPhone -> Grange
poll(r, hosts)
assert parent_name("AA:00:00:00:00:03") == "Clients Wi-Fi" and not UPDATES  # 1 relevé : on attend
hosts["AA:00:00:00:00:03"]["access_point"] = wifi_ap("gateway", RM)  # revenu : rien ne bouge
poll(r, hosts)
hosts["AA:00:00:00:00:03"]["access_point"] = wifi_ap("repeater", "22:66:CF:C9:A0:56")
poll(r, hosts); assert parent_name("AA:00:00:00:00:03") == "Clients Wi-Fi"
poll(r, hosts); assert parent_name("AA:00:00:00:00:03") == "Grange"
assert len(UPDATES) == 1, UPDATES
# Redémarrage de HA : mémoire vide, classement relu depuis le registre (via_device).
r2 = make_router()
hosts["AA:00:00:00:00:05"]["active"] = False
hosts["AA:00:00:00:00:05"].pop("access_point", None)
poll(r2, hosts)
assert r2.lan_links["AA0000000005"] == "repeater:20:66:CF:4B:49:63", r2.lan_links
assert parent_name("AA:00:00:00:00:05") == "Chambre fille"
print("OK : hors ligne / itinérance / redémarrage sans va-et-vient")

# --- 4. Surcharge « Groupes des appareils » prioritaire ----------------------
r3 = make_router({"device_group_overrides": {"mac:aa:00:00:00:00:04": "player", "mac:aa:00:00:00:00:02": "server"}})
r3.player_identifiers = {"player1"}
DEV["pl"] = Dev("pl", [("d", "player1")], name="Freebox Player")
poll(r3, hosts)
assert parent_name("AA:00:00:00:00:04") == "Freebox Player"
assert parent_name("AA:00:00:00:00:02") == "Freebox Server"
assert r3.grouped_devices["mac:aa:00:00:00:00:01"][1] == dg.GROUP_LAN_WIRED
print("OK : surcharges utilisateur prioritaires")

# --- 5. Nettoyage : groupes conservés tant qu'ils ont des enfants -------------
removed = dg.async_remove_unused_group_devices(None, entry, RM, set())
assert not removed, removed  # groupes non « utilisés » mais avec enfants : conservés
for d in list(DEV.values()):
    if d.via_device_id == r.group_device_ids.get(dg.GROUP_LAN_WIRED):
        d.via_device_id = "srv"
removed = dg.async_remove_unused_group_devices(None, entry, RM, {dg.GROUP_LAN_WIFI})
assert removed == ["Clients réseau filaires"], removed
print("SIMULATION_CLIENTS_FILAIRES_WIFI_OK")
