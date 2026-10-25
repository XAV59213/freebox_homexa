"""Simulation hors HA : option « Créer des appareils pour les clients réseau ».

- nouvelle installation : option désactivée par défaut ;
- entrée existante (1.1, option jamais réglée) : migration 1.2 -> True, rien ne change ;
- entrée existante avec un choix explicite : choix conservé ;
- option désactivée : aucun appareil client créé / déplacé, tracker non relié par
  Homexa, appareils partagés avec une autre intégration jamais supprimés.
Lancer depuis la racine du dépôt : python3 tests/simulation_option_appareils_clients.py
"""
import asyncio
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
sys.modules["homeassistant.config_entries"].ConfigFlow = ConfigFlow
sys.modules["homeassistant.config_entries"].OptionsFlow = object
sys.modules["homeassistant.helpers.device_registry"].CONNECTION_NETWORK_MAC = "mac"

pkg = types.ModuleType("freebox_homexa")
pkg.__path__ = ["custom_components/freebox_homexa"]
sys.modules["freebox_homexa"] = pkg

from freebox_homexa import const  # noqa: E402
init = __import__("freebox_homexa.__init__", fromlist=["x"])  # noqa: E402
from freebox_homexa import config_flow, device_groups, device_tracker, router as R  # noqa: E402

# --- Défaut et version du flux ------------------------------------------------
assert const.DEFAULT_CREATE_LAN_DEVICES is False
assert (config_flow.FreeboxFlowHandler.VERSION, config_flow.FreeboxFlowHandler.MINOR_VERSION) == (1, 2)
print("OK : nouvelle installation -> option décochée par défaut, flux en 1.2")


# --- Migration --------------------------------------------------------------------
class Entry:
    def __init__(self, options, version=1, minor=1):
        self.options = options
        self.version = version
        self.minor_version = minor
        self.entry_id = "E"


class Hass:
    def __init__(self):
        self.config_entries = self

    def async_update_entry(self, entry, options=None, minor_version=None):
        if options is not None:
            entry.options = options
        if minor_version is not None:
            entry.minor_version = minor_version


async def migrate(entry):
    return await init.async_migrate_entry(Hass(), entry)

old = Entry({"track_lan_clients": True})
assert asyncio.run(migrate(old)) is True
assert old.options == {"track_lan_clients": True, "create_lan_devices": True}, old.options
assert old.minor_version == 2
assert const.option_enabled(old, const.CONF_CREATE_LAN_DEVICES, const.DEFAULT_CREATE_LAN_DEVICES)
print("OK : entrée existante sans réglage -> create_lan_devices: True (aucun changement)")

chose_off = Entry({"create_lan_devices": False})
asyncio.run(migrate(chose_off))
assert chose_off.options["create_lan_devices"] is False and chose_off.minor_version == 2
chose_on = Entry({"create_lan_devices": True})
asyncio.run(migrate(chose_on))
assert chose_on.options["create_lan_devices"] is True
print("OK : choix explicite (coché ou décoché) conservé")

fresh = Entry({}, minor=2)  # nouvelle entrée sans option (cas limite)
asyncio.run(migrate(fresh))
assert fresh.options == {}
assert not const.option_enabled(fresh, const.CONF_CREATE_LAN_DEVICES, const.DEFAULT_CREATE_LAN_DEVICES)
assert asyncio.run(migrate(Entry({}, version=2))) is False
print("OK : entrée 1.2 non retouchée ; version future refusée")

# --- Option désactivée : rien de créé / déplacé ---------------------------------
calls = []
reg = MagicMock()
reg.async_get_or_create.side_effect = lambda **kw: calls.append(("create", kw))
reg.async_update_device.side_effect = lambda *a, **kw: calls.append(("update", a, kw))
R.dr.async_get = lambda hass: reg
r = R.FreeboxRouter.__new__(R.FreeboxRouter)
r.hass = None
r.create_lan_devices = False
r.devices = {"AA:BB:CC:DD:EE:FF": {"l2ident": {"id": "AA:BB:CC:DD:EE:FF"}, "attrs": None}}
r.lan_device_ids = {"AABBCCDDEEFF": "old"}
r.lan_client_placements = {"AABBCCDDEEFF": "lan_wifi"}
r.tracked_lan_macs = {"AABBCCDDEEFF"}
assert r.ensure_lan_client_device("AA:BB:CC:DD:EE:FF") is None
assert calls == [] and not r.lan_device_ids and not r.lan_client_placements
print("OK : option désactivée -> aucun appareil client créé ni déplacé, pas de placement")

t = device_tracker.FreeboxDevice.__new__(device_tracker.FreeboxDevice)
t._create_lan_devices = False
t._lan_client = True
t._router = MagicMock()
t.registry_entry = MagicMock()
t.hass = object()
t._async_link_device()
t._router.ensure_lan_client_device.assert_not_called()
print("OK : option désactivée -> le tracker n'est pas relié par Homexa (comportement HA)")


class Dev:
    def __init__(self, i, entries, conns, idents=()):
        self.id = i
        self.config_entries = set(entries)
        self.connections = set(conns)
        self.identifiers = set(idents)

devs = [
    Dev("own", {"E"}, {("mac", "aa:aa:aa:aa:aa:01")}),
    Dev("shared", {"E", "SHELLY"}, {("mac", "aa:aa:aa:aa:aa:02")}),
    Dev("server", {"E"}, {("mac", "srv")}, {("freebox_homexa", "srv")}),
]
removed = []
device_groups.dr.async_get = lambda hass: MagicMock()
device_groups.dr.async_entries_for_config_entry = lambda registry, eid: devs
device_groups.dr.CONNECTION_NETWORK_MAC = "mac"
device_groups.remove_device = lambda registry, i: removed.append(i)
n = device_groups.async_remove_lan_client_devices(None, Entry({}), "srv")
assert removed == ["own"] and n == 1, removed
print("OK : désactivation -> seuls les appareils clients 100 % Homexa sont retirés")
print("SIMULATION_OPTION_APPAREILS_CLIENTS_OK")
