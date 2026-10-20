# Changelog

## Non publié
- Alarme : les entités du module d'alarme Freebox Home sont désormais portées par l'appareil de groupe « Maison connectée et alarme », qui n'apparaît plus comme « Cet appareil n'a pas d'entités » ; l'ancien appareil séparé du module d'alarme est retiré automatiquement (identifiants d'entités inchangés)
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.40
- Appareils : les groupes suivent désormais les **services des droits d'accès Freebox OS** au lieu des types d'appareils : « Maison connectée et alarme », « Caméras », « Freebox Player », « Contrôle de la VM », « Téléchargements », « Contrôle parental », « Journal d'appels », « Guide TV et enregistrements », « Équipements et réglages Freebox » et « Autres » (repli)
- Les nœuds Freebox Home (alarme, détecteurs, fenêtres, volets, prises…) sont réunis dans « Maison connectée et alarme » ; les sous-groupes de clients réseau passent sous « Équipements et réglages Freebox », avec les répéteurs et les disques
- Nouveaux appareils de service « Journal d'appels Freebox » (appels manqués, marquer les appels comme lus) et « Guide TV Freebox » (calendrier), rangés dans leur groupe ; le guide « Programme TNT FR » passe dans « Guide TV et enregistrements »
- Écran « Groupes des appareils » : choix mis à jour ; les surcharges enregistrées sont migrées vers le groupe le plus proche (Sécurité / Fenêtres / Volets → Maison connectée et alarme, Multimédia → Freebox Player, Infrastructure / Réseau → Équipements)
- Les anciens groupes par type sont retirés par le nettoyage différé (~2 min après le chargement) ; identifiants d'entités inchangés
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.39
- Appareils : nouveau groupe « Caméras » (rattaché au Freebox Server) : caméras Freebox Home (sorties de « Sécurité ») et caméras IP du réseau (`ip_camera`, Hikvision, Dahua, Reolink, Foscam, Ezviz, Axis), auparavant dans « Objets connectés »
- « Caméras » ajouté aux choix de l'écran « Groupes des appareils » (#64)
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.38
- Appareils : **tous** les appareils Homexa sont désormais rangés dans un groupe ; nouveaux groupes « Multimédia » (Freebox Player, guide TNT), « Infrastructure » (répéteurs, disques) et « Autres » (repli) ; le sous-groupe réseau de repli devient « Autres (réseau) »
- Correction : les volets (et d'autres appareils ajoutés après le démarrage) n'étaient plus rattachés à « Volets », car le groupe était retiré trop tôt comme « vide »
- Classement réseau amélioré : ProBook / EliteBook / Laptop / -PC et cartes Chongqing Fugui (HP), Hon Hai, Liteon, Intel, AzureWave → Ordinateurs ; WLED / FOSS → Objets connectés
- Nouvel écran d'options « Groupes des appareils » pour forcer le groupe de chaque appareil (par défaut « Automatique ») (#63)
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.37
- Appareils : nouveau groupe « Fenêtres » (détecteurs d'ouverture, sortis de « Sécurité »)
- Clients réseau rangés en sous-groupes sous « Réseau » : Amazon, Téléphones, Ordinateurs, TV & multimédia, Objets connectés, Consoles, Imprimantes, Autres (type d'hôte Freebox, puis fabricant, puis nom d'hôte)
- Seuls les groupes ayant des membres sont créés ; les groupes vides (y compris Sécurité / Volets / Réseau de la 28.8.36) sont retirés au rechargement
- Identifiants d'entités inchangés ; appareils re-rattachés au rechargement (#62)
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.36
- Appareils : parents virtuels « Sécurité », « Volets » et « Réseau » par Freebox (rattachés au Freebox Server) pour désencombrer la liste ; identifiants d'entités inchangés
- Pièce suggérée déduite du nom des appareils (uniquement pour les nouveaux appareils)
- Noms : plus de « Unknown device » ; clients nommés « wlan0 » ou par MAC renommés via un autre nom d'hôte ou le fabricant
- Option « Créer des appareils pour les clients réseau » : désactivée, les appareils clients existants sont retirés au rechargement (#61)
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.35
- Carte Lovelace « Homexa TNT » (`custom:homexa-tnt-card`), adaptée de Programme TNT FR (cyclope205, MIT) : servie directement par l'intégration (aucune copie dans `www`, aucun CDN), avec rappels et affiches TMDB (#60)
- Capteurs TNT : nouveau créneau « À suivre » (attribut `next`) (#60)
- Guide TV par journée de diffusion (05h → 05h) pour la carte (#60)
- ⚠️ Carte pas encore testée dans Home Assistant : merci de signaler tout problème dans les issues

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
