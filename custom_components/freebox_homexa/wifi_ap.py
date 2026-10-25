"""Inventaire des points d'accès Wi-Fi Freebox (gateway + répéteurs)."""

from __future__ import annotations

import logging
from typing import Any

from .const import REPEATER_MODEL
from .device_groups import (
    has_ethernet_evidence,
    has_wifi_evidence,
    is_specific_repeater_name,
    lan_client_name,
    ul_twin,
)

_LOGGER = logging.getLogger(__name__)


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
    manual_links: dict[str, str] | None = None,
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
      5. jumeau « locally administered » EXACT : 22:66:CF:4B:49:69 = 20:66:CF:4B:49:69
         avec le seul bit 0x02 du 1er octet inversé (les 5 autres octets identiques) ;
      6. bloc de BSSID : une MAC Free 22:66:CF:A:B:xx dont les 5 premiers octets sont
         ceux des BSSID connus d'UN SEUL répéteur (fronthaul de l'API /repeater/,
         access_point.mac des clients) ;
      7. fusions manuelles choisies dans les options (`manual_links` doublon -> cible).
    Les règles 5 et 6 ne réunissent jamais deux répéteurs ayant chacun leur propre MAC
    principale. Aucune fusion sur la seule proximité des MAC (ex. Garage 22:66:CF:96:92:D2
    et Chambre fille 22:66:CF:C6:92:D2 ne diffèrent que par le 4e octet).
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
    # MAC principale = adresse universelle (bit 0x02 à 0) d'un hôte ou de l'API.
    def _mains_of(root: str) -> set[str]:
        return {
            m for m in nodes
            if find(m) == root and (m in main_macs or (m in hosts and not int(m[:2], 16) & 0x02))
        }

    def safe_union(a: str, b: str, why: str) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        ma, mb = _mains_of(ra), _mains_of(rb)
        if ma and mb and ma != mb:
            return False  # deux répéteurs distincts : jamais fusionnés automatiquement
        union(a, b, why)
        return True

    # 5. Jumeau « locally administered » exact. (L'ancienne règle « MAC voisines »,
    # retirée en 28.8.49, fusionnait Garage 20:66:CF:4B:49:69 avec Chambre fille
    # 20:66:CF:4B:49:63 car mêmes octets 2 à 5 et dernier octet proche ; le jumeau
    # exact, lui, ne dépend que de la MAC du répéteur lui-même.)
    for n in sorted(nodes):
        if len(n) != 12 or not int(n[:2], 16) & 0x02 or not is_free_mac(n):
            continue
        univ = ul_twin(n)
        if univ in nodes and is_free_mac(univ):
            if safe_union(univ, n, "jumeau U/L"):
                main_macs.add(univ)
    # 6. Bloc de BSSID (5 premiers octets) d'un seul répéteur.
    bssids = {m for m in ap_uids if is_free_mac(m)}
    for rep in api_repeaters or []:
        for f in rep.get("fronthaul") or []:
            if isinstance(f, dict) and f.get("bssid"):
                bssids.add(normalize_mac(f.get("bssid")))
    for n in sorted(nodes):
        if len(n) != 12 or not int(n[:2], 16) & 0x02 or not is_free_mac(n):
            continue
        if ul_twin(n) in nodes:
            continue  # jumeau d'une MAC connue : règle 5 uniquement
        roots = {find(b) for b in bssids if b != n and b[:10] == n[:10]}
        if len(roots) == 1:
            root = next(iter(roots))
            if root != find(n):
                safe_union(root, n, f"bloc BSSID {display_mac(n)[:14]}")
    # 7. Fusions manuelles (choix explicite de l'utilisateur).
    for dup, target in (manual_links or {}).items():
        d, t = normalize_mac(dup), normalize_mac(target)
        if len(d) == 12 and len(t) == 12 and d != t:
            nodes.update((d, t))
            if not int(t[:2], 16) & 0x02:
                main_macs.add(t)
            union(t, d, "fusion manuelle")
    # Pas de regroupement par simple proximité de MAC : en cas de doute, pas de fusion.

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
    # Hôte branché en Ethernet (sur la box, un port du répéteur ou derrière un switch) :
    # access_point.type vaut aussi « gateway » / « repeater », mais ce n'est pas un client
    # Wi-Fi. « gateway » seul (sans connectivity_type) n'est pas une preuve de Wi-Fi.
    if has_ethernet_evidence(device):
        return False
    if has_wifi_evidence(device):
        return True
    access_point = device.get("access_point") or {}
    # Client d'un répéteur sans détail : Wi-Fi (voir lan_client_link).
    return access_point.get("type") == "repeater" and bool(access_point.get("mac"))


