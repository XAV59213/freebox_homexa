"""Simulation hors HA : appareils partagés avec une autre intégration (revue frenck).

- ensure_lan_client_device : une MAC déjà portée par un appareil Shelly / ESPHome
  (ou partagé avec Homexa) n'est jamais renommée, modifiée, rattachée ni re-parentée ;
- async_clean_repeater_connections : un doublon de répéteur partagé n'est ni vidé
  ni supprimé ; les entités des autres intégrations ne sont jamais déplacées ;
- async_merge_repeater_devices : mêmes gardes (doublon partagé ignoré, seules nos
  entités déplacées, jamais de suppression s'il reste une entité tierce) ;
- nos propres appareils restent gérés comme avant.
Lancer depuis la racine du dépôt : python3 tests/simulation_registre_partage.py
"""
import sys
import types
from unittest.mock import MagicMock

sys.dont_write_bytecode = True  # ne pas régénérer les .pyc suivis du dépôt

MODS = """aiohttp freebox_api freebox_api.api freebox_api.api.call freebox_api.api.home
freebox_api.api.wifi freebox_api.exceptions homeassistant homeassistant.components
homeassistant.components.alarm_control_panel homeassistant.components.binary_sensor
homeassistant.components.button homeassistant.components.calendar homeassistant.components.camera
homeassistant.components.cover homeassistant.components.device_tracker
homeassistant.components.diagnostics homeassistant.components.ffmpeg
homeassistant.components.ffmpeg.camera homeassistant.components.frontend
homeassistant.components.http homeassistant.components.media_player homeassistant.components.remote
homeassistant.components.sensor homeassistant.components.switch homeassistant.config_entries
homeassistant.const homeassistant.core homeassistant.exceptions homeassistant.helpers
homeassistant.helpers.aiohttp_client homeassistant.helpers.config_validation
homeassistant.helpers.device_registry homeassistant.helpers.dispatcher homeassistant.helpers.entity
homeassistant.helpers.entity_platform homeassistant.helpers.entity_registry homeassistant.helpers.event
homeassistant.helpers.service_info homeassistant.helpers.service_info.zeroconf
homeassistant.helpers.storage homeassistant.helpers.typing homeassistant.helpers.update_coordinator
homeassistant.helpers.selector homeassistant.data_entry_flow homeassistant.util homeassistant.util.dt
homeassistant.components.websocket_api voluptuous""".split()
for m in MODS:
    sys.modules[m] = MagicMock()
sys.modules["aiohttp"].ClientError = type("ClientError", (Exception,), {})
sys.modules["freebox_api.exceptions"].HttpRequestError = type("HttpRequestError", (Exception,), {})
sys.modules["freebox_api.exceptions"].NotOpenError = type("NotOpenError", (Exception,), {})
sys.modules["freebox_api.exceptions"].AuthorizationError = type("AuthorizationError", (Exception,), {})
sys.modules["freebox_api.exceptions"].InsufficientPermissionsError = type("IPE", (Exception,), {})


class Entity:
    _attr_available = True

    @property
    def available(self):
        return self._attr_available


class ScannerEntity(Entity):
    pass


class ConfigFlow:
    def __init_subclass__(cls, **kw):
        pass


sys.modules["homeassistant.helpers.entity"].Entity = Entity
sys.modules["homeassistant.components.device_tracker"].ScannerEntity = ScannerEntity
_tracker_config = types.ModuleType("homeassistant.components.device_tracker.entity")
_tracker_config.ScannerEntity = ScannerEntity
sys.modules[_tracker_config.__name__] = _tracker_config
sys.modules["homeassistant.config_entries"].ConfigFlow = ConfigFlow
sys.modules["homeassistant.config_entries"].OptionsFlow = object
sys.modules["homeassistant.helpers.device_registry"].CONNECTION_NETWORK_MAC = "mac"

pkg = types.ModuleType("freebox_homexa")
pkg.__path__ = ["custom_components/freebox_homexa"]
sys.modules["freebox_homexa"] = pkg

from freebox_homexa import device_groups, router as R  # noqa: E402

