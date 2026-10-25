"""Diagnostics Freebox Homexa (« Télécharger les diagnostics »).

Contient de quoi analyser le regroupement des répéteurs Wi-Fi. Les MAC sont
conservées (indispensables à l'analyse) ; numéros de série, jetons et mots de
passe sont masqués.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
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
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    router = hass.data.get(DOMAIN, {}).get(entry.unique_id)
    data: dict[str, Any] = {
        "entry": {"title": entry.title, "version": entry.version, "options": dict(entry.options)},
        "repeater_devices_in_registry": repeater_registry_devices(hass, entry),
    }
    if router is None:
        data["router"] = "non chargé"
        return async_redact_data(data, TO_REDACT)
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
        }
    )
    return async_redact_data(data, TO_REDACT)