# États documentés (API Freebox OS, /wifi/ap/ status.state et /wifi/bss/ status.state).
_ACTIVE_STATES = frozenset({"active"})
# Radio en cours de démarrage / sélection de canal : Wi-Fi allumé mais pas encore émis.
_TRANSIENT_STATES = frozenset({"scanning", "starting", "acs", "ht_scan", "dfs"})
# Radio / BSS arrêté(e) ou en erreur.
_OFF_STATES = frozenset(
    {"no_param", "bad_param", "disabled", "disabled_planning", "no_active_bss", "failed", "phy_stopped"}
)
_KNOWN_STATES = _ACTIVE_STATES | _TRANSIENT_STATES | _OFF_STATES
_LOGGED_UNKNOWN_STATES: set[str] = set()


def _states(items: list[dict[str, Any]] | None) -> list[str]:
    states: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        state = item.get("state")
        if state is None or state == "":
            continue
        state = str(state).strip().lower()
        if state not in _KNOWN_STATES and state not in _LOGGED_UNKNOWN_STATES:
            _LOGGED_UNKNOWN_STATES.add(state)
            _LOGGER.debug("État Wi-Fi inconnu « %s » (AP/BSS %s)", state, item.get("id"))
        states.append(state)
    return states


def gateway_wifi_state(
    radio_status: list[dict[str, Any]] | None,
    bss_status: list[dict[str, Any]] | None = None,
    global_enabled: bool | None = None,
    active_clients: int = 0,
) -> tuple[bool | None, str]:
    """État du Wi-Fi de la box : (en ligne, état).

    - /wifi/config/ ``enabled`` à False : Wi-Fi coupé (comme l'interrupteur).
    - Un AP (/wifi/ap/) ou un BSS (/wifi/bss/) ``active`` : en ligne.
    - Un client Wi-Fi actif rattaché à la box : en ligne.
    - Wi-Fi activé mais AP/BSS illisibles, ou états inconnus : en ligne (« enabled »).
    - Sinon : hors ligne avec l'état de la radio ; None si rien n'est lisible.
    """
    if global_enabled is False:
        return False, "disabled"
    ap_states = _states(radio_status)
    bss_states = _states(bss_status)
    states = ap_states + bss_states
    if any(state in _ACTIVE_STATES for state in states):
        return True, "active"
    if active_clients > 0:
        return True, "active"
    unknown = [state for state in states if state not in _KNOWN_STATES]
    if global_enabled is True and (not states or unknown):
        return True, "enabled"
    if states:
        transient = next((state for state in states if state in _TRANSIENT_STATES), None)
        return False, transient or states[0]
    return None, "unknown"


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


