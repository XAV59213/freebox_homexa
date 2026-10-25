# Changelog

## Non publié
- Actions : `tv_guide` et `play_channel` retirées de `services.yaml`. Elles y étaient décrites depuis la 28.8.8 mais n'ont **jamais été enregistrées** par le code : elles apparaissaient dans Outils de développement et échouaient à l'appel. Le guide TV reste disponible via le calendrier « Guide TV » et les capteurs TNT. Pour changer de chaîne, on utilise le lecteur multimédia du Player (`media_player.select_source`, `media_player.play_media`) ou les touches de la télécommande. La constante inutilisée `SERVICE_TV_GUIDE` est supprimée
- Tests : `tests/check_translations.py` vérifie aussi que `services.yaml`, les sections « services » de `strings.json` / `translations/*.json` et les actions réellement enregistrées (`services.py`, `tnt_reminders.py`) sont exactement les mêmes

## 28.8.58
- Actions (revue HACS) : `reboot`, `reload` et `remote` sont enregistrées **une seule fois** au chargement de l'intégration (`async_setup`), plus à chaque entrée, et ne sont plus retirées au déchargement. Noms et paramètres inchangés. Chaque appel retrouve l'entrée concernée : `config_entry_id` ou `device_id` (facultatifs) s'ils sont fournis, sinon l'unique Freebox chargée. Sans Freebox chargée, ou avec plusieurs Freebox et aucune cible, l'action renvoie une erreur claire et traduite au lieu d'agir sur une Freebox au hasard. `reload` sans cible recharge toutes les entrées actives, y compris une entrée en échec. Les actions des rappels TNT sont elles aussi enregistrées au chargement et restent disponibles. La configuration YAML `freebox_homexa:` (jamais lue) est désormais signalée comme non prise en charge (`config_entry_only_config_schema`)
- Traductions : les noms des boutons (Redémarrer Freebox, Marquer les appels comme lus, touches et applis du Player), du capteur « Signal Wi-Fi » et de « Array RAID n degradé » passent par les fichiers de traduction (fr / en). **En français, les noms et les entity_id ne changent pas** ; une installation Home Assistant en anglais les affiche maintenant en anglais. Les messages d'erreur (autorisation Freebox en attente ou refusée, Freebox injoignable, actions, rappels TNT) sont traduits. Les noms historiques des capteurs sans `has_entity_name` (débits, IP, appels, températures, Wi-Fi, TNT, partitions) et les noms des appareils de groupe restent en français pour ne pas renommer les entités existantes
- Dépendance : `freebox-api` en **`>=1.3.1`**, version minimale égale à celle qu'épingle l'intégration Freebox du cœur de Home Assistant (1.3.1). hassfest refuse un `==` sur un paquet que Home Assistant épingle déjà : le minimum lui permet de suivre les mises à jour du cœur, sans conflit si les deux intégrations sont installées
- Qualité : `quality_scale.yaml` réécrit au format officiel (règles done / todo / exempt avec commentaires). Le niveau « silver » n'est plus revendiqué dans `manifest.json` tant que des règles bronze / silver restent à faire
- Tests : `tests/check_translations.py` vérifie que `strings.json` et `translations/*.json` ont les mêmes clés et placeholders, et que chaque `translation_key` du code existe

