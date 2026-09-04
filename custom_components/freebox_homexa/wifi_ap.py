"""Inventaire des points d'accès Wi-Fi Freebox (gateway + répéteurs)."""

from __future__ import annotations

from typing import Any

from .const import DEFAULT_DEVICE_NAME, REPEATER_MODEL
from .router import is_freebox_repeater, normalize_mac


def _client_summary(device: dict[str, Any]) -> dict[str, Any]:
    wifi = device.get("wifi") or {}
    ident = device.get("l2ident") or {}
    mac = ident.get("id") or ""
    name = (device.get("primary_name") or "").strip() or mac or DEFAULT_DEVICE_NAME
    return {
        "name": name,
        "mac": mac,
        "active": bool(device.get("active")),
        "signal_dbm": wifi.get("wifi_signal_dbm"),
        "band": wifi.get("wifi_band_label") or wifi.get("wifi_band"),
        "ssid": wifi.get("wifi_ssid"),
    }


def _is_wifi_client(device: dict[str, Any], router_mac: str) -> bool:
    if device.get("attrs") is not None:
        return False
    if is_freebox_repeater(device, router_mac):
        return False
    access_point = device.get("access_point") or {}
    wifi = device.get("wifi") or {}
    if access_point.get("type") in {"repeater", "gateway"}:
        return True
    if access_point.get("connectivity_type") == "wifi":
        return True
    if wifi.get("connectivity") == "wifi":
        return True
    if wifi.get("wifi_signal_dbm") is not None:
        return True
    return bool(access_point.get("wifi_information"))


def _gateway_state(radio_status: list[dict[str, Any]]) -> str:
    states = [item.get("state") for item in radio_status if item.get("state")]
    if "active" in states:
        return "active"
    if states:
        return str(states[0])
    return "unknown"


def build_wifi_aps(
    *,
    router_mac: str,
    router_name: str,
    router_model: str,
    devices: dict[str, dict[str, Any]],
    radio_status: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Group Wi-Fi clients by gateway / repeater access point."""
    radio_status = radio_status or []
    gateway_clients: list[dict[str, Any]] = []
    repeater_clients: dict[str, list[dict[str, Any]]] = {}

    for device in devices.values():
        if not _is_wifi_client(device, router_mac):
            continue
        summary = _client_summary(device)
        access_point = device.get("access_point") or {}
        ap_type = access_point.get("type")
        ap_mac = normalize_mac(access_point.get("mac"))
        if ap_type == "repeater" and ap_mac:
            repeater_clients.setdefault(ap_mac, []).append(summary)
        else:
            gateway_clients.append(summary)

    state = _gateway_state(radio_status)
    wifi_aps: dict[str, dict[str, Any]] = {
        "gateway": {
            "id": "gateway",
            "kind": "gateway",
            "name": f"Wi-Fi {router_name}",
            "mac": router_mac,
            "model": router_model,
            "vendor_name": "Freebox SAS",
            "online": state == "active",
            "state": state,
            "radios": radio_status,
            "client_count": len(gateway_clients),
            "clients": gateway_clients,
            "client_names": [item["name"] for item in gateway_clients],
        }
    }

    repeaters: dict[str, dict[str, Any]] = {}
    matched: set[str] = set()
    for mac, device in devices.items():
        if not is_freebox_repeater(device, router_mac):
            continue
        norm = normalize_mac(mac)
        clients = list(repeater_clients.get(norm, []))
        if not clients:
            for ap_mac, grouped in repeater_clients.items():
                if ap_mac.endswith(norm[-6:]) or norm.endswith(ap_mac[-6:]):
                    clients = list(grouped)
                    matched.add(ap_mac)
                    break
        else:
            matched.add(norm)
        name = (device.get("primary_name") or "").strip() or f"Répéteur Wi-Fi {mac[-5:]}"
        payload = dict(device)
        payload.update(
            {
                "id": mac,
                "kind": "repeater",
                "name": name,
                "mac": mac,
                "model": device.get("model") or REPEATER_MODEL,
                "vendor_name": device.get("vendor_name") or "Freebox SAS",
                "online": bool(device.get("active")),
                "state": "active" if device.get("active") else "offline",
                "client_count": len(clients),
                "clients": clients,
                "client_names": [item["name"] for item in clients],
            }
        )
        repeaters[mac] = payload
        wifi_aps[mac] = payload

    for ap_mac, clients in repeater_clients.items():
        if ap_mac in matched:
            continue
        if any(normalize_mac(key) == ap_mac for key in wifi_aps):
            continue
        display_mac = ":".join(ap_mac[i : i + 2] for i in range(0, len(ap_mac), 2)) if len(ap_mac) == 12 else ap_mac
        payload = {
            "id": display_mac,
            "kind": "repeater",
            "name": f"Répéteur Wi-Fi {display_mac[-5:]}",
            "mac": display_mac,
            "l2ident": {"id": display_mac},
            "model": REPEATER_MODEL,
            "vendor_name": "Freebox SAS",
            "active": True,
            "online": True,
            "state": "active",
            "client_count": len(clients),
            "clients": clients,
            "client_names": [item["name"] for item in clients],
        }
        repeaters[display_mac] = payload
        wifi_aps[display_mac] = payload

    return wifi_aps, repeaters
