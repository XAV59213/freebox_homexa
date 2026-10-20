"""Accès au registre des appareils compatible HA 2026.8+ (un appareil = une entrée).

Utilise les API récentes (async_get_device_by_identifier / _by_connection,
DeviceEntry.config_entry_id, async_remove_device) et retombe sur les anciennes
uniquement si elles sont absentes.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import device_registry as dr


def device_entry_id(device: Any) -> str | None:
    """Entrée de configuration propriétaire de l'appareil."""
    entry_id = getattr(device, "config_entry_id", None)
    if entry_id is not None or hasattr(type(device), "config_entry_id"):
        return entry_id
    entries = getattr(device, "config_entries", None) or set()
    return next(iter(entries), None)


def device_owned_by(device: Any, entry_id: str) -> bool:
    return device is not None and device_entry_id(device) == entry_id


def get_device_by_identifier(registry: Any, identifier: tuple[str, str], entry_id: str) -> Any:
    """Appareil de cette entrée portant cet identifiant (None sinon)."""
    getter = getattr(registry, "async_get_device_by_identifier", None)
    if getter is not None:
        device = getter(identifier, entry_id)
        if device is None:  # appareil enfant (via_device) éventuel
            child = getattr(registry, "async_get_child_device_by_identifier", None)
            if child is not None:
                device = child(identifier, entry_id)
        return device
    device = registry.async_get_device(identifiers={identifier})
    return device if device_owned_by(device, entry_id) else None


def get_device_by_connection(registry: Any, connection: tuple[str, str], entry_id: str) -> Any:
    getter = getattr(registry, "async_get_device_by_connection", None)
    if getter is not None:
        return getter(connection, entry_id)
    device = registry.async_get_device(connections={connection})
    return device if device_owned_by(device, entry_id) else None


def entry_devices(registry: Any, entry_id: str) -> list[Any]:
    """Appareils de cette entrée (sans passer par registry.devices)."""
    return list(dr.async_entries_for_config_entry(registry, entry_id))


def remove_device(registry: Any, device_id: str) -> None:
    """Supprime l'appareil (remplace remove_config_entry_id, déprécié)."""
    registry.async_remove_device(device_id)
