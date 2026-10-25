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
try:
    import aiohttp  # noqa: F401
except ImportError:  # bouchon minimal (HA fournit aiohttp)
    _aio = types.ModuleType("aiohttp")
    _aio.ClientError = type("ClientError", (Exception,), {})
    _aio.ClientConnectionError = type("ClientConnectionError", (_aio.ClientError,), {})
    sys.modules["aiohttp"] = _aio
ha["freebox_api"].Freepybox = object
ha["freebox_api.api.call"].Call = object; ha["freebox_api.api.home"].Home = object; ha["freebox_api.api.wifi"].Wifi = object
ha["freebox_api.exceptions"].HttpRequestError = type("HttpRequestError", (Exception,), {})
ha["freebox_api.exceptions"].NotOpenError = type("NotOpenError", (Exception,), {})


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

    def async_get_or_create(s, config_entry_id, identifiers=(), name=None, connections=(), **kw):
        d = next((d for d in DEV.values() if d.identifiers & set(identifiers)
                  or d.connections & set(connections)), None)
        if d is None:
            d = Dev(f"dev{next(ids)}", identifiers, connections, name=name); DEV[d.id] = d
            CREATED.append(name)
        return d

    def async_update_device(s, i, **kw):
        d = DEV[i]
        for k, v in kw.items():
            setattr(d, {"new_connections": "connections", "new_identifiers": "identifiers"}.get(k, k), v)
        UPDATES.append((d.name, kw))
        return d

    def async_remove_device(s, i):
        DEV.pop(i)


UPDATES = []
CREATED = []
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


load("registry_compat"); er_mod = load("errors"); dg = load("device_groups"); wa = load("wifi_ap"); rt = load("router")

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
    hosts["AA:00:00:00:00:08"] = host("AA:00:00:00:00:08", "TV-Garage", eth_ap("repeater", "20:66:CF:4B:49:69"), host_type="television")
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


def parent_name_of(name):
    d = next(d for d in DEV.values() if d.name == name)
    return DEV[d.via_device_id].name if d.via_device_id else None


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
assert t["Clients réseau filaires"] == ["Ordinateurs (filaire)", "Serveurs (filaire)", "TV et multimédia (filaire)"], t
assert t["Serveurs (filaire)"] == ["NAS"] and t["Ordinateurs (filaire)"] == ["PC-Bureau"], t
assert t["TV et multimédia (filaire)"] == ["TV-Garage"], t
assert t["Clients Wi-Fi"] == ["Amazon / Alexa (Wi-Fi)", "Chambre fille", "Garage", "Grange",
                              "Téléphones et tablettes (Wi-Fi)"], t
assert t["Téléphones et tablettes (Wi-Fi)"] == ["iPhone-Xav"] and t["Amazon / Alexa (Wi-Fi)"] == ["Echo-Salon"], t
# Clients des répéteurs : directement sous le répéteur, sans couche de type.
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
assert parent_name("AA:00:00:00:00:03") == "Téléphones et tablettes (Wi-Fi)" and not UPDATES  # 1 relevé : on attend
hosts["AA:00:00:00:00:03"]["access_point"] = wifi_ap("gateway", RM)  # revenu : rien ne bouge
poll(r, hosts)
hosts["AA:00:00:00:00:03"]["access_point"] = wifi_ap("repeater", "22:66:CF:C9:A0:56")
poll(r, hosts); assert parent_name("AA:00:00:00:00:03") == "Téléphones et tablettes (Wi-Fi)"
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
assert r3.grouped_devices["mac:aa:00:00:00:00:01"][1] == "lan_wired_net_computers"
assert dg.group_label(r3.grouped_devices["mac:aa:00:00:00:00:01"][1]) == "Clients réseau filaires › Ordinateurs"
assert dg.group_label(r3.grouped_devices["mac:aa:00:00:00:00:02"][1]) == "Clients réseau filaires › Serveurs"
assert dg.group_label(r3.grouped_devices["mac:aa:00:00:00:00:06"][1], r3.repeater_names()) == "Clients Wi-Fi › Garage"
print("OK : surcharges utilisateur prioritaires")

# --- 5. Nettoyage : groupes conservés tant qu'ils ont des enfants -------------
def sub_devices():
    idents = {dg.group_identifier(RM, k) for k in dg.LAN_TYPE_GROUPS}
    return [d for d in DEV.values() if d.identifiers & idents]


def has_kids(d):
    return any(x.via_device_id == d.id for x in DEV.values())


