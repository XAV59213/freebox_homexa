"""Simulation hors HA : journal d'appels sans données personnelles dans l'état.

- capteur « Derniers appels Freebox » : état = appels non lus, aucun attribut ;
- capteur « Appels manqués Freebox » : état = manqués non lus, aucun nom/numéro ;
- format_calls (servi à la carte par freebox_homexa/calls) : tri, limite, champs.
Lancer depuis la racine du dépôt : python3 tests/simulation_journal_appels.py
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
sys.modules["homeassistant.config_entries"].ConfigFlow = ConfigFlow
sys.modules["homeassistant.config_entries"].OptionsFlow = object
sys.modules["homeassistant.helpers.device_registry"].CONNECTION_NETWORK_MAC = "mac"

pkg = types.ModuleType("freebox_homexa")
pkg.__path__ = ["custom_components/freebox_homexa"]
sys.modules["freebox_homexa"] = pkg

import datetime as _dt  # noqa: E402

sys.modules["homeassistant.util"].dt.utc_from_timestamp = lambda ts: _dt.datetime.fromtimestamp(ts, _dt.timezone.utc)
sys.modules["homeassistant.core"].callback = lambda f: f


class SensorEntity(Entity):
    pass


sys.modules["homeassistant.components.sensor"].SensorEntity = SensorEntity
# Real HA descriptions are dataclasses (including dataclasses.replace support).
from dataclasses import dataclass

@dataclass
class SensorDescription:
    key: str
    name: str = ""
    icon: str | None = None
    translation_key: str | None = None
    device_class: object = None
    native_unit_of_measurement: object = None
    entity_category: object = None

sys.modules["homeassistant.components.sensor"].SensorEntityDescription = SensorDescription
_tnt = types.ModuleType("freebox_homexa.tnt_sensor")
_tnt.HomexaTntSensor = object
sys.modules["freebox_homexa.tnt_sensor"] = _tnt
from freebox_homexa import calls_ws, sensor  # noqa: E402

CALLS = [
    {"name": "Naomie", "number": "0601020304", "type": "missed", "datetime": 1793460000, "new": True},
    {"name": "", "number": "0605060708", "type": "accepted", "datetime": 1793470000, "duration": 125, "new": False},
    {"name": "Oceane", "number": "0611", "type": "missed", "datetime": 1793450000, "new": False},
    {"name": "Bureau", "number": "0622", "type": "outgoing", "datetime": 1793440000, "duration": 30, "new": True},
]


class Router:
    mac = "srv"
    device_info = None
    call_list = CALLS


log = sensor.FreeboxCallLogSensor(Router(), sensor.CALL_LOG_SENSOR)
log.async_update_state()
assert log._attr_native_value == 2
assert not getattr(log, "extra_state_attributes", None), log.extra_state_attributes
print("OK : Derniers appels -> état 2 (non lus), aucun attribut (ni nom ni numéro)")

missed = sensor.FreeboxCallSensor(Router(), sensor.CALL_SENSORS[0])
missed.async_update_state()
assert missed._attr_native_value == 1
assert not getattr(missed, "extra_state_attributes", None)
print("OK : Appels manqués -> état 1, plus de nom dans les attributs")

out = calls_ws.format_calls(CALLS, 3)
assert [c["type"] for c in out] == ["accepted", "missed", "missed"], out
assert out[0]["name"] == "0605060708" and out[0]["duration"] == 125
assert set(out[0]) == {"name", "number", "type", "datetime", "duration", "new"}
assert out[0]["datetime"].startswith("2026-")
print("OK : format_calls -> du plus récent au plus ancien, limite respectée")
print("SIMULATION_JOURNAL_APPELS_OK")
