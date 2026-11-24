"""Accès au registre des appareils compatible HA 2026.8+ (un appareil = une entrée).

Utilise les API récentes (async_get_device_by_identifier / _by_connection,
DeviceEntry.config_entry_id, async_remove_device) et retombe sur les anciennes
uniquement si elles sont absentes.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

_LOGGER = logging.getLogger(__name__)


def device_entry_id(device: object) -> str | None:
    """Entrée de configuration propriétaire de l'appareil."""
    entry_id: object = getattr(device, "config_entry_id", None)
    if entry_id is not None or hasattr(type(device), "config_entry_id"):
        return entry_id if isinstance(entry_id, str) else None
    entries: object = getattr(device, "config_entries", None)
    if not isinstance(entries, (set, frozenset, list, tuple)):
        return None
    return next((owner for owner in entries if isinstance(owner, str)), None)


def device_owned_by(device: object, entry_id: str) -> bool:
    return device is not None and device_entry_id(device) == entry_id


def device_entries(device: object) -> set[str]:
    """Toutes les entrées de configuration liées à l'appareil."""
    entry_id: object = getattr(device, "config_entry_id", None)
    if entry_id is not None or hasattr(type(device), "config_entry_id"):
        # HA 2026.8+ : un appareil = une entrée (config_entries, déprécié, vaut
        # {config_entry_id}) ; on évite de lire la propriété dépréciée.
        return {entry_id} if isinstance(entry_id, str) and entry_id else set()
    entries: object = getattr(device, "config_entries", None)
    if not isinstance(entries, (set, frozenset, list, tuple)):
        return set()
    return {owner for owner in entries if isinstance(owner, str)}


def shared_with_other_entries(device: object, entry_id: str) -> bool:
    """True si l'appareil appartient (aussi) à une autre entrée / intégration.

    Même garde que async_remove_lan_client_devices : un tel appareil n'est
    jamais renommé, déplacé, re-parenté, modifié ni supprimé par Homexa.
    """
    if device is None:
        return False
    owner: object = getattr(device, "config_entry_id", None)
    if owner is not None or hasattr(type(device), "config_entry_id"):
        if owner is not None and not isinstance(owner, str):
            return True  # Unknown owner is protected, never treated as ours.
    else:
        owners: object = getattr(device, "config_entries", None)
        if owners is not None:
            if not isinstance(owners, (set, frozenset, list, tuple)):
                return True
            if any(not isinstance(value, str) for value in owners):
                return True
    return bool(device_entries(device) - {entry_id})


def foreign_device_with_connection(
    registry: Any, connection: tuple[str, str], entry_id: str
) -> Any:
    """Appareil d'une AUTRE intégration portant cette connexion (MAC), dans tout le registre.

    Couvre aussi l'appareil auquel Home Assistant a relié notre tracker
    (ScannerEntity) : il appartient à l'autre intégration.
    """
    device = registry.async_get_device(connections={connection})
    return device if shared_with_other_entries(device, entry_id) else None


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


def as_version(value: object) -> str | None:
    """sw_version / hw_version : toujours une chaîne (HA 2026.12 refuse les int)."""
    if value is None or value == "":
        return None
    return str(value)


def device_is_disabled(device: object | None) -> bool:
    """True si l'appareil est désactivé (les entités suivent alors disabled_by)."""
    if device is None:
        return False
    if getattr(device, "disabled_by", None) is not None:
        return True
    return getattr(device, "disabled", False) is True


def update_entity_device(
    hass: HomeAssistant,
    entity_id: str,
    device_id: str | None,
    *,
    allow_enable: bool = False,
) -> bool:
    """Change l'appareil d'une entité seulement si l'identifiant diffère.

    Quitter un appareil désactivé remet disabled_by à vide : Home Assistant
    recharge alors l'entrée au bout de 30 secondes. Ce déplacement est refusé,
    sauf si l'ancien appareil va être supprimé (allow_enable). Un basculement
    possible est journalisé en debug, sans nom, adresse ni numéro.
    """
    from homeassistant.helpers import entity_registry as er

    entities = er.async_get(hass)
    current = entities.async_get(entity_id)
    if current is None or current.device_id == device_id:
        return False
    registry = dr.async_get(hass)
    previous = registry.async_get(current.device_id) if current.device_id else None
    nxt = registry.async_get(device_id) if device_id else None
    if device_is_disabled(previous) != device_is_disabled(nxt):
        domain = entity_id.split(".", 1)[0]
        _LOGGER.debug(
            "Une entité %s change d'appareil : disabled_by peut basculer",
            domain,
        )
    if device_is_disabled(previous) and not device_is_disabled(nxt) and not allow_enable:
        return False
    entities.async_update_entity(entity_id, device_id=device_id)
    return True


def registry_device_id(device: object) -> str | None:
    """Read a real HA registry id without coercing legacy/malformed identities."""
    identifier: object = getattr(device, "id", None)
    return identifier if isinstance(identifier, str) else None