## 28.8.57
- Correction : les **connexions MAC d'un appareil répéteur** ne contiennent plus que les MAC du répéteur lui-même : MAC principale (ex. `20:66:CF:4B:49:69`), son jumeau « locally administered » (`22:66:CF:4B:49:69`), ses BSSID Free (`22:66:CF:96:92:Dx`), les hôtes LAN reconnus comme répéteur et les interfaces déclarées par l'API `/repeater/` pour ce répéteur (principale, backhaul, fronthaul). Une MAC non Free vue seulement comme `access_point.mac` d'un client (ex. `4E:C4:E5:8E:62:A7`, adresse aléatoire d'un téléphone, sur « Répéteur Wifi Garage ») sert encore à ranger ce client sous le répéteur, mais n'est plus ajoutée à l'appareil. Une MAC présente dans `lan/browser` comme client n'est jamais traitée comme une MAC de répéteur
- Nettoyage du registre à chaque relevé (appareils de l'entrée Homexa uniquement) : les MAC non Free étrangères restées dans les connexions d'un répéteur (Home Assistant ajoute les connexions sans jamais en retirer) sont retirées ; les MAC Free du répéteur ne sont jamais retirées. Un appareil Homexa sans identifiant dont toutes les MAC sont celles d'un répéteur (ex. appareil « 22:66:CF:4B:49:69 » créé pour le jumeau) est supprimé, ses entités et enfants passent sur le répéteur. Les appareils des autres intégrations (ex. intégration **Freebox** native, affichée dans « Appareils connectés — partagent le matériel ») ne sont jamais modifiés

## 28.8.56
- Journal : l'erreur sans gravité **« Connector is closed »** (ex. endpoint 6, appareil 48) pendant un **rechargement** de l'intégration n'apparaît plus comme une erreur. Pendant le déchargement / rechargement de l'entrée, ou quand la session vers la Freebox est fermée (`NotOpenError`, « Connector is closed », « Session is closed »), les relevés (appareils réseau, capteurs, nœuds Freebox Home, volets, caméras, Wi-Fi) s'arrêtent sans bruit (niveau debug). Les vraies erreurs restent signalées
- Nouveau : capteur **« Clients connectés »** sur chaque groupe de clients réseau (« Clients réseau filaires », « Clients Wi-Fi » et chaque sous-groupe de type, ex. « Serveurs (filaire) ») : nombre de clients **en ligne** rangés dans le groupe, attributs `appareils` (en ligne), `hors_ligne` et `total` (listes limitées à 50 noms, non enregistrées dans l'historique). « Clients Wi-Fi » compte aussi les clients des répéteurs. Le capteur est créé avec le groupe et disparaît avec lui (il n'empêche pas le retrait d'un groupe vide). Pas de doublon sur les répéteurs, qui ont déjà leur capteur « Clients Wi-Fi »
- Qualité (revue HACS) :
  - noms traduits (fr / en) pour les capteurs Wi-Fi (« Répéteurs Wi-Fi », « Clients Wi-Fi », « Clients Wi-Fi box », « Appareils connectés », « Appareils sur le Wi-Fi box », « Clients Wi-Fi total »), « Wi-Fi Freebox », « En ligne » (répéteurs), « Télécommande », « Guide TV » et le nouveau capteur ; en français, les noms ne changent pas ; aide du champ « Hôte » traduite
  - plus d'accès disque dans la boucle d'événements (lecture du token, suppression d'un token invalide)
  - télécommande Player : session HTTP partagée de Home Assistant au lieu d'une session créée à chaque appel
  - journaux : messages au format `%s` (plus de f-strings), « Répéteurs Wi-Fi détectés » et le détail de fusion des répéteurs passent en debug (ils étaient écrits à chaque relevé / démarrage)
  - diagnostics : adresses IP et SSID des hôtes masqués
  - imports inutilisés retirés

## 28.8.55
- Types des clients réseau : un client dont le **nom** désigne un serveur (`pve`, `proxmox`, `serveur`/`server`, `hyperviseur`, `truenas`…) va dans **Serveurs** même avec une MAC virtuelle. Depuis Proxmox VE 8, le pont `vmbr0` de l'**hôte** Proxmox a lui aussi une MAC `BC:24:11` : il était classé « VM et conteneurs ». Le nom par défaut de la Freebox « Proxmox Server Solutions GmbH (MAC) » (fabricant + MAC) ne compte pas : une VM / un LXC sans nom reste dans « VM et conteneurs »
- Types des clients réseau : le mot **« tv »** dans le nom (ex. « Tv chambre papa ») classe le client dans **TV et multimédia** avant le fabricant (Realtek, Intel…) ou le type Freebox ; les Fire TV restent dans « Amazon / Alexa »

## 28.8.54
- Correction : les **clients réseau sans appareil** (ex. switch Cisco) n'apparaissaient dans aucun groupe, et « Équipements réseau (filaire) » restait **vide**. Home Assistant ignore le `device_info` des entités `device_tracker` (`ScannerEntity.device_info` est figé à `None`) : un appareil n'existait que si une autre intégration (DHCP, UniFi…) connaissait déjà la MAC, et l'entité était sinon créée **désactivée** et sans appareil. Homexa crée maintenant lui-même l'appareil de chaque client dont l'entité `device_tracker` est **active** (option « Créer les appareils des clients LAN »), le range dans « Clients réseau filaires › type », « Clients Wi-Fi › type » ou sous le répéteur, et y rattache l'entité. Rien n'est créé pour une entité désactivée
- Correction : la MAC d'un client restée dans les **connexions d'un appareil répéteur** (reste d'anciennes versions, ex. Grange) rattachait l'entité du client au répéteur (« Grange ▸ Cisco… ») et faisait lire son classement depuis le répéteur (« Clients Wi-Fi ») : la MAC est retirée du répéteur et le client reçoit son propre appareil. Un identifiant `repeater_<MAC>` périmé sur l'appareil d'un client (ancien faux répéteur) est retiré
- Les sous-groupes « (filaire) » / « (Wi-Fi) » et les groupes filaires / Wi-Fi devenus vides sont retirés à chaque relevé (jamais un groupe qui contient encore un appareil), et ne sont plus créés pour des clients sans appareil
- Les appareils clients prennent le nom Homexa du client (au lieu de la MAC). Diagnostics : `lan_tracked_entities`, `lan_client_devices`

## 28.8.53
- Correction : des appareils **branchés en câble** n'apparaissaient pas dans **« Clients réseau filaires »** (ex. un switch Cisco, type « Périphérique réseau », joignable). Deux causes : (1) un hôte sans `access_point` (ou sans `connectivity_type`) dans `lan/browser`, cas fréquent derrière un switch ou pour un équipement réseau, n'était pas classé et restait directement sous le Freebox Server ; (2) un `access_point.type` « gateway » sans `connectivity_type` suffisait à le compter comme **client Wi-Fi de la box** (rangé dans « Clients Wi-Fi » et compté dans « Appareils sur le Wi-Fi box »). Désormais, un client n'est Wi-Fi que sur une preuve explicite (`connectivity_type` « wifi », `wifi_information`, signal / bande / SSID / BSSID, station `/wifi/ap/*/stations/`), filaire sur `connectivity_type` « ethernet » ou `ethernet_information`, et un appareil **en ligne sans aucun indice Wi-Fi** est filaire. Un client de répéteur sans détail reste Wi-Fi (répéteur)
- Un appareil hors ligne sans information garde son dernier classement (un téléphone Wi-Fi hors ligne ne passe jamais en filaire). Un appareil mal classé en Wi-Fi par la 28.8.52 est corrigé automatiquement dès qu'il est en ligne (2 relevés, environ 1 minute)
- « Groupes des appareils » : deux nouveaux choix, **« Clients réseau filaires »** et **« Clients Wi-Fi »**, pour forcer le regroupement d'un appareil mal détecté. Rappel : un appareil forcé sur « Freebox Server » (choix fait à la main ou hérité de la migration des anciens groupes réseau) reste directement sous le Server ; le remettre sur « Automatique »
- Nouveau : **sous-groupes par type** dans « Clients réseau filaires » et « Clients Wi-Fi » (Wi-Fi de la box) : **Serveurs**, **VM et conteneurs**, **Équipements réseau**, Ordinateurs, Téléphones et tablettes, TV et multimédia, Objets connectés, Consoles, Imprimantes, Caméras, Amazon / Alexa, Autres. Chaque sous-groupe est un appareil (ex. « Serveurs (filaire) », « Téléphones et tablettes (Wi-Fi) ») créé seulement s'il sert, rattaché à son groupe ; les clients Wi-Fi d'un répéteur (Grange, Chambre fille, Garage…) restent directement sous le répéteur, sans couche de type
  - **VM et conteneurs** : carte réseau virtuelle (OUI Proxmox `BC:24:11`, QEMU/KVM `52:54:00`, Xen/LXC `00:16:3E`, VMware `00:50:56` / `00:0C:29` / `00:05:69` / `00:1C:14`, Hyper-V `00:15:5D`, VirtualBox `08:00:27`) ou nom d'hôte contenant le mot `lxc`, `ct`, `vm`, `docker`, `container`/`conteneur`, `site`, `web`, `www`, `nginx`, `apache`, `wordpress`, `portainer`, `k3s`/`k8s` (ex. `ct-101-pihole`, `site-vitrine` ; pas `webcam`)
  - **Serveurs** : type Freebox « NAS », fabricant Synology / QNAP, ou nom `pve…`, `proxmox`, `nas`, `nas1`, `srv01`, `truenas`, `unraid`, `esxi`, `hyperviseur`, `serveur`/`server`, `diskstation`, `openmediavault`…
  - **Équipements réseau** : type Freebox « Périphérique réseau » d'un fabricant non Free (ex. switch Cisco), fabricants Cisco, Netgear, D-Link, Ubiquiti, MikroTik, Zyxel, Aruba, Juniper, Fortinet, Ruckus, DrayTek, Linksys, Meraki, ou nom `routeur`/`router`, `firewall`, `pfsense`, `opnsense`, `unifi`. TP-Link reste « Objets connectés » sauf s'il est déclaré « Périphérique réseau »
  - Le type est statique (pas d'attente) ; le passage filaire ↔ Wi-Fi garde l'anti va-et-vient (2 relevés)
- Options : nouvel écran **« Types des clients réseau »** pour forcer le type d'un client (« Automatique » affiche le type calculé). « Groupes des appareils » affiche maintenant le classement complet, ex. « auto : Clients réseau filaires › Serveurs » ou « auto : Clients Wi-Fi › Garage ». Un client forcé dans « Clients réseau filaires » / « Clients Wi-Fi » va dans le sous-groupe de son type
- Nettoyage : un sous-groupe vide est retiré (au démarrage, après 2 minutes), jamais un sous-groupe qui a encore des appareils. Identifiants distincts des anciens sous-groupes réseau (28.8.36 → 28.8.42). Diagnostics : `lan_client_types`, `lan_type_overrides`

## 28.8.52
- Nouveau : les **clients réseau sont séparés en filaires et Wi-Fi**. Sous le Freebox Server, deux appareils de regroupement sont créés (seulement s'ils servent) : **« Clients réseau filaires »** (appareils branchés en Ethernet, sur la box ou sur le port d'un répéteur) et **« Clients Wi-Fi »**. Dans « Clients Wi-Fi » : les appareils connectés au Wi-Fi de la box, et les répéteurs (Grange, Chambre fille, Garage…), qui portent chacun leurs propres clients Wi-Fi. Classement d'après `lan/browser` (`access_point.connectivity_type` et point d'accès), le point d'accès étant relié au répéteur physique avec les règles de regroupement existantes (MAC principale, jumeau `22:66:CF`, bloc de BSSID)
- Stabilité : un appareil hors ligne garde son dernier classement (mémorisé, et relu dans le registre après un redémarrage) ; un appareil actif qui change de point d'accès n'est déplacé qu'après 2 relevés consécutifs (pas de va-et-vient d'un téléphone entre la box et un répéteur). Un appareil jamais classé (hors ligne, sans information de connexion) reste directement sous le Freebox Server
- Les choix de **« Groupes des appareils »** restent prioritaires (un appareil forcé sur « Freebox Server », « Player », « Maison connectée » ou « TNT » y reste) ; l'écran affiche le regroupement automatique (« auto : Clients Wi-Fi » / « Clients réseau filaires »)
- Correction : un appareil branché en **Ethernet** sur la box était compté comme client Wi-Fi (« Appareils sur le Wi-Fi box », « Clients Wi-Fi box ») car `access_point.type` vaut aussi `gateway` pour le filaire
- Diagnostics : `lan_client_links` (nombre de clients par lien : filaire, Wi-Fi box, répéteur)

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
