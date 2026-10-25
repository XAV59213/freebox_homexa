# Changelog

## 28.8.51
- Correction : le capteur **« Wi-Fi Freebox »** (appareil Freebox Server) affichait « Déconnecté » alors que le Wi-Fi de la box fonctionnait. Son état ne dépendait que de `/wifi/ap/` (`status.state` = `active`) : si cette liste était vide ou illisible (erreur avalée en debug), il passait à « Déconnecté ». Il suit maintenant aussi `/wifi/config/` (`enabled`, comme l'interrupteur « Freebox WiFi »), `/wifi/bss/` (`status.state`) et les clients Wi-Fi actifs de la box : en ligne dès qu'un AP ou un BSS est `active`, ou qu'un client Wi-Fi est connecté à la box, ou que le Wi-Fi est activé sans état radio lisible ; hors ligne si le Wi-Fi est coupé ou toutes les radios arrêtées (planning, `disabled`…) ; « inconnu » plutôt que « Déconnecté » si rien n'est lisible. États inconnus tolérés (journal debug une fois), indisponibilité d'une API Wi-Fi signalée une fois au niveau info
- Correction : le capteur **« Appareils sur le Wi-Fi box »** (et « Appareils connectés » des répéteurs) affichait « Inconnu » dès que la liste des noms des clients dépassait 255 caractères (limite d'état de Home Assistant ; ex. 30 clients Wi-Fi sur la box). L'état est désormais tronqué à 255 caractères avec « … +N » pour les appareils non affichés ; la liste complète reste dans les attributs `appareils` (ajouté) et `detail_appareils`. Même source que « Clients Wi-Fi box », qui reste le compteur numérique (historique, graphiques)
- Diagnostics : `wifi_bss_status`, `wifi_global_enabled`, `wifi_api_errors` et l'état calculé du Wi-Fi de la box. Attributs `wifi_actif` et `bss` sur le capteur « Wi-Fi Freebox »

## 28.8.50
- Répéteurs : fusion du **jumeau « locally administered » exact** d'une MAC principale (ex. `22:66:CF:4B:49:69` = `20:66:CF:4B:49:69` avec le seul bit 0x02 du 1er octet inversé, les 5 autres octets identiques). Ce n'était pas le jumeau qui fusionnait « Garage » à tort avant la 28.8.49, mais l'ancienne règle « MAC voisines » (mêmes octets 2 à 5, dernier octet proche : `20:66:CF:4B:49:69` ~ `20:66:CF:4B:49:63`). Le jumeau exact ne dépend que de la MAC du répéteur lui-même : il est fiable. Fonctionne aussi pour un doublon resté seul dans le registre (absent de lan/browser)
- Répéteurs : fusion par **bloc de BSSID** : une MAC Free `22:66:CF:A:B:xx` dont les 5 premiers octets sont ceux des BSSID connus d'un seul répéteur (fronthaul de l'API `/repeater/`, `access_point.mac` des clients Wi-Fi) est une interface de ce répéteur (ex. `22:66:CF:C6:92:D4` pour les BSSID `…C6:92:D2` / `D6` de Chambre fille). Jamais sur moins de 5 octets (Garage `…96:92:D2` et Chambre fille `…C6:92:D2` ne diffèrent que par le 4e octet), et jamais entre deux répéteurs ayant chacun leur MAC principale
- Répéteurs : nouvelle option **« Fusionner un répéteur en double »** (Options de l'intégration) : choisir l'appareil en double et le répéteur cible, pour les cas où la Freebox ne donne aucun lien fiable (API `/repeater/` indisponible et BSSID non reliés à la MAC principale). Fusion mémorisée, annulable depuis le même écran
- Répéteurs : à la fusion, l'appareil conservé est celui de la MAC principale (`20:66:CF…`) ; il récupère la pièce, le nom personnalisé et les entités du doublon s'il ne les a pas. Un nom explicite (« Repeteur Wifi Freebox Garage ») est préféré à un nom générique (« Repeteur Wifi Freebox #2 »)

## 28.8.49
- Correction : la fusion des répéteurs plantait (`AttributeError: 'int' object has no attribute 'startswith'`) sur les appareils dont l'identifiant n'est pas du texte (id entier des nœuds Freebox Home) ; tous les parcours d'identifiants ignorent désormais les valeurs non texte
- Répéteurs : un hôte n'est retenu comme répéteur que si sa MAC est un OUI Free (ex. `20:66:CF`) ou son jumeau « locally administered » (`22:66:CF`). Les hôtes nommés « Repeteur… » avec une MAC non Free (ex. `AC:E2:D3…`, `C0:F8:53…`) redeviennent des clients réseau ordinaires (entités conservées)
- Répéteurs : plus aucune fusion sur la seule proximité des MAC (plages consécutives d'un répéteur à l'autre, jumeau 20/22 non fiable : « Garage » était fusionné à tort). Fusion uniquement sur signaux fiables : API `/repeater/`, même `access_point.uid`, IP commune, IPv6 EUI-64. En cas de doute, pas de fusion
- Les appareils répéteurs absents de lan/browser (débranchés) sont conservés et signalés par un avertissement
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.48
- Guide TNT (revue de frenck) : suppression des commandes websocket `programme_tnt_fr/programmes` et `programme_tnt_fr/reminder_profiles` (et de `async_register_websocket_api`), qui occupaient l'espace de noms d'une autre intégration. Homexa ne lit plus `hass.data["programme_tnt_fr"]` ni les entrées de configuration de l'intégration séparée Programme TNT FR. Seules les commandes `freebox_homexa/tnt_programmes`, `freebox_homexa/tnt_reminder_profiles` et `freebox_homexa/tnt_version` (utilisées par la carte `homexa-tnt-card`) restent enregistrées
- Rappels TNT : les services de rappel Homexa sont toujours enregistrés (ils ne dépendent plus de la présence de l'intégration séparée)
- Calendrier « Guide TV » : les programmes TNT viennent désormais du guide TNT embarqué de Homexa (plus des capteurs `sensor.programme_tnt_fr_*` de l'intégration séparée) ; repli sur l'EPG Freebox sinon. Attribut `guide_source` : `tnt` au lieu de `programme_tnt_fr`
- Sécurité, carte `freebox-homexa-card` (revue de frenck) : toutes les valeurs insérées dans le HTML (nom des entités, états bruts de l'alarme, du volet et du Player, heure du PIR, RSSI) sont échappées ; l'éditeur de la carte échappe aussi les valeurs de configuration placées dans l'attribut `value`. Renommer une entité ne permet plus d'injecter du HTML ou du script dans un tableau de bord

## 28.8.47
- Correction : `sw_version` des appareils toujours passé en texte (firmware des nœuds Freebox Home, disques, Freebox Server) ; Home Assistant 2026.12 refusera les nombres
- Diagnostics (« Télécharger les diagnostics » sur l'intégration) : hôtes LAN répéteurs ou clients de répéteurs bruts, réponse brute ou erreur de l'API `/repeater/`, regroupement calculé par répéteur, et tous les appareils `repeater_*` du registre (identifiants, connexions, modèle, pièce, entités). Les MAC sont conservées ; numéros de série, jetons, mots de passe et clés sont masqués
- Journal : avertissement au chargement quand des appareils répéteurs restent en double (visible sans activer le mode debug)
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.46
- Répéteurs Wi-Fi : nouveau regroupement des MAC par répéteur physique à partir de `lan/browser` (seule API documentée dans `API_FREEBOX_OS.txt`) : même `access_point.uid`, même adresse IP entre hôtes répéteurs (interfaces pontées), IPv6 EUI-64 désignant la MAC principale, puis MAC voisines ; l'API `/repeater/` (non documentée) reste un simple bonus. Les 28.8.44 / 28.8.45 ne regroupaient rien quand cette API ne répondait pas
- Journal (niveau info) : pour chaque répéteur physique, ses MAC et la raison de chaque regroupement ; appareils trouvés / conservé lors de la fusion ; appareils répéteurs restés non rattachés ; indisponibilité de l'API `/repeater/`
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.45
- Répéteurs Wi-Fi : correction de la fusion de la 28.8.44, qui laissait encore ~9 appareils pour 3 répéteurs. Les MAC d'un répéteur n'ont rien de « proche » (principale `8C:97:EA:55:…`, Ethernet `16:E4:…`, radios et BSSID `8C/8E:97:EA:9B:…`) : elles sont désormais lues dans l'API `/repeater/` (`main_mac`, `backhaul[].mac`, `fronthaul[].bssid`), et chaque hôte LAN / BSSID est rattaché au bon répéteur ; les doublons existants sont fusionnés au chargement (entités, pièce et nom conservés)
- Journal de débogage : liste des répéteurs de l'API, MAC retenues par répéteur, appareils trouvés et appareil conservé lors de la fusion
- Registre des appareils (HA 2026.8+) : plus d'API dépréciées — `async_get_device_by_identifier` au lieu de `async_get_device`, `config_entry_id` au lieu de `config_entries`, `async_remove_device` au lieu de `remove_config_entry_id`, plus de parcours de `registry.devices`, `via_device_id` au lieu de `via_device` (avec repli si les nouvelles API sont absentes)
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.44
- Répéteurs Wi-Fi : **un seul appareil par répéteur physique**. Un répéteur Free expose plusieurs MAC (Ethernet, radios, BSSID) que la Freebox liste comme autant d'hôtes (« Repeteur Wifi Freebox », « #2 », « -2 »…) ; chaque MAC créait son propre appareil. Les MAC sont désormais regroupées (API `/repeater/` quand elle est disponible, sinon par proximité des adresses) sous un identifiant stable, avec toutes les MAC en connexions et le numéro de série
- Migration au démarrage : les appareils répéteurs en double sont fusionnés (entités et pièce déplacées sur l'appareil conservé, entity_id inchangés), puis retirés ; les entités « En ligne » / clients Wi-Fi des anciennes MAC, devenues doublons, sont supprimées
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.43
- Appareils : nouvelle organisation en **4 services de premier niveau** : « Freebox Server », « Freebox Player », « Freebox Maison connectée » (entités du module d'alarme + nœuds Freebox Home, caméras Home comprises) et « TNT » (Guide TV + Programme TNT FR)
- Correction des doublons : les parents virtuels portant le même nom que de vrais appareils (« Freebox Player » dans « Freebox Player », « Guide TV Freebox » à côté de « Programme TNT FR », « Journal d'appels »…) et les anciens groupes restés en place sont supprimés ; les clients réseau, répéteurs, disques et caméras IP sont rattachés directement au Freebox Server ; les entités d'appels reviennent sur le Freebox Server ; le Guide TV rejoint l'appareil TNT
- Nettoyage différé (~2 min) plus sûr : un ancien groupe n'est retiré que s'il n'a plus ni entité ni appareil enfant ; Players et TNT sont d'abord détachés de leurs anciens groupes ; identifiants d'entités inchangés
- Écran « Groupes des appareils » : 4 choix (+ Automatique), surcharges existantes migrées
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.42
- Alarme : les entités du module d'alarme Freebox Home sont désormais portées par l'appareil de groupe « Maison connectée et alarme », qui n'apparaît plus comme « Cet appareil n'a pas d'entités » ; l'ancien appareil séparé du module d'alarme est retiré automatiquement (identifiants d'entités inchangés)
- ⚠️ Pas encore testé dans Home Assistant : merci de signaler tout problème dans les issues

## 28.8.41
- Version publiée sans changement de code (identique à la 28.8.40) : le correctif de l'alarme est dans la 28.8.42

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
