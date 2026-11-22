"""Entités du Freebox Server pour la carte Lovelace, par entrée de configuration.

La carte demande ``freebox_homexa/server_entities``. Les entity_id sont lus dans
le registre à partir de l'entrée et du unique_id (ou de sa clé), jamais du nom
affiché : un renommage ou une deuxième Freebox ne mélange pas les rôles.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import ERR_NOT_FOUND
from homeassistant.components.websocket_api.decorators import websocket_command
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .device_groups import GROUP_SENSOR_UID_PART
from .registry_compat import get_device_by_identifier

if TYPE_CHECKING:
    from .router import FreeboxConfigEntry

_WS_FLAG = "_server_ws"

# Rôles dont la valeur est une liste d'entity_id (plusieurs ventilateurs, disques…).
_LIST_ROLES = frozenset({
    "health.temperatures",
    "health.fans",
    "health.disks",
    "health.raid",
    "network.access_points",
    "network.wifi_clients",
    "network.lan_groups",
})


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _named(items: Sequence[object], key: str) -> str:
    """Nom historique porté par le unique_id (pas la clé technique)."""
    for item in items:
        if getattr(item, "key", None) != key:
            continue
        name = getattr(item, "name", None)
        if isinstance(name, str):
            return name
    raise ValueError(f"Missing description {key}")


def _keyed(items: Sequence[object], key: str) -> str:
    """Clé technique portée par le unique_id (disque, RAID)."""
    for item in items:
        if getattr(item, "key", None) == key:
            return key
    raise ValueError(f"Missing description {key}")


def description_names() -> dict[str, str]:
    """Libellés et clés réellement utilisés pour construire les unique_id."""
    from .binary_sensor import RAID_SENSORS
    from .button import BUTTON_DESCRIPTIONS
    from .sensor import CALL_SENSORS, CONNECTION_SENSORS, DISK_PARTITION_SENSORS
    from .switch import SWITCH_DESCRIPTIONS

    return {
        "rate_down": _named(CONNECTION_SENSORS, "rate_down"),
        "rate_up": _named(CONNECTION_SENSORS, "rate_up"),
        "ipv4": _named(CONNECTION_SENSORS, "ipv4"),
        "uptime": _named(CONNECTION_SENSORS, "uptime"),
        "missed": _named(CALL_SENSORS, "missed"),
        "wifi": _named(SWITCH_DESCRIPTIONS, "wifi"),
        "reboot": _named(BUTTON_DESCRIPTIONS, "reboot"),
        "disk": _keyed(DISK_PARTITION_SENSORS, "partition_free_space"),
        "raid": _keyed(RAID_SENSORS, "raid_degraded"),
    }


def entity_role(
    mac: str, domain: str, unique_id: str, names: Mapping[str, str] | None = None
) -> str | None:
    """Rôle ``groupe.clé`` d'une entité, ou None si elle n'appartient pas à la carte."""
    resolved = description_names() if names is None else names
    if not mac or not unique_id.startswith(mac):
        return None
    fixed = {
        ("sensor", f"{mac} {resolved['rate_down']}"): "connection.rate_down",
        ("sensor", f"{mac} {resolved['rate_up']}"): "connection.rate_up",
        ("sensor", f"{mac} {resolved['ipv4']}"): "connection.ipv4",
        ("sensor", f"{mac} {resolved['uptime']}"): "system.uptime",
        # ScannerEntity expose la MAC comme unique_id (pas le _attr_unique_id).
        ("device_tracker", mac): "connection.attributes",
        ("switch", f"{mac} {resolved['wifi']}"): "network.wifi",
        ("sensor", f"{mac} {resolved['missed']}"): "calls.missed",
        ("button", f"{mac} {resolved['reboot']}"): "actions.reboot",
        ("binary_sensor", f"{mac}_wifi_ap_gateway"): "network.access_points",
        ("sensor", f"{mac}_wifi_repeater_count"): "network.repeater_count",
    }
    found = fixed.get((domain, unique_id))
    if found is not None:
        return found
    if domain == "sensor" and unique_id.startswith(f"{mac} fan_") and " " not in unique_id[len(mac) + 1:]:
        return "health.fans"
    if domain == "sensor" and unique_id.startswith(f"{mac} Freebox "):
        return "health.temperatures"
    if domain == "sensor":
        parts = unique_id.split(" ")
        if len(parts) == 4 and parts[0] == mac and parts[1] == resolved["disk"]:
            return "health.disks"
    if domain == "binary_sensor" and unique_id.startswith(f"{mac}_{resolved['raid']}_"):
        return "health.raid"
    if domain == "binary_sensor" and unique_id.startswith(f"{mac}_repeater_"):
        return "network.access_points"
    if domain == "sensor" and unique_id.startswith(f"{mac}_wifi_clients_"):
        return "network.wifi_clients"
    if domain == "sensor" and unique_id.startswith(f"{mac}{GROUP_SENSOR_UID_PART}"):
        return "network.lan_groups"
    return None


def _blank(entry_id: str) -> dict[str, object]:
    return {
        "entry_id": entry_id,
        "connection": {"rate_down": None, "rate_up": None, "ipv4": None, "attributes": None},
        "system": {"uptime": None, "firmware": None, "model": None, "pretty_name": None},
        "health": {"temperatures": [], "fans": [], "disks": [], "raid": []},
        "network": {
            "wifi": None,
            "access_points": [],
            "wifi_clients": [],
            "repeater_count": None,
            "lan_groups": [],
        },
        "calls": {"missed": None},
        "actions": {"reboot": None},
    }


def _put(view: dict[str, object], role: str, entity_id: str) -> None:
    group_name, key = role.split(".", 1)
    group = view[group_name]
    if not isinstance(group, dict):
        return
    if role in _LIST_ROLES:
        bucket = group.get(key)
        if isinstance(bucket, list) and entity_id not in bucket:
            bucket.append(entity_id)
        return
    if group.get(key) is None:
        group[key] = entity_id


def _sort_lists(view: dict[str, object]) -> None:
    for role in _LIST_ROLES:
        group_name, key = role.split(".", 1)
        group = view[group_name]
        if not isinstance(group, dict):
            continue
        bucket = group.get(key)
        if isinstance(bucket, list):
            bucket.sort()


def server_entities_for_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
    can_read: Callable[[str], bool],
) -> dict[str, object] | None:
    """Vue d'une Freebox chargée. None si l'entrée n'a pas de routeur identifiable."""
    router = entry.runtime_data
    mac = getattr(router, "mac", None)
    if not isinstance(mac, str) or not mac:
        return None
    view = _blank(entry.entry_id)
    device = get_device_by_identifier(dr.async_get(hass), (DOMAIN, mac), entry.entry_id)
    pretty = _text(getattr(device, "name", None)) or _text(getattr(router, "name", None))
    model = _text(getattr(device, "model", None)) or _text(getattr(router, "model", None))
    firmware = _text(getattr(device, "sw_version", None)) or _text(getattr(router, "_sw_v", None))
    system = view["system"]
    if isinstance(system, dict):
        system["pretty_name"] = pretty
        system["model"] = model
        system["firmware"] = firmware
    names = description_names()
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        role = entity_role(mac, reg_entry.domain, reg_entry.unique_id, names)
        if role is None or not can_read(reg_entry.entity_id):
            continue
        _put(view, role, reg_entry.entity_id)
    _sort_lists(view)
    return view