empty = sorted(d.name for d in sub_devices() if not has_kids(d))
full = sorted(d.name for d in sub_devices() if has_kids(d))
assert full, full
removed = dg.async_remove_unused_group_devices(None, entry, RM, set())
assert sorted(removed) == empty, (removed, empty)  # seuls les sous-groupes vides partent
assert sorted(d.name for d in sub_devices()) == full  # les non vides restent, même « inutilisés »
assert any(d.name == "Clients réseau filaires" for d in DEV.values())
wired_subs = [d.id for d in sub_devices() if d.name.endswith("(filaire)")]
for d in list(DEV.values()):
    if d.via_device_id in wired_subs:
        d.via_device_id = "srv"
removed = dg.async_remove_unused_group_devices(None, entry, RM, {dg.GROUP_LAN_WIFI})
assert "Clients réseau filaires" in removed and all(n.endswith("(filaire)") or n == "Clients réseau filaires"
                                                    for n in removed), removed
assert all(d.name.endswith("(Wi-Fi)") for d in sub_devices()), [d.name for d in sub_devices()]
# Identifiants distincts des anciens sous-groupes réseau (28.8.36 → 28.8.42, ex. « net_phones »).
assert not set(dg.LAN_TYPE_GROUPS) & set(dg.LEGACY_GROUPS)
print("OK : nettoyage des sous-groupes vides, non vides conservés")

# --- 6. Switch Cisco (rapport utilisateur, Freebox OS 4.13) ----------------------
# « Cisco Systems, Inc (A4:56:30:73:AF:C0) », type « Périphérique réseau », joignable.
CISCO = "A4:56:30:73:AF:C0"


def cisco(ap=None, active=True):
    h = host(CISCO, f"Cisco Systems, Inc ({CISCO})", ap, active=active, host_type="networking_device")
    h["vendor_name"] = "Cisco Systems, Inc"
    return h


def gw_no_conn(mac=RM):
    return {"type": "gateway", "mac": mac, "uid": f"uid-{mac}"}


# Classement pur : sans access_point, ou « gateway » sans connectivity_type -> filaire.
for ap in (None, gw_no_conn(), {}):
    h = cisco(ap)
    h["wifi"] = rt.extract_wifi_details(h)
    assert not wa._is_wifi_client(h, RM), ap
    assert dg.lan_client_link(h) == dg.LINK_WIRED, ap
assert not wa.is_freebox_repeater(cisco(), RM)
# Ethernet sans connectivity_type mais avec ethernet_information : filaire, même hors ligne.
eth_only = {"type": "gateway", "mac": RM, "ethernet_information": {"speed": 1000, "link": "up"}}
assert dg.lan_client_link(cisco(eth_only, active=False)) == dg.LINK_WIRED
# Hors ligne sans indice : non classé (dernier classement conservé).
assert dg.lan_client_link(cisco(None, active=False)) is None
assert dg.lan_client_link(cisco(gw_no_conn(), active=False)) is None
# Wi-Fi reconnu par le signal (station de la box), même sans connectivity_type.
ph = host("AA:00:00:00:00:0A", "Tel", gw_no_conn())
ph["_wifi_station"] = {"signal": -60, "bssid": "34:27:92:D9:E0:31"}
ph["wifi"] = rt.extract_wifi_details(ph)
assert wa._is_wifi_client(ph, RM) and dg.lan_client_link(ph) == dg.LINK_WIFI
# Client d'un répéteur sans détail : reste Wi-Fi (répéteur).
rp = host("AA:00:00:00:00:0B", "Tel2", {"type": "repeater", "mac": "22:66:CF:96:92:D2"})
assert wa._is_wifi_client(rp, RM)
assert dg.lan_client_link(rp, lambda m: "20:66:CF:4B:49:69") == "repeater:20:66:CF:4B:49:69"
print("OK : switch sans access_point / gateway sans connectivity_type -> filaire")

# Bout en bout : switch sans access_point -> « Clients réseau filaires » dès le 1er relevé.
for d in list(DEV.values()):
    if d.via_device_id and DEV.get(d.via_device_id) is None:
        d.via_device_id = "srv"
r6 = make_router()
hosts6 = lan()
hosts6[CISCO] = cisco(None)
poll(r6, hosts6)
register_entities(r6, hosts6)
poll(r6, hosts6)
assert parent_name(CISCO) == "Équipements réseau (filaire)", parent_name(CISCO)
assert dg.group_label(r6.grouped_devices[f"mac:{CISCO.lower()}"][1]) == "Clients réseau filaires › Équipements réseau"
assert "Cisco" not in " ".join(r6.wifi_aps["gateway"]["client_names"])

