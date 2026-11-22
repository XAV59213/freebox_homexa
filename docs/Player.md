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

`media_player.play_media` prépare une URL HTTP ou HTTPS (type `audio/*` ou `music`, ou sans type si l'adresse finit par `.mp3`, `.aac`, `.ogg`, `.wav` ou `.flac`) : Home Assistant télécharge le fichier, l'emballe en MP4 (son AAC et image noire) et le sert sur une adresse signée de courte durée. L'API du Player ne sait pas imposer une application : l'ouverture annonce `video/mp4`, ce qui préselectionne le lecteur multimédia plutôt que le navigateur. Si le choix reste affiché, OK est envoyé une ou deux fois avec le code télécommande déjà enregistré, et seulement tant que la lecture n'a pas démarré. AirMedia vise le récepteur du Player (pas le Freebox Server). Un refus `http` ou `req_in_progress` est réessayé une fois. Sans changement d'application ou de média, l'action échoue avec un message traduit. L'adresse d'origine n'est envoyée que si la préparation échoue.

Le changement de chaîne reste `tv:?channel=N` avec le type `url`. La vidéo n'emprunte pas AirMedia.

Deux sons d'alarme sont inclus (synthèse, environ 5 secondes). Ils sont aussi dans le navigateur multimédia, dossier **Sons d'alarme**.

Sirène :

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
      media_content_id: freebox_homexa://sound/alarme_sirene
      media_content_type: audio/mpeg
```

Bip-bip :

```yaml
alias: Bip d'alarme sur le Player
actions:
  - action: media_player.play_media
    target:
      entity_id: media_player.freebox_player
    data:
      media_content_id: freebox_homexa://sound/alarme_bip
      media_content_type: audio/mpeg
```

Un fichier placé dans `config/www` reste utilisable, par exemple `http://homeassistant.local:8123/local/sirene.mp3`.

## Code télécommande

Sur le Player : **Réglages → Système → Informations**.

L’API Player n’est pas la même selon le modèle (v6 / v8) : l’intégration bascule toute seule.
