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


# OUI Free / Freebox SAS (répéteurs, box, players). Le jumeau « locally administered »
# (bit 0x02 du 1er octet, ex. 22:66:CF pour 20:66:CF) est aussi accepté.
FREE_OUIS = frozenset(
    {"0007CB", "0024D4", "140C76", "2066CF", "342792", "68A378", "70FC8F", "8C97EA", "E49E12", "F4CAE5"}
)


def is_free_mac(norm: str) -> bool:
    """MAC normalisée appartenant à un OUI Free (ou à son jumeau local)."""
    if len(norm) != 12:
        return False
    try:
        first = int(norm[:2], 16)
    except ValueError:
        return False
    return norm[:6] in FREE_OUIS or f"{first & ~0x02:02X}{norm[2:6]}" in FREE_OUIS


def display_mac(norm: str) -> str:
    """AABBCCDDEEFF -> AA:BB:CC:DD:EE:FF."""
    return ":".join(norm[i : i + 2] for i in range(0, len(norm), 2)) if len(norm) == 12 else norm


def api_repeater_macs(repeater: dict[str, Any]) -> list[str]:
    """Toutes les MAC d'un répéteur de l'API /repeater/ (principale, backhaul, BSSID).

    Ex. réel : main_mac 8C:97:EA:55:BB:B6, backhaul 16:E4:EF:… (eth) et 8E:97:EA:9B:1F:9x
    (wifi), fronthaul 8C/8E:97:EA:9B:1F:90/94 : ces MAC n'ont rien de « proche ».
    """
    macs = [repeater.get("main_mac")]
    macs += [b.get("mac") for b in repeater.get("backhaul") or [] if isinstance(b, dict)]
    macs += [f.get("bssid") for f in repeater.get("fronthaul") or [] if isinstance(f, dict)]
    return [m for m in macs if m]


def eui64_mac(addr: str | None) -> str:
    """MAC (normalisée) encodée dans une adresse IPv6 SLAAC/EUI-64, sinon ""."""
    if not addr or ":" not in addr:
        return ""
    try:
        import ipaddress

        packed = ipaddress.IPv6Address(addr.split("%")[0]).packed
    except ValueError:
        return ""
    iid = packed[8:]
    if iid[3] != 0xFF or iid[4] != 0xFE:
        return ""
    raw = bytes([iid[0] ^ 0x02, iid[1], iid[2], iid[5], iid[6], iid[7]])
    return raw.hex().upper()


def _host_addrs(device: dict[str, Any]) -> list[str]:
    return [
        str(c.get("addr")).lower()
        for c in device.get("l3connectivities") or []
        if isinstance(c, dict) and c.get("addr")
    ]


