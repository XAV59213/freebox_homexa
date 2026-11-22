# Fonctionnalités

## Freebox Server

Capteurs réseau / connexion, suivi des appareils Wi-Fi, températures et vitesse des ventilateurs.

Carte Lovelace **Freebox Server** (connexion, santé, réseau, appels manqués, redémarrage). Elle est chargée avec l'intégration : rien à ajouter dans les ressources Lovelace.

## Freebox Home

Détection automatique : interrupteurs, caméras, volets roulants, détecteurs.

## Alarme

Trois modes, comme l’application Freebox :

- **Présent** (`armed_home`)
- **Absent** (`armed_away`)
- **Désarmé** (`disarmed`)

## Répéteurs Wi-Fi Free (F-RP01A)

Chaque répéteur apparaît comme un appareil avec un capteur **En ligne** et la liste des clients.

## Téléphone (port FXS, DECT, messagerie)

Boutons **Démarrer la sonnerie FXS** et **Arrêter la sonnerie FXS** sur le Freebox Server, et actions `freebox_homexa.start_fxs_ring` / `freebox_homexa.stop_fxs_ring`.

Si la Freebox a au moins un combiné DECT : **Faire sonner les combinés DECT** et **Arrêter la sonnerie DECT**, actions `start_dect_ring` (durée 1 à 300 s, 30 s par défaut) et `stop_dect_ring`. Chaque combiné a les capteurs **Sonne** et **Décroché**.

Messagerie : capteur **Messages vocaux non lus**, actions pour marquer lu, supprimer et lire sur un lecteur. Carte Lovelace **Homexa Téléphone**.

Le droit **Téléphonie** est requis (Freebox OS → Paramètres → Gestion des accès → Applications → Home Assistant). Sans ce droit, ou sans port FXS / avec le DECT coupé, l'action échoue avec un message clair. Une durée programme toujours l'arrêt, y compris en cas d'erreur, d'annulation ou de déchargement. Aucun numéro ni nom d'appelant n'est journalisé. La lecture sur Alexa / Echo est au mieux : elle a besoin d'une URL HTTPS publique (Nabu Casa ou URL externe). L'état **Décroché** dépend du champ `on_hook`, qui peut manquer ou être en retard.

```yaml
action: freebox_homexa.start_fxs_ring
data:
  duration: 5
```

## Player

Voir [Player et HDMI](Player.md).