# Mal classé par l'ancienne logique (gateway sans connectivity_type = Wi-Fi box) :
# après mise à jour, corrigé en 2 relevés tant qu'il est en ligne.
d_cisco = R.async_get_device_by_connection(("mac", CISCO.lower()), "E")
d_cisco.via_device_id = r6.group_device_id(dg.GROUP_LAN_WIFI)
r7 = make_router()
hosts6[CISCO] = cisco(gw_no_conn())
poll(r7, hosts6)
assert parent_name(CISCO) == "Équipements réseau (Wi-Fi)"  # 1 relevé : anti va-et-vient
poll(r7, hosts6)
assert parent_name(CISCO) == "Équipements réseau (filaire)", parent_name(CISCO)
assert r7.lan_links[wa.normalize_mac(CISCO)] == dg.LINK_WIRED

# Téléphone Wi-Fi hors ligne (sans access_point) : reste sous son point d'accès Wi-Fi.
hosts6["AA:00:00:00:00:04"]["active"] = False
hosts6["AA:00:00:00:00:04"].pop("access_point")
for _ in range(3):
    poll(r7, hosts6)
assert parent_name("AA:00:00:00:00:04") == "Amazon / Alexa (Wi-Fi)", parent_name("AA:00:00:00:00:04")
assert r7.lan_links["AA0000000004"] == dg.LINK_WIFI
# Même chose hors ligne avec un access_point « gateway » sans détail.
hosts6["AA:00:00:00:00:04"]["access_point"] = gw_no_conn()
for _ in range(3):
    poll(r7, hosts6)
assert parent_name("AA:00:00:00:00:04") == "Amazon / Alexa (Wi-Fi)"
print("OK : switch Cisco filaire, correction d'un ancien classement Wi-Fi, téléphone hors ligne conservé")

# --- 7. Surcharge « Clients réseau filaires » / « Clients Wi-Fi » --------------
assert dg.migrate_overrides({"mac:x": "lan_wired", "mac:y": "lan_wifi", "mac:z": "net_other"}) == {
    "mac:x": "lan_wired", "mac:y": "lan_wifi", "mac:z": "server"}
assert "lan_wired" in dg.group_choices() and "lan_wifi" in dg.group_choices()
r8 = make_router({"device_group_overrides": {f"mac:{CISCO.lower()}": "lan_wifi",
                                             "mac:aa:00:00:00:00:09": "lan_wired"}})
hosts6[CISCO] = cisco(None)
poll(r8, hosts6)
assert parent_name(CISCO) == "Équipements réseau (Wi-Fi)"  # surcharge prioritaire (type conservé)
assert parent_name("AA:00:00:00:00:09") == "Téléphones et tablettes (filaire)"  # Vieux-PC hors ligne forcé
print("OK : surcharges vers les groupes filaires / Wi-Fi")

# --- 8. Sous-groupes de type : données proches de l'installation de l'utilisateur --
cls = lambda **kw: dg.lan_client_type({"l2ident": {"id": kw.pop("mac", "AA:BB:CC:00:00:01")}, **kw})
# Équipements réseau : switch Cisco (networking_device non Free), fabricants réseau.
assert cls(mac=CISCO, primary_name=f"Cisco Systems, Inc ({CISCO})", vendor_name="Cisco Systems, Inc",
           host_type="networking_device") == dg.NET_NETWORK
