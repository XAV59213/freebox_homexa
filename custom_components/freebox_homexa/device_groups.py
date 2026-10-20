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
SERVICE_CHOICES = (GROUP_SERVER, GROUP_HOME, GROUP_PLAYER, GROUP_TNT)

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

# "player" : ancien parent virtuel « Freebox Player » (28.8.40), source de doublon.
LEGACY_GROUPS = (*LEGACY_GROUP_MAP, *NETWORK_SUBGROUPS, GROUP_PLAYER)

GROUP_NAMES = {
    GROUP_SERVER: "Freebox Server",
    GROUP_HOME: "Freebox Maison connectée",
    GROUP_PLAYER: "Freebox Player",
    GROUP_TNT: "TNT",
}
GROUP_MODELS = {
    GROUP_HOME: "Freebox Home : alarme, détecteurs, volets, caméras, prises",
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
    if group in SERVICE_CHOICES:
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
        if new in SERVICE_CHOICES:
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
    if GROUP_HOME not in used:
        candidates.append(group_identifier(router_mac, GROUP_HOME))
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
    return [GROUP_AUTO, *SERVICE_CHOICES]


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


def _norm_mac(value: str | None) -> str:
    return (value or "").upper().replace(":", "").replace("-", "")


def async_merge_repeater_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    router_mac: str,
    repeaters: dict[str, dict[str, Any]],
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
    for canon, payload in repeaters.items():
        norms = {_norm_mac(m) for m in payload.get("macs") or [canon]} - {router_norm}
        canon_ident = (DOMAIN, f"repeater_{canon}")

        def _belongs(device: dr.DeviceEntry) -> bool:
            for domain, ident in device.identifiers:
                if domain == DOMAIN and ident.startswith("repeater_") and _norm_mac(ident[9:]) in norms:
                    return True
            return any(
                c[0] == dr.CONNECTION_NETWORK_MAC and _norm_mac(c[1]) in norms
                for c in device.connections
            )

        group = [d for d in devices if _belongs(d)]
        _LOGGER.info(
            "Répéteur %s : appareils trouvés %s",
            canon,
            [(d.id, d.name, d.model, sorted(i for _, i in d.identifiers)) for d in group],
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
            name_by_user = name_by_user or dup.name_by_user
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
    for device in devices:
        idents = [i for dom, i in device.identifiers if dom == DOMAIN and i.startswith("repeater_")]
        if idents and not any(_norm_mac(i[9:]) in known for i in idents):
            _LOGGER.info(
                "Appareil répéteur non rattaché : %s (%s, modèle %s)", idents, device.name, device.model
            )
    return merged
