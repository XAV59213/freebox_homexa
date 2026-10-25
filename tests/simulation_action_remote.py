"""Simulation hors HA : action freebox_homexa.remote.

Vérifie que l'action passe par la même voie que l'entité « Télécommande »
(freebox_api remote.send_key -> Freebox Player), et plus par
http://<hôte du Freebox Server>/pub/remote_control.
Lancer depuis la racine du dépôt : python3 tests/simulation_action_remote.py
"""
import asyncio
import sys
import types
from enum import Enum
from unittest.mock import MagicMock

sys.dont_write_bytecode = True  # ne pas régénérer les .pyc suivis du dépôt

for m in ("homeassistant homeassistant.config_entries homeassistant.core homeassistant.exceptions "
          "homeassistant.helpers homeassistant.helpers.device_registry homeassistant.components "
          "homeassistant.components.alarm_control_panel homeassistant.const").split():
    sys.modules[m] = MagicMock()


class ConfigEntryState(Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"


class _TranslatedError(Exception):
    def __init__(self, *args, translation_domain=None, translation_key=None,
                 translation_placeholders=None):
        super().__init__(translation_key)
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders or {}


class HomeAssistantError(_TranslatedError):
    pass


class ServiceValidationError(HomeAssistantError):
    pass


sys.modules["homeassistant.config_entries"].ConfigEntryState = ConfigEntryState
sys.modules["homeassistant.config_entries"].ConfigEntry = object
sys.modules["homeassistant.exceptions"].HomeAssistantError = HomeAssistantError
sys.modules["homeassistant.exceptions"].ServiceValidationError = ServiceValidationError
sys.modules["homeassistant.core"].callback = lambda f: f

pkg = types.ModuleType("freebox_homexa")
pkg.__path__ = ["custom_components/freebox_homexa"]
sys.modules["freebox_homexa"] = pkg
from freebox_homexa import services  # noqa: E402

DEVICES = {}
services.dr.async_get = lambda hass: types.SimpleNamespace(async_get=DEVICES.get)


class Remote:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    async def send_key(self, code, key, long_press=False, repeat=0):
        if key == self.fail:
            raise OSError("Player injoignable")
        self.sent.append((code, key))
        return True


class Player:
    def __init__(self, players):
        self.players = players

    async def get_players(self):
        return self.players


def make_entry(players, options, fail=None):
    api = types.SimpleNamespace(remote=Remote(fail), player=Player(players))
    entry = types.SimpleNamespace(
        entry_id="E", state=ConfigEntryState.LOADED, options=options,
        data={"host": "192.168.1.254", "port": 80}, runtime_data=types.SimpleNamespace(_api=api),
        disabled_by=None,
    )
    return entry, api


handlers = {}


class Hass:
    def __init__(self, entry):
        self.entry = entry
        self.data = {}
        self.config_entries = types.SimpleNamespace(async_entries=lambda domain: [entry])
        self.services = types.SimpleNamespace(
            has_service=lambda d, s: False,
            async_register=lambda d, s, h, *a, **k: handlers.__setitem__(s, h),
        )


def call(entry, **data):
    hass = Hass(entry)
    handlers.clear()
    services.async_setup_services(hass)
    return asyncio.run(handlers["remote"](types.SimpleNamespace(data=data, service="remote")))


def expect(err_key, entry, **data):
    try:
        call(entry, **data)
    except ServiceValidationError as err:
        assert err.translation_key == err_key, (err.translation_key, err_key)
        return err
    except HomeAssistantError as err:
        assert err.translation_key == err_key, (err.translation_key, err_key)
        return err
    raise AssertionError(f"erreur {err_key} attendue")


assert not hasattr(services, "PLAYER_PATH_TEMPLATE")

# Un seul Player, code par Player (comme le salon de l'utilisateur)
entry, api = make_entry([{"id": 1}], {"remote_codes": {"1": "12345678"}})
call(entry, code="power")
assert api.remote.sent == [("12345678", "power")], api.remote.sent
call(entry, code=" OK , 1,2 ")
assert api.remote.sent[1:] == [("12345678", "ok"), ("12345678", "1"), ("12345678", "2")]
print("OK : un Player -> touches via remote.send_key avec son code (plus l'hôte du Server)")

# Plusieurs Player : player_id, device_id, ou code commun
players = [{"id": 1}, {"id": 2}]
entry, api = make_entry(players, {"remote_codes": {"1": "11111111", "2": "22222222"}})
call(entry, code="mute", player_id=2)
assert api.remote.sent == [("22222222", "mute")]
DEVICES["dev-p1"] = types.SimpleNamespace(identifiers={("freebox_homexa", "player_1")}, config_entry_id="E")
call(entry, code="mute", device_id="dev-p1")
assert api.remote.sent[-1] == ("11111111", "mute")
expect("remote_multiple_players", entry, code="mute")
entry, api = make_entry(players, {"remote_code": "99999999"})
call(entry, code="home")
assert api.remote.sent == [("99999999", "home")]
print("OK : plusieurs Player -> player_id / device_id, sinon code commun, sinon erreur claire")

# Erreurs traduites
entry, api = make_entry([], {})
expect("remote_no_player", entry, code="power")
entry, api = make_entry([{"id": 1}], {})
err = expect("remote_code_missing", entry, code="power")
assert err.translation_placeholders == {"player": "1"}
entry, api = make_entry([{"id": 1}], {"remote_code": "12345678"})
err = expect("remote_invalid_key", entry, code="power,bogus")
assert api.remote.sent == [] and err.translation_placeholders == {"key": "bogus"}
expect("remote_invalid_player", entry, code="power", player_id="abc")
entry, api = make_entry([{"id": 1}], {"remote_code": "12345678"}, fail="ok")
err = expect("remote_failed", entry, code="power,ok")
assert api.remote.sent == [("12345678", "power")] and err.translation_placeholders["key"] == "ok"
call(entry, code="")  # rien à envoyer : sans erreur (comportement historique)
print("OK : aucun Player, code manquant, touche inconnue, Player invalide, échec d'envoi -> erreurs traduites")
print("SIMULATION_ACTION_REMOTE_OK")
