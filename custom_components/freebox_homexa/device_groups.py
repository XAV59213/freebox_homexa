"""Rattachement des appareils aux 4 services (Server, Player, Maison connectée, TNT), noms et pièces."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, FreeboxHomeCategory
from .registry_compat import (
    device_owned_by,
    entry_devices,
    get_device_by_identifier,
    remove_device,
)

_LOGGER = logging.getLogger(__name__)

# 4 services de premier niveau : Freebox Server, Freebox Player, Maison connectée, TNT.
GROUP_SERVER = "server"
GROUP_HOME = "home"
GROUP_PLAYER = "player"
GROUP_TNT = "tnt"
GROUP_AUTO = "auto"
CONF_DEVICE_GROUP_OVERRIDES = "device_group_overrides"
# Fusions manuelles de répéteurs (options) : MAC du doublon -> MAC du répéteur cible.
CONF_REPEATER_MERGES = "repeater_merges"
SERVICE_CHOICES = (GROUP_SERVER, GROUP_HOME, GROUP_PLAYER, GROUP_TNT)

# Regroupements des clients réseau sous le Freebox Server (créés seulement s'ils servent) :
# « Clients réseau filaires » (Ethernet) et « Clients Wi-Fi » (Wi-Fi de la box + répéteurs).
GROUP_LAN_WIRED = "lan_wired"
GROUP_LAN_WIFI = "lan_wifi"
LAN_GROUPS = (GROUP_LAN_WIRED, GROUP_LAN_WIFI)
# Lien d'un client : filaire, Wi-Fi de la box, ou « repeater:<MAC canonique> ».
LINK_WIRED = "wired"
LINK_WIFI = "wifi"
LINK_REPEATER = "repeater:"

# Anciens groupes (28.8.36 → 28.8.42) : valeurs « automatiques » encore produites
# par le classement des clients, et identifiants de parents virtuels à nettoyer.
GROUP_CAMERAS = "cameras"
GROUP_EQUIPMENT = "equipment"
GROUP_TV = "tv"
GROUP_OTHER = "other"
LEGACY_GROUP_MAP = {
    "security": GROUP_HOME,
    "windows": GROUP_HOME,
    "covers": GROUP_HOME,
    "media": GROUP_PLAYER,
    "tv": GROUP_TNT,
    "network": GROUP_SERVER,
    "infrastructure": GROUP_SERVER,
    "equipment": GROUP_SERVER,
    "cameras": GROUP_SERVER,
    "vm": GROUP_SERVER,
    "downloads": GROUP_SERVER,
    "parental": GROUP_SERVER,
    "calls": GROUP_SERVER,
    "other": GROUP_SERVER,
}

NET_AMAZON = "net_amazon"
NET_PHONES = "net_phones"
NET_COMPUTERS = "net_computers"
NET_MEDIA = "net_media"
NET_IOT = "net_iot"
NET_CONSOLES = "net_consoles"
NET_PRINTERS = "net_printers"
NET_OTHER = "net_other"
NETWORK_SUBGROUPS = (
    NET_AMAZON, NET_PHONES, NET_COMPUTERS, NET_MEDIA,
    NET_IOT, NET_CONSOLES, NET_PRINTERS, NET_OTHER,
)

# Types des clients réseau (sous-groupes de « Clients réseau filaires » / « Clients Wi-Fi »).
NET_SERVERS = "net_servers"
NET_VIRTUAL = "net_virtual"
NET_NETWORK = "net_network"
NET_CAMERAS = "net_cameras"
LAN_TYPES = (
    NET_SERVERS, NET_VIRTUAL, NET_NETWORK, NET_COMPUTERS, NET_PHONES, NET_MEDIA,
    NET_IOT, NET_CONSOLES, NET_PRINTERS, NET_CAMERAS, NET_AMAZON, NET_OTHER,
)
LAN_TYPE_NAMES = {
    NET_SERVERS: "Serveurs",
    NET_VIRTUAL: "VM et conteneurs",
    NET_NETWORK: "Équipements réseau",
    NET_COMPUTERS: "Ordinateurs",
    NET_PHONES: "Téléphones et tablettes",
    NET_MEDIA: "TV et multimédia",
    NET_IOT: "Objets connectés",
    NET_CONSOLES: "Consoles",
    NET_PRINTERS: "Imprimantes",
    NET_CAMERAS: "Caméras",
    NET_AMAZON: "Amazon / Alexa",
    NET_OTHER: "Autres",
}
CONF_DEVICE_TYPE_OVERRIDES = "device_type_overrides"
# Séparateur des libellés « Clients réseau filaires › Serveurs ».
LABEL_SEP = " › "

# "player" : ancien parent virtuel « Freebox Player » (28.8.40), source de doublon.
LEGACY_GROUPS = (*LEGACY_GROUP_MAP, *NETWORK_SUBGROUPS, GROUP_PLAYER)

GROUP_NAMES = {
    GROUP_SERVER: "Freebox Server",
    GROUP_HOME: "Freebox Maison connectée",
    GROUP_PLAYER: "Freebox Player",
    GROUP_TNT: "TNT",
    GROUP_LAN_WIRED: "Clients réseau filaires",
    GROUP_LAN_WIFI: "Clients Wi-Fi",
}
GROUP_MODELS = {
    GROUP_HOME: "Freebox Home : alarme, détecteurs, volets, caméras, prises",
    GROUP_LAN_WIRED: "Appareils branchés en Ethernet (box ou répéteur)",
    GROUP_LAN_WIFI: "Appareils sur le Wi-Fi de la box, répéteurs Wi-Fi et leurs clients",
}
# Anciens appareils de service (28.8.40 → 28.8.42), fusionnés dans le serveur / TNT.
LEGACY_SERVICE_KEYS = ("calls", "tv_guide")


def group_identifier(router_mac: str, group: str) -> tuple[str, str]:
    """Identifiant stable du parent virtuel, ex. (DOMAIN, "<mac>_group_security")."""
    return (DOMAIN, f"{router_mac}_group_{group}")


def to_service(group: str | None) -> str:
    """Groupe (ancien ou automatique) -> un des 4 services ; défaut : Freebox Server."""
    if group in SERVICE_CHOICES:
        return group
    return LEGACY_GROUP_MAP.get(group or "", GROUP_SERVER)


def home_node_group(node: dict[str, Any]) -> str:
    """Tous les nœuds Freebox Home (caméras comprises) : Freebox Maison connectée."""
    return GROUP_HOME


def migrate_group(group: str | None) -> str | None:
    """Ancien groupe -> service le plus proche (None pour « Automatique »)."""
    if group is None or group == GROUP_AUTO:
        return None
    if group in SERVICE_CHOICES or group in LAN_GROUPS:
        return group
    if group == GROUP_CAMERAS:
        return None  # caméra Home -> Maison, caméra IP -> serveur : laissé en automatique
    if group in NETWORK_SUBGROUPS:
        return GROUP_SERVER
    return LEGACY_GROUP_MAP.get(group)


def migrate_overrides(overrides: dict[str, str] | None) -> dict[str, str]:
    """Surcharges enregistrées migrées vers les 4 services (inconnues ignorées)."""
    result: dict[str, str] = {}
    for key, value in (overrides or {}).items():
        new = migrate_group(value)
        if new in SERVICE_CHOICES or new in LAN_GROUPS:
            result[key] = new
    return result


# --- Classification des clients réseau --------------------------------------

_HOST_TYPE_GROUPS = {
    "smartphone": NET_PHONES,
    "tablet": NET_PHONES,
    "ip_phone": NET_PHONES,
    "workstation": NET_COMPUTERS,
    "laptop": NET_COMPUTERS,
    "nas": NET_SERVERS,
    "television": NET_MEDIA,
    "multimedia_device": NET_MEDIA,
    "freebox_player": GROUP_PLAYER,
    "freebox_mini": GROUP_PLAYER,
    "freebox_hd": GROUP_PLAYER,
    "freebox_delta": GROUP_PLAYER,
    "vg_console": NET_CONSOLES,
    "printer": NET_PRINTERS,
    "ip_camera": GROUP_CAMERAS,
    "car": NET_IOT,
}
# (mot-clé fabricant, groupe) — testés dans l'ordre
_VENDOR_GROUPS = (
    ("hikvision", GROUP_CAMERAS),
    ("dahua", GROUP_CAMERAS),
    ("reolink", GROUP_CAMERAS),
    ("foscam", GROUP_CAMERAS),
    ("shenzhen foscam", GROUP_CAMERAS),
    ("ezviz", GROUP_CAMERAS),
    ("axis communications", GROUP_CAMERAS),
    ("amazon", NET_AMAZON),
    ("nintendo", NET_CONSOLES),
    ("sony interactive", NET_CONSOLES),
    ("microsoft xbox", NET_CONSOLES),
    ("valve", NET_CONSOLES),
    ("epson", NET_PRINTERS),
    ("canon", NET_PRINTERS),
    ("brother", NET_PRINTERS),
    ("hewlett", NET_PRINTERS),
    ("lexmark", NET_PRINTERS),
    ("kyocera", NET_PRINTERS),
    ("xerox", NET_PRINTERS),
    ("espressif", NET_IOT),
    ("tuya", NET_IOT),
    ("shelly", NET_IOT),
    ("allterco", NET_IOT),
    ("sonoff", NET_IOT),
    ("itead", NET_IOT),
    ("signify", NET_IOT),
    ("philips lighting", NET_IOT),
    ("netatmo", NET_IOT),
    ("nest", NET_IOT),
    ("ring llc", NET_IOT),
    ("meross", NET_IOT),
    ("tp-link", NET_IOT),
    ("lifx", NET_IOT),
    ("ecovacs", NET_IOT),
    ("roborock", NET_IOT),
    ("irobot", NET_IOT),
    ("dreame", NET_IOT),
    ("raspberry", NET_IOT),
    ("sonos", NET_MEDIA),
    ("roku", NET_MEDIA),
    ("lg electronics", NET_MEDIA),
    ("vizio", NET_MEDIA),
    ("tcl", NET_MEDIA),
    ("hisense", NET_MEDIA),
    ("bose", NET_MEDIA),
    ("freebox", NET_MEDIA),
    ("dell", NET_COMPUTERS),
    ("chongqing fugui", NET_COMPUTERS),
    ("hon hai", NET_COMPUTERS),
    ("liteon", NET_COMPUTERS),
    ("lite-on", NET_COMPUTERS),
    ("azurewave", NET_COMPUTERS),
    ("wistron", NET_COMPUTERS),
    ("quanta", NET_COMPUTERS),
    ("compal", NET_COMPUTERS),
    ("realtek", NET_COMPUTERS),
    ("foss", NET_IOT),
    ("lenovo", NET_COMPUTERS),
    ("asustek", NET_COMPUTERS),
    ("intel", NET_COMPUTERS),
    ("micro-star", NET_COMPUTERS),
    ("synology", NET_SERVERS),
    ("qnap", NET_SERVERS),
    ("oneplus", NET_PHONES),
    ("oppo", NET_PHONES),
    ("realme", NET_PHONES),
    ("huawei", NET_PHONES),
    ("motorola", NET_PHONES),
    ("fairphone", NET_PHONES),
)
# (mot-clé nom d'hôte, groupe) — testés dans l'ordre
_NAME_GROUPS = (
    (("hikvision", "reolink", "foscam", "ezviz", "dahua", "ipcam", "ip-cam", "camera",
      "cam-", "-cam", "axis-"), GROUP_CAMERAS),
    (("echo", "alexa", "fire tv", "firetv", "fire-tv", "kindle"), NET_AMAZON),
    (("iphone", "android", "galaxy", "pixel", "redmi", "xiaomi", "phone", "smartphone",
      "ipad", "tablet", "tab-", "oneplus", "huawei", "honor"), NET_PHONES),
    (("probook", "elitebook", "zbook", "pavilion", "envy", "ideapad", "latitude",
      "inspiron", "vivobook", "zenbook", "macbook", "imac", "mac-mini", "macmini", "mac mini", "desktop-", "laptop", "pc-",
      "-pc", "ordi", "thinkpad", "nas-", "-nas", "diskstation", "workstation", "surface"), NET_COMPUTERS),
    (("playstation", "ps4", "ps5", "xbox", "switch", "nintendo", "steamdeck",
      "steam-deck"), NET_CONSOLES),
    (("printer", "imprimante", "epson", "officejet", "deskjet", "laserjet", "brn",
      "canon"), NET_PRINTERS),
    (("tv", "chromecast", "roku", "sonos", "apple-tv", "appletv", "shield", "kodi",
      "player", "freebox", "bravia", "speaker", "enceinte"), NET_MEDIA),
    (("esp", "tuya", "shelly", "sonoff", "tasmota", "hue", "plug", "prise", "netatmo", "nest", "ring", "robot", "roborock", "vacuum", "aspirateur",
      "thermostat", "zigbee", "bridge", "raspberry", "homeassistant", "wled"), NET_IOT),
)
# Mots-clés forts du nom d'hôte, testés avant le fabricant (ex. carte Wi-Fi Intel dans un objet WLED).
_STRONG_NAME_GROUPS = (
    (("wled", "tasmota", "esphome", "shelly", "sonoff"), NET_IOT),
    (("probook", "elitebook", "zbook", "thinkpad", "latitude", "macbook", "laptop",
      "desktop-", "-pc", "pc-"), NET_COMPUTERS),
)


_AMAZON_NAMES = next(k for k, g in _NAME_GROUPS if g == NET_AMAZON)


def _client_names(device: dict[str, Any]) -> str:
    names = [device.get("primary_name") or "", device.get("default_name") or ""]
    names += [
        (n.get("name") or "") for n in device.get("names") or [] if isinstance(n, dict)
    ]
    return " ".join(names).lower()


def classify_lan_client(device: dict[str, Any]) -> str:
    """Sous-groupe réseau : host_type Freebox, puis fabricant, puis nom d'hôte."""
    vendor = (device.get("vendor_name") or "").lower()
    names = _client_names(device)
    # Amazon d'abord : la Freebox classe souvent les Echo en "multimedia_device".
    if "amazon" in vendor or any(k in names for k in _AMAZON_NAMES):
        return NET_AMAZON
    group = _HOST_TYPE_GROUPS.get(device.get("host_type") or "")
    if group:
        return group
    for keywords, kw_group in _STRONG_NAME_GROUPS:
        if any(k in names for k in keywords):
            return kw_group
    if "apple" in vendor or "samsung" in vendor or "xiaomi" in vendor or "google" in vendor:
        # Fabricants multi-produits : le nom d'hôte tranche, sinon téléphone.
        for keywords, kw_group in _NAME_GROUPS:
            if any(k in names for k in keywords):
                return kw_group
        if "samsung" in vendor and "tv" in names:
            return NET_MEDIA
        return NET_PHONES
    for keyword, vendor_group in _VENDOR_GROUPS:
        if keyword in vendor:
            return vendor_group
    for keywords, kw_group in _NAME_GROUPS:
        if any(k in names for k in keywords):
            return kw_group
    return NET_OTHER


