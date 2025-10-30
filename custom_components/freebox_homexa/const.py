"""Constantes pour l'intégration Freebox dans Home Assistant."""
# DESCRIPTION: Ce fichier contient les constantes utilisées dans l'intégration Freebox.
# OBJECTIF: Centraliser les valeurs constantes pour une gestion facile et cohérente.

from __future__ import annotations
import enum
import socket
from homeassistant.const import Platform
from homeassistant.components.alarm_control_panel import AlarmControlPanelState  # Ajout pour ARMED_NIGHT

# SECTION: Domaines et services
DOMAIN = "freebox_homexa"  # Domaine de l'intégration dans Home Assistant
SERVICE_REBOOT = "reboot"  # Nom du service pour redémarrer la Freebox

# SECTION: Valeurs par défaut
VALUE_NOT_SET = -1  # Valeur utilisée lorsque aucune valeur n'est définie
DEFAULT_DEVICE_NAME = "Unknown device"  # Nom par défaut pour un appareil non identifié

# SECTION: Description de l'application
APP_DESC = {
    "app_id": "hass",  # Identifiant de l'application
    "app_name": "Home Assistant",  # Nom de l'application
    "app_version": "0.106",  # Version de l'application
    "device_name": socket.gethostname(),  # Nom de l'appareil hôte
}
API_VERSION = "v6"  # Version de l'API Freebox utilisée

# SECTION: Plateformes supportées
PLATFORMS = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.COVER,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
]  # Liste des plateformes Home Assistant supportées par l'intégration

# SECTION: Stockage
STORAGE_KEY = DOMAIN  # Clé de stockage pour les données de configuration
STORAGE_VERSION = 1  # Version du stockage

# SECTION: Attributs
ATTR_MODEL = "model"  # Attribut pour le modèle de l'appareil
ATTR_DETECTION = "detection"  # Attribut pour la détection de mouvement

# SECTION: Capteurs de connexion
CONNECTION_SENSORS_KEYS = {"rate_down", "rate_up"}  # Clés des capteurs de vitesse de connexion (débit descendant et montant)

# SECTION: Icônes des appareils
DEVICE_ICONS = {
    "freebox_delta": "mdi:television-guide",
    "freebox_hd": "mdi:television-guide",
    "freebox_mini": "mdi:television-guide",
    "freebox_player": "mdi:television-guide",
    "ip_camera": "mdi:cctv",
    "ip_phone": "mdi:phone-voip",
    "laptop": "mdi:laptop",
    "multimedia_device": "mdi:play-network",
    "nas": "mdi:nas",
    "networking_device": "mdi:network",
    "printer": "mdi:printer",
    "router": "mdi:router-wireless",
    "smartphone": "mdi:cellphone",
    "tablet": "mdi:tablet",
    "television": "mdi:television",
    "vg_console": "mdi:gamepad-variant",
    "workstation": "mdi:desktop-tower-monitor",
}  # Dictionnaire associant les types d'appareils à leurs icônes Material Design

# SECTION: Catégories Freebox Home
class FreeboxHomeCategory(enum.StrEnum):
    """Énumération des catégories d'appareils Freebox Home."""
    ALARM = "alarm"
    CAMERA = "camera"
    DWS = "dws"
    IOHOME = "iohome"
    KFB = "kfb"
    OPENER = "opener"
    PIR = "pir"
    RTS = "rts"
    BASIC_SHUTTER = "basic_shutter"
    SHUTTER = "shutter"

CATEGORY_TO_MODEL = {
    FreeboxHomeCategory.PIR: "F-HAPIR01A",
    FreeboxHomeCategory.CAMERA: "F-HACAM01A",
    FreeboxHomeCategory.DWS: "F-HADWS01A",
    FreeboxHomeCategory.KFB: "F-HAKFB01A",
    FreeboxHomeCategory.ALARM: "F-MSEC07A",
    FreeboxHomeCategory.RTS: "RTS",
    FreeboxHomeCategory.IOHOME: "IOHome",
    FreeboxHomeCategory.SHUTTER: "Volet roulant",
    FreeboxHomeCategory.BASIC_SHUTTER: "Volet roulant basic",
    FreeboxHomeCategory.OPENER: "Ouvrant,Porte",
}  # Mapping des catégories aux modèles d'appareils pour l'affichage dans Home Assistant

HOME_COMPATIBLE_CATEGORIES = [
    FreeboxHomeCategory.ALARM,
    FreeboxHomeCategory.CAMERA,
    FreeboxHomeCategory.DWS,
    FreeboxHomeCategory.IOHOME,
    FreeboxHomeCategory.KFB,
    FreeboxHomeCategory.PIR,
    FreeboxHomeCategory.RTS,
    FreeboxHomeCategory.OPENER,
    FreeboxHomeCategory.SHUTTER,
    FreeboxHomeCategory.BASIC_SHUTTER,
]  # Liste des catégories compatibles avec Freebox Home
