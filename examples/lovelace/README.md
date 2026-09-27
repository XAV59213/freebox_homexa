# Cartes Lovelace Freebox Homexa

Vue branchée sur **tes** entités Home Assistant (pas des exemples génériques).

## Entités utilisées

### Volets Homexa
- `cover.volet_salon`
- `cover.volet_cuisine`
- `cover.volet_papa`
- `cover.volet_fille`
- `cover.volet_loulou`
- `cover.volets_maison`

### Player
- `media_player.freebox_player`

### Contacts / portes / fenêtres Home
- `binary_sensor.porte_entree`
- `binary_sensor.porte_cuisine`
- `binary_sensor.baie_vitree`
- `binary_sensor.fenetre_cuisine`
- `binary_sensor.fenetre_papa`
- `binary_sensor.fenetre_loulous`
- `binary_sensor.porte_fenetre_filles`

### Découverts auto (intégration `freebox_homexa`)
- `alarm_control_panel.*` → carte Alarme Présent / Absent / Désarmé
- `binary_sensor` motion → PIR
- `sensor` signal_strength → RSSI Wi-Fi

Nécessite HACS → [auto-entities](https://github.com/thomasloven/lovelace-auto-entities).

### SMS
- `custom:freesmsxa-send-card` ([freesmsxa](https://github.com/XAV59213/freesmsxa))

## Prérequis

- Mushroom
- auto-entities (recommandé)
- Free Mobile SMS XA