# OUI des cartes réseau virtuelles : Proxmox (BC:24:11), QEMU/KVM (52:54:00),
# Xen / LXC (00:16:3E), VMware (00:50:56, 00:0C:29, 00:05:69, 00:1C:14),
# Hyper-V (00:15:5D), VirtualBox (08:00:27).
VIRTUAL_OUIS = frozenset(
    {"BC2411", "525400", "00163E", "005056", "000C29", "000569", "001C14", "00155D", "080027"}
)
# Mots (entiers) du nom d'hôte : conteneur / VM / site hébergé.
_VIRTUAL_TOKENS = frozenset(
    {"lxc", "ct", "vm", "vms", "docker", "container", "containers", "conteneur", "conteneurs",
     "site", "sites", "web", "www", "nginx", "apache", "wordpress", "portainer", "k3s", "k8s"}
)
_VIRTUAL_PREFIXES = ("lxc", "docker", "wordpress", "nginx", "apache", "container", "conteneur")
# Mots (entiers) / préfixes du nom d'hôte : serveurs, NAS, hyperviseurs.
_SERVER_TOKENS = frozenset(
    {"pve", "proxmox", "nas", "synology", "diskstation", "qnap", "truenas", "freenas",
     "unraid", "esxi", "vmware", "hyperviseur", "hypervisor", "server", "serveur", "srv",
     "openmediavault", "omv", "xcp", "xcpng"}
)
_SERVER_PREFIXES = ("pve", "proxmox", "truenas", "unraid", "esxi", "hyperviseur", "hypervisor",
                    "serveur", "server", "synology", "diskstation")
