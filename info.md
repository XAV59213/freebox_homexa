# Freebox Homexa

Intégration Home Assistant pour Freebox Server, Freebox Home, répéteurs Wi-Fi Free et Freebox Player.

**Version :** 28.8.91 · Home Assistant **2026.8.0+**

Doc complète : [Wiki](https://github.com/XAV59213/freebox_homexa/wiki)

## Installation

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Default-41BDF5?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=white" alt="HACS Default"></a>
</p>

> [!TIP]
> 🎉 **Freebox Homexa est maintenant disponible directement dans la bibliothèque HACS / Marketplace.**
> Plus besoin d’ajouter le dépôt personnalisé : cherche simplement « Freebox Homexa » dans HACS.

[![Ouvrir Freebox Homexa dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=XAV59213&repository=freebox_homexa&category=integration)

1. HACS → recherche **Freebox Homexa** → **Télécharger**
2. Redémarre Home Assistant
3. Ajoute l’intégration via l’UI (appairage sur l’écran Freebox)

## Fonctionnalités

- Détection Freebox Home (interrupteurs, caméras, volets, PIR, contacts)
- Alarme **Présent / Absent / Désarmé**
- Suivi des clients Wi-Fi
- Répéteurs Free **F-RP01A**
- Player Devialet / Mini 4K / Pop + télécommande
- Sources TV / HDMI (CEC) / YouTube / Netflix
- Code télécommande Player réglable dans Configurer
- Sonnerie du téléphone sur le port FXS (boutons et actions, durée avec arrêt garanti, droit Téléphonie requis)
- Action `freebox_homexa.remote` vers le Player (touches, `player_id` / `device_id` facultatifs)
- Entités indisponibles si la Freebox est injoignable (journal unique « Freebox injoignable » / « de nouveau joignable »)
- Appareils par client réseau sur option (décochée par défaut sur une nouvelle installation)

HDMI = sortie Player vers la TV (CEC), pas un switch d’entrée HDMI.

## Dépannage

Voir [Wiki — Dépannage](https://github.com/XAV59213/freebox_homexa/wiki/D%C3%A9pannage).
