"""Simulation hors HA : état du capteur « Wi-Fi Freebox » (box) selon les API Wi-Fi.

Lancer depuis la racine du dépôt : python3 tests/simulation_wifi_box.py
"""
import sys, types

pkg = types.ModuleType("fh"); pkg.__path__ = []; sys.modules["fh"] = pkg
c = types.ModuleType("fh.const"); c.DOMAIN = "d"; c.REPEATER_MODEL = "F-RP01A"; c.FreeboxHomeCategory = type("C", (), {})
sys.modules["fh.const"] = c
for m in ["homeassistant", "homeassistant.config_entries", "homeassistant.core", "homeassistant.helpers",
          "homeassistant.helpers.entity_registry", "homeassistant.helpers.device_registry"]:
    sys.modules.setdefault(m, types.ModuleType(m))
sys.modules["homeassistant.config_entries"].ConfigEntry = object
sys.modules["homeassistant.core"].HomeAssistant = object
sys.modules["homeassistant.helpers.device_registry"].CONNECTION_NETWORK_MAC = "mac"


def load(name):
    m = types.ModuleType("fh." + name)
    src = open(f"custom_components/freebox_homexa/{name}.py").read().replace("from .", "from fh.")
    sys.modules["fh." + name] = m
    exec(src, m.__dict__)
    return m


load("registry_compat"); load("device_groups"); wa = load("wifi_ap")
st = wa.gateway_wifi_state
RM = "34:27:92:D9:E0:30"

# Cas utilisateur (Freebox v7 r1, Wi-Fi allumé) : /wifi/ap/ vide ou illisible, /wifi/config/ enabled.
assert st([], [], True) == (True, "enabled")
# Un AP actif, même si les autres font un DFS / sont coupés.
assert st([{"id": 0, "state": "dfs"}, {"id": 1, "state": "active"}], [], None) == (True, "active")
# Valeur en majuscules / BSS seul actif.
assert st([{"id": 0, "state": "ACTIVE"}], None, None) == (True, "active")
assert st([{"id": 0, "state": "no_active_bss"}], [{"id": "x", "state": "active"}], True) == (True, "active")
# Wi-Fi coupé par l'interrupteur : toujours hors ligne, quoi que disent les AP.
assert st([{"id": 0, "state": "active"}], [], False) == (False, "disabled")
# Planning : Wi-Fi activé mais radios arrêtées.
assert st([{"id": 0, "state": "disabled_planning"}], [{"id": "x", "state": "phy_stopped"}], True) == (False, "disabled_planning")
# Démarrage : état transitoire remonté.
assert st([{"id": 0, "state": "disabled"}, {"id": 1, "state": "starting"}], [], True) == (False, "starting")
# Valeur inconnue (firmware récent) : on suit /wifi/config/.
assert st([{"id": 0, "state": "running"}], [], True) == (True, "enabled")
assert st([{"id": 0, "state": "running"}], [], None) == (False, "running")
# Des clients Wi-Fi actifs sur la box prouvent que le Wi-Fi marche.
assert st([], [], None, active_clients=2) == (True, "active")
# Rien de lisible : inconnu (et non « Déconnecté »).
assert st([], [], None) == (None, "unknown")
assert st([{"id": 0}, "x", {"state": ""}], None, None) == (None, "unknown")

# Bout en bout via build_wifi_aps.
devices = {
    RM: {"l2ident": {"id": RM}, "attrs": {}, "host_type": "router", "active": True},
    "AA:BB:CC:00:00:01": {"l2ident": {"id": "AA:BB:CC:00:00:01"}, "primary_name": "Téléphone", "active": True,
                          "access_point": {"type": "gateway", "mac": RM, "connectivity_type": "wifi"}},
}
aps, _ = wa.build_wifi_aps(router_mac=RM, router_name="Freebox v7 (r1)", router_model="fbxgw7-r1",
                           devices=devices, radio_status=[], bss_status=[], wifi_enabled=True)
gw = aps["gateway"]
assert gw["online"] is True and gw["state"] == "active", gw
aps, _ = wa.build_wifi_aps(router_mac=RM, router_name="Freebox v7 (r1)", router_model="fbxgw7-r1",
                           devices={RM: devices[RM]}, radio_status=[{"id": 0, "state": "active"}],
                           wifi_enabled=False)
assert aps["gateway"]["online"] is False and aps["gateway"]["state"] == "disabled"
# Rétrocompatibilité : sans les nouveaux arguments.
aps, _ = wa.build_wifi_aps(router_mac=RM, router_name="F", router_model="m", devices={RM: devices[RM]},
                           radio_status=[{"id": 0, "state": "active"}])
assert aps["gateway"]["online"] is True
print("OK : capteur Wi-Fi Freebox")
