"""Diagnostics Freebox Homexa (« Télécharger les diagnostics »).

Contient de quoi analyser le regroupement des répéteurs Wi-Fi. Les valeurs et noms de champs inconnus sont
remplacés par leur structure typée ; aucun historique de lecture exporté.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .player_diagnostics import status_schema
from .device_groups import repeater_registry_devices
from .wifi_ap import is_freebox_repeater

TO_REDACT = {
    "sn",
    "serial",
    "serial_number",
    "app_token",
    "token",
    "session_token",
    "password",
    "Pass",
    "pass",
    "pin",
    "key",
    "remote_code",
    "remote_codes",
    "tmdb_api_key",
    "tnt_tmdb_api_key",
    "api_key",
    "Stream",
    # Données personnelles des hôtes LAN (IP, SSID) : inutiles au diagnostic des répéteurs.
    "addr",
    "l3connectivities",
    "ipv4",
    "ipv6",
    "ssid",
    "wifi_ssid",
}


def _count_links(links: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for link in links.values():
        counts[link] = counts.get(link, 0) + 1
    return dict(sorted(counts.items()))


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    router = getattr(entry, "runtime_data", None)
    data: dict[str, Any] = {
        "entry": {"title": entry.title, "version": entry.version, "options": dict(entry.options)},
        "repeater_devices_in_registry": repeater_registry_devices(hass, entry),
    }
    if router is None:
        data["router"] = "non chargé"
        return {"legacy_schema": status_schema(async_redact_data(data, TO_REDACT)),
                "players": []}
    hosts = {
        mac: device
        for mac, device in (router.devices or {}).items()
        if is_freebox_repeater(device, router.mac)
        or ((device.get("access_point") or {}).get("type") == "repeater")
    }
    data.update(
        {
            "router_mac": router.mac,
            "router_model": router.model,
            "lan_hosts_repeaters_or_repeater_clients": hosts,
            "repeater_api": {
                "raw": getattr(router, "api_repeaters_raw", None),
                "error": getattr(router, "api_repeaters_error", None),
            },
            "repeater_grouping": {
                canon: {
                    "name": payload.get("name"),
                    "model": payload.get("model"),
                    "macs": payload.get("macs"),
                    "grouping": payload.get("grouping"),
                    "client_count": payload.get("client_count"),
                }
                for canon, payload in (router.repeaters or {}).items()
            },
            "repeater_aliases": dict(getattr(router, "repeater_aliases", {}) or {}),
            "wifi_radio_status": router.wifi_radio_status,
            "wifi_bss_status": getattr(router, "wifi_bss_status", []),
            "wifi_global_enabled": getattr(router, "wifi_global_enabled", None),
            "wifi_api_errors": dict(getattr(router, "wifi_api_errors", {}) or {}),
            "wifi_gateway_state": {
                key: (router.wifi_aps.get("gateway") or {}).get(key)
                for key in ("online", "state", "wifi_enabled", "client_count")
            },
            # Classement des clients : nombre par lien (filaire, Wi-Fi box, répéteur).
            "lan_client_links": _count_links(getattr(router, "lan_links", {}) or {}),
            # Type automatique des clients (sous-groupes Serveurs, VM et conteneurs…).
            "lan_client_types": _count_links(
                {k: v[1] for k, v in (getattr(router, "lan_client_types", {}) or {}).items()}
            ),
            "lan_type_overrides": len(getattr(router, "type_overrides", {}) or {}),
            # Clients dont l'entité device_tracker est active / appareils clients rangés.
            "lan_tracked_entities": len(getattr(router, "tracked_lan_macs", set()) or set()),
            "lan_client_devices": len(getattr(router, "lan_device_ids", {}) or {}),
        }
    )
    # Les anciens diagnostics contenaient notamment des MAC et noms d'appareils.
    # Leur structure seule est exportée : pas de promesse d'anonymisation partielle.
    return {
        "privacy_mode": "schema_only_no_personal_values",
        "legacy_schema": status_schema(async_redact_data(data, TO_REDACT)),
        "players": list(getattr(router, "player_diagnostic_schemas", {}).values()),
    }
