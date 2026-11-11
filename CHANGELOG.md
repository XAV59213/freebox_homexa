# Changelog

## 28.8.93 — 2026-11-11
- Listes vides de l'API Freebox (#123) : quand la Freebox omet `result`, freebox-api renvoie None. Ce n'est plus une erreur. Températures, débits, IP, uptime et espace disque restent disponibles. Seul un vrai échec du journal d'appels rend les deux capteurs d'appels indisponibles.

## 28.8.92 — 2026-11-09
- L'entrée se reconnaît par la MAC de la Freebox, plus seulement par l'hôte. La découverte met à jour l'adresse d'une Freebox déjà connue. La reconfiguration et la réauthentification refusent une autre Freebox. Les entity_id et les options ne changent pas.
- Le capteur RAID ne dépend plus du libellé : l'identifiant du registre est migré, l'entity_id choisi reste. Le disque utilise l'identifiant texte exigé par Home Assistant. L'intervalle Home n'est plus réglable dans les options : la valeur existante est conservée, et 15 s par défaut pour une nouvelle installation.
- Autoévaluation Quality Scale, pas une certification Home Assistant. Les règles documentaires qui exigent une page core sont exemptées pour cette intégration HACS. Plusieurs critères restent todo.

## 28.8.91 — 2026-11-09
- Téléphone FXS (#120) : boutons « Démarrer la sonnerie FXS » et « Arrêter la sonnerie FXS », actions `start_fxs_ring` et `stop_fxs_ring`. Une durée (1 à 300 s) demande toujours l'arrêt, y compris en cas d'erreur, d'annulation ou de déchargement. Droit Téléphonie requis. Sans ce droit ou sans port FXS : erreur traduite, pas de succès fictif, les boutons restent en place. Aucun numéro ni nom d'appelant n'est lu.

## 28.8.90 — 2026-11-08
- 23 critères Quality Scale démontrés, 29 todo, 2 exempt. Pas de certification Home Assistant officielle. Tout n'est pas résolu.

## Non publié
- 2026-11-08 — Quality Scale, jalon 25 : devices passe done. Sept contrats d'appareil couvrent les familles actives, testés une fois. Inconnu et les identifiants entiers restent. Mypy 2.4.1 confirme les deux mêmes erreurs (base_class.py:86 et sensor.py:333) ; le nom de caméra n'en fait pas partie. 699 tests, 98,19 % lignes / 92,74 % branches, 23/29/2, préparation 28.8.90 sans merge/release.
- 2026-11-08 — Quality Scale, jalon 24 : deux serveurs gardent des appareils distincts pour les mêmes identifiants entiers, player_3 et le service TNT. Le dict FFmpeg est la configuration de flux, pas le DeviceInfo. Le modèle LAN n'est recopié que s'il est déjà dans l'hôte. devices reste todo. 698 tests, 98,19 % lignes / 92,74 % branches, 42/42 modules au-dessus de 95 % de lignes. 22/30/2, préparation 28.8.90 sans merge/release.
- 2026-11-08 — Quality Scale, jalon 23 : suppression d'un appareil depuis sa page seulement s'il est absent d'une liste complète. Le routeur, les groupes, le guide TNT, les identifiants entiers non confirmés et les appareils d'une autre intégration restent. Aucune suppression automatique. Numéro de série du routeur recopié sans changer la MAC. Exemptions conditions/triggers confirmées par absence de ces plateformes. devices et stale-devices restent todo. 697 tests, 98,16 % lignes / 92,65 % branches, 42/42 modules au-dessus de 95 % de lignes. 22/30/2, préparation 28.8.90 sans merge/release.
- 2026-11-08 — Quality Scale, jalon 22 : 695 tests HA, 98,15 % lignes / 92,44 % branches, 42/42 modules au-dessus de 95 % de lignes. device_groups, wifi_ap, router et tnt_tmdb franchissent le seuil de lignes. test-coverage passe done sur ce seul seuil. Branches publiées à part, plusieurs sous 95 %. Artefact CI 42431543845 identique aux deux passages locaux. 22/30/2, mypy 2 erreurs inchangées, préparation 28.8.90 sans merge/release.
- 2026-11-08 — Quality Scale, jalon 21 : 687 tests HA, 89,10 % lignes / 75,58 % branches, 38/42 modules au-dessus de 95 % de lignes. Setup, guide, Player, rappels et frontend franchissent le seuil de lignes. Quatre modules restent en dessous. 21/31/2 inchangé, préparation 28.8.90 sans merge/release.
- 2026-11-08 — Quality Scale, jalon 20 : 681 tests HA, 84,83 % lignes / 69,75 % branches, 33/42 modules au-dessus de 95 % de lignes. Associations Player/disque/MAC étrangère et cycle d'erreur FFmpeg prouvés sans migration d'identité. 21/31/2 inchangé, mypy 2 erreurs, préparation 28.8.90 sans merge/release.
- 2026-11-07 — Quality Scale, jalon17 : router strict105→85 diagnostics globaux,7fichiers/42modules ; contrats SDK object et validations sans Any/cast/ignore ajouté. IDs/propriétaires NativeRegistry bornés sans conversion, propriétaires inconnus protégés, cache/reparentage LAN gardés. Registry compat100% lignes/96,67% branches ;617tests HA,79,63% lignes/61,49% branches,20/42modules >95%,21/31/2 inchangé. Vrai SDK/HA transports mockés, aucun polling/commande réelle/migration ; préparation28.8.90 sans publication.
- 2026-11-07 — Quality Scale, jalon16 : typage strict120→105 diagnostics,14→8fichiers,42modules ; six modules supplémentaires sans diagnostic, protocoles SDK object/validations réelles et imports HA canoniques. MAC/IDs/préférences conservés, EPG absent distinct de réellement vide, erreurs/reprises sur SDK réel et transports mockés. 610tests HA,79,22% lignes/60,75% branches ; seuil officiel >95% par module encore non atteint (19/42),21/31/2 inchangé. Partition honnête des31todo, sans nouvelle commande/polling, sans Any/cast/ignore ajouté. Préparation28.8.90, sans publication.
- 2026-11-07 — Quality Scale, jalon15 : Repairs sur12scopes de lectures existantes en plus de Home, refus SDK structurés seuls, ignorer et IDs préservés ; observation valide du même scope requise, reprise agrégée stations, nettoyage entrée ciblé. Pas de commande/sonde/nouveau polling. Home tardif ne résout pas une alerte après close, journal appels invalide indisponible plutôt que faux zéro, erreurs repeater sans payload brut/endpoint inchangé. 593tests,79,07 % lignes/60,59 % branches,120diagnostics stricts/14fichiers ;21/31/2 inchangé, règles globales Repairs/caméra toujours todo. Préparation28.8.90 sans publication.
- 2026-11-07 — Quality Scale, jalon 14 (inclut lot13) : Player tardif découvert par metadata partagé au timer existant, zéro nouveau timer/reload/commande ; inventaire dynamique multi-entrées Home/LAN/répéteurs/stockage, IDs et préférences conservés. Repair Home actionnable FR/EN, ignorer persistant et suppression ciblée après récupération/retrait ; règle Repairs globale reste todo. 567 tests HA, 78,69 % lignes /59,90 % branches, 21/31/2, mypy122 erreurs/16 fichiers/41 modules. Préparation28.8.90, sans merge/release.
- 2026-11-07 — Quality Scale, lot 13 local (CI non encore livrée) : flow 100 % via manager réel, 20/32/2 ; découverte incrémentale Home/stockage/températures sans recréation des entités connues ni nouveaux polls. Ajouts tardifs et retour après absence conservent IDs/noms/icônes/préférences. Alarm réellement borné/typé, état malformé inconnu ; 553 tests HA, 76,18 % lignes / 55,57 % branches, mypy 122 erreurs/16 fichiers/40 modules. Player tardif et disponibilité caméra globale encore todo ; préparation 28.8.90 sans publication.
- 2026-11-07 — Quality Scale, lot 12 : noms fixes consommés réellement en FR/EN et icônes Player dynamiques par métadonnées frontend, deux règles closes (19/33/2). Observation image distincte Home sans sonde, frames tardives ignorées après retrait/closing ; réserve disponibilité globale conservée. 536 tests HA, 75,74 % lignes / 54,34 % branches ; mypy 130 diagnostics, préparation 28.8.90 sans publication. IDs/préférences conservés.
- 2026-11-07 — Quality Scale, lot 11 : boutons seuls surveillés au timer partagé sans doubler le média ; transitions perte/retour par source sans spam ni données privées, Wi-Fi inconnu distinct de panne. Icônes fixes déplacées dans icons.json avec vrai chargeur HA et préférences conservées ; icône dynamique Player préservée. 511 tests HA, 17/35/2 ; mypy 162 erreurs, préparation 28.8.90 sans publication.
- 2026-11-07 — Quality Scale, lot 10 : panne/récupération Remote/Player/boutons, LAN/Wi-Fi et endpoints Home individuels sans faux états ; veille confirmée contrôlable conservée, bridge nodev reconnu/retesté et caches disparus invalidés. Contrat débit vérifié par vrai SDK + HTTP JSON ; provenance SDK 1.3.1 signée vérifiée, minimum >= conservé après refus réel de pin partagé par hassfest. 490 tests HA, couverture 74,44 % lignes/52,12 % branches ; 16/36/2, inventaire fini des 36 réserves. Préparation 28.8.90 sans publication.
- 2026-11-07 — Quality Scale, lot 9 : débit octets/s corrigé en kB/s (/1000, historique/IDs conservés) ; disponibilité disques/RAID/Home/XMLTV et récupération réelles, sans cache faussement frais ni désactivation permanente sur panne transitoire. Valeurs inconnues sans faux zéro/RAID sain. 451 tests HA, deux suites JS ; couverture 68,47 % lignes/44,13 % branches, mypy 167 erreurs restantes. 16/36/2 honnête, préparation 28.8.90 sans publication.
- 2026-11-07 — Quality Scale, lot 8 : noms relatifs globaux avec IDs/choix utilisateur conservés ; nouveaux RSSI opt-in sans désactiver les anciens. Perte de source capteurs signalée, débit absent/invalide inconnu et récupération réelle HA ; refus/annulation unload compatible avec fermeture concurrente. Contrats XMLTV typés/testés, FFmpeg hérité et rollback refusé caractérisés sans fausse garantie. 407 tests HA, couverture 67,33 % lignes/42,47 % branches, 186 erreurs strictes restantes ; 16/36/2, préparation 28.8.90 sans publication.
- 2026-11-07 — Quality Scale, lot 7 : inversion volet indépendante de l’ordre de découverte/renommage ; lectures SDK des entités drainées avant fermeture. Revue globale des 30 familles/81 variantes et catégories config/diagnostic corrigées avec préférences registre conservées. 377 tests HA, deux suites JS ; couverture 64,80 % lignes/39,18 % branches, typage 227 erreurs restantes. 14 done/38 todo/2 exempt, préparation 28.8.90 sans publication.
- 2026-11-07 — Quality Scale, lot 6 : vrai discovery/forward des onze plateformes et rollback partiel/complet ; fuite du listener caméra corrigée. Lectures d’intervalle drainées avant close, fermeture sérialisée, sans garantie de fermeture SDK amont. Store partagé vérifié avant actions/teardown ; rappels ambigus signalés, minuteurs remplacés sans doublon, restauration sans perte de métadonnées et erreur de statut visible dans la carte. 356 tests HA (+14), couverture 62,02 % lignes/35,61 % branches, typage strict mesuré 268→230 erreurs après correction Coroutine. 13/39/2 inchangé, préparation 28.8.90 sans publication.
- 2026-11-07 — Quality Scale, lot 5 : 342 tests (+108), 13 done/39 todo/2 exempt. Erreurs des 42 frontières d’actions remontées en HA, sans faux succès ni payload privé ; commande télécommande non confirmée distinguée sans retry automatique. Rappels : verrou/relecture publique du vrai Store HA et conservation du timer si annulation non persistée. Fermeture publique tentée après échec post-probe ; onze plateformes simultanées/TNT testées. Couverture lignes 58,02 %, branches 30,44 % ; préparation 28.8.90, sans publication.
- 2026-11-07 — Quality Scale, lot 4 : 234 tests (+47), vraies plateformes caméra/volets/interrupteurs/boutons, contrat Home du vrai SDK sur transport mocké, récupération après erreurs de configuration et matrice de preuves des 54 règles. Correction double inversion/position inconnue, état caméra périmé, disponibilité Wi-Fi et faux succès camera/cover. Aucun changement d’identité, endpoint repeater/ ou publication ; préparation 28.8.90, évaluation 12/40/2 inchangée.
- 2026-11-07 — Quality Scale, lot 3 : 187 tests HA (+69), plateformes Player/télécommande/calendrier et inventaire des 41 boutons ; veille correctement reconnue, indisponibilité après échec du statut, volume/muet inconnus non réutilisés, dates TV débordantes ignorées. Évaluation prudente inchangée (12 done / 40 todo / 2 exempt), aucun niveau officiel revendiqué.
- 2026-11-07 — Quality Scale, lot 2 : guide utilisateur détaillé, propriétaires CODEOWNERS cohérents avec le manifeste et métadonnées des six services FR/EN, vrais tests de plateformes HA/dispatcher/coordinateurs et multi-entrées, couverture mesurée renforcée. Aucun niveau officiel revendiqué.
- 2026-11-07 — Options : conserve les codes télécommande des Players absents de la liste ou non listables ; un code visible reste effaçable explicitement. Autres options/IDs inchangés.
- 2026-11-07 — Robustesse : RAID absent sur plusieurs cycles puis revenu sans crash ; watcher alarme remplacé sans fuite et nettoyé ; hooks Home coopératifs ; coordinateur TNT lié explicitement à son entrée. Rappel sans fuseau refusé avec message traduit avant sauvegarde ; erreurs XMLTV traduites. Aucune commande réelle lors des tests, aucun endpoint repeater/ modifié.
- 2026-11-07 — Quality Scale (préparation 28.8.90) : tests sous le vrai framework HA 2026.10.4, couverture globale mesurée et publiée en artefact CI, preuves/réserves par règle ; autoévaluation sans certification HA.
- 2026-11-07 — Connexion initiale : tentative de fermeture publique du SDK si open/probe échoue ou est annulé (limite de close amont documentée) ; erreurs réseau temporaires vers ConfigEntryNotReady, token invalide/droits insuffisants vers réauthentification. Conservation de l'erreur initiale si close échoue ; suppression des logs d'erreur redondants avant les exceptions HA. Aucun changement repeater/ ni commande appareil.
- 2026-11-07 — Carte Player : correction de `volume_set` (`volume_level` 0–1 exigé par HA, et non `volume`). Le rejet de schéma empêchait tout appel à l’API Freebox. Muet conserve `is_volume_muted` ; conversion backend en volume entier 0–100 inchangée. Tests de contrat HA et SDK sans commande réelle.
- Carte Player : curseur volume 0–100 % et bouton muet selon les capacités et valeurs disponibles. Envoi seulement à validation du curseur ; aucun appel automatique. Masqués à l’arrêt/indisponibilité ou si valeur inconnue.
- 2026-11-07 — Carte Freebox Homexa : image de lecture du Player (`entity_picture`, sinon `media_image_url`) au-dessus des commandes. Affichage sans recadrage ni étirement ; masqué sans image, en veille ou sur erreur. Carte TNT inchangée.


## 28.8.87 — 2026-11-06
- Carte Homexa TNT : bouton **« Regarder sur {chaîne} »** dans le détail d’un programme (carrousel « En ce moment », guide, top films) pour zapper sur le Freebox Player configuré (`media_player` / `play_media` avec `tv:?channel=N`, ou script `zap_channel_scripts` s’il existe). Bouton masqué si aucun Player ni script. Numéro Freebox exposé sur les capteurs TNT (`channel_number`). Carte `3.0.8-homexa.2`.

## 28.8.86 — 2026-11-06
- Player : artwork YouTube/Netflix via PNG carrés embarqués (`frontend/youtube.png`, `frontend/netflix.png`) servis en local (`/freebox_homexa/youtube.png`, `/freebox_homexa/netflix.png`) — plus de hotlink externe pour `media_image_url`. TNT reste prioritaire.

## 28.8.85 — 2026-11-06
- Player : en YouTube/Netflix sans miniature API, `media_image_url` utilise les logos publics `https://brands.home-assistant.io/youtube/logo.png` et `https://upload.wikimedia.org/wikipedia/commons/e/ea/Netflix_Logomark.png` (Logomark Netflix issu de brand.netflix.com, domaine public sur Wikimedia Commons). Icône entité `mdi:youtube` / `mdi:netflix`. L’artwork TNT en live TV reste prioritaire ; image et icône effacées à l’arrêt.

## 28.8.84 — 2026-11-06
- Player : artwork TNT sur le media_player en live TV — poster/icone du programme en cours, sinon logo de chaîne (même préférence que la carte Homexa TNT ; le capteur TNT préfère encore le logo). Matching par nom/numéro (`BFM TV` / `BFMTV` / numéro). Effacé hors TV (veille, YouTube, Netflix, sans match). Réutilise les URL HTTP déjà en mémoire dans le coordinateur TNT, sans requête réseau supplémentaire.
- Player : si YouTube ou Netflix est déjà reconnu comme source et qu'aucun titre/chaîne n'est fourni, le media_player affiche « YouTube » / « Netflix » au lieu d'une carte vide. Aucun titre de vidéo inventé ; la chaîne TV (ex. BFM TV) reste prioritaire. Le diagnostic aligne la catégorie d'application sur la même détection large (youtube/netflix dans package/cur_url), toujours sans exporter le package brut.

## 28.8.83 — 2026-11-05
- Diagnostic Player : deux observations récentes du polling normal pour vérifier l'avancement YouTube, sans commande ni requête supplémentaire. Seules les durées/positions numériques finies de 0 à 7 jours, un état de lecture validé, une catégorie d'application connue et les dates de collecte sont exportés. Confidentialité volontairement moins stricte que le schéma seul pour ces valeurs précises ; aucun titre, auteur, URL, package brut ou identifiant. Échantillons effacés sur erreur/changement de catégorie et retirés après 120 secondes ; dernière collecte marquée périmée si nécessaire. Aucun changement du media_player ni support du titre vidéo.

## 28.8.82 — 2026-11-05
- Diagnostic Player : dernier schéma de statut reçu lors du polling normal (aucune requête supplémentaire ni commande). Types et présence des champs média uniquement, sans titres, auteurs, images/URL, valeurs numériques ou identifiants ; noms de champs inconnus remplacés. Les anciens diagnostics réseau sont aussi limités à leur structure pour ne plus exporter MAC/noms/identités. Aucun JSON brut conservé ni journalisé ; collecte bornée en mémoire, réinitialisée au rechargement. Ce mode privilégie la confidentialité et réduit les informations disponibles pour le dépannage réseau.

## 28.8.81 — 2026-11-05
- Player Devialet : lecture du statut imbriqué (`player.state.playback_state`) et de la chaîne (`foreground_app.context.channel.channelName` / `channelNumber`). Le media_player expose la chaîne et utilise son nom en repli du titre, sans inventer de titre d'émission. Formats plats conservés, informations effacées à l'arrêt ou lorsqu'elles disparaissent. Tests sur extrait public Devialet anonymisé ; validation sur appareil réel encore à faire.

## 28.8.80 — 2026-11-05
- Correction thread-safety (#106) : le retry Player (`async_schedule_player_api_retry`) passait `hass.async_create_task` via un lambda à `async_call_later`, ce qui plantait avec `RuntimeError` hors de la boucle d'événements. On passe maintenant la coroutine directement (comme le frontend Lovelace) — HassJob la planifie correctement

## 28.8.79 — 2026-11-05
- Issue #106 — messages et robustesse :
  - **Freebox Home (`home/nodes`)** : on ne confond plus une erreur HTTP quelconque avec un refus de droit. Un vrai `insufficient_rights` affiche le message d'autorisation (droits de l'application dans Freebox OS, sans imposer une case « maison connectée » qui n'existe pas sur tous les modèles). Toute autre erreur (endpoint absent sur Freebox v8, indisponibilité temporaire…) a un message neutre et actionnable
  - **Player POP / `api_available=False`** : message clair (nom, `api_available`, modèle, pistes : Player allumé, Android TV Remote). Pas de contrôle inventé sans `id` — Free n'expose alors pas d'API locale. Si l'API devient disponible plus tard, Homexa recharge automatiquement l'entrée (retries espacés). Les chemins Homexa passent toujours un `player_id` explicite et ne s'appuient pas sur `freebox-api` `players[0]["id"]` non gardé
  - **Appairage (`async_step_link`)** : journalise le type d'exception ; gère `InvalidTokenError`, timeouts et erreurs réseau aiohttp à part de l'« Erreur inconnue » ; ferme toujours la session
  - **HA 2026.12** : suppression de l'`update listener` au profit de `OptionsFlowWithReload` (reauth/reconfigure gardent `async_update_reload_and_abort`) — finit l'avertissement « has an update listener and should use it for scheduling a reload »
  - tests : `tests/simulation_issue106_home_player.py`

## 28.8.78 — 2026-11-05
- Correction : certains Freebox Player renvoyés par l’API n’ont pas de clé `id`. Les plateformes media_player, remote et button les ignorent maintenant au lieu de planter avec `KeyError: 'id'` (#106).

## 28.8.77 — 2026-11-04
- Reconfiguration : on peut maintenant changer l’hôte/port d’une entrée existante (menu ⋮ → Reconfigurer) sans la supprimer. Utile pour passer de l’URL publique `*.fbxos.fr` à `mafreebox.freebox.fr` ou une IP locale quand l’accès distant est désactivé.

## 28.8.76 — 2026-11-04
- Découverte zeroconf : le menu ⋮ de la carte de découverte affiche maintenant **Ignorer** (unique_id posé dès la découverte). Permet de masquer la carte sans créer d’entrée.

## 28.8.75 — 2026-11-04
- Configuration : le formulaire de saisie de l’hôte est **toujours affiché**, même après une découverte zeroconf. L’utilisateur peut ainsi modifier manuellement l’adresse (`mafreebox.freebox.fr` ou IP locale) quand l’accès à distance est désactivé et que l’URL publique `*.fbxos.fr` est injoignable (#101, PR #102)
- Suite revue HACS (frenck) : `async_merge_repeater_devices` applique les mêmes gardes que `async_clean_repeater_connections` — un doublon de répéteur partagé avec une autre intégration n’est ni vidé ni supprimé (ni choisi comme appareil conservé), seules nos propres entités sont déplacées, et un doublon portant encore une entité d’une autre intégration n’est jamais supprimé (tests : `tests/simulation_registre_partage.py`)

## 28.8.74 — 2026-11-02
- Revue HACS (frenck) — **appareils des autres intégrations jamais modifiés** :
  - `ensure_lan_client_device` : avant de créer l’appareil d’un client réseau, la MAC est cherchée dans **tout** le registre. Si un appareil d’une autre intégration la porte (Shelly, ESPHome…), ou si Home Assistant y a relié le tracker, il n’est plus jamais renommé, modifié (fabricant), rattaché à l’entrée Homexa, re-parenté ni rangé dans « Clients réseau »
  - `async_clean_repeater_connections` : un appareil partagé avec une autre entrée n’est plus modifié ni supprimé ; un appareil portant une entité d’une autre intégration n’est plus vidé ; seules nos propres entités sont déplacées
  - même garde que `async_remove_lan_client_devices`, factorisée dans `registry_compat.shared_with_other_entries`
  - tests : `tests/simulation_registre_partage.py` (Shelly / ESPHome intacts, nos appareils toujours gérés)
- Revue HACS (frenck) — **vie privée du journal d’appels** :
  - capteur « Derniers appels Freebox » : l’état reste le nombre d’appels non lus ; l’attribut `calls` (noms, numéros) est **supprimé**
  - capteur « Appels manqués Freebox » : même problème, les attributs « date → nom » (le nom vaut le numéro pour un appelant inconnu) sont **supprimés** ; l’état (nombre de manqués non lus) ne change pas. Une carte Markdown ou une automatisation qui lisait ces attributs doit passer à la carte « Homexa Appels »
  - nouvelle commande WebSocket `freebox_homexa/calls` (entité capteur Homexa obligatoire pour un non-administrateur, droit de lecture sur l’entité vérifié) ; la carte `homexa-calls-card` l’utilise, se rafraîchit à chaque changement du capteur et toutes les 60 s, et affiche un message clair si la commande est indisponible ou refusée
  - tests : `tests/simulation_journal_appels.py`

## 28.8.71 (2026-10-31)
- Documentation : capture de la carte **Homexa Appels** ajoutée au README (`docs/images/homexa-calls-card.jpg`)
- Documentation : captures des cartes **Freebox Homexa** et **Homexa TNT** ajoutées au README (`docs/images/freebox-homexa-card.jpg`, `docs/images/homexa-tnt-card.jpg`)

## 28.8.70 (2026-10-31)
- Nouvelle carte **`homexa-calls-card`** (« Homexa Appels ») : journal des appels de la Freebox, livrée avec l’intégration (chargée automatiquement comme la carte TNT)
  - une ligne par appel : icône colorée (manqué / reçu / émis), nom en gras, heure, « Aujourd'hui » / « Hier » / date, durée, numéro en option ; point rouge sur les non lus et badge « N manqués »
  - éditeur visuel : capteur, titre, nombre d’appels (1 à 30), types affichés, numéro, durée
  - fonctionne aussi avec l’ancien capteur « Appels manqués Freebox »
- Nouveau capteur **« Derniers appels Freebox »** (`calls_log`) : état = appels non lus, attribut `calls` (30 derniers appels : nom, numéro, type, date, durée, non lu), exclu de l’historique. Les capteurs existants ne changent pas

## 28.8.69 (2026-10-31)
- **TNT / guide XMLTV** : la mise à jour horaire du guide (~78 Mo) ne bloque plus Home Assistant (#91). Le parsing se fait désormais par morceaux (`XMLPullParser`) au lieu d'un `ET.fromstring()` qui gardait le GIL ~13 s sur HA Green et faisait planter ZHA. Mémoire réduite, résultats identiques

## 28.8.68 (2026-10-31)
- Carte **`homexa-tnt-card`**, éditeur visuel : les **libellés des interrupteurs** avaient disparu (Home Assistant récent n'affiche plus l'attribut `label` de `<ha-formfield>`). Chaque interrupteur (vues, carrousel, Favoris, Guide TV, Top films, chaînes favorites) a de nouveau son texte, à gauche ; toucher le texte bascule l'interrupteur. Accents rétablis (« À suivre », « soirée »)
- Carte **`freebox-homexa-card`** :
  - **interrupteurs « Sections affichées »** : ils apparaissaient désactivés alors que les sections étaient affichées (clé absente), si bien que les désactiver semblait sans effet. Ils sont maintenant activés par défaut (`default: true`) et reflètent l’état réel ; les désactiver masque bien la section. Clé absente = section affichée, comme avant
  - **plusieurs volets / PIR / Player / RSSI / alarmes** : le sélecteur était déjà multiple, mais ne le montrait pas. L’aide indique maintenant qu’après un choix, un nouveau champ apparaît dessous pour ajouter une autre entité
  - listes saisies en YAML sous forme de texte (`covers: cover.a, cover.b`) acceptées en plus des listes

## 28.8.67 (2026-10-31)
- Carte **`freebox-homexa-card`** réglable :
  - nouvel éditeur visuel natif de Home Assistant (`getConfigForm`) : vrais sélecteurs d’entités et bouton **Enregistrer** actif dès qu’on change un réglage (l’ancien éditeur à champs texte ne l’activait qu’en quittant le champ)
  - **plusieurs entités par section** : `alarms`, `covers`, `pirs`, `players`, `rssi_entities` ; une tuile par entité, chacune avec ses propres boutons
  - **sections masquables** : `show_alarm`, `show_covers`, `show_pir`, `show_player`, `show_rssi`, et `title` facultatif
  - détection auto limitée aux entités Freebox Homexa quand il y en a ; « salon » est bien préféré à « volet » pour le volet par défaut
  - à l’ajout de la carte, elle est pré-remplie avec les entités détectées
  - compatibilité : `alarm_entity`, `cover_entity`, `pir_entity`, `player_entity`, `rssi_entity` restent lues ; une carte existante s’affiche comme avant

## 28.8.66

- docs: badge Downloads cumulés

## 28.8.65
- Publication / HACS :
  - chaque release GitHub joint désormais l'archive **`freebox_homexa.zip`** (contenu de `custom_components/freebox_homexa`, sans `__pycache__` ni `.pyc`). `hacs.json` passe en `"zip_release": true` / `"filename": "freebox_homexa.zip"` : HACS installe depuis ce zip et peut afficher un **compteur de téléchargements**
  - le workflow `release.yaml` vérifie que `manifest.json`, `const.py` et le `manifest.json` du zip portent la même version que le tag, puis que l'archive est bien jointe à la release
  - aucun changement pour l'intégration elle-même (aucun code modifié)

## 28.8.64
- Documentation :
  - README : nouvelles sections « Actions » (les 6 actions ; `freebox_homexa.remote` avec `code`, `player_id`, `device_id`, liste des touches, exemples YAML, erreurs), « Disponibilité et journal » (entités indisponibles quand la Freebox est injoignable, nœuds Home « unreachable » hors RTS, journal unique, astuce `not_from` pour les automatisations d'alarme) et « Suppression ». L'option « Créer des appareils pour les clients réseau » est mise à jour (décochée par défaut sur une nouvelle installation, conservée sur une existante, retrait automatique des appareils clients 100 % Homexa). Dépannage complété
  - info.md complété
  - `quality_scale.yaml` : `docs-actions` et `docs-removal-instructions` passent à « done »

## 28.8.63
- Correction : l'action **`freebox_homexa.remote`** envoyait les touches à `http://<adresse du Freebox Server>/pub/remote_control`, une adresse qui n'existe pas sur le Server : la commande ne faisait rien. Elle passe désormais par le même chemin que l'entité « Télécommande » du Player (ex. `remote.salon_freebox_player_telecommande`), c'est-à-dire `freebox_api` → Freebox Player, avec le même code télécommande réseau (celui du Player, sinon le code commun des options). Code partagé dans `player_remote.py`
  - compatible avec les appels existants : `code: power`, ou plusieurs touches séparées par des virgules (`code: "1,2"`) ; majuscules et espaces tolérés
  - nouveau, facultatif : `player_id` (numéro du Player) ou `device_id` (appareil Player Homexa) pour viser un Player. Avec un seul Player, rien à préciser
  - erreurs claires et traduites (fr / en) au lieu d'un simple journal : aucun Player détecté, code télécommande manquant (avec le numéro du Player), plusieurs Player sans cible ni code commun, touche inconnue (rien n'est envoyé), numéro de Player invalide, touche non envoyée (Player injoignable)
- Tests : `tests/simulation_action_remote.py`

## 28.8.62
- Option **« Créer des appareils pour les clients réseau »** : **décochée par défaut pour les nouvelles installations**. C'est la règle de Home Assistant : un `device_tracker` (ScannerEntity) ne crée pas d'appareil, il se relie seul à l'appareil d'une autre intégration qui a la même MAC (ex. Shelly, ESPHome)
  - **installations existantes : aucun changement**. Une migration (entrée 1.1 → 1.2) écrit l'option **cochée** si elle n'avait jamais été réglée. Un choix déjà fait (coché ou décoché) est conservé. Appareils clients, groupes « Clients réseau filaires / Clients Wi-Fi », capteurs « Clients connectés », entity_id et unique_id restent identiques
  - option décochée :
    - Homexa ne crée plus d'appareil client et ne modifie plus le registre pour y rattacher les trackers ;
    - un appareil existant, même celui d'une autre intégration, n'est plus déplacé sous un groupe ;
    - les capteurs RSSI Wi-Fi restent des entités seules, pas rattachées à la Freebox Server pour ne pas la surcharger ;
    - les groupes de clients et leurs capteurs « Clients connectés » ne sont pas créés : ils n'ont de sens qu'avec des appareils clients
  - en décochant l'option, seuls les appareils clients **créés uniquement par Homexa** sont retirés au rechargement. Un appareil partagé avec une autre intégration n'est plus jamais supprimé (avant, il pouvait l'être)
  - à noter, option décochée (nouvelles installations) : Home Assistant crée **désactivé par défaut** le tracker d'un client qu'aucune autre intégration ne connaît. On l'active dans la liste des entités, comme avec l'intégration Freebox officielle
- Tests : `tests/simulation_option_appareils_clients.py` (défaut, migration, choix conservé, option décochée)

## 28.8.61
- Qualité (Integration Quality Scale) — **entity-unavailable** :
  - quand la Freebox est **injoignable** (journal « Freebox injoignable »), les entités Homexa passent **indisponibles** au lieu de garder une valeur figée ou de passer « inconnu » : capteurs (débits, températures, appels, disques, Wi-Fi, répéteurs, groupes de clients), capteurs binaires, interrupteur Wi-Fi, boutons, télécommande et lecteurs Player, calendrier Guide TV, et toutes les entités Freebox Home (volets, alarme, caméras, détecteurs, batteries). Elles redeviennent disponibles dès le retour de la Freebox (« Freebox de nouveau joignable ») ; les entités pilotées par signal sont réécrites tout de suite, les autres au relevé suivant
  - nœud Freebox Home signalé **« unreachable »** par la Freebox (ex. détecteur hors de portée, caméra débranchée) : ses entités passent indisponibles. Les volets **RTS** (Somfy, radio sans retour d'état) ne sont jamais rendus indisponibles pour ce motif
  - **inchangé** : les suivis d'appareils (`device_tracker`) gardent leur dernier état pendant une coupure, pour ne pas perturber la présence et les automatisations `to: home` / `to: not_home` ; l'interrupteur « inversion » des volets (réglage local) et les capteurs TNT (source Internet) restent disponibles
  - attention aux automatisations sur l'**alarme** (ou un volet) déclenchées par `to:` : au retour, l'état passe de `unavailable` à la vraie valeur (ex. `disarmed`) et peut redéclencher l'automatisation. Ajouter `not_from: [unavailable, unknown]` au déclencheur pour l'éviter

## 28.8.60
- Qualité (Integration Quality Scale) :
  - **runtime-data** : le routeur Freebox est rangé dans `entry.runtime_data` (entrée typée `FreeboxConfigEntry`) au lieu de `hass.data[freebox_homexa][unique_id]`. Plateformes, actions, diagnostics, options et déchargement lisent `entry.runtime_data`. `hass.data` ne garde que l'état global (cache de configuration, carte Lovelace, coordinateurs TNT). Aucun changement visible
  - **parallel-updates** : `PARALLEL_UPDATES = 0` pour les plateformes mises à jour par le relevé central (capteurs, capteurs binaires, suivi d'appareils, calendrier) ; `PARALLEL_UPDATES = 1` pour les plateformes d'action (boutons, interrupteurs, volets, caméras, alarme, télécommande, lecteur multimédia) : une seule commande ou mise à jour à la fois par plateforme vers la Freebox
  - **log-when-unavailable** : quand la Freebox ne répond plus, le journal affiche **une seule fois** « Freebox injoignable » (niveau info), puis « Freebox de nouveau joignable » à son retour. Avant, chaque relevé (toutes les 40 s) écrivait une erreur ou une trace complète. Pendant la coupure, les échecs de relevé des volets, caméras, Wi-Fi et nœuds Freebox Home passent en debug

## 28.8.59
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
- Release de maintenance (voir https://github.com/XAV59313/freebox_homexa/compare/28.8.25...28.8.27)

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
