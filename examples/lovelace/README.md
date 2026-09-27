# Cartes Lovelace Freebox Homexa

Vue **Alarme / Volet / PIR / Player / RSSI / SMS Free**.

## Fichiers

| Fichier | Usage |
|---|---|
| [homexa-dashboard.yaml](homexa-dashboard.yaml) | Vue **Mushroom** + carte FreeSMS XA |
| [homexa-tuiles-natives.yaml](homexa-tuiles-natives.yaml) | Tuiles HA + carte FreeSMS XA |

## Prérequis

1. HACS → Frontend → [Mushroom](https://github.com/piitaya/lovelace-mushroom) (version Mushroom seulement)
2. Intégration [Free Mobile SMS XA](https://github.com/XAV59213/freesmsxa) installée
3. Si la carte SMS manque : **Paramètres → Tableaux de bord → ⋮ → Ressources**
   - URL : `/freesmsxa/freesmsxa-send-card.js`
   - Type : Module JavaScript

## Coller la vue

1. Tableau de bord → **Modifier** → 3 points → **Éditeur brut**
2. Ajoute le contenu de `homexa-dashboard.yaml` dans `views:`
3. Remplace les `entity_id` :

```yaml
alarm_control_panel.alarme
cover.volet_salon
binary_sensor.pir_entree
media_player.freebox_player
sensor.wifi_rssi
sensor.papa_etat_sms
sensor.papa_sms_aujourdhui
sensor.papa_sms_envoyes
```

La carte `custom:freesmsxa-send-card` détecte toute seule `notify.papa`, `notify.maman`, etc.

## Boutons Player

| Puce | Action |
|---|---|
| YouTube | `select_source` → YouTube |
| Netflix | `select_source` → Netflix |
| prime | `play_media` → https://www.primevideo.com |

## États alarme

| Bouton | État HA |
|---|---|
| Présent | `armed_home` |
| Absent | `armed_away` |
| Désarmé | `disarmed` |