assert cls(primary_name="GS308", vendor_name="NETGEAR") == dg.NET_NETWORK
assert cls(primary_name="UniFi-AP", vendor_name="Ubiquiti Inc") == dg.NET_NETWORK
assert cls(primary_name="Tapo-P100", vendor_name="TP-LINK TECHNOLOGIES") == dg.NET_IOT  # TP-Link reste IoT
assert cls(primary_name="Deco", vendor_name="TP-LINK TECHNOLOGIES", host_type="networking_device") == dg.NET_NETWORK
assert cls(primary_name="Nintendo Switch", vendor_name="Nintendo Co.,Ltd") == dg.NET_CONSOLES
# Serveurs : Proxmox, NAS, hyperviseurs.
assert cls(primary_name="pve-hpdle", vendor_name="Hewlett Packard") == dg.NET_SERVERS
assert cls(primary_name="proxmox", vendor_name="Intel Corporate") == dg.NET_SERVERS
assert cls(primary_name="DS920", vendor_name="Synology Incorporated") == dg.NET_SERVERS
assert cls(primary_name="nas1", vendor_name="") == dg.NET_SERVERS
assert cls(primary_name="TrueNAS-Scale", vendor_name="") == dg.NET_SERVERS
assert cls(primary_name="Stockage", host_type="nas") == dg.NET_SERVERS
assert cls(primary_name="esxi01", vendor_name="Dell Inc.") == dg.NET_SERVERS
assert cls(primary_name="Nastya-iPhone", vendor_name="Apple, Inc.") == dg.NET_PHONES  # pas « nas »
# VM et conteneurs (y compris sites hébergés) : OUI virtuels ou nom.
assert cls(mac="BC:24:11:12:34:56", primary_name="homeassistant") == dg.NET_VIRTUAL  # LXC / VM Proxmox
assert cls(mac="52:54:00:AB:CD:EF", primary_name="debian") == dg.NET_VIRTUAL  # QEMU/KVM
assert cls(mac="00:16:3E:00:00:01", primary_name="x") == dg.NET_VIRTUAL  # Xen / LXC
assert cls(mac="08:00:27:00:00:01", primary_name="x") == dg.NET_VIRTUAL  # VirtualBox
assert cls(mac="00:50:56:00:00:01", primary_name="x") == dg.NET_VIRTUAL  # VMware
assert cls(mac="00:15:5D:00:00:01", primary_name="x") == dg.NET_VIRTUAL  # Hyper-V
assert cls(mac="02:11:22:33:44:55", primary_name="ct-101-pihole") == dg.NET_VIRTUAL
assert cls(mac="02:11:22:33:44:56", primary_name="lxc-nextcloud") == dg.NET_VIRTUAL
assert cls(primary_name="vm-windows") == dg.NET_VIRTUAL
assert cls(primary_name="docker01") == dg.NET_VIRTUAL
assert cls(primary_name="site-vitrine") == dg.NET_VIRTUAL
assert cls(primary_name="wordpress") == dg.NET_VIRTUAL
assert cls(primary_name="web") == dg.NET_VIRTUAL
assert cls(primary_name="Webcam-Entree", host_type="ip_camera") == dg.NET_CAMERAS  # « webcam » != « web »
# Autres types inchangés.
assert cls(primary_name="iPhone-Xav", vendor_name="Apple, Inc.", host_type="smartphone") == dg.NET_PHONES
assert cls(primary_name="Echo Dot", vendor_name="Amazon Technologies Inc.") == dg.NET_AMAZON
assert cls(primary_name="Bluebank") == dg.NET_OTHER
assert cls(primary_name="Freebox Player", host_type="freebox_player") == dg.NET_MEDIA
# Proxmox VE 8+ : le pont vmbr0 de l'HÔTE a aussi une MAC BC:24:11 (données réelles).
PVE_VENDOR = "Proxmox Server Solutions GmbH"
assert cls(mac="BC:24:11:B4:3D:38", primary_name="pve", vendor_name=PVE_VENDOR) == dg.NET_SERVERS
assert cls(mac="BC:24:11:B4:3D:38", primary_name="Proxmox", vendor_name=PVE_VENDOR) == dg.NET_SERVERS
assert cls(mac="BC:24:11:B4:3D:38", primary_name="Serveur Proxmox", vendor_name=PVE_VENDOR) == dg.NET_SERVERS
assert cls(mac="BC:24:11:B4:3D:38", primary_name="pve-hpdle", vendor_name=PVE_VENDOR,
           names=[{"name": "Proxmox Server Solutions GmbH (BC:24:11:B4:3D:38)"}]) == dg.NET_SERVERS
# Nom par défaut « fabricant (MAC) » : ses mots Proxmox / Server ne comptent pas -> VM.
for mac in ("BC:24:11:B4:3D:38", "BC:24:11:63:90:C9"):
    assert cls(mac=mac, primary_name=f"{PVE_VENDOR} ({mac})", vendor_name=PVE_VENDOR) == dg.NET_VIRTUAL
assert cls(mac="BC:24:11:63:90:C9", primary_name=PVE_VENDOR, vendor_name=PVE_VENDOR) == dg.NET_VIRTUAL
assert cls(mac="BC:24:11:63:90:C9", primary_name="", default_name=f"{PVE_VENDOR} (BC:24:11:63:90:C9)",
           vendor_name=PVE_VENDOR) == dg.NET_VIRTUAL
# VM / LXC de l'utilisateur.
for mac, name in (("BC:24:11:07:7A:6B", "frigate"), ("BC:24:11:96:80:58", "uptimekuma"),
                  ("BC:24:11:F6:AC:35", "inventree")):
    assert cls(mac=mac, primary_name=name, vendor_name=PVE_VENDOR) == dg.NET_VIRTUAL, name
# « Server » dans un nom par défaut d'un autre fabricant : pas un serveur.
assert cls(primary_name="Super Server Corp (AA:BB:CC:00:00:01)", vendor_name="Super Server Corp") == dg.NET_OTHER
# « tv » (mot entier) dans le nom : TV et multimédia avant le fabricant / host_type.
assert cls(primary_name="Tv chambre papa", vendor_name="Realtek Semiconductor Corp.") == dg.NET_MEDIA
assert cls(primary_name="Tv chambre papa", vendor_name="Intel Corporate", host_type="workstation") == dg.NET_MEDIA
assert cls(primary_name="TV-Salon", vendor_name="Hon Hai Precision") == dg.NET_MEDIA
assert cls(primary_name="Fire TV Stick", vendor_name="Amazon Technologies Inc.") == dg.NET_AMAZON
assert cls(primary_name="tvheadend", vendor_name="Intel Corporate") == dg.NET_COMPUTERS  # pas le mot « tv »
print("OK : règles Serveurs / VM et conteneurs / Équipements réseau")

