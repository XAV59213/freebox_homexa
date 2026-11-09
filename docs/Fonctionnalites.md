# Fonctionnalités

## Freebox Server

Capteurs réseau / connexion, suivi des appareils Wi-Fi.

## Freebox Home

Détection automatique : interrupteurs, caméras, volets roulants, détecteurs.

## Alarme

Trois modes, comme l’application Freebox :

- **Présent** (`armed_home`)
- **Absent** (`armed_away`)
- **Désarmé** (`disarmed`)

## Répéteurs Wi-Fi Free (F-RP01A)

Chaque répéteur apparaît comme un appareil avec un capteur **En ligne** et la liste des clients.

## Téléphone (port FXS)

Boutons **Démarrer la sonnerie FXS** et **Arrêter la sonnerie FXS** sur le Freebox Server, et actions `freebox_homexa.start_fxs_ring` / `freebox_homexa.stop_fxs_ring`.

Le droit **Téléphonie** est requis (Freebox OS → Paramètres → Gestion des accès → Applications → Home Assistant). Sans ce droit, ou sans port FXS, l'action échoue avec un message clair. Une durée (1 à 300 s) programme toujours l'arrêt, y compris en cas d'erreur, d'annulation ou de déchargement. Aucun numéro ni nom d'appelant n'est lu.

```yaml
action: freebox_homexa.start_fxs_ring
data:
  duration: 5
```

## Player

Voir [Player et HDMI](Player.md).
