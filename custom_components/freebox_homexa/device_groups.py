"""Appareils parents virtuels (un par service Freebox OS), noms et pièces suggérées."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, FreeboxHomeCategory

# Groupes calqués sur les droits d'accès de Freebox OS (un groupe par service).
GROUP_HOME = "home"
GROUP_CAMERAS = "cameras"
GROUP_PLAYER = "player"
GROUP_VM = "vm"
GROUP_DOWNLOADS = "downloads"
GROUP_PARENTAL = "parental"
GROUP_CALLS = "calls"
GROUP_TV = "tv"
GROUP_EQUIPMENT = "equipment"
GROUP_OTHER = "other"
GROUP_AUTO = "auto"
CONF_DEVICE_GROUP_OVERRIDES = "device_group_overrides"

# Anciens groupes par type (≤ 28.8.39) : conservés pour la migration et le nettoyage.
LEGACY_GROUP_MAP = {
    "security": GROUP_HOME,
    "windows": GROUP_HOME,
    "covers": GROUP_HOME,
    "network": GROUP_EQUIPMENT,
    "media": GROUP_PLAYER,
    "infrastructure": GROUP_EQUIPMENT,
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

SERVICE_GROUPS = (
    GROUP_HOME, GROUP_CAMERAS, GROUP_PLAYER, GROUP_VM, GROUP_DOWNLOADS,
    GROUP_PARENTAL, GROUP_CALLS, GROUP_TV, GROUP_EQUIPMENT, GROUP_OTHER,
)

GROUP_NAMES = {
    GROUP_HOME: "Maison connectée et alarme",
    GROUP_CAMERAS: "Caméras",
    GROUP_PLAYER: "Freebox Player",
    GROUP_VM: "Contrôle de la VM",
    GROUP_DOWNLOADS: "Téléchargements",
    GROUP_PARENTAL: "Contrôle parental",
    GROUP_CALLS: "Journal d'appels",
    GROUP_TV: "Guide TV et enregistrements",
    GROUP_EQUIPMENT: "Équipements et réglages Freebox",
    GROUP_OTHER: "Autres",
    NET_AMAZON: "Amazon",
    NET_PHONES: "Téléphones",
    NET_COMPUTERS: "Ordinateurs",
    NET_MEDIA: "TV & multimédia",
    NET_IOT: "Objets connectés",
    NET_CONSOLES: "Consoles",
    NET_PRINTERS: "Imprimantes",
    NET_OTHER: "Autres (réseau)",
    # anciens groupes, uniquement pour le libellé du nettoyage
    "security": "Sécurité",
    "windows": "Fenêtres",
    "covers": "Volets",
    "network": "Réseau",
    "media": "Multimédia",
    "infrastructure": "Infrastructure",
}
GROUP_MODELS = {
    GROUP_HOME: "Service Freebox Home : alarme, détecteurs, volets, ouvrants, prises",
    GROUP_CAMERAS: "Service caméras (Freebox Home et caméras IP)",
    GROUP_PLAYER: "Service Freebox Player",
    GROUP_VM: "Service machines virtuelles",
    GROUP_DOWNLOADS: "Service gestionnaire de téléchargements",
    GROUP_PARENTAL: "Service contrôle parental",
    GROUP_CALLS: "Service téléphonie / journal d'appels",
    GROUP_TV: "Service guide TV, TNT et enregistrements",
    GROUP_EQUIPMENT: "Service équipements : répéteurs, disques, clients réseau",
    GROUP_OTHER: "Appareils non classés",
}


def group_identifier(router_mac: str, group: str) -> tuple[str, str]:
    """Identifiant stable du parent virtuel, ex. (DOMAIN, "<mac>_group_security")."""
    return (DOMAIN, f"{router_mac}_group_{group}")


def group_parent(group: str) -> str | None:
    """Groupe parent (les sous-groupes réseau sont sous « Équipements »)."""
    return GROUP_EQUIPMENT if group in NETWORK_SUBGROUPS else None


def home_node_group(node: dict[str, Any]) -> str:
    """Groupe d'un nœud Freebox Home : Caméras, sinon Maison connectée et alarme."""
    if node.get("category") == FreeboxHomeCategory.CAMERA:
        return GROUP_CAMERAS
    return GROUP_HOME


def migrate_group(group: str | None) -> str | None:
    """Ancien groupe par type -> groupe de service le plus proche."""
    if group is None:
        return None
    return LEGACY_GROUP_MAP.get(group, group)


def migrate_overrides(overrides: dict[str, str] | None) -> dict[str, str]:
    """Surcharges enregistrées migrées vers les groupes de service (inconnus ignorés)."""
    valid = set(SERVICE_GROUPS) | set(NETWORK_SUBGROUPS)
    result: dict[str, str] = {}
    for key, value in (overrides or {}).items():
        new = migrate_group(value)
        if new in valid:
            result[key] = new
    return result


# --- Classification des clients réseau --------------------------------------

_HOST_TYPE_GROUPS = {
    "smartphone": NET_PHONES,
    "tablet": NET_PHONES,
    "ip_phone": NET_PHONES,
    "workstation": NET_COMPUTERS,
    "laptop": NET_COMPUTERS,
    "nas": NET_COMPUTERS,
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
    ("synology", NET_COMPUTERS),
    ("qnap", NET_COMPUTERS),
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


# --- Registre ---------------------------------------------------------------


def async_get_group_device(
    hass: HomeAssistant,
    entry_id: str,
    router_mac: str,
    server_device_id: str | None,
    group: str,
) -> str:
    """Crée au besoin le parent virtuel (et son parent) ; retourne son device_id."""
    registry = dr.async_get(hass)
    parent = group_parent(group)
    parent_id = (
        async_get_group_device(hass, entry_id, router_mac, server_device_id, parent)
        if parent
        else server_device_id
    )
    device = registry.async_get_or_create(
        config_entry_id=entry_id,
        identifiers={group_identifier(router_mac, group)},
        manufacturer="Freebox SAS",
        model=GROUP_MODELS.get(group, f"Groupe {GROUP_NAMES[group]}"),
        name=GROUP_NAMES[group],
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    if parent_id and device.via_device_id != parent_id:
        registry.async_update_device(device.id, via_device_id=parent_id)
    return device.id


ALL_GROUPS = (*SERVICE_GROUPS, *NETWORK_SUBGROUPS)
# Groupes vérifiés par le nettoyage : actuels + anciens groupes par type.
CLEANUP_GROUPS = (*ALL_GROUPS, *LEGACY_GROUP_MAP)


def async_remove_unused_group_devices(
    hass: HomeAssistant, entry: ConfigEntry, router_mac: str, used: set[str]
) -> list[str]:
    """Retire les parents virtuels de cette entrée qu'aucun appareil n'a demandés.

    `used` contient les groupes (et leurs parents) résolus par les entités : on ne
    se fie pas au registre, où les enfants ne sont pas encore tous enregistrés.
    """
    registry = dr.async_get(hass)
    removed: list[str] = []
    for group in CLEANUP_GROUPS:
        if group in used:
            continue
        device = registry.async_get_device(identifiers={group_identifier(router_mac, group)})
        if device is None or entry.entry_id not in device.config_entries:
            continue
        registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
        removed.append(GROUP_NAMES[group])
    return removed


def group_choices() -> list[str]:
    """Valeurs proposées dans l'écran « Groupes des appareils »."""
    return [GROUP_AUTO, *ALL_GROUPS]


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