def _loaded_entries(hass: HomeAssistant) -> list[FreeboxConfigEntry]:
    return [
        entry for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]


@callback
def async_register_server_websocket_api(hass: HomeAssistant) -> None:
    """Enregistre la commande une seule fois (async_setup peut être rappelé)."""
    store = hass.data.setdefault(DOMAIN, {})
    if isinstance(store, dict) and store.get(_WS_FLAG):
        return
    websocket_api.async_register_command(hass, websocket_server_entities)
    if isinstance(store, dict):
        store[_WS_FLAG] = True


@websocket_command({
    vol.Required("type"): "freebox_homexa/server_entities",
    vol.Optional("entry_id"): str,
})
@callback
def websocket_server_entities(
    hass: HomeAssistant, connection: ActiveConnection, msg: Mapping[str, object]
) -> None:
    """Entity_id du serveur, groupés par rôle, pour une entrée ou toutes."""
    message_id = msg["id"]
    if not isinstance(message_id, int):
        raise vol.Invalid("Invalid message id", path=["id"])
    requested = msg.get("entry_id")
    if requested is not None and (not isinstance(requested, str) or not requested.strip()):
        raise vol.Invalid("Invalid entry id", path=["entry_id"])
    entries = _loaded_entries(hass)
    if isinstance(requested, str):
        entries = [entry for entry in entries if entry.entry_id == requested]
        if not entries:
            connection.send_error(message_id, ERR_NOT_FOUND, "Aucune Freebox Homexa chargée")
            return

    def can_read(entity_id: str) -> bool:
        return connection.user.permissions.check_entity(entity_id, POLICY_READ)

    payload: list[dict[str, object]] = []
    for entry in entries:
        view = server_entities_for_entry(hass, entry, can_read)
        if view is not None:
            payload.append(view)
    if isinstance(requested, str) and not payload:
        connection.send_error(message_id, ERR_NOT_FOUND, "Aucune Freebox Homexa chargée")
        return
    connection.send_result(message_id, {"entries": payload})
