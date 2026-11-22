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

## Fichier audio

`media_player.play_media` envoie une URL HTTP ou HTTPS au Player par AirMedia (le même chemin que la messagerie) lorsque le type est `audio/*` ou `music`, ou lorsqu'il est absent et que l'adresse finit par `.mp3`, `.aac`, `.ogg`, `.wav` ou `.flac`. `control/open` est le second essai. Sans changement d'état, l'action échoue avec un message traduit.

Le changement de chaîne reste `tv:?channel=N` avec le type `url`. La vidéo n'emprunte pas AirMedia.

Exemple, sirène quand l'alarme se déclenche (fichier dans `config/www`) :

```yaml
alias: Sirène du Player quand l'alarme se déclenche
triggers:
  - trigger: state
    entity_id: alarm_control_panel.systeme_d_alarme
    to: triggered
    not_from:
      - unavailable
      - unknown
actions:
  - action: media_player.play_media
    target:
      entity_id: media_player.freebox_player
    data:
      media_content_id: http://homeassistant.local:8123/local/sirene.mp3
      media_content_type: audio/mpeg
```

## Code télécommande

Sur le Player : **Réglages → Système → Informations**.

L’API Player n’est pas la même selon le modèle (v6 / v8) : l’intégration bascule toute seule.