def repeater_own_macs(
    canon: str,
    members: list[str],
    hosts: dict[str, dict[str, Any]],
    api_repeaters: list[dict[str, Any]] | None = None,
    manual_norms: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Sépare les MAC d'un répéteur : (MAC propres, MAC de point d'accès seulement).

    MAC propres (connexions de l'appareil) : MAC canonique, MAC Free (OUI Free ou jumeau
    « locally administered » : principale 20:66:CF:…, jumeau et BSSID 22:66:CF:…), hôtes
    LAN reconnus comme répéteur, interfaces déclarées par l'API /repeater/ pour CE
    répéteur (main_mac, backhaul, fronthaul) et fusions manuelles. Toute autre MAC (ex.
    4E:C4:E5:8E:62:A7, adresse aléatoire de téléphone vue en access_point.mac d'un client)
    n'est jamais une connexion du répéteur.
    """
    member_set = set(members)
    api_own: set[str] = set()
    for rep in api_repeaters or []:
        rep_macs = {normalize_mac(m) for m in api_repeater_macs(rep)} - {""}
        if rep_macs & member_set:
            api_own |= rep_macs
    manual = manual_norms or set()
    own: list[str] = []
    ap_only: list[str] = []
    for n in sorted(member_set):
        if n == canon or is_free_mac(n) or n in hosts or n in api_own or n in manual:
            own.append(n)
        else:
            ap_only.append(n)
    if canon and canon not in own:
        own.append(canon)
    return own, ap_only


def build_wifi_aps(
    *,
    router_mac: str,
    router_name: str,
    router_model: str,
    devices: dict[str, dict[str, Any]],
    radio_status: list[dict[str, Any]] | None = None,
    api_repeaters: list[dict[str, Any]] | None = None,
    manual_links: dict[str, str] | None = None,
    bss_status: list[dict[str, Any]] | None = None,
    wifi_enabled: bool | None = None,
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

    online, state = gateway_wifi_state(
        radio_status,
        bss_status,
        wifi_enabled,
        sum(1 for item in gateway_clients if item.get("active")),
    )
    wifi_aps: dict[str, dict[str, Any]] = {
        "gateway": {
            "id": "gateway",
            "kind": "gateway",
            "name": f"Wi-Fi {router_name}",
            "mac": router_mac,
            "model": router_model,
            "vendor_name": "Freebox SAS",
            "online": online,
            "state": state,
            "wifi_enabled": wifi_enabled,
            "radios": radio_status,
            "bss": bss_status or [],
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
    aliases, grouping = group_repeater_macs(hosts, ap_uids, api_repeaters, manual_links)
    wifi_aps["gateway"]["rejected_repeater_macs"] = grouping.pop("_rejected", [])
    canon_macs: dict[str, list[str]] = {}
    for norm, canon in aliases.items():
        canon_macs.setdefault(canon, []).append(display_mac(norm))

    manual_norms = {
        normalize_mac(m) for pair in (manual_links or {}).items() for m in pair if m
    }
    repeaters: dict[str, dict[str, Any]] = {}
    for canon, macs in canon_macs.items():
        norms = [normalize_mac(m) for m in macs]
        canon_norm = normalize_mac(canon)
        own, ap_only = repeater_own_macs(canon_norm, norms, hosts, api_repeaters, manual_norms)
        if ap_only:
            _LOGGER.debug(
                "Répéteur %s : MAC non Free ignorées dans les connexions %s",
                canon, [display_mac(n) for n in ap_only],
            )
        member_hosts = [hosts[n] for n in sorted(norms, key=lambda n: (n != canon_norm, n)) if n in hosts]
        api = api_by_norm.get(canon_norm) or {}
        if not member_hosts and not api and not any(n in repeater_clients for n in norms):
            continue
        clients = [c for n in norms for c in repeater_clients.get(n, [])]
        host = member_hosts[0] if member_hosts else {}
        # Nom choisi par l'utilisateur sur une des MAC (ex. « … Garage ») plutôt que « #2 ».
        specific = next(
            (
                (h.get("primary_name") or "").strip()
                for h in member_hosts
                if is_specific_repeater_name(h.get("primary_name"))
            ),
            "",
        )
        name = (
            (api.get("name") or "").strip()
            or specific
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
                # Connexions de l'appareil : uniquement les MAC propres au répéteur.
                "macs": sorted(display_mac(n) for n in own),
                # MAC de point d'accès non Free vues chez les clients : rattachement des
                # clients au répéteur seulement, jamais en connexion de l'appareil.
                "ap_aliases": sorted(display_mac(n) for n in ap_only),
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
