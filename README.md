[![GitHub Release](https://img.shields.io/github/v/release/XAV59213/freebox_homexa?style=flat-square)](https://github.com/XAV59213/freebox_homexa/releases) [![hacs](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://hacs.xyz/) [![GitHub Activity](https://img.shields.io/github/commit-activity/m/XAV59213/freebox_homexa?style=flat-square)](https://github.com/XAV59213/freebox_homexa/commits/main)
[![Downloads](https://img.shields.io/github/downloads/XAV59213/freebox_homexa/total.svg?label=Downloads)](https://github.com/XAV59213/freebox_homexa/releases)

# Freebox Homexa

Intégration **Home Assistant** pour la Freebox Server, Freebox Home, les répéteurs Wi-Fi Free et le Freebox Player.

**Version actuelle :** [28.8.70](https://github.com/XAV59213/freebox_homexa/releases/tag/28.8.70) · Home Assistant **2026.8.0+**

Wiki : [Documentation](https://github.com/XAV59213/freebox_homexa/wiki)

> Projet indépendant, non affilié à Free.

---

## Fonctionnalités

| Domaine | Ce que ça fait |
|---|---|
| Freebox Server | État, réseau, Wi-Fi, capteurs connexion |
| Freebox Home | Détection auto : interrupteurs, caméras, volets, PIR, contacts |
| Alarme | 3 modes comme l’app Free : **Présent / Absent / Désarmé** |
| Appareils Wi-Fi | Suivi des clients + **RSSI (dBm)**, bande, SSID, AP / répéteur |
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

### Options (clients LAN)

Dès l’installation, ou ensuite : **Paramètres → Appareils et services → Freebox Homexa → Configurer**.

| Option | Défaut | Intérêt |
|---|---|---|
| Suivre les clients LAN | oui | `device_tracker` des téléphones / PC / objets |
| Créer les capteurs RSSI Wi-Fi | oui | Signal en dBm dès que le client est vu en Wi-Fi |
| Créer des appareils pour les clients réseau | non pour une nouvelle installation ; oui conservé pour une installation existante (migration automatique) | Activé : un appareil par client, rangé sous « Clients réseau filaires / Clients Wi-Fi › type » ou son répéteur, avec les capteurs « Clients connectés ». Désactivé : comportement standard de Home Assistant — le `device_tracker` ne crée pas d’appareil et se relie seul à l’appareil d’une autre intégration ayant la même MAC ; le RSSI reste une entité seule ; pas de groupes de clients. En désactivant, les appareils clients créés par Homexa seuls sont retirés au rechargement (ceux partagés avec une autre intégration sont gardés) |
| Intervalle Home (secondes) | 15 | PIR, contacts, alarme, volets : 5 / 10 / 15 / 20 / 25 / 30 |
| Code télécommande Player | vide | 8 chiffres, Player : Réglages → Système → Informations |

Le Server, les répéteurs et le pack Home (alarme, PIR, caméras, volets) gardent toujours leurs devices.

« Créer des appareils pour les clients réseau » :

- **décochée par défaut** sur une nouvelle installation : règle de Home Assistant, un `device_tracker` ne crée pas d’appareil. Home Assistant crée alors **désactivé** le tracker d’un client qu’aucune autre intégration ne connaît : activez-le dans la liste des entités si besoin (comme avec l’intégration Freebox officielle) ;
- **installation existante** (avant la 28.8.62) : l’option est conservée **cochée** à la mise à jour, rien ne change ;
- en la décochant après coup : au rechargement, les appareils clients créés **uniquement** par Homexa sont retirés automatiquement ; un appareil partagé avec une autre intégration (Shelly, ESPHome…) est conservé.

Pour 5 s, désactivez l’intégration officielle Freebox : les deux en parallèle saturent l’API.

### Organisation des appareils

Les appareils Homexa sont rangés sous **4 services de premier niveau** :

| Service | Contenu |
|---|---|
| **Freebox Server** (ex. « Freebox v7 (r1) ») | entités du serveur (débits, températures, Wi-Fi, redémarrage, appels manqués, « Marquer les appels comme lus »…) ; enfants : répéteurs Wi-Fi, disques, clients réseau (si l'option est activée), caméras IP |
| **Freebox Player** | chaque Player (lecteur, télécommande, boutons d'applis) |
| **Freebox Maison connectée** | entités du module d'alarme ; enfants : tous les nœuds Freebox Home (détecteurs, fenêtres, volets, ouvrants, RTS / IO, caméras Freebox Home, prises…) |
| **TNT** | calendrier « Guide TV » et capteurs « Programme TNT FR » |

Les anciens groupes (Sécurité, Volets, Réseau et ses sous-groupes, Caméras, Journal d'appels, Guide TV Freebox, Équipements…) sont retirés environ 2 minutes après le chargement, **uniquement s'ils n'ont plus ni entité ni appareil enfant** ; aucune entité n'est supprimée.

**Forcer un service** : Configurer → **Groupes des appareils** liste les appareils Homexa (avec leur service automatique entre parenthèses). Choix : Automatique, Freebox Server, Freebox Maison connectée, Freebox Player, TNT. Les choix enregistrés avec les anciens groupes sont migrés automatiquement (Sécurité / Fenêtres / Volets → Maison connectée, Multimédia → Player, Guide TV → TNT, Caméras → Automatique, le reste → Freebox Server).

- Les identifiants d'entités ne changent pas ; les appareils existants sont re-rattachés au rechargement.
- **Pièce suggérée** déduite du nom (« Volet cuisine » → Cuisine, « Fenêtre Papa » → Papa…). Home Assistant ne l'applique **qu'à la création** d'un appareil : les appareils existants gardent leur pièce.
- Les clients sans nom (« Unknown device », « wlan0 », adresse MAC) prennent un autre nom d'hôte connu, sinon « <fabricant> <fin de MAC> ».

### Player (télécommande)

Le **code télécommande réseau** (8 chiffres) se règle dans **Configurer**, sous l’intervalle Home.

Sur le Player : **Réglages → Système → Informations**. Utile sur Révolution / Delta / Devialet pour power, TV, chiffres. Mini 4K / Pop passent souvent par **Android TV Remote**. Laisser vide si vous n’avez pas de Player.

Volume et lecture passent par l’API Player, sans ce code.

---

## Actions

| Action | Rôle |
|---|---|
| `freebox_homexa.reboot` | Redémarre la Freebox |
| `freebox_homexa.reload` | Recharge l’intégration (reconnexion, redécouverte des appareils Home) |
| `freebox_homexa.remote` | Envoie des touches de télécommande au **Freebox Player** |
| `freebox_homexa.schedule_reminder` | Programme un rappel TNT (notification et/ou annonce vocale) 5, 10 ou 15 min avant un programme |
| `freebox_homexa.cancel_reminder` | Annule un rappel TNT |
| `freebox_homexa.get_reminder_status` | Indique si un rappel est programmé (réponse de l’action) |

Avec plusieurs Freebox, `config_entry_id` ou `device_id` choisit la Freebox visée par `reboot`, `reload` et `remote`.

### `freebox_homexa.remote`

Même chemin que l’entité « Télécommande » du Player, avec le **code télécommande réseau** réglé dans Configurer (celui du Player, sinon le code commun).

| Champ | Obligatoire | Rôle |
|---|---|---|
| `code` | oui | Une touche, ou plusieurs séparées par des virgules (`"1,2"` → chaîne 12) |
| `player_id` | non | Numéro du Player (1, 2…) ; inutile avec un seul Player |
| `device_id` | non | Appareil Player Homexa à piloter (à la place de `player_id`) |

Touches : `power`, `ok`, `up`, `down`, `left`, `right`, `back`, `home`, `0` à `9`, `vol_inc`, `vol_dec`, `mute`, `prgm_inc`, `prgm_dec`, `play`, `bwd`, `fwd`, `prev`, `next`, `rec`, `red`, `green`, `blue`, `yellow`, `tv`, `list`, `info`, `epg`, `mail`, `media`, `help`, `options`, `pip`, `swap`.

```yaml
action: freebox_homexa.remote
data:
  code: "power"
```

```yaml
# Chaîne 12 sur le Player n° 2
action: freebox_homexa.remote
data:
  code: "1,2"
  player_id: 2
```

Erreurs affichées (au lieu d’un échec silencieux) : aucun Player détecté, code télécommande manquant, plusieurs Player sans `player_id` / `device_id` ni code commun, touche inconnue (rien n’est envoyé), numéro de Player invalide, touche non envoyée.

---

## Disponibilité et journal

- **Freebox injoignable** : le journal affiche **une seule fois** « Freebox injoignable » (niveau info), puis « Freebox de nouveau joignable » à son retour, sans erreur répétée à chaque relevé. Entre les deux, les entités Homexa passent **indisponibles** (capteurs, Wi-Fi, boutons, Player, Guide TV, entités Freebox Home…).
- **Nœud Freebox Home injoignable** (la Freebox le signale « unreachable », ex. détecteur hors de portée) : ses entités passent indisponibles. Les volets **RTS** (sans retour d’état) ne sont jamais rendus indisponibles pour ce motif.
- Non concernés : les `device_tracker` gardent leur dernier état (la présence n’est pas perturbée) ; l’interrupteur « inversion » des volets (réglage local) et les capteurs TNT (source Internet) ne dépendent pas de la Freebox.

Automatisation sur l’alarme (ou un volet) avec `to:` : au retour de la Freebox, l’état passe de `unavailable` à sa vraie valeur et peut la relancer. Ajoutez `not_from` :

```yaml
triggers:
  - trigger: state
    entity_id: alarm_control_panel.systeme_d_alarme
    to: disarmed
    not_from:
      - unavailable
      - unknown
```

---

## Tableau de bord (carte prête à coller)

Vue Lovelace **Alarme / Volet / PIR / Player / RSSI** :

- [examples/lovelace/homexa-dashboard.yaml](examples/lovelace/homexa-dashboard.yaml) — Mushroom (rendu de la capture)
- [examples/lovelace/homexa-tuiles-natives.yaml](examples/lovelace/homexa-tuiles-natives.yaml) — tuiles natives, sans carte custom
- Mode d’emploi : [examples/lovelace/README.md](examples/lovelace/README.md)

### Carte « Homexa Appels »

```yaml
type: custom:homexa-calls-card
```

Journal des appels de la Freebox (manqués, reçus, émis) avec icônes, heure et durée, à partir du capteur « Derniers appels Freebox ». Détails : [examples/lovelace/README.md](examples/lovelace/README.md)

### Carte « Freebox Homexa »

```yaml
type: custom:freebox-homexa-card
```

Entièrement réglable dans l’éditeur visuel : titre, sections affichées ou masquées, et choix de **plusieurs** alarmes, volets, PIR, Player et capteurs RSSI (sélecteurs d’entités natifs). Liste vide = détection automatique. Détails : [examples/lovelace/README.md](examples/lovelace/README.md)

### Carte « Homexa TNT » (guide TV)

Carte guide TV livrée avec l'intégration, adaptée de [Programme TNT FR](https://github.com/cyclope205/programme-tnt-fr) (MIT) : carrousels « En ce moment / À suivre / 1re et 2e partie de soirée », Guide TV par jour, chaînes favorites, affiches et notes TMDB (si une clé personnelle est configurée) et rappels (profils de rappel Homexa).

```yaml
type: custom:homexa-tnt-card
```

- Chargée automatiquement depuis l'intégration (`/freebox_homexa/homexa-tnt-card.js`), sans ressource Lovelace à ajouter, sans CDN.
- Nom distinct (`homexa-tnt-card`, « Homexa TNT » dans le sélecteur de cartes) : aucune collision avec la carte `programme-tnt-fr-card` si l'intégration séparée est aussi installée.
- N'affiche que les capteurs TNT de Freebox Homexa ; chaînes à choisir dans Configurer → Guide TNT.
- Exemple complet : [examples/lovelace/homexa-tnt-card.yaml](examples/lovelace/homexa-tnt-card.yaml)

HACS → Frontend → [Mushroom](https://github.com/piitaya/lovelace-mushroom), puis colle le YAML dans l’éditeur brut du tableau de bord. Remplace les `entity_id` par tes entités Homexa.

---

## Mise à jour

HACS → Freebox Homexa → **Mettre à jour** → redémarrer Home Assistant.

## Suppression

1. **Paramètres → Appareils et services → Freebox Homexa** → ⋮ → **Supprimer**
2. HACS → Freebox Homexa → ⋮ → **Supprimer**, puis redémarrer Home Assistant
3. Facultatif : Freebox OS → Paramètres → Applications → retirer l’application Home Assistant

---

## Dépannage

| Symptôme | Piste |
|---|---|
| L’intégration ne démarre pas | HA 2026.8.0+ requis (`via_device_id`) |
| `bad_json` sur l’alarme | Version **28.8.2** (payload `{\"value\": ...}`) |
| Seulement 2 boutons d’alarme | 28.8+ expose Présent / Absent / Désarmé |
| Répéteur invisible | Redémarre HA ; le F-RP01A est détecté via les hôtes LAN |
| Répéteur en double | Options → **Fusionner un répéteur en double** : choisir le doublon puis le répéteur portant la MAC principale `20:66:CF…` (visible dans l'app Freebox) ; pièce, nom et entités sont conservés |
| Player absent | Droits Player dans Freebox OS + redémarrage |
| Télécommande sans effet | Renseigner le code Player dans Configurer |
| Action `remote` en erreur | Lire le message : code manquant → Configurer ; plusieurs Player → ajouter `player_id` ou `device_id` ; touche inconnue → voir la liste des touches |
| Entités indisponibles | Freebox injoignable (journal « Freebox injoignable ») ou nœud Home hors de portée ; elles reviennent seules |
| Automatisation relancée au retour de la Freebox | Ajouter `not_from: [unavailable, unknown]` au déclencheur `to:` |
| HDMI ne change pas l’entrée TV | Normal : CEC réveille la TV, ça ne sélectionne pas HDMI 1/2/3 |
| Pas de RSSI Wi-Fi | Client Ethernet, ou droit LAN / Wi-Fi manquant dans Freebox OS |
| Devices en doublon (HA 2026.8) | Désactivez « Créer des appareils pour les clients réseau » |
| PIR décalé vs intégration officielle | Officielle désactivée + intervalle Home à 5 ou 10 s |

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