def group_repeater_macs(
    hosts: dict[str, dict[str, Any]],
    ap_uids: dict[str, str],
    api_repeaters: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Regroupe toutes les MAC vues par répéteur PHYSIQUE (union-find).

    `hosts` : MAC normalisée -> hôte LAN reconnu comme répéteur.
    `ap_uids` : MAC normalisée d'un point d'accès répéteur (access_point.mac des
    clients LAN) -> access_point.uid (identifiant du répéteur côté Freebox).

    Signaux, du plus sûr au moins sûr :
      1. API /repeater/ si elle répond (main_mac, backhaul, fronthaul) ;
      2. même access_point.uid ;
      3. adresse IP (v4/v6) commune entre hôtes (interfaces pontées du répéteur) ;
      4. IPv6 EUI-64 d'un hôte qui encode la MAC d'un autre hôte ;
    Aucune fusion sur la seule proximité des MAC.
    Retourne (MAC -> MAC canonique, MAC canonique -> raisons du regroupement).
    """
    parent: dict[str, str] = {}
    reasons: dict[str, list[str]] = {}
    rejected: list[str] = []

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str, why: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
            reasons.setdefault(ra, []).extend(reasons.pop(rb, []))
            reasons[ra].append(f"{why}: {display_mac(a)} ~ {display_mac(b)}")

    nodes = set(hosts) | set(ap_uids)
    main_macs: set[str] = set()
    for rep in api_repeaters or []:
        macs = [normalize_mac(m) for m in api_repeater_macs(rep)]
        macs = [m for m in macs if m]
        if not macs:
            continue
        main_macs.add(macs[0])
        nodes.update(macs)
        for m in macs[1:]:
            union(macs[0], m, f"API repeater {rep.get('id')}")
    for n in nodes:
        find(n)
    by_uid: dict[str, str] = {}
    for mac, uid in ap_uids.items():
        if uid in by_uid:
            union(by_uid[uid], mac, f"uid {uid}")
        else:
            by_uid[uid] = mac
    by_addr: dict[str, str] = {}
    for mac, device in hosts.items():
        for addr in _host_addrs(device):
            if addr.startswith("fe80") or addr in ("0.0.0.0", "::"):
                encoded = eui64_mac(addr)
                if encoded == mac:
                    main_macs.add(mac)
                elif encoded and encoded in nodes:
                    union(encoded, mac, "EUI-64")
                    main_macs.add(encoded)
                continue
            if addr in by_addr:
                union(by_addr[addr], mac, f"IP {addr}")
            else:
                by_addr[addr] = mac
            encoded = eui64_mac(addr)
            if encoded == mac:
                main_macs.add(mac)  # l'adresse SLAAC désigne l'interface principale
            elif encoded and encoded in nodes:
                union(encoded, mac, "EUI-64")
                main_macs.add(encoded)
    # Pas de regroupement par simple proximité de MAC (plages consécutives d'un
    # répéteur à l'autre, jumeau 20/22 non fiable) : en cas de doute, pas de fusion.

    clusters: dict[str, list[str]] = {}
    for n in nodes:
        clusters.setdefault(find(n), []).append(n)
    aliases: dict[str, str] = {}
    why: dict[str, list[str]] = {}
    api_nodes = {
        normalize_mac(m) for rep in api_repeaters or [] for m in api_repeater_macs(rep)
    }
    for root, members in list(clusters.items()):
        # Pas un répéteur Free : ex. hôte nommé « Repeteur… » avec une MAC aléatoire.
        # Il faut au moins un hôte LAN ou une entrée API (un BSSID seul, sans lien
        # fiable vers un hôte, ne crée pas d'appareil) et au moins une MAC Free / API.
        has_anchor = any(m in hosts or m in api_nodes for m in members)
        if not has_anchor or not any(is_free_mac(m) or m in api_nodes for m in members):
            for m in members:
                rejected.append(display_mac(m))
            del clusters[root]
    for root, members in clusters.items():
        # Ancre stable : MAC principale (API / EUI-64), sinon plus petite MAC d'hôte.
        candidates = sorted(m for m in members if m in main_macs) or sorted(
            m for m in members if m in hosts
        ) or sorted(members)
        canon = display_mac(candidates[0])
        for m in members:
            aliases[m] = canon
        why[canon] = reasons.get(root, [])
    if rejected:
        why["_rejected"] = sorted(rejected)
    return aliases, why


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
    ap_uids: dict[str, str] = {}
    for device in devices.values():
        access_point = device.get("access_point") or {}
        ap_norm = normalize_mac(access_point.get("mac"))
        if access_point.get("type") == "repeater" and ap_norm:
            ap_uids.setdefault(ap_norm, str(access_point.get("uid") or f"mac:{ap_norm}"))
    for ap_norm in repeater_clients:
        ap_uids.setdefault(ap_norm, f"mac:{ap_norm}")
    aliases, grouping = group_repeater_macs(hosts, ap_uids, api_repeaters)
    wifi_aps["gateway"]["rejected_repeater_macs"] = grouping.pop("_rejected", [])
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
                "grouping": grouping.get(canon, []),
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
