# Freebox Homexa : guide de configuration, actions et limites

Ce guide concerne **l'intégration personnalisée HACS Freebox Homexa**, pas une
intégration certifiée de Home Assistant. Il complète le README et décrit le
comportement du code ; un test mocké ne certifie pas un modèle physique.

## Description et prérequis

Les [Freebox de Free](https://www.free.fr/freebox/) regroupent un Server (routeur)
et, selon l'offre, un ou plusieurs Players. Homexa relie Home Assistant aux
fonctions exposées par l'API locale Freebox OS : réseau, Wi-Fi, stockage, appels,
Player et équipements Freebox Home compatibles. Le guide TNT utilise en plus
XMLTV sur Internet ; l'enrichissement TMDB est facultatif. Ces sources sont
indépendantes : une chaîne du guide n'est pas une preuve que le Player la lit.

- Home Assistant **2026.8.0 ou ultérieur** est déclaré par le projet. La suite HA
  de cette PR est exécutée sur **2026.10.4**, pas sur tous les minimums/supports.
- Le Server doit être accessible depuis **la machine exécutant Home Assistant**.
  Une page visible depuis un téléphone ne prouve pas cet accès.
- L'appairage se confirme sur le Server. Autoriser uniquement les fonctions
  nécessaires dans Freebox OS ; une permission absente limite la fonction concernée.
- Ne pas exposer de port Freebox/ADB sur Internet pour installer Homexa. Ne pas
  publier code télécommande, token, adresse IP/MAC, noms d'appareils ou fichiers
  `.storage`. Aucun de ces éléments n'est requis dans une issue publique.

## Installation et premier appairage

1. Ajouter le dépôt `XAV59213/freebox_homexa` comme intégration personnalisée HACS,
   télécharger, puis redémarrer Home Assistant. Sans HACS, copier le répertoire
   `custom_components/freebox_homexa` dans le dossier `custom_components` de la
   configuration HA, sans changer son nom, puis redémarrer.
2. Dans **Paramètres → Appareils et services → Ajouter une intégration**, choisir
   **Freebox Homexa**. La découverte peut également proposer la Freebox.
3. Saisir le nom d'hôte/adresse locale du **Server**, pas du Player, et le port.
   Le port proposé est **80**. Ne pas coller d'URL contenant un token.
4. Confirmer l'autorisation demandée sur le Server. Homexa teste l'ouverture et
   la lecture de la configuration avant de créer l'entrée. Une erreur laisse
   le formulaire ouvert ; l'entrée n'est pas créée « quand même ».
5. Régler les options proposées. Le code télécommande est facultatif, et ne
   remplace pas l'appairage Freebox OS.

| Champ initial | Obligatoire | Usage |
|---|---|---|
| `host` | oui | Hôte local du Server joignable depuis HA ; identité historique de l'entrée |
| `port` | oui, défaut 80 | Port de l'API locale du Server |

Le jeton d'appairage est conservé dans l'espace de stockage propre à Homexa.
Ne pas modifier/supprimer le stockage d'une autre intégration Freebox.
**Limite actuelle :** changer le host touche à l'identité et au fichier de jeton.
Le flow Reconfigurer ne constitue pas encore une migration sûre de l'identité ;
voir la réserve `reconfiguration-flow` de l'audit. Ne pas multiplier les entrées
hostname/IP du même Server pour contourner une erreur.

## Options et effets

Dans **Paramètres → Appareils et services → Freebox Homexa → Configurer** :

| Écran / option | Défaut ou valeurs | Effet / précaution |
|---|---|---|
| Général : `track_lan_clients` | activé | Crée les trackers LAN ; un appareil inconnu n'est pas automatiquement une présence fiable |
| Général : `create_wifi_sensors` | activé | Capteurs de signal Wi-Fi des clients connus |
| Général : `create_lan_devices` | désactivé pour nouvelle entrée | Crée des appareils pour les clients ; les anciennes entrées migrées conservent leur choix/ancien comportement activé |
| Général : `home_poll_interval` | 15 s ; choix 5/10/15/20/25/30 s | Relevé Home séparé ; choisir plus court augmente la charge, pas une garantie de latence |
| Général : `remote_code` | vide | Code télécommande réseau commun ; information privée, ne pas le publier |
| Général : `remote_code_<id>` | vide | Code spécifique à un Player détecté ; prioritaire sur le code commun ; regroupé aussi dans `remote_codes` |
| Groupes : `device_group_overrides` | automatique | Surcharge du rangement des appareils ; ne change pas leur identité |
| Types : `device_type_overrides` | automatique | Classement des clients réseau ; ce n'est pas une détection garantie du matériel |
| Répéteurs : `repeater_merges` | aucune fusion manuelle | Rapprochement de doublons, pas une découverte d'un nouvel endpoint ; ne fusionner que des appareils réellement identiques |
| Guide TNT : `tnt_channels` | catalogue TNT français par défaut si aucune sélection enregistrée | Choix France/Belgique ; une validation du formulaire sans chaîne est refusée |
| Guide TNT : `tnt_tmdb_api_key` | vide | Enrichissement facultatif d'affiches/métadonnées TMDB ; clé privée, ne pas la publier |
| Profils de rappel : `reminder_profiles` | aucun | Nom, cibles notify/media_player, moteur TTS facultatif selon cible, volume d'annonce facultatif |

Les options modifiées sont enregistrées puis l'entrée est rechargée ; à valeurs identiques, HA évite le rechargement inutile. Le formulaire Général
préserve les réglages des autres écrans. Donner aux profils des noms distincts,
y compris entre plusieurs entrées : la résolution des rappels cherche dans les
profils de toutes les entrées et utilise le premier nom correspondant.
Un media_player générique sans moteur TTS ne suffit pas pour une annonce vocale ;
les appareils Alexa peuvent utiliser leur service notify existant. Aucun service
externe n'est installé/configuré automatiquement par Homexa.

## Données, fréquences et disponibilité

| Source | Déclenchement dans le code | Limite |
|---|---|---|
| Server / LAN / capteurs centraux | `__init__.py` programme `router.update_all` toutes les **40 s**, plus le premier relevé au setup | La constante 120 s de router.py n'est pas le timer actif ; une requête lente/échouée n'est pas une mesure instantanée |
| Freebox Home | timer séparé **15 s** par défaut, configurable ci-dessus | Si le poll est déjà en cours, le cycle suivant est ignoré pour éviter le chevauchement |
| Player et autres entités pollées | planification de leur plateforme HA et mises à jour après certaines actions | Pas de promesse de « temps réel » ni d'intervalle global unique ; certaines méthodes relisent des endpoints |
| Alarme en armement | watcher **1 s** lancé après armement ; remplacé si armement répété, retiré au retrait de l'entité ou état idle relevé | Le watcher peut rester actif en état armé : audit de charge encore ouvert ; ne pas assimiler cela à un push |
| Volets | plateforme : **30 s** dans cover.py | RTS sans retour d'état : disponibilité/position ne prouvent pas l'état physique |
| Guide TNT | coordinateur toutes les **5 min** ; nouvelle récupération XMLTV au minimum toutes les **60 min** | Les calculs du programme courant réutilisent le cache ; dépend d'Internet et de la qualité du flux |
| TMDB | enrichissement facultatif à la demande du guide, avec cache | Aucune garantie d'affiche pour tous les programmes |

Les entités à signaux reçoivent le résultat des polls, elles n'interrogent pas
chacune le Server. Un poll central perdu annonce une fois la perte puis le retour ;
les logs d'autres sources ne sont pas encore garantis sans répétition.
Les trackers conservent leur dernier état ; le guide TNT est indépendant du
Server. Un nœud Home `unreachable` rend ses entités indisponibles, sauf RTS sans
retour d'état. Une valeur absente n'est pas un zéro garanti.

## Modèles et fonctions : ce qui est établi, pas une liste certifiée

| Catégorie | Couverture connue du code/tests | Limites physiques |
|---|---|---|
| Server avec API Freebox OS et droits nécessaires | réseau/Wi-Fi, appels, stockage, équipements Home ; fonctionnalités conditionnelles selon les réponses | Aucune matrice exhaustive modèle × firmware validée sur matériel ; les options disponibles varient |
| Player avec `id` et API disponible | media_player et télécommande selon capacités ; fixture Devialet TV/lecture/pause testée | La fixture prouve le parsing, pas tous les firmwares/apps ; volume et commandes restent à confirmer sur l'appareil |
| Player POP `fbx8am`, sans `id`, `api_available=false` | fixture explicite de filtrage, pas d'entité API utilisable créée par ce chemin | « joignable » ne donne pas titre/chaîne/lecture ; Homexa ne peut pas inventer ces données |
| Freebox Home reconnu / droits accordés | alarme, détecteurs, caméra/volets selon catégorie et endpoints réellement fournis | Pas de certification de toutes les générations ; caméra/RTS dépendent de capacités et configuration locales |
| Chaînes TNT / RTBF du catalogue | capteurs et calendrier en lecture, cartes intégrées | Ce sont des programmes de guide, pas un statut OQEE/Player |

Pour YouTube/Netflix : si l'API n'envoie aucun titre vidéo, seul le nom de l'app
peut être utilisé en repli. Les PNG locaux carrés sont des **logos d'application**,
pas des miniatures de vidéos. La TV peut utiliser l'affiche du programme du guide
si la chaîne reconnue correspond ; cela ne constitue pas une identification vidéo.
Android TV Remote, ADB ou Cast ne garantissent pas le titre OQEE/chaîne/app/lecture
sur tous les modèles : ne pas remplacer une absence de donnée par une promesse.

## Les six actions propres à Homexa

Elles existent avant le chargement d'une entrée ; une action sans entrée valable
renvoie une erreur traduite. Les exemples ci-dessous sont documentaires : ils ne
sont pas exécutés par l'installation ou les tests.

### `freebox_homexa.reboot`

Redémarre le **Server**, pas le Player. C'est une action perturbant le réseau.
Champs facultatifs : `config_entry_id` (ID de l'entrée Homexa), ou `device_id`
(appareil Homexa pour retrouver l'entrée). Sans cible, une seule entrée chargée
est nécessaire ; avec plusieurs entrées, préciser laquelle. Pas de réponse métier.

### `freebox_homexa.reload`

Recharge l'intégration et redécouvre les appareils, sans redémarrer le Server.
Champs facultatifs : `config_entry_id`, `device_id`, comme ci-dessus. **Sans cible,
recharge toutes les entrées non désactivées**, y compris celles en échec. Les
entités peuvent être temporairement indisponibles. Pas de réponse métier.

### `freebox_homexa.remote`

Envoie des touches par le même mécanisme que l'entité Remote, avec le code privé
enregistré dans les options. Champs :

- `code` (**obligatoire**) : touche, ou touches séparées par virgules, par exemple
  `1,2`. Touches reconnues par player_remote.py, notamment `power`, `ok`,
  `up`, `down`, `left`, `right`, `back`, `home`, `0`–`9`, `vol_inc`, `vol_dec`,
  `mute`, `prgm_inc`, `prgm_dec`, `play` ; une touche invalide est refusée.
- `player_id` (facultatif) : ID API du Player ; ambiguïté entre plusieurs Players
  signalée si aucune cible ne peut être déterminée.
- `device_id` (facultatif) : appareil Player Homexa, alternative à `player_id` et
  permettant de résoudre l'entrée.
- `config_entry_id` (facultatif) : entrée Homexa à sélectionner si plusieurs
  Servers ; ne sélectionne pas à lui seul le Player parmi plusieurs.

Pas de réponse métier. Une absence de code/Player ou un échec de touche remonte
une erreur traduite. Ne pas mettre le code télécommande dans une configuration
partagée ou une issue.

### `freebox_homexa.schedule_reminder`

Programme une notification/annonce avant un programme, **sans zapper**. Champs :
`channel_name` (nom de chaîne, requis), `program_title` (titre, requis),
`start_time` (date ISO 8601 avec fuseau, requise), `minutes_before` (5, 10 ou 15,
requis), `profile_name` (facultatif uniquement si un profil unique utilisable
existe). Un profil sans cible utilisable, une date invalide ou un rappel déjà
passé sont refusés. Pas de réponse métier. Le rappel et sa destination sont
persistés localement : ils contiennent volontairement titre/chaîne/cibles, pas
à publier. Ils ne sont pas ajoutés aux diagnostics publics Homexa.

### `freebox_homexa.cancel_reminder`

Annule le rappel correspondant exactement à `channel_name`, `program_title`,
`start_time`, `minutes_before` (tous requis, même valeur que la programmation) et
`profile_name` (facultatif, doit correspondre). Annuler un rappel absent n'en crée
pas un nouveau. Pas de réponse métier.

### `freebox_homexa.get_reminder_status`

Lecture seule, avec `channel_name`, `program_title`, `start_time` requis et
`profile_name` facultatif. Ne prend pas `minutes_before` : renvoie tous les délais
programmés pour cette combinaison. **Réponse** :

```yaml
scheduled_minutes: [5, 10]
```

Dans un script HA, utiliser `response_variable` ; il s'agit d'une action à réponse
uniquement, pas d'un capteur ni d'un envoi de notification.

## Exemples et cas d'usage

- [Cartes/dashboards du dépôt](../examples/lovelace/) : remplacer les entity_id
  par ceux de **votre** installation. Les noms affichés ne sont pas les IDs.
- Afficher la chaîne/programme : utiliser le media_player quand les données API
  existent ; utiliser les capteurs TNT pour le **guide**, pas pour déduire que le
  Player est allumé. L'image app n'est pas un titre vidéo.
- Suivre une ouverture/détection : exploiter l'entité Home disponible et une
  transition explicite. Exclure `unavailable`/`unknown` dans une automation de
  sécurité (exemple du README), pour éviter un déclenchement au retour du réseau.
- Lire les rappels avant d'en programmer un autre (exemple à adapter, non lancé) :

```yaml
action: freebox_homexa.get_reminder_status
data:
  channel_name: TF1
  program_title: Programme exemple
  start_time: "2030-01-01T20:00:00+01:00"
response_variable: rappels_tnt
```

Les rappels/annonces peuvent agir sur d'autres services notify/TTS déjà configurés.
Vérifier leurs destinataires et volumes avant un essai réel.

## Dépannage : test minimal et données à ne pas publier

| Symptôme | Vérification utile | Ce qu'il ne faut pas en déduire |
|---|---|---|
| Appairage en attente | Confirmer sur le Server ; attendre le retry ; contrôler les droits dans Freebox OS | Ne pas recréer plusieurs entrées ni publier le token |
| Erreur réseau/entrée non prête | Accès local depuis HA au Server, port configuré, état réseau | Joignable depuis un autre client ≠ joignable depuis HA |
| Home absent | Autorisation Home et présence d'endpoints/catégories reconnus | Un refus de droit n'est pas une preuve d'absence de matériel |
| Player absent, surtout POP | Vérifier si l'API fournit un ID et annonce sa disponibilité | Reachable seul ne suffit pas ; ne pas promettre titre/chaîne |
| App sans titre vidéo | Vérifier les attributs déjà fournis par l'entité, anonymisés | Logo app ≠ miniature ; ne pas inventer de métadonnées |
| Guide vide/ancien | Source XMLTV accessible, chaînes sélectionnées, attendre le cycle ; Internet nécessaire | Pas de lien avec l'état du Player |
| Image Player absente | État actif, entity_picture/media_image_url existant et ressource carte à jour | Pas de hotlink app requis : logos YouTube/Netflix embarqués |
| Rappel sans annonce | Nom de profil unique, cibles notify/TTS existantes, moteur TTS si requis, date future | Un nom de profil correct ne garantit pas que l'appareil de diffusion réponde |

Pour une issue, commencer par version Homexa/HA, fonction/app concernée et message
d'erreur précis, sans données personnelles. Les diagnostics Homexa exportent
**types/présence** et quelques timings autorisés, pas les payloads bruts. Les
fichiers de stockage/logs complets ne sont pas anonymisés par cette protection.
Ne jamais partager des captures contenant adresse, IP/MAC, code, titre privé ou
identifiants ; masquer également les noms d'attributs inconnus si besoin.

## Suppression et données conservées

1. Supprimer l'entrée dans **Paramètres → Appareils et services**. Cela décharge
   ses plateformes et la connexion ; cela ne supprime pas les appareils physiques.
2. Retirer séparément les cartes/ressources/dashboard ajoutés manuellement, si
   elles ne sont plus utilisées. Les retirer n'est pas désinstaller l'intégration.
3. Désinstaller Homexa dans HACS puis redémarrer, ou retirer uniquement son
   répertoire `custom_components/freebox_homexa` pour une installation manuelle.
4. Annuler les rappels souhaités **avant** suppression : ils sont globaux/persistés,
   et le déchargement d'une entrée ne promet pas leur suppression. Les services
   globaux restent enregistrés pendant le processus HA courant.
5. Le code ne garantit pas l'effacement du jeton propre à Homexa, des profils/
   rappels ou des sauvegardes HA. Pour une révocation, gérer l'autorisation de
   l'application dans Freebox OS. Ne pas effacer le stockage d'autres intégrations.

Une désinstallation n'est pas une garantie d'effacement des sauvegardes. Aucun
script de nettoyage destructif automatique n'est fourni dans cette PR.


### Inversion des volets et erreurs de commande (préparation 28.8.90)

Le réglage d’inversion est stocké localement. Si sa lecture échoue, il est inconnu,
non remis silencieusement à « désactivé ». Si l’inversion configurée est inconnue,
Homexa refuse une position ambiguë : vérifier ce réglage avant de réessayer.
Une position non fournie reste inconnue, sans l’afficher comme un volet ouvert.
Les commandes camera/cover échouées remontent une erreur traduite et ne présentent
plus un nouvel état optimiste comme acquis. Le succès d’un appel API ne garantit
pas qu’un équipement physique a terminé son mouvement.


### Erreurs d’actions et rappels (préparation 28.8.90)

Les erreurs des commandes sont remontées dans HA, pas seulement journalisées.
Une saisie invalide (source, volume, touche ou code remote manquant) est refusée
avant la commande concernée. L’état optimiste n’est pas présenté comme réussi
après une erreur détectée. Aucun nouveau protocole de commande n’est ajouté.

Une télécommande peut renvoyer « commande non confirmée » alors que le Player a
réagi : le SDK ne considère pas toutes les réponses HTTP 200 comme confirmées.
**Vérifier l’état du Player avant de réessayer**, surtout une touche bascule.
Aucun retry automatique n’est ajouté. Une macro peut être partiellement exécutée.

Pour les rappels, l’écriture est relue par l’API publique de stockage HA. Si la
persistance échoue, le service remonte une erreur ; une annulation n’enlève pas le
timer existant tant que l’enregistrement de sa suppression n’est pas confirmé.
Ce contrôle ne garantit pas une transaction contre une coupure de courant.


### Confirmation du stockage et état ambigu (préparation 28.8.90)

Si une écriture réussit mais que sa vérification échoue, une erreur ne prouve pas
que rien n’a été enregistré. Le statut refuse de confirmer un rappel lorsque
l’enregistrement et le minuteur actif ne concordent pas ; la carte affiche cette
erreur. Après correction du stockage, programmez ou annulez explicitement le rappel
souhaité. Aucun retry automatique n’est effectué ; une reprogrammation remplace
l’ancien minuteur. Les rappels futurs restaurés restent actifs si seule la purge
d’anciens enregistrements échoue.

Le cache partagé est vérifié avant une action Homexa reboot/reload et avant le
teardown d’une entrée. Un échec initial de ce contrôle empêche la commande/le
teardown ; aucune confirmation de persistance n’est inventée. Les effets réseau
et les fichiers ne constituent pas une transaction atomique.


Cette relecture confirme les valeurs persistées observées, pas un `fsync` ni le
succès physique de chaque écriture. Si les mêmes valeurs étaient déjà enregistrées,
le seul contrat public de HA Store ne distingue pas une écriture identique échouée
d’une valeur déjà correcte ; HA peut la journaliser. Aucun acquittement durable
universel n’est revendiqué.
