# Changelog

## 28.8.34
- Correction : l'écran d'options « Profils de rappel » n'affiche plus une boîte « Erreur » vide (#59)
- Appareils : `via_device` (déprécié dans Home Assistant) remplacé par `via_device_id` pour les répéteurs, clients LAN et capteurs RSSI (#59)

## 28.8.33
- Guide TNT : nouvel écran d'options « Guide TNT » (Configurer) pour choisir les chaînes suivies : 30 chaînes TNT, chaînes supplémentaires (Canal+, Ciné+, sport, jeunesse…) et chaînes belges RTBF ; les capteurs des chaînes décochées sont supprimés (#56)
- Rappels : écran « Profils de rappel » (notification, enceintes/TV, synthèse vocale, volume) et services `freebox_homexa.schedule_reminder`, `cancel_reminder`, `get_reminder_status`, avec rappels conservés après redémarrage (#57)
- Affiches, notes et votes TMDB avec votre propre clé API TMDB (aucune clé partagée fournie) (#58)
- Correction : valider « Paramètres généraux » n'écrase plus les autres options (#56)
- ⚠️ Fonctions portées de Programme TNT FR (cyclope205, MIT) pas encore testées dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.32
- Guide TNT : l'appareil « Programme TNT FR » et ses capteurs par chaîne sont désormais toujours créés dans Freebox Homexa, même si l'intégration séparée Programme TNT FR est installée (désactivée, ignorée ou active) (#55)
- Les commandes websocket `programme_tnt_fr/*` ne sont enregistrées que si l'intégration séparée n'est pas active
- Identifiant d'appareil propre à Homexa (`freebox_homexa` / `programme_tnt_fr`) : plus de fusion avec l'appareil de l'intégration séparée
- ⚠️ L'ancien appareil TNT, désormais vide, peut subsister : le supprimer manuellement dans Paramètres → Appareils

## 28.8.31
- Guide TNT : le websocket `programme_tnt_fr/programmes` retrouve le coordinateur TNT embarqué (`hass.data["freebox_homexa"]["tnt"]`) (#53)
- Clé `tnt` réservée dans `hass.data` : les services `reboot` / `reload` / `remote` sont bien retirés au déchargement (#53)
- Version de la carte (`const.VERSION`), README et info.md alignés sur 28.8.31

## 28.8.30
- Correction : `resolve_token_file` rétabli dans `router.py` (erreur d'import de `config_flow` au démarrage)

## 28.8.29
- Revue HACS : token stocké uniquement dans `.storage/freebox_homexa`
- Suppression de la copie dans `www` et de la ressource `/local/`
- Carte TNT embarquée retirée (plus de CDN ni de réécriture des ressources d'autres intégrations)
- Analyse XMLTV et accès fichiers des volets hors de la boucle d'événements

## 28.8.28
- Carte Lovelace : hauteur de carte et boutons inactifs (#52)

## 28.8.27
- Release de maintenance (voir https://github.com/XAV59213/freebox_homexa/compare/28.8.25...28.8.27)

## 28.8.26
- Synchronisation de la version 28.8.24 (#51)

## 28.8.25
- Carte Lovelace : hauteur auto en vue Sections (plus de débordement qui masque la carte du dessous)
- Boutons alarme / volet / player : délégation de clic stable, plus détruits à chaque refresh hass
- Layout mobile compact pour PIR / Player / RSSI

## 28.8.24
- Synchronisation de la version affichée avec la release GitHub `28.8.24`
- `manifest.json`, README, info.md et wiki alignés
- Exemple de tableau de bord Lovelace (alarme, volet, PIR, Player, RSSI)

## 25.4.0
- Correction des problèmes pour la soumission à HACS
- Mise à jour de la documentation
- Actions de workflow réussies

## 25.3.2
- Intégration du Freebox Player
- Ajout de la gestion des commandes `remote`
- Mise à jour de `services.yaml`
- Optimisation du dépôt Git avec `.gitignore`

## 2025.2.7
- Intégration du Freebox Player
- Ajout de la gestion des commandes `remote`
- Mise à jour de `services.yaml`
- Optimisation du dépôt Git avec `.gitignore`