class Dev:
    def __init__(self, i, entries, conns, idents=(), via=None, name="x"):
        self.id = i
        self.config_entries = set(entries)
        self.connections = set(conns)
        self.identifiers = set(idents)
        self.via_device_id = via
        self.name = name
        self.name_by_user = None
        self.area_id = None
        self.model = None


class Registry:
    def __init__(self, devs):
        self.devs = {d.id: d for d in devs}
        self.log = []

    def async_get_device(self, identifiers=None, connections=None):
        for d in self.devs.values():
            if connections and d.connections & set(connections):
                return d
            if identifiers and d.identifiers & set(identifiers):
                return d
        return None

    def async_get_device_by_connection(self, connection, entry_id):
        return next((d for d in self.devs.values() if connection in d.connections and d.config_entries == {entry_id}), None)

    def async_get_device_by_identifier(self, identifier, entry_id):
        return next((d for d in self.devs.values() if identifier in d.identifiers and entry_id in d.config_entries), None)

    def async_get_child_device_by_identifier(self, identifier, entry_id):
        return None

    def async_get_or_create(self, **kw):
        self.log.append(("create", kw["connections"]))
        d = Dev("new", {kw["config_entry_id"]}, kw["connections"], name=kw.get("name"))
        self.devs[d.id] = d
        return d

    def async_update_device(self, device_id, **kw):
        self.log.append(("update", device_id, tuple(sorted(kw))))
        d = self.devs[device_id]
        for k, v in kw.items():
            setattr(d, k, v)
        return d

    def async_remove_device(self, device_id):
        self.log.append(("remove", device_id))
        self.devs.pop(device_id)


from freebox_homexa import registry_compat  # noqa: E402

_entries = lambda reg, eid: [d for d in list(reg.devs.values()) if eid in d.config_entries]  # noqa: E731
for _dr in {id(m): m for m in (registry_compat.dr, device_groups.dr, R.dr)}.values():
    _dr.async_entries_for_config_entry = _entries
    _dr.CONNECTION_NETWORK_MAC = "mac"

# --- ensure_lan_client_device ------------------------------------------------
MAC = "AA:BB:CC:DD:EE:FF"


def router_with(reg):
    R.dr.async_get = lambda hass: reg
    r = R.FreeboxRouter.__new__(R.FreeboxRouter)
    r.hass = None
    r.entry_id = "E"
    r.create_lan_devices = True
    r.devices = {MAC: {"l2ident": {"id": MAC}, "primary_name": "Prise salon", "vendor_name": "Shelly"}}
    r.lan_device_ids = {}
    r.lan_client_placements = {}
    r.tracked_lan_macs = {"AABBCCDDEEFF"}
    r._is_lan_client = lambda d: True
    r._is_current_repeater_device = lambda d: False
    r._stale_repeater_idents = lambda d: set()
    r.lan_client_parent = lambda mac, name: "group"
    r._placement_of = lambda pid: None
    return r


conn = ("mac", MAC.lower())
for label, entries in (("Shelly seul", {"SHELLY"}), ("Shelly + Homexa", {"SHELLY", "E"})):
    shelly = Dev("shelly", entries, {conn}, name="Shelly Plug")
    reg = Registry([shelly])
    assert router_with(reg).ensure_lan_client_device(MAC) is None
    assert reg.log == [], (label, reg.log)
    assert shelly.name == "Shelly Plug" and shelly.via_device_id is None and shelly.config_entries == entries
    print(f"OK : appareil {label} avec la même MAC -> intact (ni renommé, ni rattaché, ni déplacé)")

reg = Registry([])
assert router_with(reg).ensure_lan_client_device(MAC) == "new"
assert reg.log[0][0] == "create" and ("update", "new", ("via_device_id",)) in reg.log, reg.log
print("OK : MAC inconnue -> appareil Homexa créé et rangé (comme avant)")

own = Dev("own", {"E"}, {conn})
reg = Registry([own])
assert router_with(reg).ensure_lan_client_device(MAC) == "own" and own.via_device_id == "group"
print("OK : notre propre appareil client -> toujours rangé sous son groupe")