# « nas1 », « srv02 » : préfixe court suivi de chiffres seulement.
_SERVER_NUMBERED = re.compile(r"^(nas|srv)\d+$")
# Fabricants d'équipements réseau (switch, routeur, point d'accès tiers).
_NETWORK_VENDORS = (
    "cisco", "netgear", "d-link", "dlink", "ubiquiti", "mikrotik", "routerboard", "zyxel",
    "aruba", "juniper", "fortinet", "ruckus", "edgecore", "draytek", "linksys", "meraki",
)
_NETWORK_TOKENS = frozenset({"routeur", "router", "firewall", "pfsense", "opnsense", "unifi"})


def _name_tokens(names: str) -> list[str]:
    return [t for t in re.split(r"[^0-9a-zà-ÿ]+", names) if t]


def _mac_norm(device: dict[str, Any]) -> str:
    mac = (device.get("l2ident") or {}).get("id") or ""
    return re.sub(r"[^0-9A-Fa-f]", "", str(mac)).upper()


def is_virtual_client(device: dict[str, Any]) -> bool:
    """VM / conteneur (LXC, Docker…) ou site hébergé, d'après l'OUI ou le nom d'hôte."""
    mac = _mac_norm(device)
    if mac[:6] in VIRTUAL_OUIS:
        return True
    tokens = _name_tokens(_client_names(device))
    if any(t in _VIRTUAL_TOKENS for t in tokens):
        return True
    return any(t.startswith(_VIRTUAL_PREFIXES) for t in tokens)