PROXMOX, LXC = "70:5A:0F:11:22:33", "BC:24:11:AA:BB:CC"
r9 = make_router()
hosts9 = lan()
hosts9[CISCO] = cisco(None)
hosts9[PROXMOX] = host(PROXMOX, "pve-hpdle", eth_ap("gateway", RM), host_type="workstation")
hosts9[LXC] = host(LXC, "nextcloud", None, host_type="other")  # LXC derrière le pont Proxmox
hosts9["AA:00:00:00:00:0C"] = host("AA:00:00:00:00:0C", "Galaxy-S23", wifi_ap("repeater", "22:66:CF:96:92:D6"))
for h in (hosts9[PROXMOX], hosts9[LXC]):
    h["vendor_name"] = ""
poll(r9, hosts9)
register_entities(r9, hosts9)
poll(r9, hosts9)
t = tree()
print("   hiérarchie utilisateur :", {k: v for k, v in t.items() if k != "Freebox Server"})
assert parent_name(CISCO) == "Équipements réseau (filaire)", (parent_name(CISCO), tree())
assert parent_name(PROXMOX) == "Serveurs (filaire)"
assert parent_name(LXC) == "VM et conteneurs (filaire)"
assert parent_name("AA:00:00:00:00:03") == "Téléphones et tablettes (Wi-Fi)"  # Wi-Fi box
assert parent_name("AA:00:00:00:00:0C") == "Garage"  # Wi-Fi répéteur : directement sous lui
for sub in ("Équipements réseau (filaire)", "Serveurs (filaire)", "VM et conteneurs (filaire)"):
    assert parent_name_of(sub) == "Clients réseau filaires", sub
assert parent_name_of("Téléphones et tablettes (Wi-Fi)") == "Clients Wi-Fi"
assert parent_name_of("Garage") == "Clients Wi-Fi"
# Aucun sous-groupe de type sous un répéteur.
rep_ids = {d.id for d in DEV.values() if d.name in ("Grange", "Chambre fille", "Garage")}
assert not [d.name for d in sub_devices() if d.via_device_id in rep_ids]
# Libellés de l'écran « Groupes des appareils » et « Types des clients réseau ».
assert dg.group_label(r9.grouped_devices[f"mac:{PROXMOX.lower()}"][1]) == "Clients réseau filaires › Serveurs"
assert dg.group_label(r9.grouped_devices["mac:aa:00:00:00:00:0c"][1], r9.repeater_names()) == "Clients Wi-Fi › Garage"
assert r9.lan_client_types[f"mac:{LXC.lower()}"][1] == dg.NET_VIRTUAL

# Redémarrage : le lien est relu depuis le sous-groupe (pas de reclassement, pas de mouvement).
UPDATES.clear()
r10 = make_router()
hosts9[PROXMOX]["active"] = False
hosts9[PROXMOX].pop("access_point")
poll(r10, hosts9)
assert r10.lan_links[wa.normalize_mac(PROXMOX)] == dg.LINK_WIRED
assert parent_name(PROXMOX) == "Serveurs (filaire)" and not UPDATES, UPDATES

# Type forcé dans les options : immédiat (pas d'anti va-et-vient pour le type).
assert dg.migrate_type_overrides({"a": "net_servers", "b": "bad", "c": "auto"}) == {"a": "net_servers"}
assert dg.type_choices()[0] == "auto" and set(dg.type_choices()[1:]) == set(dg.LAN_TYPES)
r11 = make_router({"device_type_overrides": {f"mac:{LXC.lower()}": dg.NET_SERVERS,
                                             "mac:aa:00:00:00:00:03": dg.NET_IOT}})
poll(r11, hosts9)
assert parent_name(LXC) == "Serveurs (filaire)"
assert parent_name("AA:00:00:00:00:03") == "Objets connectés (Wi-Fi)"
assert r11.lan_client_types[f"mac:{LXC.lower()}"][1] == dg.NET_VIRTUAL  # auto affiché inchangé
# Type forcé + groupe forcé « Clients Wi-Fi » : sous-groupe de type du groupe forcé.
r12 = make_router({"device_type_overrides": {f"mac:{LXC.lower()}": dg.NET_SERVERS},
                   "device_group_overrides": {f"mac:{LXC.lower()}": "lan_wifi"}})
poll(r12, hosts9)
assert parent_name(LXC) == "Serveurs (Wi-Fi)"
print("OK : hiérarchie par type (filaires / Wi-Fi box), répéteurs sans couche de type, types forcés")

