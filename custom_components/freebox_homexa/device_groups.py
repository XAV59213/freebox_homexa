"""Appareils parents virtuels (Sécurité, Volets, Réseau), noms et pièces suggérées."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, FreeboxHomeCategory

GROUP_SECURITY = "security"
GROUP_COVERS = "covers"
GROUP_NETWORK = "network"

GROUP_NAMES = {
    GROUP_SECURITY: "Sécurité",
    GROUP_COVERS: "Volets",
    GROUP_NETWORK: "Réseau",
}
GROUP_MODELS = {
    GROUP_SECURITY: "Groupe alarme, télécommandes, capteurs et caméras",
    GROUP_COVERS: "Groupe volets et ouvrants",
    GROUP_NETWORK: "Groupe clients LAN / Wi-Fi",
}

_SECURITY_CATEGORIES = {
    FreeboxHomeCategory.ALARM,
    FreeboxHomeCategory.KFB,
    FreeboxHomeCategory.DWS,
    FreeboxHomeCategory.PIR,
    FreeboxHomeCategory.CAMERA,
}
_COVER_CATEGORIES = {
    FreeboxHomeCategory.SHUTTER,
    FreeboxHomeCategory.BASIC_SHUTTER,
    FreeboxHomeCategory.OPENER,
    FreeboxHomeCategory.RTS,
    FreeboxHomeCategory.IOHOME,
}


def group_identifier(router_mac: str, group: str) -> tuple[str, str]:
    """Identifiant stable du parent virtuel, ex. (DOMAIN, "<mac>_group_security")."""
    return (DOMAIN, f"{router_mac}_group_{group}")


def home_node_group(node: dict[str, Any]) -> str | None:
    """Groupe d'un nœud Freebox Home (None = rattaché directement au Freebox Server)."""
    category = node.get("category")
    if category in _SECURITY_CATEGORIES:
        return GROUP_SECURITY
    if category in _COVER_CATEGORIES:
        return GROUP_COVERS
    inherit = (node.get("type") or {}).get("inherit")
    if inherit in ("node::rts", "node::ios"):
        return GROUP_COVERS
    return None


def async_ensure_group_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    router_mac: str,
    server_device_id: str,
    create_network: bool,
) -> dict[str, str]:
    """Crée/met à jour les parents virtuels ; retourne {groupe: device_id}."""
    registry = dr.async_get(hass)
    ids: dict[str, str] = {}
    for group, name in GROUP_NAMES.items():
        identifier = group_identifier(router_mac, group)
        if group == GROUP_NETWORK and not create_network:
            device = registry.async_get_device(identifiers={identifier})
            if device is not None:
                registry.async_update_device(
                    device.id, remove_config_entry_id=entry.entry_id
                )
            continue
        device = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={identifier},
            manufacturer="Freebox SAS",
            model=GROUP_MODELS[group],
            name=name,
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        if device.via_device_id != server_device_id:
            registry.async_update_device(device.id, via_device_id=server_device_id)
        ids[group] = device.id
    return ids


def async_remove_lan_client_devices(
    hass: HomeAssistant, entry: ConfigEntry, router_mac: str
) -> int:
    """Détache cette entrée des devices clients LAN (option désactivée).

    Un client LAN = device de l'entrée sans identifiant Homexa, uniquement
    des connexions MAC (répéteurs, players, disques… ont des identifiants).
    Le device n'est supprimé que s'il n'appartient à aucune autre intégration.
    """
    registry = dr.async_get(hass)
    removed = 0
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if any(ident[0] == DOMAIN for ident in device.identifiers):
            continue
        macs = {c[1] for c in device.connections if c[0] == dr.CONNECTION_NETWORK_MAC}
        if not macs or router_mac in macs:
            continue
        registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
        removed += 1
    return removed


# --- Noms -------------------------------------------------------------------

_MAC_RE = re.compile(r"^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$", re.I)
_GENERIC_NAMES = {
    "", "wlan0", "wlan1", "eth0", "eth1", "localhost", "unknown", "unknown device",
    "android", "espressif", "(null)", "none",
}


def _is_generic(name: str | None) -> bool:
    if not name:
        return True
    value = name.strip()
    return value.lower() in _GENERIC_NAMES or bool(_MAC_RE.match(value))


def lan_client_name(device: dict[str, Any]) -> str:
    """Nom lisible d'un client LAN (évite « wlan0 », MAC, « Unknown device »)."""
    primary = (device.get("primary_name") or "").strip()
    if not _is_generic(primary):
        return primary
    for entry in device.get("names") or []:
        candidate = (entry.get("name") or "").strip() if isinstance(entry, dict) else ""
        if not _is_generic(candidate):
            return candidate
    default = (device.get("default_name") or "").strip()
    if not _is_generic(default):
        return default
    mac = ((device.get("l2ident") or {}).get("id") or "").upper()
    tail = mac.replace(":", "")[-4:] if mac else ""
    vendor = (device.get("vendor_name") or "").strip()
    if vendor:
        return f"{vendor} {tail}".strip()
    return f"Appareil réseau {tail}".strip()


def home_node_name(node: dict[str, Any], model: str | None) -> str:
    """Nom d'un nœud Home, avec repli « <modèle/type> <id> » si le libellé est vide."""
    label = (node.get("label") or "").strip()
    if label and label.lower() != "unknown device":
        return label
    kind = model or (node.get("type") or {}).get("label") or node.get("category") or "Appareil"
    return f"{kind} {node.get('id')}"


# --- Pièces suggérées -------------------------------------------------------

_KNOWN_AREAS = {
    "cuisine": "Cuisine",
    "salon": "Salon",
    "séjour": "Séjour",
    "sejour": "Séjour",
    "chambre": "Chambre",
    "bureau": "Bureau",
    "garage": "Garage",
    "entrée": "Entrée",
    "entree": "Entrée",
    "couloir": "Couloir",
    "salle de bain": "Salle de bain",
    "sdb": "Salle de bain",
    "grange": "Grange",
    "cellier": "Cellier",
    "buanderie": "Buanderie",
    "papa": "Papa",
    "maman": "Maman",
    "fille": "Fille",
    "fils": "Fils",
    "loulou": "Loulou",
    "parents": "Parents",
}
_AREA_STOPWORDS = {"basic", "roulant", "roulants", "porte", "gauche", "droite", "droit", "haut", "bas", "io", "rts"}
_PREFIX_RE = re.compile(
    r"\b(?:volet|volets|fen[êe]tre|porte|baie|store|d[ée]tecteur|capteur|cam[ée]ra)"
    r"(?:\s+roulant)?\s+(?:de\s+la\s+|du\s+|de\s+l'|des\s+|de\s+)?([\wÀ-ÿ'-]+)",
    re.I,
)


def suggested_area(name: str | None) -> str | None:
    """Pièce déduite du nom (appliquée par HA uniquement à la création du device)."""
    if not name:
        return None
    lower = name.lower()
    for key, area in _KNOWN_AREAS.items():
        if re.search(rf"\b{re.escape(key)}\b", lower):
            return area
    match = _PREFIX_RE.search(name)
    if match:
        word = match.group(1).strip("'-")
        if word and not word.isdigit() and len(word) > 1 and word.lower() not in _AREA_STOPWORDS:
            return word[:1].upper() + word[1:].lower()
    return None
