"""Simulation hors HA : correctifs issue #106 (home/nodes, Player POP, reload).

- home_granted : distinguer insufficient_rights d'une autre HttpRequestError ;
- Player api_available=False sans id : message actionnable, pas de contrôle inventé ;
- OptionsFlowWithReload à la place de l'update listener (HA 2026.12).
Lancer depuis la racine du dépôt : python3 tests/simulation_issue106_home_player.py
"""
import asyncio
import logging
import sys
import types
from unittest.mock import MagicMock

sys.dont_write_bytecode = True

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


class HttpRequestError(Exception):
    pass


class InsufficientPermissionsError(HttpRequestError):
    pass


class NotOpenError(Exception):
    pass


class AuthorizationError(Exception):
    pass


sys.modules["freebox_api.exceptions"].HttpRequestError = HttpRequestError
sys.modules["freebox_api.exceptions"].InsufficientPermissionsError = InsufficientPermissionsError
sys.modules["freebox_api.exceptions"].NotOpenError = NotOpenError
sys.modules["freebox_api.exceptions"].AuthorizationError = AuthorizationError
sys.modules["freebox_api.exceptions"].InvalidTokenError = type("InvalidTokenError", (Exception,), {})


class Entity:
    _attr_available = True

    @property
    def available(self):
        return self._attr_available


class ConfigFlow:
    def __init_subclass__(cls, **kw):
        pass


class OptionsFlow:
    pass


class OptionsFlowWithReload(OptionsFlow):
    pass


sys.modules["homeassistant.helpers.entity"].Entity = Entity
sys.modules["homeassistant.config_entries"].ConfigFlow = ConfigFlow
sys.modules["homeassistant.config_entries"].OptionsFlow = OptionsFlow
sys.modules["homeassistant.config_entries"].OptionsFlowWithReload = OptionsFlowWithReload
sys.modules["homeassistant.config_entries"].SOURCE_REAUTH = "reauth"
sys.modules["homeassistant.config_entries"].SOURCE_RECONFIGURE = "reconfigure"
sys.modules["homeassistant.helpers.device_registry"].CONNECTION_NETWORK_MAC = "mac"
sys.modules["homeassistant.core"].callback = lambda f: f
sys.modules["homeassistant.const"].CONF_HOST = "host"
sys.modules["homeassistant.const"].CONF_PORT = "port"

pkg = types.ModuleType("freebox_homexa")
pkg.__path__ = ["custom_components/freebox_homexa"]
sys.modules["freebox_homexa"] = pkg

from freebox_homexa import errors, player_remote  # noqa: E402
from freebox_homexa import config_flow as cf  # noqa: E402
from freebox_homexa import router as R  # noqa: E402

# --- api_error_code / is_permission_denied -----------------------------------
perm = InsufficientPermissionsError(
    'Request failed (APIResponse: {"success": false, "error_code": "insufficient_rights", '
    '"missing_right": "home", "msg": "no"})'
)
other = HttpRequestError(
    'Request failed (APIResponse: {"success": false, "error_code": "nodev", "msg": "missing"})'
)
assert errors.api_error_code(perm) == "insufficient_rights"
assert errors.api_error_code(other) == "nodev"
assert errors.is_permission_denied(perm) is True
assert errors.is_permission_denied(other) is False
assert errors.is_permission_denied(HttpRequestError("access denied by firewall")) is True
print("OK : distinction insufficient_rights / autre HttpRequestError")

# --- update_home_devices messages --------------------------------------------
logs: list[tuple[int, str]] = []


class _Handler(logging.Handler):
    def emit(self, record):
        logs.append((record.levelno, record.getMessage()))


handler = _Handler()
R._LOGGER.addHandler(handler)
R._LOGGER.setLevel(logging.DEBUG)


class _Lock:
    def locked(self):
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _router():
    r = R.FreeboxRouter.__new__(R.FreeboxRouter)
    r.home_granted = True
    r.closing = False
    r._home_update_lock = _Lock()
    r.home_devices = {}
    r.hass = MagicMock()
    r.mac = "AA:BB:CC:DD:EE:FF"
    r._host = "mafreebox.freebox.fr"
    r._api = MagicMock()
    return r


async def _run_home(exc):
    logs.clear()
    r = _router()

    async def boom():
        raise exc

    r._api.home.get_home_nodes = boom
    await r.update_home_devices()
    return r, list(logs)


r, msgs = asyncio.run(_run_home(perm))
assert r.home_granted is False
assert any("n'est pas autorisé" in m for _, m in msgs)
assert not any("pas forcément un refus" in m for _, m in msgs)
print("OK : refus de droit -> message permission (pas le faux négatif générique)")

r, msgs = asyncio.run(_run_home(other))
assert r.home_granted is False
assert any("pas forcément un refus" in m or "home/nodes" in m for _, m in msgs)
assert not any(m == "L'accès aux appareils domestiques n'est pas autorisé" for _, m in msgs)
print("OK : autre erreur home/nodes -> message neutre (pas « maison connectée »)")

# --- Player POP api_available=False ------------------------------------------
POP = {
    "mac": "aa:bb:cc:dd:ee:ff",
    "stb_type": "stb_v8",
    "api_available": False,
    "device_name": "Freebox Player POP",
    "device_model": "fbx8am",
    "reachable": True,
}
DELTA = {
    "id": 1,
    "api_available": True,
    "device_name": "Salon",
    "device_model": "fbx7hd-delta",
}
assert player_remote.player_api_ready(POP) is False
assert player_remote.player_api_ready(DELTA) is True
assert player_remote.player_api_ready({"id": 2}) is True  # clé absente = OK
msg = player_remote.player_skip_message(POP, "media_player")
assert "Freebox Player POP" in msg
assert "api_available=False" in msg
assert "Android TV" in msg
ready, skipped = player_remote.filter_ready_players([POP, DELTA], log_skipped=False)
assert [p["id"] for p in ready] == [1] and skipped == [POP]
print("OK : Player POP sans id / api_available=False filtré, message actionnable")

# freebox-api players[0]["id"] : on ne passe jamais un player non prêt aux entités
assert all("id" in p for p in ready)
print("OK : seuls les Players avec id sont exposés (évite players[0]['id'] non gardé)")

# --- OptionsFlowWithReload ---------------------------------------------------
assert issubclass(cf.FreeboxOptionsFlowHandler, OptionsFlowWithReload)
assert issubclass(cf.FreeboxOptionsFlowHandler, OptionsFlow)
init_src = open("custom_components/freebox_homexa/__init__.py", encoding="utf-8").read()
assert "add_update_listener" not in init_src
assert "OptionsFlowWithReload" in open(
    "custom_components/freebox_homexa/config_flow.py", encoding="utf-8"
).read()
print("OK : OptionsFlowWithReload sans update listener (HA 2026.12)")


# --- retry Player sans async_create_task hors boucle -------------------------
src = open("custom_components/freebox_homexa/player_remote.py", encoding="utf-8").read()
assert "async_schedule_player_api_retry" in src
assert "async_call_later" in src
assert "lambda n: hass.async_create_task" not in src
assert "async_call_later(hass, PLAYER_API_RETRY_DELAYS[0], _attempt)" in src
print("OK : retry Player passe la coroutine à async_call_later (thread-safe)")

print("Tous les tests issue #106 sont verts.")
