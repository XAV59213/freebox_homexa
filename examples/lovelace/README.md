# Carte Lovelace Freebox Homexa

Carte native livrée avec l’intégration : **Freebox Homexa**.

```yaml
type: custom:freebox-homexa-card
```

Après mise à jour : redémarre Home Assistant.
Tableau de bord → Modifier → Ajouter une carte → cherche **Freebox Homexa**.

Si elle n’apparaît pas :

**Paramètres → Tableaux de bord → ⋮ → Ressources**

- URL : `/freebox_homexa/freebox-homexa-card.js`
- Type : Module JavaScript

## Réglages (éditeur visuel)

Dans l’éditeur de la carte (crayon → **Configuration**) :
- **Titre** facultatif
- **Sections affichées** : Alarme, Volets, Détecteurs PIR, Freebox Player, WiFi RSSI (décocher = masquer)
- **Alarme(s), Volets, PIR, Freebox Player, Capteurs RSSI** : sélecteurs d’entités natifs de Home Assistant, **plusieurs entités possibles** (une tuile par entité, dans l’ordre choisi)
- liste vide = détection automatique (une entité par section, celles de Freebox Homexa en priorité)

## Options YAML

```yaml
type: custom:freebox-homexa-card
title: Maison
covers:
  - cover.volet_salon
  - cover.volet_cuisine
pirs:
  - binary_sensor.pir_entree
players:
  - media_player.freebox_player
rssi_entities:
  - sensor.signal_wi_fi
show_alarm: true
show_rssi: false
```

Les anciennes clés `alarm_entity`, `cover_entity`, `pir_entity`, `player_entity`, `rssi_entity` restent lues (ajoutées à la liste correspondante) : une carte déjà configurée continue de fonctionner. Elles sont visibles dans l’éditeur sous « Ancien réglage » pour pouvoir les vider.

Sans entité choisie, la carte prend toute seule :
- l’alarme Homexa
- le volet dont le nom contient `salon`, sinon `volet`
- un PIR / motion (`entree` en priorité)
- le Player Homexa (`media_player.freebox_player`)
- le premier capteur RSSI

# Carte « Homexa TNT »

```yaml
type: custom:homexa-tnt-card
```

Tableau de bord → Ajouter une carte → cherche **Homexa TNT**. Options : voir [homexa-tnt-card.yaml](homexa-tnt-card.yaml).
