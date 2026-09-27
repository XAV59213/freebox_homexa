# Cartes Lovelace Freebox Homexa

Reproduction de la vue **Alarme / Volet / PIR / Player / RSSI**.

## Fichiers

| Fichier | Usage |
|---|---|
| [homexa-dashboard.yaml](homexa-dashboard.yaml) | Vue complète **Mushroom** (identique à la capture) |
| [homexa-tuiles-natives.yaml](homexa-tuiles-natives.yaml) | Même idée avec les **tuiles HA**, sans carte custom |

## Prérequis (version Mushroom)

1. HACS → Frontend → dépôt [Mushroom](https://github.com/piitaya/lovelace-mushroom)
2. Télécharger → **Recharger les ressources** (Ctrl+F5)

`card-mod` est optionnel (juste pour centrer / taille d’icône).

## Coller la vue

1. Tableau de bord → **Modifier** → menu 3 points → **Éditeur brut**
2. Ajoute le contenu de `homexa-dashboard.yaml` dans `views:`
3. Remplace les `entity_id` :

```yaml
alarm_control_panel.alarme      # pack sécurité Freebox Home
cover.volet_salon               # volet Freebox Home
binary_sensor.pir_entree        # détecteur de mouvement
media_player.freebox_player     # Player Devialet / Mini 4K / Pop
sensor.wifi_rssi                # capteur RSSI d’un client Wi-Fi
```

Pour trouver tes IDs : **Paramètres → Appareils et services → Freebox Homexa → entités**.

## Boutons Player

| Puce | Action Homexa |
|---|---|
| YouTube | `media_player.select_source` → `YouTube` |
| Netflix | `media_player.select_source` → `Netflix` |
| prime | `media_player.play_media` → `https://www.primevideo.com` |

Prime Video n’est pas une source officielle du Player : on ouvre l’URL.
TV / HDMI (CEC) se sélectionnent aussi via `select_source` si tu veux les ajouter.

## États alarme

Comme l’app Free :

| Bouton | État HA |
|---|---|
| Présent | `armed_home` |
| Absent | `armed_away` |
| Désarmé | `disarmed` |

## Qualité RSSI

| dBm | Libellé |
|---|---|
| ≥ −50 | Excellent |
| ≥ −60 | Bon |
| ≥ −70 | Moyen |
| < −70 | Faible |
