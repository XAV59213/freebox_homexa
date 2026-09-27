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

## Options (facultatif)

```yaml
type: custom:freebox-homexa-card
alarm_entity: alarm_control_panel.alarme
cover_entity: cover.volet_salon
pir_entity: binary_sensor.pir_entree
player_entity: media_player.freebox_player
rssi_entity: sensor.signal_wi_fi
```

Sans ces clés, la carte prend toute seule :
- l’alarme Homexa
- le volet dont le nom contient `salon`
- un PIR / motion
- `media_player.freebox_player`
- le premier capteur RSSI