def is_server_client(device: dict[str, Any]) -> bool:
    """Serveur, NAS ou hyperviseur (Proxmox, Synology, TrueNAS, ESXi…)."""
    if device.get("host_type") == "nas":
        return True
    vendor = (device.get("vendor_name") or "").lower()
    if "synology" in vendor or "qnap" in vendor:
        return True
    tokens = _name_tokens(_client_names(device))
    if any(t in _SERVER_TOKENS or _SERVER_NUMBERED.match(t) for t in tokens):
        return True
    return any(t.startswith(_SERVER_PREFIXES) for t in tokens)


def is_network_client(device: dict[str, Any]) -> bool:
    """Switch, routeur, point d'accès tiers (pas un répéteur Free, exclu en amont)."""
    vendor = (device.get("vendor_name") or "").lower()
    if device.get("host_type") == "networking_device" and "free" not in vendor:
        return True
    if any(v in vendor for v in _NETWORK_VENDORS):
        return True
    tokens = _name_tokens(_client_names(device))
    return any(t in _NETWORK_TOKENS for t in tokens)


def lan_client_type(device: dict[str, Any]) -> str:
    """Type d'un client réseau (sous-groupe sous « filaires » / « Wi-Fi »), un de LAN_TYPES.

    Ordre : VM et conteneurs (OUI virtuel ou nom lxc / ct / vm / docker / site…),
    Serveurs (NAS, Proxmox, hyperviseurs), Équipements réseau (switch, routeur), puis
    le classement existant (host_type Freebox, fabricant, nom d'hôte).
    """
    if is_virtual_client(device):
        return NET_VIRTUAL
    if is_server_client(device):
        return NET_SERVERS
    if is_network_client(device):
        return NET_NETWORK
    group = classify_lan_client(device)
    if group == GROUP_CAMERAS:
        return NET_CAMERAS
    if group == GROUP_PLAYER:
        return NET_MEDIA
    return group if group in LAN_TYPES else NET_OTHER


def lan_type_group(lan_group: str, lan_type: str) -> str:
    """Clé du sous-groupe, ex. « lan_wired_net_servers » (identifiant distinct des anciens net_*)."""
    return f"{lan_group}_{lan_type}"


LAN_TYPE_GROUPS = {
    lan_type_group(g, t): (g, t) for g in (GROUP_LAN_WIRED, GROUP_LAN_WIFI) for t in LAN_TYPES
}


def lan_type_name(lan_group: str, lan_type: str) -> str:
    """Nom de l'appareil sous-groupe : unique dans la liste des appareils de HA."""
    suffix = "filaire" if lan_group == GROUP_LAN_WIRED else "Wi-Fi"
    return f"{LAN_TYPE_NAMES[lan_type]} ({suffix})"


def group_label(value: str | None, repeater_names: dict[str, str] | None = None) -> str:
    """Libellé « auto : … » : « Clients réseau filaires › Serveurs », « Clients Wi-Fi › Grange »."""
    if not value:
        return ""
    if value in LAN_TYPE_GROUPS:
        group, lan_type = LAN_TYPE_GROUPS[value]
        return f"{GROUP_NAMES[group]}{LABEL_SEP}{LAN_TYPE_NAMES[lan_type]}"
    if value.startswith(LINK_REPEATER):
        name = (repeater_names or {}).get(value[len(LINK_REPEATER):]) or "répéteur"
        return f"{GROUP_NAMES[GROUP_LAN_WIFI]}{LABEL_SEP}{name}"
    if value in LAN_TYPE_NAMES:
        return LAN_TYPE_NAMES[value]
    return GROUP_NAMES.get(migrate_group(value) or "", "")