# --- 9. Appareil du client créé par Homexa (28.8.53 : switch Cisco sans appareil) -----
# HA fige device_info à None pour les device_tracker : l'appareil n'existait que si une
# autre intégration connaissait la MAC. Homexa le crée pour les entités ACTIVES.
DEV.clear(); UPDATES.clear(); CREATED.clear()
GRANGE = "20:66:CF:4A:05:93"


def by_name(name):
    return next((d for d in DEV.values() if d.name == name), None)


r13 = make_router()
hosts13 = lan()
hosts13[CISCO] = cisco(eth_ap("gateway", RM))
poll(r13, hosts13)
register_entities(r13, {m: h for m, h in hosts13.items() if m != CISCO})  # Cisco : pas d'appareil
poll(r13, hosts13)
# Entité désactivée (jamais ajoutée) : ni appareil, ni sous-groupe vide.
assert R.async_get_device_by_connection(("mac", CISCO.lower()), "E") is None
assert by_name("Équipements réseau (filaire)") is None, tree()
# L'utilisateur active l'entité : ajoutée à HA -> appareil créé et rangé.
r13.tracked_lan_macs.add(wa.normalize_mac(CISCO))
poll(r13, hosts13)
assert parent_name(CISCO) == "Équipements réseau (filaire)", parent_name(CISCO)
assert parent_name_of("Équipements réseau (filaire)") == "Clients réseau filaires"
cisco_dev = R.async_get_device_by_connection(("mac", CISCO.lower()), "E")
assert r13.lan_device_ids[wa.normalize_mac(CISCO)] == cisco_dev.id
assert cisco_dev.name == f"Cisco Systems, Inc ({CISCO})"
n = len(CREATED)
poll(r13, hosts13); poll(r13, hosts13)
assert len(CREATED) == n  # pas de doublon
# Option « Créer les appareils des clients LAN » désactivée : rien n'est créé.
r13b = make_router(); r13b.create_lan_devices = False
r13b.tracked_lan_macs.add("AABBCCDDEEFF")
hosts13["AA:BB:CC:DD:EE:FF"] = host("AA:BB:CC:DD:EE:FF", "Nouveau-PC", eth_ap("gateway", RM), host_type="workstation")
poll(r13b, hosts13)
assert R.async_get_device_by_connection(("mac", "aa:bb:cc:dd:ee:ff"), "E") is None
hosts13.pop("AA:BB:CC:DD:EE:FF")
print("OK : appareil créé pour une entité active seulement, rangé dans Équipements réseau (filaire)")

# MAC du Cisco restée dans les connexions de l'appareil répéteur Grange (ancienne version) :
# l'entité était rattachée à Grange (« Grange ▸ Cisco… ») et le Cisco n'avait pas d'appareil.
DEV.pop(cisco_dev.id)
grange = R.async_get_device_by_identifier(("d", f"repeater_{GRANGE}"), "E")
assert grange is not None
grange.connections = set(grange.connections) | {("mac", CISCO.lower())}
r14 = make_router()
r14.tracked_lan_macs.add(wa.normalize_mac(CISCO))
poll(r14, hosts13)
assert ("mac", CISCO.lower()) not in grange.connections, grange.connections
assert grange.connections, "le répéteur garde ses propres MAC"
cisco_dev = R.async_get_device_by_connection(("mac", CISCO.lower()), "E")
assert cisco_dev is not None and cisco_dev.id != grange.id
assert parent_name(CISCO) == "Équipements réseau (filaire)", (parent_name(CISCO), tree())
assert r14.lan_device_ids[wa.normalize_mac(CISCO)] == cisco_dev.id  # l'entité est reliée ici
print("OK : MAC du client retirée de l'appareil répéteur, appareil propre créé")

# Identifiant « repeater_<MAC Cisco> » périmé (ancien faux répéteur) : retiré, appareil rangé.
cisco_dev.identifiers = {("d", f"repeater_{CISCO}")}
cisco_dev.via_device_id = "srv"
r15 = make_router()
poll(r15, hosts13)  # même sans entité suivie : l'appareil existe déjà
assert cisco_dev.identifiers == set(), cisco_dev.identifiers
assert parent_name(CISCO) == "Équipements réseau (filaire)", (parent_name(CISCO), tree())
# Un vrai répéteur garde son identifiant.
assert ("d", f"repeater_{GRANGE}") in grange.identifiers
print("OK : identifiant répéteur périmé retiré")

# Sous-groupe vidé (appareil supprimé) : retiré au relevé suivant ; groupe non vide conservé.
DEV.pop(cisco_dev.id)
r15.tracked_lan_macs.discard(wa.normalize_mac(CISCO))
poll(r15, hosts13)
assert by_name("Équipements réseau (filaire)") is None, tree()
assert by_name("Clients réseau filaires") is not None  # NAS, PC… encore dedans
assert by_name("Serveurs (filaire)") is not None
print("OK : sous-groupes vides retirés en continu, non vides conservés")

