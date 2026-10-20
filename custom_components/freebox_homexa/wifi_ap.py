"""Inventaire des points d'accès Wi-Fi Freebox (gateway + répéteurs)."""

from __future__ import annotations

from typing import Any

from .const import REPEATER_MODEL
from .device_groups import lan_client_name


def normalize_mac(mac: str | None) -> str:
    """Normalize a MAC address for comparisons."""
    return (mac or "").upper().replace(":", "").replace("-", "")


def is_freebox_repeater(device: dict[str, Any], router_mac: str) -> bool:
    """Return True if the LAN host looks like a Free Wi-Fi repeater."""
    mac = normalize_mac((device.get("l2ident") or {}).get("id"))
    if not mac or mac == normalize_mac(router_mac):
        return False

    name = (device.get("primary_name") or "").lower()
    host_type = device.get("host_type") or ""
    vendor = (device.get("vendor_name") or "").lower()

    if any(token in name for token in ("répét", "repet", "repeater", "rp01")):
        return True
    if host_type in {"networking_device", "freebox_wifi"} and "free" in vendor:
        return True
    return False


def display_mac(norm: str) -> str:
    """AABBCCDDEEFF -> AA:BB:CC:DD:EE:FF."""
    return ":".join(norm[i : i + 2] for i in range(0, len(norm), 2)) if len(norm) == 12 else norm


def _repeater_distance(a: str, b: str) -> int | None:
    """Distance entre deux MAC d'un même répéteur physique, None si sans rapport.

    Un répéteur Free expose plusieurs MAC (Ethernet, radios 2,4 / 5 GHz, backhaul,
    BSSID « locally administered ») : mêmes 3 derniers octets, ou mêmes octets 2 à 5
    avec un dernier octet proche.
    """
    if len(a) != 12 or len(b) != 12:
        return 0 if a == b else None
    if a == b or a[6:] == b[6:]:
        return 0
    if a[2:10] == b[2:10]:
        diff = abs(int(a[10:], 16) - int(b[10:], 16))
        if diff < 16:
            return diff
    return None


def cluster_repeater_macs(macs: list[str], anchors: list[str] | None = None) -> dict[str, str]:
    """MAC normalisée -> MAC canonique (affichage) du répéteur physique.

    `anchors` : MAC principales de l'API /repeater/ (une par répéteur) ; à défaut,
    la plus petite MAC de chaque grappe sert d'ancre (stable d'un démarrage à l'autre).
    """
    result: dict[str, str] = {}
    anchor_norms: list[str] = []
    for anchor in anchors or []:
        norm = normalize_mac(anchor)
        if norm and norm not in anchor_norms:
            anchor_norms.append(norm)
            result[norm] = display_mac(norm)
    for norm in sorted({normalize_mac(m) for m in macs if m}):
        if norm in result:
            continue
        best: tuple[int, str] | None = None
        for anchor in anchor_norms:
            dist = _repeater_distance(norm, anchor)
            if dist is not None and (best is None or dist < best[0]):
                best = (dist, anchor)
        if best is None:
            anchor_norms.append(norm)
            result[norm] = display_mac(norm)
        else:
            result[norm] = display_mac(best[1])
    return result


def parent_identifier(access_point: dict[str, Any], router_mac: str) -> str:
    """HA device identifier for the AP that owns this client."""
    if access_point.get("kind") == "gateway":
        return router_mac
    mac = access_point.get("mac") or access_point.get("id")
    return f"repeater_{mac}"


def _client_summary(device: dict[str, Any]) -> dict[str, Any]:
    wifi = device.get("wifi") or {}
    ident = device.get("l2ident") or {}
    mac = ident.get("id") or ""
    name = lan_client_name(device)
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


def annotate_wifi_parents(
    devices: dict[str, dict[str, Any]],
    wifi_aps: dict[str, dict[str, Any]],
    router_mac: str,
) -> None:
    """Stamp each LAN host with the AP it is associated to."""
    for access_point in wifi_aps.values():
        identifier = parent_identifier(access_point, router_mac)
        parent = {
            "kind": access_point.get("kind"),
            "ap_id": access_point.get("id"),
            "name": access_point.get("name"),
            "identifier": identifier,
        }
        for client in access_point.get("clients") or []:
            mac = client.get("mac")
            if not mac:
                continue
            device = devices.get(mac) or devices.get(str(mac).upper()) or devices.get(str(mac).lower())
            if device is None:
                continue
            device["wifi_parent"] = parent


def build_wifi_aps(
    *,
    router_mac: str,
    router_name: str,
    router_model: str,
    devices: dict[str, dict[str, Any]],
    radio_status: list[dict[str, Any]] | None = None,
    api_repeaters: list[dict[str, Any]] | None = None,
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

    # Une entrée par répéteur PHYSIQUE : toutes ses MAC (hôtes LAN, BSSID) regroupées.
    api_repeaters = [r for r in api_repeaters or [] if isinstance(r, dict)]
    api_by_norm = {normalize_mac(r.get("main_mac")): r for r in api_repeaters if r.get("main_mac")}
    hosts = {
        normalize_mac(mac): device
        for mac, device in devices.items()
        if is_freebox_repeater(device, router_mac)
    }
    aliases = cluster_repeater_macs(
        [*hosts, *repeater_clients], [r.get("main_mac") for r in api_repeaters]
    )
    canon_macs: dict[str, list[str]] = {}
    for norm, canon in aliases.items():
        canon_macs.setdefault(canon, []).append(display_mac(norm))

    repeaters: dict[str, dict[str, Any]] = {}
    for canon, macs in canon_macs.items():
        norms = [normalize_mac(m) for m in macs]
        canon_norm = normalize_mac(canon)
        member_hosts = [hosts[n] for n in sorted(norms, key=lambda n: (n != canon_norm, n)) if n in hosts]
        api = api_by_norm.get(canon_norm) or {}
        if not member_hosts and not api and not any(n in repeater_clients for n in norms):
            continue
        clients = [c for n in norms for c in repeater_clients.get(n, [])]
        host = member_hosts[0] if member_hosts else {}
        name = (
            (api.get("name") or "").strip()
            or (host.get("primary_name") or "").strip()
            or f"Répéteur Wi-Fi {canon[-5:]}"
        )
        active = any(h.get("active") for h in member_hosts) or bool(clients) or (
            api.get("status") in ("running", "ok", "active")
        )
        payload = dict(host)
        payload.update(
            {
                "id": canon,
                "kind": "repeater",
                "name": name,
                "mac": canon,
                "macs": sorted(macs),
                "l2ident": {"id": canon},
                "serial": api.get("sn"),
                "model": api.get("model") or host.get("model") or REPEATER_MODEL,
                "vendor_name": host.get("vendor_name") or "Freebox SAS",
                "active": active,
                "online": active,
                "state": "active" if active else "offline",
                "client_count": len(clients),
                "clients": clients,
                "client_names": [item["name"] for item in clients],
            }
        )
        repeaters[canon] = payload
        wifi_aps[canon] = payload

    annotate_wifi_parents(devices, wifi_aps, router_mac)
    return wifi_aps, repeaters