def migrate_type_overrides(overrides: Any) -> dict[str, str]:
    """Types forcés enregistrés (valeurs inconnues ignorées)."""
    if not isinstance(overrides, dict):
        return {}
    return {str(k): v for k, v in overrides.items() if v in LAN_TYPES}


def type_choices() -> list[str]:
    """Valeurs proposées dans l'écran « Types des clients réseau »."""
    return [GROUP_AUTO, *LAN_TYPES]


# --- Filaire / Wi-Fi --------------------------------------------------------


def has_wifi_evidence(device: dict[str, Any]) -> bool:
    """Preuve explicite d'une liaison Wi-Fi dans lan/browser (ou /wifi/ap/*/stations/).

    `access_point.type` seul (« gateway » / « repeater ») ne suffit pas : la Freebox le
    renseigne aussi pour les hôtes Ethernet (ex. switch Cisco branché sur la box).
    """
    access_point = device.get("access_point") or {}
    if not isinstance(access_point, dict):
        access_point = {}
    wifi = device.get("wifi") or {}
    if not isinstance(wifi, dict):
        wifi = {}
    if str(access_point.get("connectivity_type") or "").lower() == "wifi":
        return True
    if access_point.get("wifi_information"):
        return True
    if device.get("_wifi_station"):
        return True
    if str(wifi.get("connectivity") or "").lower() == "wifi":
        return True
    return any(
        wifi.get(key) is not None for key in ("wifi_signal_dbm", "wifi_band", "wifi_ssid", "wifi_bssid")
    )


def has_ethernet_evidence(device: dict[str, Any]) -> bool:
    """Preuve explicite d'une liaison Ethernet (connectivity_type / ethernet_information)."""
    access_point = device.get("access_point") or {}
    if not isinstance(access_point, dict):
        return False
    if str(access_point.get("connectivity_type") or "").lower() == "ethernet":
        return True
    return bool(access_point.get("ethernet_information"))


def lan_client_link(device: dict[str, Any], repeater_of: Any = None) -> str | None:
    """Mode de connexion d'un client LAN d'après lan/browser.

    - Wi-Fi d'un répéteur reconnu : « repeater:<MAC canonique> » ;
    - Wi-Fi de la box (ou point d'accès Wi-Fi non identifié) : « wifi » ;
    - Ethernet (sur la box, sur un port d'un répéteur ou derrière un switch) : « wired » ;
      un hôte EN LIGNE sans aucun indice Wi-Fi (pas d'access_point, ou access_point
      « gateway » sans connectivity_type, ex. switch Cisco) est filaire ;
    - rien de lisible (hôte hors ligne sans indice) : None, dernier classement conservé
      (un téléphone Wi-Fi hors ligne ne passe jamais en filaire).
    `repeater_of(mac)` renvoie la MAC canonique du répéteur physique, sinon "".
    """
    parent = device.get("wifi_parent") or {}
    access_point = device.get("access_point") or {}
    if not isinstance(access_point, dict):
        access_point = {}
    if parent.get("kind") == "repeater" and parent.get("ap_id"):
        return f"{LINK_REPEATER}{parent['ap_id']}"
    if parent.get("kind") == "gateway":
        return LINK_WIFI
    if has_ethernet_evidence(device):
        return LINK_WIRED
    ap_type = access_point.get("type")
    if has_wifi_evidence(device) or (ap_type == "repeater" and access_point.get("mac")):
        # Client d'un répéteur sans détail : Wi-Fi (les ports Ethernet du répéteur
        # remontent connectivity_type « ethernet »).
        if ap_type == "repeater" and access_point.get("mac") and repeater_of:
            canon = repeater_of(access_point["mac"])
            if canon:
                return f"{LINK_REPEATER}{canon}"
        return LINK_WIFI
    if device.get("active"):
        return LINK_WIRED
    return None


def link_group(link: str | None) -> str | None:
    """Regroupement affiché dans « Groupes des appareils » (auto : …)."""
    if link == LINK_WIRED:
        return GROUP_LAN_WIRED
    if link == LINK_WIFI or (link or "").startswith(LINK_REPEATER):
        return GROUP_LAN_WIFI
    return None


# Un client actif doit être vu 2 relevés de suite sur un nouveau point d'accès avant
# d'être déplacé (un téléphone qui passe de la box au répéteur ne « clignote » pas).
LINK_CONFIRM_POLLS = 2


def next_lan_link(
    current: str | None,
    seen: str | None,
    active: bool,
    pending: tuple[str, int] | None,
) -> tuple[str | None, tuple[str, int] | None]:
    """Nouveau lien retenu et attente éventuelle : (lien, (lien en attente, nombre))."""
    if seen is None or seen == current:
        return current, None  # rien de lisible / inchangé : dernier classement conservé
    if current is None:
        return seen, None  # premier classement : immédiat
    if not active:
        return current, None  # hors ligne : on ne déplace pas sur des données périmées
    count = pending[1] + 1 if pending and pending[0] == seen else 1
    if count >= LINK_CONFIRM_POLLS:
        return seen, None
    return current, (seen, count)


# --- Registre ---------------------------------------------------------------