# --- 10. Capteurs « Clients connectés » par groupe -----------------------------
DEV.clear(); ENT.clear()
r16 = make_router()
hosts16 = lan()
hosts16[CISCO] = cisco(eth_ap("gateway", RM))
PVE = "BC:24:11:B4:3D:38"
hosts16[PVE] = host(PVE, "pve", eth_ap("gateway", RM), host_type="workstation")
hosts16[PVE]["vendor_name"] = "Proxmox Server Solutions GmbH"
hosts16["AA:00:00:00:00:02"]["active"] = False  # NAS hors ligne
poll(r16, hosts16)
for m, h in hosts16.items():
    if h.get("attrs") is None and not r16.is_repeater_host(h):
        r16.tracked_lan_macs.add(wa.normalize_mac(m))
register_entities(r16, hosts16)
poll(r16, hosts16)
names = lambda key: sorted(dg.lan_client_name(d) for d in r16.lan_group_members(key) if d.get("active"))
assert names("lan_wired_net_network") == [f"Cisco Systems, Inc ({CISCO})"], names("lan_wired_net_network")
assert names("lan_wired_net_servers") == ["pve"]  # NAS hors ligne non compté
assert len(r16.lan_group_members("lan_wired_net_servers")) == 2  # total = en ligne + hors ligne
assert set(names("lan_wired")) >= {"PC-Bureau", "TV-Garage", "pve", f"Cisco Systems, Inc ({CISCO})"}
# « Clients Wi-Fi » : clients de la box ET des répéteurs (rangés sous lui).
assert set(names("lan_wifi")) == {"iPhone-Xav", "Echo-Salon", "Tel-Fille", "Shelly-Garage", "Camera-Grange"}, names("lan_wifi")
assert names("lan_wifi_net_phones") == ["iPhone-Xav"]
# Le capteur d'un groupe n'empêche pas son retrait quand il est vide.
sub_id = r16.group_device_ids["lan_wired_net_network"]
ENT[f"{RM}_lan_group_clients_lan_wired_net_network"] = sub_id
class _E:  # entrée de registre d'entité (unique_id)
    def __init__(s, uid): s.unique_id = uid
er.async_entries_for_device = lambda r, did, include_disabled_entities=True: [
    _E(e) for e, d in ENT.items() if d == did]
assert not dg._has_entities(None, sub_id)
ENT["autre_entite"] = sub_id
assert dg._has_entities(None, sub_id)
ENT.pop("autre_entite")
DEV.pop(R.async_get_device_by_connection(("mac", CISCO.lower()), "E").id)
r16.tracked_lan_macs.discard(wa.normalize_mac(CISCO))
poll(r16, hosts16)
assert "lan_wired_net_network" not in r16.group_device_ids and sub_id not in DEV
assert names("lan_wired_net_network") == []
print("OK : capteurs Clients connectés (membres par groupe, retrait avec le groupe)")

# --- 12. Connexions MAC des répéteurs : uniquement leurs propres MAC (28.8.57) ---
# Rapport utilisateur : l'appareil « Répéteur Wifi Garage » portait 4E:C4:E5:8E:62:A7
# (adresse aléatoire de téléphone) parmi ses MAC, à côté des BSSID 22:66:CF:96:92:Dx.
DEV.clear(); UPDATES.clear(); CREATED.clear()
GARAGE = "20:66:CF:4B:49:69"
TWIN = "22:66:CF:4B:49:69"
PHONE = "4E:C4:E5:8E:62:A7"


class _ER:
    def async_update_entity(s, e, device_id):
        ENT[e] = device_id


_entries_for_device = er.async_entries_for_device
er.async_get = lambda h: _ER()
er.async_entries_for_device = lambda r, did, include_disabled_entities=True: [
    types.SimpleNamespace(entity_id=e, unique_id=e) for e, d in ENT.items() if d == did]
r18 = make_router()
hosts18 = lan()
# Jumeau « locally administered » du Garage, listé par la Freebox comme hôte répéteur.
hosts18[TWIN] = {"l2ident": {"id": TWIN}, "primary_name": "Repeteur Wifi Freebox Garage",
                 "host_type": "networking_device", "vendor_name": "Freebox SAS", "active": False}