# --- async_clean_repeater_connections ----------------------------------------
er = sys.modules["homeassistant.helpers.entity_registry"]
sys.modules["homeassistant.helpers"].entity_registry = er


class Ent:
    def __init__(self, eid, entry):
        self.entity_id = eid
        self.config_entry_id = entry


ents = {}
moved = []
er.async_get = lambda hass: er
er.async_entries_for_device = lambda reg, did, include_disabled_entities=True: ents.get(did, [])
er.async_update_entity = lambda eid, device_id=None: moved.append((eid, device_id))

REP = "00:24:D4:00:00:01"
TWIN = "22:66:cf:4b:49:69"
repeaters = {REP: {"macs": [REP, TWIN]}}


def run(dup_entries, dup_ents):
    rep = Dev("rep", {"E"}, {("mac", REP.lower())}, {("freebox_homexa", f"repeater_{REP}")})
    dup = Dev("dup", dup_entries, {("mac", TWIN)})
    reg = Registry([rep, dup])
    device_groups.dr.async_get = lambda hass: reg
    ents.clear()
    ents["dup"] = dup_ents
    moved.clear()
    device_groups.async_clean_repeater_connections(None, "E", "srv", repeaters)
    return reg


reg = run({"E", "ESPHOME"}, [Ent("sensor.esp", "ESPHOME"), Ent("sensor.homexa", "E")])
assert "dup" in reg.devs and moved == [] and not [x for x in reg.log if x[0] == "remove"], reg.log
print("OK : doublon de répéteur partagé (ESPHome) -> ni entités déplacées ni suppression")

reg = run({"E"}, [Ent("sensor.esp", "ESPHOME"), Ent("sensor.homexa", "E")])
assert "dup" in reg.devs and moved == [], moved
print("OK : appareil portant une entité d'une autre intégration -> intact")

reg = run({"E"}, [Ent("sensor.homexa", "E")])
assert "dup" not in reg.devs and moved == [("sensor.homexa", "rep")], (reg.log, moved)
print("OK : doublon 100 % Homexa -> entités vers le répéteur puis suppression (comme avant)")

# --- async_merge_repeater_devices --------------------------------------------
ROUTER = "AA:00:00:00:00:01"
ALIAS = "00:24:D4:00:00:02"
merge_reps = {REP: {"macs": [REP, ALIAS], "name": "Repeteur"}}
entry = types.SimpleNamespace(entry_id="E")


def run_merge(dup_entries, dup_ents):
    rep = Dev("rep", {"E"}, {("mac", REP.lower())}, {("freebox_homexa", f"repeater_{REP}")})
    dup = Dev("dup", dup_entries, {("mac", ALIAS.lower())}, {("freebox_homexa", f"repeater_{ALIAS}")})
    reg = Registry([rep, dup])
    device_groups.dr.async_get = lambda hass: reg
    ents.clear()
    ents["dup"] = dup_ents
    moved.clear()
    n = device_groups.async_merge_repeater_devices(None, entry, ROUTER, merge_reps)
    return reg, n


reg, n = run_merge({"E", "ESPHOME"}, [Ent("sensor.esp", "ESPHOME"), Ent("sensor.homexa", "E")])
assert "dup" in reg.devs and moved == [] and n == 0, (reg.log, moved)
assert not [x for x in reg.log if x[0] == "remove"], reg.log
print("OK : fusion — doublon partagé (ESPHome) -> ignoré, ni entités déplacées ni suppression")

reg, n = run_merge({"E"}, [Ent("sensor.esp", "ESPHOME"), Ent("sensor.homexa", "E")])
assert "dup" in reg.devs and moved == [("sensor.homexa", "rep")] and n == 0, (reg.log, moved)
print("OK : fusion — entité tierce -> seule notre entité déplacée, doublon conservé")

reg, n = run_merge({"E"}, [Ent("sensor.homexa", "E")])
assert "dup" not in reg.devs and moved == [("sensor.homexa", "rep")] and n == 1, (reg.log, moved)
print("OK : fusion — doublon 100 % Homexa -> fusionné puis supprimé (comme avant)")
print("SIMULATION_REGISTRE_PARTAGE_OK")