def async_get_group_device(
    hass: HomeAssistant, entry_id: str, router_mac: str, group: str
) -> str:
    """Crée au besoin l'appareil « Freebox Maison connectée » (premier niveau)."""
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry_id,
        identifiers={group_identifier(router_mac, group)},
        manufacturer="Freebox SAS",
        model=GROUP_MODELS.get(group, GROUP_NAMES[group]),
        name=GROUP_NAMES[group],
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    updates: dict[str, Any] = {}
    if device.name != GROUP_NAMES[group]:
        updates["name"] = GROUP_NAMES[group]  # renommage (name_by_user conservé)
    if device.via_device_id is not None:
        updates["via_device_id"] = None  # service de premier niveau
    if updates:
        device = registry.async_update_device(device.id, **updates) or device
    return device.id


def async_get_lan_group_device(
    hass: HomeAssistant, entry_id: str, router_mac: str, group: str, parent_id: str | None
) -> str:
    """Crée au besoin « Clients réseau filaires » / « Clients Wi-Fi » sous le Freebox Server."""
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry_id,
        identifiers={group_identifier(router_mac, group)},
        manufacturer="Freebox SAS",
        model=GROUP_MODELS.get(group, GROUP_NAMES[group]),
        name=GROUP_NAMES[group],
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    updates: dict[str, Any] = {}
    if device.name != GROUP_NAMES[group]:
        updates["name"] = GROUP_NAMES[group]
    if parent_id and device.via_device_id != parent_id:
        updates["via_device_id"] = parent_id
    if updates:
        device = registry.async_update_device(device.id, **updates) or device
    return device.id