# Client du Garage dont access_point.mac est une MAC non Free (même uid que le BSSID D2).
odd_ap = wifi_ap("repeater", PHONE); odd_ap["uid"] = "uid-22:66:CF:96:92:D2"
hosts18["AA:00:00:00:00:12"] = host("AA:00:00:00:00:12", "Tablette-Garage", odd_ap)
poll(r18, hosts18)
garage = r18.repeaters[GARAGE]
assert PHONE not in garage["macs"], garage["macs"]
assert PHONE in garage["ap_aliases"], garage
assert {GARAGE, TWIN, "22:66:CF:96:92:D2", "22:66:CF:96:92:D6"} <= set(garage["macs"]), garage["macs"]
assert all(wa.is_free_mac(wa.normalize_mac(m)) for m in garage["macs"]), garage["macs"]
info = r18.repeater_device_info(GARAGE, garage["name"])
assert ("mac", PHONE.lower()) not in info["connections"] and ("mac", TWIN.lower()) in info["connections"]
# Le client reste rangé sous le Garage (rattachement par ap_aliases), sans devenir un répéteur.
assert r18.repeater_canonical_mac(PHONE) == GARAGE
assert not r18.is_repeater_host(hosts18["AA:00:00:00:00:12"])
register_entities(r18, hosts18)
poll(r18, hosts18)
assert parent_name("AA:00:00:00:00:12") == "Garage", (parent_name("AA:00:00:00:00:12"), tree())

# Registre hérité d'une ancienne version : MAC du téléphone + BSSID D0 (non vu ce relevé).
gdev = R.async_get_device_by_identifier(("d", f"repeater_{GARAGE}"), "E")
gdev.connections = set(gdev.connections) | {("mac", PHONE.lower()), ("mac", "22:66:cf:96:92:d0")}
# Appareil Homexa orphelin pour le jumeau (sans identifiant Homexa), avec une entité.
stale = Dev("stale_twin", (), [("mac", TWIN.lower())], TWIN); DEV[stale.id] = stale
ENT["sensor.twin_signal"] = stale.id
# Même MAC portée par un appareil d'une autre intégration (Freebox native) : intouchable.
core = Dev("core_twin", [("freebox", TWIN)], [("mac", TWIN.lower())], TWIN); core.config_entry_id = "CORE"
DEV[core.id] = core
poll(r18, hosts18)
assert ("mac", PHONE.lower()) not in gdev.connections, gdev.connections
assert ("mac", "22:66:cf:96:92:d0") in gdev.connections  # MAC Free conservée
assert ("mac", TWIN.lower()) in gdev.connections and ("mac", GARAGE.lower()) in gdev.connections
assert "stale_twin" not in DEV and ENT.pop("sensor.twin_signal") == gdev.id
assert DEV["core_twin"].connections == {("mac", TWIN.lower())} and DEV["core_twin"].config_entry_id == "CORE"
n = len(UPDATES)
poll(r18, hosts18); poll(r18, hosts18)
assert not [u for u in UPDATES[n:] if "new_connections" in u[1]], UPDATES[n:]  # stable
print("OK : MAC étrangère retirée du répéteur, doublon du jumeau supprimé, autres intégrations intactes")

# Le téléphone à MAC aléatoire est lui-même un client LAN : jamais une MAC du répéteur.
hosts18[PHONE] = host(PHONE, "Pixel-Xav", wifi_ap("repeater", "22:66:CF:96:92:D2"))
gdev.connections = set(gdev.connections) | {("mac", PHONE.lower())}
poll(r18, hosts18)
assert PHONE not in r18.repeaters[GARAGE]["macs"] and not r18.is_repeater_host(hosts18[PHONE])
assert wa.normalize_mac(PHONE) not in r18.repeater_aliases
assert ("mac", PHONE.lower()) not in gdev.connections, gdev.connections
print("OK : téléphone à MAC aléatoire traité en client, retiré du répéteur")
er.async_get = lambda h: None
er.async_entries_for_device = _entries_for_device

# --- 11. « Connector is closed » pendant un rechargement : pas une erreur -------
import aiohttp
assert er_mod.is_shutdown_error(aiohttp.ClientConnectionError("Connector is closed."))
assert er_mod.is_shutdown_error(RuntimeError("Session is closed"))
assert er_mod.is_shutdown_error(ha["freebox_api.exceptions"].NotOpenError("x"))
assert er_mod.is_shutdown_error(ValueError("boom"), types.SimpleNamespace(closing=True))
assert not er_mod.is_shutdown_error(ValueError("boom"), types.SimpleNamespace(closing=False))
assert not er_mod.is_shutdown_error(aiohttp.ClientConnectionError("Cannot connect to host"))
assert not er_mod.is_shutdown_error(RuntimeError("autre erreur"))
r17 = make_router(); r17.closing = True
import asyncio
asyncio.run(r17.update_all())  # ne fait rien, ne lève rien
print("OK : erreurs de fermeture rétrogradées en debug, vraies erreurs conservées")
print("SIMULATION_CLIENTS_FILAIRES_WIFI_OK")
