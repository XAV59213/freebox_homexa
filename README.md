[![GitHub Release](https://img.shields.io/github/v/release/XAV59213/freebox_homexa?style=flat-square)](https://github.com/XAV59213/freebox_homexa/releases) [![hacs](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://hacs.xyz/) [![GitHub Activity](https://img.shields.io/github/commit-activity/m/XAV59213/freebox_homexa?style=flat-square)](https://github.com/XAV59213/freebox_homexa/commits/main)

# Freebox Homexa

Intégration **Home Assistant** pour la Freebox Server, Freebox Home, les répéteurs Wi-Fi Free et le Freebox Player.

**Version actuelle :** [28.8.2](https://github.com/XAV59213/freebox_homexa/releases/tag/28.8.2) · Home Assistant **2026.8.0+**

Wiki : [Documentation](https://github.com/XAV59213/freebox_homexa/wiki)

> Projet indépendant, non affilié à Free.

---

## Fonctionnalités

| Domaine | Ce que ça fait |
|---|---|
| Freebox Server | État, réseau, Wi-Fi, capteurs connexion |
| Freebox Home | Détection auto : interrupteurs, caméras, volets |
| Alarme | 3 modes comme l’app Free : **Présent / Absent / Désarmé** |
| Appareils Wi-Fi | Suivi des clients connectés |
| Répéteurs Free | F-RP01A : capteur *En ligne* + clients |
| Player | Devialet, Mini 4K, Pop : volume, play/pause, sources |
| Télécommande | Entité `remote` + sources TV / HDMI (CEC) / YouTube / Netflix |

HDMI sur le Player = **sortie vers le téléviseur** (CEC One Touch Play), pas un changement d’entrée HDMI de la TV.

---

## Installation (HACS)

L’intégration n’est pas encore dans le store HACS par défaut. Ajoute le dépôt custom :

1. HACS → menu → **Dépôts personnalisés**
2. URL : `https://github.com/XAV59213/freebox_homexa`
3. Catégorie : **Integration**
4. Installe **Freebox Homexa**, puis redémarre Home Assistant

Installation manuelle : copie le dossier `custom_components/freebox_homexa` dans `/config/custom_components/` puis redémarre.

---

## Configuration

[![Ouvrir le flux de config](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=freebox_homexa)

1. **Paramètres → Appareils et services → Ajouter une intégration**
2. Cherche **Freebox Homexa**
3. Host Freebox (souvent `mafreebox.freebox.fr` ou `xxx.fbxos.fr`)
4. Valide l’appairage **sur l’écran de la Freebox**
5. Dans [Freebox OS → Paramètres → Applications](http://mafreebox.freebox.fr/#Fbx.os.app.settings.Accounts), accorde les droits à l’application Home Assistant (Home, Player, LAN, etc.)

Pas besoin de coller un token dans `configuration.yaml` : tout passe par l’interface.

### Player (télécommande)

Sur le Player : **Réglages → Système → Informations** → note le code télécommande si l’intégration le demande.

---

## Mise à jour

HACS → Freebox Homexa → **Mettre à jour** → redémarrer Home Assistant.

---

## Dépannage

| Symptôme | Piste |
|---|---|
| L’intégration ne démarre pas | HA 2026.8.0+ requis (`via_device_id`) |
| `bad_json` sur l’alarme | Version **28.8.2** (payload `{"value": ...}`) |
| Seulement 2 boutons d’alarme | 28.8+ expose Présent / Absent / Désarmé |
| Répéteur invisible | Redémarre HA ; le F-RP01A est détecté via les hôtes LAN |
| Player absent | Droits Player dans Freebox OS + redémarrage |
| HDMI ne change pas l’entrée TV | Normal : CEC réveille la TV, ça ne sélectionne pas HDMI 1/2/3 |

Logs : **Paramètres → Système → Journaux**, filtre `freebox_homexa`.

Retours tests : [issue #22](https://github.com/XAV59213/freebox_homexa/issues/22)

---

## Liens

- [Wiki](https://github.com/XAV59213/freebox_homexa/wiki)
- [Releases](https://github.com/XAV59213/freebox_homexa/releases)
- [Issues](https://github.com/XAV59213/freebox_homexa/issues)

## Licence

MIT · Merci à [@gvigroux](https://github.com/gvigroux) (projet d’origine) et [@Steph73HB](https://github.com/Steph73HB).

<a href="https://www.buymeacoffee.com/xav59213"><img src="https://img.buymeacoffee.com/button-api/?text=xav59213&emoji=&slug=xav59213&button_colour=5F7FFF&font_colour=ffffff&font_family=Cookie&outline_colour=000000&coffee_colour=FFDD00" /></a>
<a href="https://www.buymeacoffee.com/gvigroux"><img src="https://img.buymeacoffee.com/button-api/?text=gvigroux&emoji=&slug=gvigroux&button_colour=5F7FFF&font_colour=ffffff&font_family=Cookie&outline_colour=000000&coffee_colour=FFDD00" /></a>