def async_get_lan_type_device(
    hass: HomeAssistant,
    entry_id: str,
    router_mac: str,
    lan_group: str,
    lan_type: str,
    parent_id: str | None,
) -> str:
    """Crée au besoin le sous-groupe de type (ex. « Serveurs (filaire) ») sous son groupe."""
    registry = dr.async_get(hass)
    name = lan_type_name(lan_group, lan_type)
    device = registry.async_get_or_create(
        config_entry_id=entry_id,
        identifiers={group_identifier(router_mac, lan_type_group(lan_group, lan_type))},
        manufacturer="Freebox SAS",
        model=f"{GROUP_NAMES[lan_group]}{LABEL_SEP}{LAN_TYPE_NAMES[lan_type]}",
        name=name,
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    updates: dict[str, Any] = {}
    if device.name != name:
        updates["name"] = name
    if parent_id and device.via_device_id != parent_id:
        updates["via_device_id"] = parent_id
    if updates:
        device = registry.async_update_device(device.id, **updates) or device
    return device.id


def _has_entities(hass: HomeAssistant, device_id: str) -> bool:
    from homeassistant.helpers import entity_registry as er

    return bool(
        er.async_entries_for_device(er.async_get(hass), device_id, include_disabled_entities=True)
    )


def _has_children(registry: Any, device_id: str, entry_id: str | None = None) -> bool:
    devices = entry_devices(registry, entry_id) if entry_id else registry.devices.values()
    return any(d.via_device_id == device_id for d in devices)


def async_remove_unused_group_devices(
    hass: HomeAssistant, entry: ConfigEntry, router_mac: str, used: set[str]
) -> list[str]:
    """Retire les anciens parents virtuels et appareils de service devenus vides.

    Appelé en différé (entités déjà ré-attachées). Un appareil n'est retiré que
    s'il n'a plus ni entité ni enfant : aucune entité n'est supprimée.
    """
    registry = dr.async_get(hass)
    removed: list[str] = []
    candidates = [group_identifier(router_mac, g) for g in LEGACY_GROUPS]
    candidates += [(DOMAIN, f"{router_mac}_service_{k}") for k in LEGACY_SERVICE_KEYS]
    # Sous-groupes de type d'abord (un groupe filaire / Wi-Fi vidé peut alors partir aussi).
    for group in (*LAN_TYPE_GROUPS, GROUP_HOME, *LAN_GROUPS):
        if group not in used:
            candidates.append(group_identifier(router_mac, group))
    for ident in candidates:
        device = get_device_by_identifier(registry, ident, entry.entry_id)
        if device is None:
            continue
        if _has_entities(hass, device.id) or _has_children(registry, device.id, entry.entry_id):
            continue
        remove_device(registry, device.id)
        removed.append(device.name or ident[1])
    return removed


def async_detach_top_level_devices(
    hass: HomeAssistant, entry: ConfigEntry, idents: list[tuple[str, str]]
) -> None:
    """Players et TNT : services de premier niveau (plus de via_device)."""
    registry = dr.async_get(hass)
    for ident in idents:
        device = get_device_by_identifier(registry, ident, entry.entry_id)
        if device is not None and device.via_device_id:
            registry.async_update_device(device.id, via_device_id=None)


def async_remove_merged_node_devices(
    hass: HomeAssistant, entry: ConfigEntry, node_ids: set[Any]
) -> int:
    """Retire les anciens appareils de nœuds fusionnés dans un groupe, s'ils n'ont plus d'entités."""
    from homeassistant.helpers import entity_registry as er

    registry = dr.async_get(hass)
    entities = er.async_get(hass)
    removed = 0
    for node_id in node_ids:
        device = get_device_by_identifier(registry, (DOMAIN, node_id), entry.entry_id)
        if device is None:
            continue
        if er.async_entries_for_device(entities, device.id, include_disabled_entities=True):
            continue
        if _has_children(registry, device.id, entry.entry_id):
            continue
        remove_device(registry, device.id)
        removed += 1
    return removed


def group_choices() -> list[str]:
    """Valeurs proposées dans l'écran « Groupes des appareils »."""
    return [GROUP_AUTO, *SERVICE_CHOICES, *LAN_GROUPS]


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
        if any(len(ident) > 0 and ident[0] == DOMAIN for ident in device.identifiers):
            continue
        macs = {c[1] for c in device.connections if c[0] == dr.CONNECTION_NETWORK_MAC}
        if not macs or router_mac in macs:
            continue
        remove_device(registry, device.id)
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


# --- Répéteurs : un appareil par répéteur physique ---------------------------


def _repeater_idents(device: Any) -> list[str]:
    """Identifiants `repeater_*` de l'appareil (ignore les valeurs non texte, ex. id de nœud int)."""
    result: list[str] = []
    for ident in getattr(device, "identifiers", None) or ():
        if not isinstance(ident, tuple) or len(ident) < 2 or ident[0] != DOMAIN:
            continue
        value = ident[1]
        if isinstance(value, str) and value.startswith("repeater_"):
            result.append(value)
    return sorted(result)


def _norm_mac(value: str | None) -> str:
    return (value or "").upper().replace(":", "").replace("-", "")


def ul_twin(norm: str) -> str:
    """Même MAC (normalisée) avec le bit « locally administered » (0x02 du 1er octet) inversé."""
    if len(norm) != 12:
        return ""
    try:
        first = int(norm[:2], 16)
    except ValueError:
        return ""
    return f"{first ^ 0x02:02X}{norm[2:]}"


_REPEATER_NAME_WORDS = {"repeteur", "répéteur", "repeater", "wifi", "wi", "fi", "freebox", "free"}


def is_specific_repeater_name(name: str | None) -> bool:
    """Nom choisi (« Grange », « Repeteur Wifi Freebox Garage ») et non générique
    (« Repeteur Wifi Freebox », « #2 », « Repeteur-Wifi-Freebox-2 », MAC)."""
    if _is_generic(name):
        return False
    words = re.findall(r"[^\W\d_]+", (name or "").lower())
    return any(w not in _REPEATER_NAME_WORDS for w in words)


def migrate_repeater_merges(value: Any) -> dict[str, str]:
    """Options « fusion manuelle » : {MAC doublon: MAC cible} au format AA:BB:..."""
    result: dict[str, str] = {}
    if not isinstance(value, dict):
        return result
    for dup, target in value.items():
        d, t = _norm_mac(str(dup)), _norm_mac(str(target))
        if len(d) == 12 and len(t) == 12 and d != t:
            result[":".join(d[i : i + 2] for i in range(0, 12, 2))] = ":".join(
                t[i : i + 2] for i in range(0, 12, 2)
            )
    return result


def _is_free_norm(norm: str) -> bool:
    from .wifi_ap import is_free_mac

    return is_free_mac(norm)


def async_merge_repeater_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    router_mac: str,
    repeaters: dict[str, dict[str, Any]],
    rejected_macs: list[str] | None = None,
    lan_macs: set[str] | None = None,
) -> int:
    """Fusionne les appareils en double d'un même répéteur physique.

    Pour chaque répéteur (MAC canonique + toutes ses MAC), les appareils de cette
    entrée portant `repeater_<une de ses MAC>` ou une de ses MAC en connexion sont
    réunis : entités et enfants déplacés vers l'appareil conservé (entity_id
    inchangés), puis les doublons vidés sont retirés. Les entités par point d'accès
    des anciennes MAC (« En ligne », clients Wi-Fi), devenues doublons, sont retirées.
    Appelé avant l'ajout des entités, pour éviter les collisions d'identifiants.
    """
    from homeassistant.helpers import entity_registry as er

    registry = dr.async_get(hass)
    entities = er.async_get(hass)
    router_norm = _norm_mac(router_mac)
    merged = 0
    devices = [
        d
        for d in entry_devices(registry, entry.entry_id)
        if (DOMAIN, router_mac) not in d.identifiers
    ]
    all_macs = {_norm_mac(m) for p in repeaters.values() for m in p.get("macs") or []}

    def _bssid_like(norm: str) -> bool:
        # MAC Free « locally administered » qui n'est pas le jumeau d'une MAC connue.
        return (
            len(norm) == 12
            and bool(int(norm[:2], 16) & 0x02)
            and _is_free_norm(norm)
            and ul_twin(norm) not in all_macs
        )

    # Bloc de BSSID (5 premiers octets) -> répéteurs qui le possèdent.
    block_owner: dict[str, set[str]] = {}
    for canon, payload in repeaters.items():
        for m in payload.get("macs") or []:
            n = _norm_mac(m)
            if _bssid_like(n):
                block_owner.setdefault(n[:10], set()).add(canon)
    for canon, payload in repeaters.items():
        norms = {_norm_mac(m) for m in payload.get("macs") or [canon]} - {router_norm}
        canon_ident = (DOMAIN, f"repeater_{canon}")

        def _belongs(device: dr.DeviceEntry) -> bool:
            for ident in _repeater_idents(device):
                mac = _norm_mac(ident[9:])
                if mac in norms:
                    return True
                # Jumeau « locally administered » exact (22:66:CF:4B:49:69 pour la MAC
                # principale 20:66:CF:4B:49:69) d'une MAC Free du répéteur : même appareil.
                twin = ul_twin(mac)
                if twin in norms and int(mac[:2], 16) & 0x02 and _is_free_norm(twin):
                    return True
                # Interface du bloc de BSSID d'UN SEUL répéteur (ex. 22:66:CF:C6:92:D4 pour
                # les BSSID 22:66:CF:C6:92:D2 / D6 de Chambre fille).
                if _bssid_like(mac) and block_owner.get(mac[:10]) == {canon}:
                    return True
            return any(
                c[0] == dr.CONNECTION_NETWORK_MAC and _norm_mac(c[1]) in norms
                for c in device.connections
            )

        group = [d for d in devices if _belongs(d)]
        _LOGGER.info(
            "Répéteur %s : appareils trouvés %s",
            canon,
            [(d.id, d.name, d.model, _repeater_idents(d)) for d in group],
        )
        # Entités par AP des anciennes MAC (une seule par répéteur désormais).
        for alias in payload.get("macs") or []:
            if _norm_mac(alias) == _norm_mac(canon):
                continue
            for domain, uid in (
                ("binary_sensor", f"{router_mac}_repeater_{alias}"),
                ("sensor", f"{router_mac}_wifi_clients_{alias}"),
                ("sensor", f"{router_mac}_wifi_client_list_{alias}"),
            ):
                entity_id = entities.async_get_entity_id(domain, DOMAIN, uid)
                if entity_id:
                    entities.async_remove(entity_id)
        if not group:
            continue
        counts = {
            d.id: len(er.async_entries_for_device(entities, d.id, include_disabled_entities=True))
            for d in group
        }
        keeper = next((d for d in group if canon_ident in d.identifiers), None) or max(
            group, key=lambda d: counts[d.id]
        )
        _LOGGER.info("Répéteur %s : appareil conservé %s (%s)", canon, keeper.id, keeper.name)
        area_id = keeper.area_id
        name_by_user = keeper.name_by_user
        for dup in group:
            if dup.id == keeper.id:
                continue
            for ent in er.async_entries_for_device(entities, dup.id, include_disabled_entities=True):
                entities.async_update_entity(ent.entity_id, device_id=keeper.id)
            for child in entry_devices(registry, entry.entry_id):
                if child.via_device_id == dup.id:
                    registry.async_update_device(child.id, via_device_id=keeper.id)
            area_id = area_id or dup.area_id
            if not name_by_user:
                if dup.name_by_user:
                    name_by_user = dup.name_by_user
                elif (
                    is_specific_repeater_name(dup.name)
                    and not is_specific_repeater_name(keeper.name)
                    and not is_specific_repeater_name(payload.get("name"))
                ):
                    # ex. « Repeteur Wifi Freebox Garage » fusionné dans « … #2 » : on garde Garage.
                    name_by_user = dup.name
            _LOGGER.info(
                "Répéteur %s : doublon %s (%s) fusionné dans %s", canon, dup.name,
                _repeater_idents(dup), keeper.name,
            )
            remove_device(registry, dup.id)
            devices = [d for d in devices if d.id != dup.id]
            merged += 1
        try:
            registry.async_update_device(
                keeper.id,
                new_identifiers={canon_ident},
                area_id=area_id,
                name_by_user=name_by_user,
            )
        except Exception:  # noqa: BLE001 — collision éventuelle : on garde l'existant
            pass
    known = {_norm_mac(m) for p in repeaters.values() for m in p.get("macs") or []}
    rejected = {_norm_mac(m) for m in rejected_macs or []}
    lan = {_norm_mac(m) for m in lan_macs or set()}
    for device in entry_devices(registry, entry.entry_id):
        idents = _repeater_idents(device)
        if not idents or any(_norm_mac(i[9:]) in known for i in idents):
            continue
        macs = {_norm_mac(i[9:]) for i in idents}
        if macs & rejected and macs & lan:
            # Hôte présent dans lan/browser mais pas un répéteur Free (MAC non Free, non
            # reliée à un répéteur) : redevient un client réseau ordinaire, entités conservées.
            try:
                registry.async_update_device(device.id, new_identifiers=set())
                _LOGGER.warning(
                    "Appareil %s (%s) n'est pas un répéteur Free : converti en client réseau",
                    device.name, idents,
                )
                merged += 1
                continue
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Conversion de %s impossible", idents, exc_info=True)
        _LOGGER.warning(
            "Appareil répéteur non rattaché conservé : %s (%s, modèle %s)%s",
            idents, device.name, device.model,
            "" if macs & lan else " — absent de lan/browser (débranché ?), supprimable à la main",
        )
    return merged


def repeater_registry_devices(hass: HomeAssistant, entry: ConfigEntry) -> list[dict[str, Any]]:
    """Appareils répéteurs (identifiant repeater_*) de l'entrée, pour diagnostic / journal."""
    from homeassistant.helpers import entity_registry as er

    registry = dr.async_get(hass)
    entities = er.async_get(hass)
    result: list[dict[str, Any]] = []
    for device in entry_devices(registry, entry.entry_id):
        idents = _repeater_idents(device)
        if not idents:
            continue
        ents = er.async_entries_for_device(entities, device.id, include_disabled_entities=True)
        result.append(
            {
                "device_id": device.id,
                "name": device.name,
                "name_by_user": device.name_by_user,
                "model": device.model,
                "area_id": device.area_id,
                "identifiers": idents,
                "connections": sorted(f"{t}:{v}" for t, v in device.connections),
                "via_device_id": device.via_device_id,
                "entity_count": len(ents),
                "entities": sorted(e.entity_id for e in ents),
            }
        )
    return result
