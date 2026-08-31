# Player et HDMI

Modèles testés : **Freebox Player Devialet**, **Mini 4K**, **Pop**.

## Entités

- `media_player` : on/off, volume, mute, play/pause, source
- `remote` : touches de la télécommande

## Sources

- **TV** : flux TV Freebox (`tv:`)
- **HDMI (CEC)** : réveille le téléviseur (One Touch Play) puis lance la TV
- **YouTube / Netflix** : applications Player

HDMI n’est **pas** un sélecteur d’entrée HDMI 1/2/3 de la télé. C’est la sortie du Player vers l’écran.

## Code télécommande

Sur le Player : **Réglages → Système → Informations**.

L’API Player n’est pas la même selon le modèle (v6 / v8) : l’intégration bascule toute seule.
