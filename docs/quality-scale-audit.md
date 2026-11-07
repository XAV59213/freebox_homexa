# Integration Quality Scale — autoévaluation Freebox Homexa

Audit du 7 novembre 2026 (Europe/Paris), base `b6a2599` (main 28.8.89),
préparation **28.8.90** après correction runtime ciblée. Aucun niveau officiel
Bronze/Silver/Gold/Platinum attribué ou revendiqué ; HACS ≠ certification IQS.
Aucun champ `quality_scale` ajouté au manifeste. PR #119 conservée, sans merge/release.

## Référentiel vérifié en direct

- [Présentation officielle](https://contributors.home-assistant.io/core/quality-scale/)
- [Toutes les règles](https://contributors.home-assistant.io/core/quality-scale/rules/)
- [Schéma et liste exacts, source HA épinglée](https://github.com/home-assistant/core/blob/49693fc6644b3555fdaaf9fe30a973517a0a9d4e/script/hassfest/quality_scale.py#L36-L95)
- [Schéma probatio](https://github.com/home-assistant/core/blob/49693fc6644b3555fdaaf9fe30a973517a0a9d4e/script/hassfest/quality_scale.py#L2007-L2030)
- Exceptions documentées : [docs-conditions](https://contributors.home-assistant.io/core/quality-scale/docs-conditions/), [docs-triggers](https://contributors.home-assistant.io/core/quality-scale/docs-triggers/).

Le référentiel actuel compte **54 règles** : 20 Bronze, 10 Silver, 21 Gold,
3 Platinum. Le précédent fichier n'en couvrait qu'une partie (Gold partiel,
Platinum absent). Le snapshot JSON documente noms et tiers ; il ne crée pas
un second fichier de statut. Le seul checklist est
`custom_components/freebox_homexa/quality_scale.yaml`, placement conventionnel.

## Résultat : 17 done / 35 todo / 2 exempt

Les 48 anciens `todo` ont tous été relus : **13 démontrés** depuis l’audit initial, **35
restent ouverts** avec réserve précise dans le YAML et ci-dessous. Pas de
transformation administrative pour atteindre un score. Les numéros de lignes
de l'audit initial se réfèrent à la base ; les preuves nouvelles utilisent les
noms de fonctions/tests pour éviter les décalages de lignes.

| Règle démontrée | Preuve locale |
|---|---|
| common-modules | const.py:1-68 centralise domaine, plateformes et constantes ; entity.py:1-225 et availability.py regroupent les bases communes. |
| config-flow | manifest.json:12 config_flow=true ; config_flow.py:180-225 ConfigFlow avec formulaire user. Constat structurel, pas preuve de couverture du flow. |
| runtime-data | router.py:1199 type FreeboxConfigEntry = ConfigEntry[FreeboxRouter] ; __init__.py:220 affecte entry.runtime_data. hass.data conserve les services/cache globaux, pas le routeur. |
| parallel-updates | PARALLEL_UPDATES explicite sur les 11 plateformes : media_player.py:120, button.py:108, remote.py:31, switch.py:42, cover.py:24, camera.py:33, alarm_control_panel.py:38 = 1 ; sensor.py:124, binary_sensor.py:62, calendar.py:24, device_tracker.py:36 = 0. |
| action-setup (nouveau) | six services réellement enregistrés une seule fois dans HA après deux async_setup sans entrée, aucun appel d'action |
| test-before-configure (nouveau) | création après open/probe ; échecs réseau/auth/probe sans création, close public tenté |
| test-before-setup (nouveau) | open/probe avant forward, erreurs temporaires/auth converties ; nettoyage public tenté, limite SDK précisée ci-dessous |
| diagnostics (lot 1) | export chargé/non chargé, valeurs privées synthétiques et clés inconnues absentes, cache borné, timings validés/périmés |
| entity-event-setup (lot 2) | inventaire AST + vraies plateformes HA/dispatcher/CoordinatorEntity, retrait des listeners et timers, isolement deux entrées |
| exception-translations (lot 2) | toutes les 36 levées custom HA/sous-classes traduites, placeholders vérifiés strings/FR/EN, moteur HA français réel |
| async-dependency (lot 2) | SDK asyncio/aiohttp ; SSL/fichiers dans asyncio.to_thread, signature coroutine publique testée et source v1.3.1 vérifiée |
| action-exceptions (lot 5) | 42 frontières AST, 103 tests dédiés HA/SDK/Store, validation/annulation préservées, pas de succès silencieux démontré |
| integration-owner (lot 2) | propriétaires du manifest repris sans ajout de personne dans CODEOWNERS ; cohérence testée, mainteneur XAV59213 actif dans les cinq derniers commits main |

| entity-category (lot 7) | 30 familles/81 variantes revues ; vrai registre conserve IDs/noms/hidden/disabled utilisateur, voir quality-scale-entity-inventory.md |

| has-entity-name (lot 8) | 30 familles/81 variantes inconditionnelles, vrais renommages HA et IDs/préférences conservés |
| entity-disabled-by-default (lot 8) | RSSI neuf opt-in, ancien activé/disabled USER conservé ; politique complète revue |

### Exemptions réexaminées, pas supprimées artificiellement

`docs-conditions` et `docs-triggers` restent **exempt**, pas `done` : aucune
plateforme spécifique condition/trigger/device_condition/device_trigger ni fichier
conditions.yaml/triggers.yaml. `test_specific_trigger_condition_exemptions` vérifie
cet inventaire. Les événements HA ordinaires ne constituent pas une telle plateforme.
Les deux exceptions sont expressément prévues par les documents officiels liés ci-dessus.

## Correctif réellement réalisé

Dans `__init__.py:async_setup_entry`, l'ouverture et le premier `system.get_config`
partagent désormais une garde de nettoyage : **tentative** de fermeture par le SDK sur échec ou
annulation, sans masquer la cause initiale si `close` échoue. Le lot 2 a prouvé
une limite amont : cette tentative ne garantit PAS que le SDK ferme sa session. Timeout,
ClientError, OSError et HttpRequestError deviennent `ConfigEntryNotReady` ; token
invalide/droits insuffisants deviennent `ConfigEntryAuthFailed`, comme le refus
d'autorisation. Un timeout d'autorisation conserve le retry. Plus de journal
warning/error juste avant ces exceptions : HA les signale déjà.

Aucune nouvelle API, aucune commande HA/Player, aucun endpoint `repeater/` modifié.
Le lot 5 ajoute une tentative publique de fermeture possédée par HA après échec
du registre/premier relevé, probe réussi. Le forward partiel des plateformes et
la fermeture SDK ne sont pas rendus transactionnels : aucune garantie universelle de nettoyage.

## Tests réels et mesure, pas simulations présentées comme couverture

Environnement isolé : Python **3.14.9**, Home Assistant **2026.10.4**,
pytest-homeassistant-custom-component **0.13.375**, freebox-api **1.3.1**.
Versions reproductibles : `tests/requirements-ha.txt`. L'environnement ne prétend
pas tester toute version HA ≥2026.8 ; un job minimum supporté reste à établir.
Le plugin HA bloque sockets externes et DNS ; toutes les réponses appareil sont
synthétiques/mocks. Aucun secret/token de production, aucun appareil connecté.

**511 tests passent** (490 au lot 10, +21 au lot 11) : config initiale, réseau/auth, duplicate host, réauth avec
reload de l'entrée existante, options général/groupes, conservation options,
migration LAN, setup/unload succès/refus, erreurs close/annulation, confidentialité,
bornes cache/timings, Entity HA et signaux dispatcher/perte-retour, logs centraux
non répétés, garde de concurrence Home et enregistrement services idempotent.
Ajouts : véritables plateformes sensor/binary_sensor/device_tracker/alarme,
callbacks supprimés et états HA restaurés respectés, deux entrées isolées,
coordinateurs TNT réels et shutdown owning-entry, options profils/TNT/types,
conservation/effacement explicite de codes, messages FR/EN, rappels et contrat SDK.
Les tests SDK/reconfigure de caractérisation documentent une limite, ils ne la corrigent pas.

| Périmètre (38 modules, aucun omit) | Lignes exécutées | Branches | Combiné |
|---|---:|---:|---:|
| Intégration entière | 4582/6132 = **74,72 %** | 1076/2046 = **52,59 %** | **69,19 %** |
| config_flow.py | 437/438 = **99,77 %** | 145/148 = **97,97 %** | **99,32 %** |
| diagnostics.py | **100 %** | **100 %** | **100 %** |
| player_diagnostics.py | **100 %** | **100 %** | **100 %** |
| availability.py | **100 %** | **100 %** | **100 %** |

`test-coverage` et `config-flow-test-coverage` restent **todo**, loin des exigences.
Imports exécutés comptés dans les lignes ; ces chiffres ne signifient donc pas
68 % des fonctionnalités validées. Pas de seuil abaissé pour déclarer un niveau.
CI ajoutée `.github/workflows/ha-tests.yaml` : vrais tests HA + inventaire YAML,
rapports coverage JSON/XML en artefact. Syntax/HACS/hassfest ne prouvent pas la
couverture runtime. Les simulations historiques restent des régressions séparées.

```sh
uv venv --python 3.14 /tmp/homexa-ha-quality
uv pip install --python /tmp/homexa-ha-quality/bin/python -r tests/requirements-ha.txt
PYTHONDONTWRITEBYTECODE=1 /tmp/homexa-ha-quality/bin/python -m pytest -q tests/ha \
  --cov=custom_components.freebox_homexa --cov-branch \
  --cov-report=term --cov-report=json:coverage.json --cov-report=xml:coverage.xml
```

## Lot 11 — une règle entière démontrée, limites restantes isolées

**511 tests HA (+21), 17 done / 35 todo / 2 exempt.**
`log-when-unavailable` est désormais done : vraie panne répétée puis récupération
par source et vraie coordination TNT, pas simple preuve du logger central.
Aucun host/ID/payload dans les nouvelles annonces. Les valeurs manquantes dans
un Wi-Fi valide sont unknown disponibles, plus des erreurs répétées.

Boutons sans MediaPlayer : lecteur refcounté au timer existant, un relevé par
Player, aucune collecte doublée quand média actif ; retrait du provider, préférences
et annulation/fermeture en vol testés. Le minimum « boutons seuls » est levé.
La réserve disponibilité est maintenant **vidéo/contrôle FFmpeg**, pas le même
travail déjà prouvé : une frame échouée ne rend pas les contrôles Home injoignables,
mais un modèle de récupération vidéo reste à définir sans polling coûteux.

Toutes icônes **fixes** de l’inventaire passent dans icons.json ; vrai chargeur HA,
registre/icônes/noms personnalisés testés, snapshot ne change que translation_key.
L’icône Player dépendant de source (YouTube/Netflix), et non state, est conservée ;
transposition dynamique via registre/cache à qualifier, pas suppression pour score.
Le placeholder TNT conserve le nom propre exact. Les autres noms fixes restant
masqués par _attr_name/name Home sont listés précisément ; clés seules ≠ traduction.

Couverture **4582/6132 lignes (74,72 %)**, **1076/2046 branches (52,59 %)**,
combiné **69,19 %**, 39 modules. **17 lignes typing** automatiquement exclues
contre 10 : nouveaux imports TYPE_CHECKING canoniques, aucune exclusion ajoutée.
Mypy **167→162 erreurs**, 23 fichiers/39 modules : contrat web.Request/Response,
chemin StaticPathConfig str, imports canoniques en typage et réexports runtime
anciens HA conservés. Aucun cast/ignore/Any pour masquer des contrats.

Deux suites JS et douze simulations historiques séparées, endpoints repeater/
intacts, version préparée 28.8.90. Provenance SDK vérifiée mais minimum >=1.3.1
conservé selon hassfest : réserve formelle de pin inchangée. Pas de merge/release.

## Lot 10 — contrat SDK vérifié et disponibilité sans faux états

**490 tests HA (+39)** ; **16 done / 36 todo / 2 exempt**. La provenance de
`freebox-api` 1.3.1 est désormais démontrée : GPL, source/tag, wheel PyPI et signature
vérifiée liés au même commit et à la CI de release amont. **La règle reste todo** :
le pin exact demandé par le guide core échoue réellement au hassfest custom, qui
exige >= pour une dépendance partagée avec HA. Minimum original conservé plutôt
que désactiver la validation ou revendiquer un faux done. Le SDK testé reste 1.3.1.
[Preuves reproductibles et hashes](quality-scale-source-contracts.md).

- Disponibilité Remote/Player/boutons, endpoints Home individuels, LAN/Wi-Fi/AP ;
  erreur ne devient ni zéro, ni valeur fraîche, ni allumé fictif. Veille confirmée
  contrôlable par code remote reste off/available, jamais déduite du seul code.
- Regex bridge erronée remplacée par le parseur public du format SDK `nodev` ;
  retest au timer existant, disparition client devient absent sans effacer son ID.
- Température/association Wi-Fi disparues ne gardent pas leur vieille valeur.
  Échec d’une lecture Home ne peut être effacé par la réussite d’un autre endpoint.
- Débit /1000 : vrai Access/Connection SDK et décodage HTTP JSON prouvent l’absence
  de conversion SDK. Valeurs bandwidth_* bit/s distinctes, pas utilisées ici.
- RSSI : Free documente « signal attenuation (in dB) » ; pas une preuve de dBm.
  Conserver l’historique existant, pas de facteur ou changement d’unité inventé.
- Couverture **4506/6053 lignes (74,44 %)**, **1057/2028 branches (52,12 %)**,
  combiné **68,84 %**. Mypy strict **167 erreurs / 24 fichiers / 38 modules**,
  ensemble d’erreurs inchangé ; aucun Any/cast/ignore ajouté pour le score.
- Deux suites JS et douze simulations historiques, séparées du compte HA.
  Endpoints `repeater/`, IDs, options, préférences et données privées préservés.

[Inventaire fini des 36 todo](quality-scale-remaining-work.md) : sept règles ont
encore du travail local indépendant, trois travaux locaux avec réserve de
compatibilité/dépendance, onze décisions de compatibilité/SDK/publication, treize
réserves documentaires formelles et deux critères transversaux de tests/typage.
Les tests ne prouvent aucun succès physique. Ce jalon n’est **pas** la fin du mandat.

## Lot 9 — unités et disponibilité par source, sans faux succès

**451 tests HA (+44)**, deux suites JS, **16 done / 36 todo / 2 exempt**.
Pas de règle entière ajoutée : les pertes partielles restantes empêchent encore
`entity-unavailable`, les sous-types opener empêchent `entity-device-class`.
[Contrats, revue des 30 familles et minimum restant](quality-scale-source-contracts.md).

- Débit : octets/s → kB/s corrigé /1000, pas /8000, source officielle HA lue.
  IDs/unité conservés ; ancien historique non réécrit, prochains relevés corrigés.
- Vrais SDK Storage/Home sur transport mocké : cache indisponible après panne,
  réponses malformées distinctes d’un succès vide, disparition/retour sans migration.
  RAID/Home ne désactivent plus définitivement leur poll sur erreur transitoire.
- XMLTV en cache : UpdateFailed conserve les données mais rend les entités
  indisponibles ; récupération réelle et erreur traduite sans payload brut.
- Uptime/disque/RAID inconnus ne produisent plus de faux zéro/état sain.
- SDK fermé hors unload : panne visible, pas fausse interruption normale.
- Typage réel **186→167 erreurs**, 24 fichiers/38 analysés ; tnt_tmdb strict sans
  erreur avec Programme, datetime, TypedDict et délai public aiohttp inchangé.
- Couverture **4090/5973 lignes (68,47 %)**, **880/1994 branches (44,13 %)**,
  combiné **62,38 %** ; dix lignes typing exclues automatiquement, aucun omit ou
  exclusion personnalisée. Tests = contrats synthétiques, pas matériel validé.
- Douze simulations historiques passent séparément. Le stub obsolète de
  `simulation_clients_filaires_wifi.py` ne fournissait pas les exceptions HA :
  fixture corrigée, aucune modification runtime pour ce harness. Ces simulations
  ne sont pas incluses dans les 451 vrais tests HA ni dans leur couverture.

Le mandat continue : Remote/Player/Wi-Fi, schémas WebSocket sous vrai HA,
annotations SDK, couverture globale et chemins config restants sont encore
traitables. Session SDK publique, rollback refusé, FFmpeg et migrations sensibles
restent explicitement distingués ; aucun merge/release.

## Lot 8 — noms/defaults globaux, source capteurs et vrais contrats typés

**407 tests HA (+30)**, deux suites JS ; **16 done / 36 todo / 2 exempt**.
`has-entity-name` et `entity-disabled-by-default` passent done après la
[revue globale et la politique explicite](quality-scale-entity-inventory.md),
pas par simple changement de compteur.

- Noms relatifs : True inconditionnel sur les 30 familles, features principales
  à None, nom source et unique_id historiques distincts de l’affichage. Le vrai
  HA suit les renommages appareil et respecte name_by_user/nom entité personnalisé.
  Les 81 variantes passent le vrai registre en gardant leurs IDs et choix USER.
  La génération standard HA peut nommer différemment une **nouvelle** entité ;
  aucun entity_id enregistré n’est régénéré et aucune donnée n’est migrée.
- RSSI individuel bruyant : off pour nouvelle création seulement. Ancien activé
  reste activé ; disabled USER reste USER. Trackers/tamper/contrôles avancés opt-in
  préservés ; données principales des cartes non désactivées pour le score.
- Source capteurs : HttpRequestError ne laisse plus d’anciens états disponibles
  quand LAN fonctionne encore. Flag par source, signal HA, logs uniques sans
  payload privé et récupération démontrés. Débit absent/invalide = unknown,
  zéro numérique réel conservé. Disponibilité globale reste todo pour les autres sources.
- Perte/fermeture/retour du routeur sur les 81 variantes ; tracker suit maintenant
  l’indisponibilité au lieu d’une fausse présence/absence déduite d’un cache.
  TNT est indépendant de Freebox OS ; inversion est une action locale.
- Unload normal refusé/échoué/annulé : admission rétablie **sauf** si un autre owner
  ferme déjà le SDK ou s’il a fini. Course déterministe Events, pas de sleep.
  Le rollback de setup refusé/exception est caractérisé sous vrai manager :
  des plateformes restent, pas de faux rollback atomique ni destruction forcée.
- FFmpeg hérité : vraie méthode snapshot/source/proxy appelée, sous-processus et
  transport entièrement mockés. Close après erreur lecteur/proxy et annulation
  prouvé ; open est avant try/finally dans HA amont. Un échec open ne prouve pas
  une fuite réelle du sous-processus (cleanup interne non qualifié), ni sa fermeture.
- XMLTV : vrai HTTP public mocké, parser réel avec UTF-8 traversant 64 Kio,
  filtrage/tri/programmes incomplets, slots et jour de diffusion nocturne testés.
  Aucun titre/affiche inventé, aucune nouvelle lecture réseau privée.
- Mypy strict **227→186 erreurs**, 25 fichiers/38 analysés. tnt_coordinator sans
  erreur, contrats Programme/metadata/datetime/parser/retours explicites ;
  DeviceInfo et IDs validés, base disponibilité vraie Entity. Pas Any/cast/ignore
  ajouté pour score. Conflit de type FFmpeg name et appels SDK non annotés restent visibles.

Couverture entière : **3997/5936 lignes (67,33 %)**, **841/1980 branches
(42,47 %)**, combiné 61,12 %. Huit lignes purement typing sont automatiquement
exclues par coverage.py (TYPE_CHECKING/overloads) ; aucune configuration d’exclusion
ni omit ajouté. Ce n’est pas 67 % des fonctionnalités vérifiées sur matériel.

### Applicabilité documentaire et exemptions revérifiées

Les pages officielles relues `docs-actions`, `docs-high-level-description`,
`docs-installation-instructions`, `docs-removal-instructions` demandent
**explicitement une page/revue sur home-assistant.io**. Le contenu local cité et
testé est disponible : la réserve indiquée est formelle, pas une promesse de
certification ni une invitation à inventer des sections vides. La matrice distingue
cette réserve du travail de code encore possible. Aucune publication HA core faite.

Les deux pages docs-conditions/docs-triggers autorisent expressément exemption
quand aucune condition/déclencheur spécifique n’est fourni. Inventaire réellement
testé inchangé ; événements/états standard ne créent pas une telle plateforme.
Le constructeur public SDK v1.3.1 a aussi été relu en direct : toujours sans
session injectable, close sans finally ; test signature/source amont restent preuves,
aucune méthode supposée à partir d’un résumé de moteur de recherche.

## Lot 7 — ordre indépendant, lectures entités drainées, catégories revues

**377 tests HA (+21)** et deux suites JS. **14 done / 38 todo / 2 exempt** :
seule `entity-category` passe done, après [revue globale](quality-scale-entity-inventory.md)
des 30 familles/81 variantes et préservation réelle des préférences registre.
L’inventaire ne valide pas par association naming, classes, defaults ni disponibilité.

- Inversion cover : lookup public par unique_id existant au moment de l’usage,
  pas au constructeur. Ordres switch/cover, renommage et suppression testés ;
  plus de dépendance au timing du forward. IDs et fichier d’inversion inchangés.
- Lectures SDK des entités Player/remote/Wi-Fi/Home/calendrier : ownership routeur,
  rejet de nouvelles lectures pendant close, annulation/attente avant SDK.close.
  Six cas bloqués via la vraie API de tâche d’entrée HA prouvent finally **et fin
  de tâche avant close**, sans sleep ni inspection de collections privées HA.
- Limites lifecycle : snapshot/stream FFmpeg hérité non démontré par ce lot,
  refus/erreurs de rollback et close SDK amont restent des limites. Pas de garantie
  universelle, ni d’accès aux sessions privées du SDK.
- Typage : 230→**227 erreurs dans 27 fichiers**, 38 analysés ; TypedDict précis
  des observations diagnostics filtrées et signatures génériques explicites,
  sans cast, ignore global ni seuil abaissé. Strict-typing reste todo.
- Régressions : deux suites JS ; aucune commande appareil/réseau de production.
  Les anciens lots ci-dessous sont l’historique, pas les mesures courantes.

## Lot 6 — discovery réel, rollback, lectures en vol et confirmations de stockage

**+14 tests, 356 au total**, sans nouveau `done` administratif : **13/39/2**.
Le minimum restant de chaque règle demeure dans la matrice ; les 39 todo ne sont
pas présentés comme tous bloqués. Ce lot ferme des défauts réels, pas seulement
un manque de quantité de tests.

- `test_full_forward.py` utilise le **vrai ConfigEntriesManager**, le vrai forward
  et les fonctions discovery des **11 plateformes** ; snapshots routeur semés et
  lectures initiales mockées. Le coordinateur TNT est réel, seul son fetch est mocké.
  Registre, ownership, états activés et retrait réels. Pas de snapshot/stream caméra
  ni commande appareil. Les entités désactivées sont distinguées des états actifs.
- Ce chemin a révélé une **fuite du listener discovery caméra** : stocké dans une
  liste routeur jamais consommée, il survivait à l’unload. Il appartient maintenant
  à `entry.async_on_unload`, sans changer les entités/IDs.
- Échec après forward partiel ou complet : le callback d’entrée tente maintenant
  le **rollback public des plateformes**, retire le coordinateur de sa map puis
  ferme le routeur. Le cas de refus/exception de rollback reste signalé, pas masqué
  comme garantie de succès ; l’erreur initiale de setup reste prioritaire.
- Les **deux callbacks d’intervalle réellement enregistrés** sont exercés avec
  lecture bloquée : tâches possédées par routeur, annulation et attente avant close.
  Fermetures concurrentes sérialisées ; succès SDK mémorisé, échec encore retentable
  explicitement. `NotOpen` conserve la suppression historique mais **n’est pas une
  preuve de fermeture mémorisée**. Aucun accès session privée ni changement SDK.
- **Reste lifecycle compatible** : lectures d’entités en vol, distinctes des deux
  intervalles routeur ; variantes/refus/exception de rollback. HA 2026.10.4 crée ses
  jobs de polling EntityPlatform via `ConfigEntry.async_create_background_task`,
  et les annule dans le traitement final des callbacks, après retour de l’unload.
  Il ne faut pas déduire leur drain préalable du seul test des intervalles routeur.
  Fermeture SDK sans finally/injection publique reste un blocage indépendant.
- **Store partagé** : échec d’écriture absorbé par HA détecté par relecture publique.
  Cache vérifié avant reboot/reload et avant teardown ; tests vrai Store sur seam
  d’écriture HA, aucune commande physique. Pas de redémarrage envoyé si ce contrôle
  initial échoue. Cela ne rend pas plusieurs effets réseau atomiques.
- Le contrôle public vérifie la valeur relue, pas fsync ni chaque appel d’écriture :
  si le disque contenait déjà la même valeur, il ne distingue pas un write identique
  échoué (HA peut le journaliser) d’une valeur déjà correcte. Pas de garantie durable
  universelle revendiquée.
- **Rappels ambigus** : tests où l’écriture réussit mais la vérification de lecture
  échoue. L’action reste en erreur ; aucun faux statut « programmé/non programmé »
  si stockage et timer divergent. L’utilisateur peut programmer/annuler explicitement
  après correction ; aucun retry/notification automatique ajouté. Deux programmations
  du même ID remplacent le timer (ancien annulé), pas de double callback.
- Restauration : verrou commun, champs non concernés conservés, contrôle public de
  la purge ; minuteurs futurs déjà restaurés conservés si purge non confirmée. Log
  sans données de rappel et sans affirmer à tort qu’ils sont tous perdus.
- **Frontend TNT** : le catch silencieux de lecture du statut est remplacé par un
  message visible ; pas de faux succès de programmation/annulation. Promesse d’une
  autre modale ignorée. Deux suites JS indépendantes exécutées en CI, aucun appel HA.
- **Typage mesuré** : [baseline détaillée](quality-scale-typing-baseline.md), 268 puis
  230 erreurs strictes sur 38 fichiers ; décorateur renvoie désormais `Coroutine`
  comme les méthodes HA qu’il enveloppe. Le SDK **possède `py.typed`** ; ne pas
  confondre ses annotations partielles avec son absence de session injectable.
- Suite complète avec `-W error::RuntimeWarning`, sans coroutine non attendue ni
  timer/tâche résiduel toléré artificiellement. Aucune migration, option/polling
  supprimé, modification `repeater/`, donnée privée ou commande réelle.

## Lot 5 — erreurs d’actions et lifecycle simultané

- **+108 tests** ; `action-exceptions` passe seul de todo à done, après inventaire
  des **42 frontières explicites** dans 11 modules (toutes les familles d’actions
  entités, six services, lecture calendrier et reboot routeur). Les erreurs de
  validation HA restent distinctes et les annulations ne sont pas transformées.
- Les erreurs SDK/Home/Wi-Fi/boutons/remote/media_player sont remontées en erreur
  traduite ; l’état optimiste ne change pas après échec. Les Home actions ne
  journalisent plus l’erreur juste avant de la lever. Contrat média existant et
  fallback firmware conservés, pas de nouvel endpoint.
- **Vrai SDK Remote v1.3.1**, transport public mocké : `False` peut signifier timeout,
  déconnexion, non-200 **ou HTTP 200 avec corps non vide**. La touche peut donc
  avoir été exécutée. Message distinct « commande non confirmée », jamais de retry
  automatique ajouté ; macros potentiellement partielles, pas atomiques.
- **Vrai Store HA** : `async_save` absorbe WriteError et retourne normalement.
  Les rappels passent par un verrou, copie des données et relecture publique après
  écriture ; en échec observé, pas de nouveau timer ni suppression du timer existant.
  Les champs de stockage non concernés sont conservés. Ce contrôle n’est ni une
  transaction durable, ni une garantie contre coupure de courant/erreur de lecture.
  Test du vrai chemin WriteError (seule écriture bas niveau HA simulée), puis reprise,
  deux sauvegardes concurrentes et lecture status pendant écriture en cours.
- **Vrai ConfigEntriesManager HA** : registre/relevé initial défaillant après probe,
  fermeture publique tentée par callback d’entrée, y compris si close échoue (4 cas).
  Échec de cleanup ne remplace pas l’erreur initiale ; aucune session privée accédée.
- **11 EntityPlatforms simultanées + TNT**, registre/ownership HA réels : retrait des
  états, listeners dispatcher/coordinateur et watcher alarme, fermeture routeur.
  Le dispatcher forward/unload est substitué par ces plateformes explicites ; ce
  n’est pas encore un test du discovery/setup complet et rollback de forward partiel.
- Calendrier : une lecture en erreur n’est plus un agenda vide prétendument réussi ;
  polling marque l’entité indisponible et efface l’événement périmé jusqu’à récupération.
- Aucune identité migrée, code remote/token perdu, commande appareil réelle,
  modification `repeater/`, merge ou release.

## Lot 4 — camera/cover/switch et minimum de validation par règle

[Matrice complète des 54 règles](quality-scale-proof-matrix.md) : pour chaque règle,
preuve acquise et minimum restant, en distinguant travail local compatible, réserve
formelle documentaire, migration sensible et limite SDK. Les **39 todo** ne sont
pas tous bloqués. **13 done / 39 todo / 2 exempt** reste le compte exact.

### Changements vérifiés, pas seulement inventaires

- Vraies EntityPlatform camera/cover/switch : ajout, état HA, perte/retour et retrait
  des listeners Home ; inversion locale utilisable sans réseau, mais indisponible
  sur erreur de lecture de son fichier. Ajout/retrait des trois familles de boutons
  sans commande automatique. Au moins un représentant des **11 domaines** a donc
  maintenant un vrai test de plateforme, sans prétendre un lifecycle complet simultané.
- **Volet inversé** : position inconnue ne provoque plus `100 - None`, ni faux état
  ouvert. La position optimiste est stockée dans le même repère brut que l’API,
  évitant une deuxième inversion. Une valeur disparue ne réutilise pas l’ancienne.
  Inversion configurée mais inconnue : pas d’envoi d’une position ambiguë.
- **Erreurs d’action Home** : nouveaux appels cover/camera exigent succès du helper
  booléen avant état optimiste ; échec/commande absente lève `command_failed` traduit
  sans détail privé. Le contrat historique du helper pour les autres appelants est
  conservé. Tests traversent aussi le **vrai adaptateur freebox-api Home 1.3.1**,
  avec transport synthétique, mêmes endpoints et payloads `{value: ...}`.
  Un retour SDK sans exception n’est pas une preuve de mouvement physique.
- **Caméra** : son nouveau node remplace bien le cache pour disponibilité après
  signal ; disparition répétée puis retour garde l’ID. Correction des chemins
  d’erreur référant un attribut `_node_id` inexistant. Aucun flux, image ni réseau
  de caméra de production utilisé ; manager FFmpeg synthétique pour ces tests.
- **Wi-Fi** : réponse absente/invalide/échouée → indisponible/inconnu, pas faux ON
  ni ancienne mesure ; retour booléen valide rétablit disponibilité.
- **Configuration** : vrais flows options répéteurs sur registre synthétique
  (aucune modification API repeater/), conflit Alexa et récupération, libellés
  identiques/override absent, codes/clé TMDB synthétiques préservés. Les erreurs
  initiales testées sont maintenant suivies de la correction de la cause et de la
  finalisation du **même flow**, unique_id vérifié à chaque création concernée.
  Port seul caractérisé sans changer l’identité ; absence de probe reste un défaut.
- **Dépendances de test** : PyTurboJPEG 1.8.3, version exacte du manifest camera HA,
  pour importer la vraie classe caméra sans stub. La présence de la bibliothèque
  native améliore les snapshots ; ni transcodage/snapshot ni qualité vidéo validés.

### Mesures et réserves précises

| Module | Lignes | Branches | Combiné |
|---|---:|---:|---:|
| camera.py | 56/79 = 70,89 % | 4/12 = 33,33 % | 65,93 % |
| cover.py | 117/162 = 72,22 % | 19/42 = 45,24 % | 66,67 % |
| switch.py | 93/107 = 86,92 % | 5/12 = 41,67 % | 82,35 % |

`config-flow-test-coverage` reste todo : ligne 369 et trois branches non couvertes
(notamment garde user/reauth et collision reconfigure). Pas de pragma omit ni appel
artificiel pour masquer ces chemins ; ils demandent une analyse du graphe HA et
des anciennes entrées. Les tests de récupération ne sont pas remplacés par le score.
La règle officielle `appropriate-polling` a été relue : elle exclut un intervalle
choisi dans le flow ; `home_poll_interval` existe encore. Le supprimer silencieusement
ne serait pas une amélioration compatible : dépréciation/proposition nécessaire.
Les docs locales ne deviennent pas absentes du seul fait de l’absence de revue
home-assistant.io. La matrice distingue exactement ces deux dimensions.
Aucun niveau officiel, merge, release, commande appareil, migration d’ID ou nettoyage
irréversible des appareils persistants. Version préparée conservée **28.8.90**.

## Lot 3 — état Player et nouvelles plateformes réelles (jalon historique)

- **Télécommande** : reproduit `standby → on` causé par la vérité d'un dictionnaire
  non vide. Les états running/on et standby/stopped/off sont maintenant distingués ;
  un état inconnu reste inconnu. Aucun ordre envoyé pour tester ce correctif.
- **Player** : si toutes les versions de statut échouent, une ancienne découverte
  `reachable=true` ne suffit plus à présenter la lecture périmée comme disponible.
  Le retour du statut rétablit la disponibilité sans changer l'identité.
- **Volume/muet** : les valeurs absentes ne réutilisent plus la dernière mesure.
  Les booléens, chaînes et nombres non finis ne deviennent pas un faux volume ;
  seul un booléen ou entier 0/1 représente le muet. Aucune commande automatique.
- **Calendrier** : ajout/retrait dans une vraie EntityPlatform HA, lecture/erreur/retour
  SDK mockés, dates secondes/millisecondes et programmes incomplets. Les dates
  débordantes sont ignorées au lieu d'interrompre l'ensemble de la collecte.
- **Inventaire** : les 41 variantes de boutons ont des tests de constructeurs réels
  (identités historiques, catégories/classes, clés de traduction, activation par défaut).
  Cela ne prouve pas l'exécution correcte des 41 actions, qui n'est pas revendiquée.
- **Preuves** : `tests/ha/test_player_platforms.py` et `test_calendar_platform.py`.
  69 cas supplémentaires ; les tests de boutons sont explicitement un inventaire,
  pas 41 tests de commandes réseau ou de plateformes complètes.

Les comptes restent **13 done / 39 todo / 2 exempt**. Les sous-cas supplémentaires
ne suffisent pas à prouver une règle globale pour toutes les plateformes.
`entity-unavailable` reste notamment à démontrer pour les autres familles.
Au jalon 3, camera/cover/switch n'avaient pas encore de couverture runtime ;
le lot 4 ci-dessus apporte ces preuves et les flows rares, sans achever les règles globales. Ce sont des travaux indépendants encore
traitables, pas des blocages architecturaux ni une déclaration de fin d'audit.
La réserve SDK, les migrations d'identité et les limites de validation matérielle
restent inchangées ; aucune session privée, API repeater ou identité n'est modifiée.

## Lot 2 — améliorations indépendantes réellement réalisées

- **Guide utilisateur complet local** : [installation, options, six actions et tous les champs,
  données/fréquences, cas d'usage, dépannage, limites et suppression](guide-utilisateur.md).
  Les treize critères documentaires correspondants ont maintenant une preuve locale
  détaillée mais restent `todo` formellement : ils visent la documentation/revue
  home-assistant.io. La matrice physique/firmware n'est pas inventée.
- **Propriétaire actif** : `.github/CODEOWNERS` reprend exactement les trois noms
  déjà déclarés au manifest, sur le seul composant. Un test vérifie la correspondance ;
  cinq derniers commits main par XAV59213 confirment au moins un mainteneur actif.
  Pas de demande de review envoyée par cette tâche ni de nomination core revendiquée.
- **Métadonnées services FR/EN** : expose les champs `config_entry_id`/`device_id`
  déjà gérés, sans changer le routage ; tous les champs et messages sont testés.
- **Options sans perte de données** : une liste Player vide/incomplète ou en erreur
  effaçait les codes des Players absents à la validation Général. Reproduit sous HA,
  corrigé : seuls les champs visibles peuvent effacer leur code explicitement.
  Les codes non présentés et les autres pages sont conservés. Pas de migration.
- **RAID absent puis revenu** : un deuxième cycle après disparition levait TypeError
  (`self._raid` était None). Reproduit, corrigé par conservation de l'ID de lookup ;
  unique_id et données restent inchangés même si le RAID réapparaît renommé.
- **Listeners/timers** : Home respecte les hooks coopératifs `super`, armement
  répété remplace le watcher au lieu d'en perdre un, retrait annule le dernier.
  Le coordinateur TNT reçoit l'entrée explicitement : plus de dépendance implicite
  au ContextVar, shutdown lié au bon propriétaire et testé à deux entrées.
- **Rappels sans fuseau** : ils provoquaient TypeError naïf/aware ; désormais erreur
  utilisateur traduite avant toute sauvegarde. Une date à fuseau valide est stockée
  et consultée/annulée dans les mocks sans déclencher de notification.
- **Erreurs traduites** : UpdateFailed XMLTV utilisait un message dur ; il utilise
  maintenant clé et placeholders FR/EN, testé sur le vrai coordinateur. Les actions
  Player/Home sont désormais couverts par `action-exceptions: done` (lot 5). Les autres règles globales ne sont pas validées par ce changement.
- **Noms/IDs non migrés** : les tests réels confirment les capteurs centraux distincts
  entre deux Servers. Attention, HA ScannerEntity définit son propre unique_id MAC :
  `_attr_unique_id` préfixé dans FreeboxDevice n'est pas celui réellement utilisé.
  Documenté, sans changement pouvant casser des entrées existantes. Les conventions
  has_entity_name et les identifiants d'appareils restent à inventorier complètement.

### Contrat SDK : correction importante d'une affirmation du premier jalon

Source officielle vérifiée :
[Freepybox v1.3.1](https://github.com/hacf-fr/freebox-api/blob/v1.3.1/src/freebox_api/aiofreepybox.py#L69-L168).
Le fichier installé et le raw de ce tag ont le même SHA-256 :
`bd24ab625b1d6768a8382c214bd6671baabd21690404dc508c49925fc43ba1bf`.
L'audit de l'async inclut [Access](https://github.com/hacf-fr/freebox-api/blob/v1.3.1/src/freebox_api/access.py).

Le constructeur n'accepte pas de session publique. `open` crée sa session puis
attend l'auth ; si cette attente échoue avant l'affectation `_access`, `close`
peut lever AttributeError avant `session.close`. Le test utilise **le vrai SDK**
et des transports synthétiques, sans jeton ni réseau. En outre, logout précède
close sans finally : une erreur de logout peut aussi empêcher la fermeture.
**La protection Homexa appelle close et préserve l'erreur ; elle ne peut pas
promettre une fermeture garantie avec cette API publique.** Le premier rapport
était trop affirmatif ; ses textes ont été corrigés plutôt que cacher la limite.

Provenance partielle connue au lot 9 : licence GPL-3.0 du tag, commit
`96322885f37df37e6f491ab889b27cf912cc293a` et
[workflow de publication](https://github.com/hacf-fr/freebox-api/blob/v1.3.1/.github/workflows/release.yml)
vérifiés. Les runs verts trouvés sur ce commit correspondent à Tests/CodeQL,
pas une preuve d'exécution du publish PyPI. La dépendance était `>=1.3.1`,
pas épinglée exactement au lot 9. **Provenance établie au lot 10** : attestation cryptographique du wheel vérifiée. Le pin exact a été refusé par hassfest custom (dépendance partagée) puis minimum initial rétabli ; règle formelle toujours todo avec raison précise. Ce paragraphe conserve la chronologie, pas l’état courant.

Proposition amont (non appliquée, personne contactée) : `close` doit fermer en
finally même sans authentification complète, et une future injection de session
publique doit préciser qui possède/ferme la session. Attendre une version publique
corrigée et réexécuter ces contrats avant changement de dépendance ; pas de lecture
ou monkeypatch de `_session` dans le runtime pour cocher une règle.

## Plan initial historique et frontières de sécurité

Ce plan des premiers lots est conservé pour traçabilité ; certains points (noms,
exceptions) sont désormais done. Pour le restant courant exhaustif, suivre
[les 36 critères](quality-scale-remaining-work.md), pas répéter ces travaux.

1. **Identité/flows** : réauth testé, mais unique ID = host et jetons nommés par host.
   Reconfigure refuse un nouveau host via `_abort_if_unique_id_mismatch` et ne
   teste pas la connexion avant sauvegarde du port. Corriger correctement exige
   une stratégie de migration de l'identité physique (MAC/équivalent) et du jeton,
   doublons hostname/IP, compatibilité entrées existantes et retour arrière.
   Ne pas modifier silencieusement les IDs/entités pour cocher ces règles.
2. **Cycle de vie/plateformes** : tests réels de toutes plateformes ajoutées,
   reload multi-entrées, rappels/timers en vol, échecs après le premier probe,
   inventaire unique IDs/associations, disponibilité spécifique par source,
   découverte runtime et nettoyage sans toucher appareils d'autres intégrations.
3. **Erreurs/noms/traductions/repairs** : Player absorbe encore certains échecs ;
   inventaire des actions avant exceptions traduites. Noms historiques et
   has_entity_name=False nécessitent compatibilité des dashboards. Repairs à
   définir par problème réellement actionnable, pas créer des alertes artificielles.
4. **SDK/typage** : Freepybox 1.3.1 n'expose pas de paramètre public session au
   constructeur ; open crée ClientSession et close la ferme. Injection nécessite
   évolution amont du SDK, pas monkeypatch interne. GPL-3.0/tag/client source vérifiés, mais publication effective par CI et pin exact non démontrés. Audit I/O tokens et typage strict complet requis.
5. **Documentation/évaluation officielle** : README/exemples custom utiles mais
   ne remplacent pas la documentation home-assistant.io formellement visée. Les logos locaux/HACS ne prouvent pas brands ; la propriété locale est maintenant démontrée, sans nomination core.
   Aucun dépôt/acceptation core effectué au nom de l'utilisateur.

Les huit nouveaux done n'annulent pas ces réserves. Les 40 restants sont tous
listés dans le tableau suivant ; celui-ci reprend le YAML, il n'est pas un second score.

| Règle encore todo | Preuve manquante / prochain travail |
|---|---|
| appropriate-polling | Règle officielle relue le 2026-11-07 : intervalle choisi par le développeur, pas de champ config flow. Le champ home_poll_interval existe encore ; ne pas le supprimer pour le score au risque de changer les réglages existants. Documenter une dépréciation compatible et vérifier les fréquences/doublons de toutes les plateformes avant done. |
| brands | Règle officielle vérifiée : assets dans home-assistant/brands sous le domaine. Lecture GitHub de core_integrations/freebox_homexa le 2026-11-07 -> 404 ; logos locaux YouTube/Netflix ne sont pas le branding de cette intégration. Aucun ajout/PR amont ni création de logo effectué. Reste todo ; HACS accepté ne vaut pas branding validé. |
| config-flow-test-coverage | 407 tests HA au total ; config_flow.py : 437/438 lignes (99,77 %), 145/148 branches (97,97 %). Les erreurs de link testées sont suivies de la correction de leur cause et de la finalisation du même flow avec unique_id vérifié. Options répéteurs (registre uniquement), conflits Alexa, doublons de libellés, defaults privés synthétiques et conservation des codes vérifiés. Reste ligne 369 et trois branches ; guard reauth/user à justifier, sans forcer un chemin artificiel. 100 % non atteint, donc todo. |
| dependency-transparency | Source GPL-3.0 tag v1.3.1 commit 96322885f37df37e6f491ab889b27cf912cc293a ; wheel PyPI SHA256 fb438c44d08293d7ca1a3d9ad55334a3e2905bdda270332345b7e30a1afbfa87, gh attestation verify réussi contre hacf-fr/freebox-api. Provenance signée liée au même commit et au run public release.yml 23742463862 réussi : transparence démontrée pour le SDK testé 1.3.1. Réserve formelle précise : règle core demande pin exact mais hassfest custom refuse ce pin pour dépendance partagée avec HA (run 42400842458). Minimum freebox-api>=1.3.1 conservé, pas validation désactivée ni exemption artificielle ; nouvelles versions à réauditer. Détails et hashes dans docs/quality-scale-source-contracts.md. |
| docs-actions | docs/guide-utilisateur.md (lié README) : Les six actions et tous leurs champs, ciblage multi-entrées et réponse scheduled_minutes sont documentés ; inventaire metadata/strings/FR/EN et YAML exemples testé. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-high-level-description | docs/guide-utilisateur.md (lié README) : Description Server/Player, usage réseau/Home/guide et lien officiel Free dans le guide. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-installation-instructions | docs/guide-utilisateur.md (lié README) : Installation HACS/manuelle, redémarrage et appairage pas à pas, prérequis locaux et confidentialité dans le guide. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-removal-instructions | docs/guide-utilisateur.md (lié README) : Suppression entrée/ressources/HACS et limites de conservation jetons, rappels et sauvegardes explicitement documentées. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| entity-unique-id | IDs historiques conservés ; plateformes multientrées, retour/disparition et variantes boutons testés. La stabilité RAID au renommage n’est prouvée que dans la même instance, pas au rechargement (constructeur utilise le nom). ScannerEntity fournit MAC client. Audit collisions/partitions et proposition de migration réversible restent nécessaires ; aucune migration imposée. |
| has-entity-name | Lot 8 : has_entity_name=True inconditionnel pour les 30 familles/81 variantes. Noms relatifs et features principales Home/Player à None ; noms sources conservés séparément des noms affichés. test_entity_naming_defaults : vrai HA, renommage appareil, name_by_user et nom personnalisé entité préservés ; inputs unique_id historiques vérifiés. test_category_registry : les 81 variantes passent le vrai EntityPlatform en conservant entity_id, unique_id, nom et hidden/disabled USER. Nouveaux entity_id générés normalement par HA ; aucune régénération des IDs existants. Revue dans docs/quality-scale-entity-inventory.md. |
| unique-config-entry | config_flow.py:222 unique ID basé sur host ; hostname/IP/URL du même Server peuvent différer. Test de déduplication identité physique manquant. |
| action-exceptions | errors.py:async_action_errors garde les 42 frontières explicites inventoriées par AST sur 11 modules (actions entités, six services, lecture calendrier et reboot routeur). Validation HA et annulation préservées ; erreurs SDK/données traduites sans payload, état optimiste non changé en échec. tests/ha/test_action_errors.py : 103 cas vrai HA, succès/échec/récupération des familles, appels services réels, contrats SDK Remote et Store publics. False du SDK remote = commande non confirmée (elle peut avoir été exécutée), erreur distincte sans retry automatique. Écriture rappel relue via API publique et sérialisée ; annulation ne supprime pas le timer si persistance échoue. Tests camera/cover/local inversion du lot 4 conservés ; aucune preuve de réussite physique revendiquée. Lot 6 : mêmes contrôles de persistance réelle sur cache partagé avant reboot/reload/unload ; échec Store détecté avant commande/teardown. Rappels : écriture réussie mais relecture échouée reste erreur utilisateur ; status refuse désaccord stockage/minuteur. Remplacement annule ancien minuteur, restauration préserve champs non concernés. Erreur de status visible dans la carte (plus de catch silencieux), tests JS sans appel HA. |
| config-entry-unloading | Lots 6-8 : vrai ConfigEntriesManager/discovery/forward des onze domaines et rollback partiel/complet ; six lectures SDK entités et deux intervalles drainés avant close, fermeture sérialisée. Refus/exception de rollback désormais caractérisés : des plateformes HA peuvent rester après erreur du setup, pas de faux rollback atomique ; nettoyage réel explicite du test. Unload normal refusé/échoué/annulé restaure admission des lectures sauf si un autre propriétaire ferme déjà le SDK ou si close est terminé, courses testées par Events. FFmpeg hérité testé sans processus/réseau : snapshot, source, fermeture après erreur lecteur/proxy/annulation ; ouverture en dehors du try/finally amont, fermeture sur échec d'ouverture non garantie. Limite SDK close/session publique inchangée. Pas garantie universelle donc todo. |
| docs-configuration-parameters | docs/guide-utilisateur.md (lié README) : Table des options général/groupes/types/répéteurs/TNT/profils, valeurs, défauts, effets et données privées ; conservation des codes Player absents testée. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-installation-parameters | docs/guide-utilisateur.md (lié README) : Table host/port initiaux, Server plutôt que Player et appairage physique ; limite host/identité expliquée. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| entity-unavailable | Lot 11 : boutons seuls sans MediaPlayer maintenant couverts par lecteur partagé au timer central existant ; refcount, absence de collecte doublée quand média actif, relais après retrait et annulation SDK en vol prouvés sous vrai HA. Veille connue/code et inconnu initial préservés. Wi-Fi valide sans enabled devient unknown disponible, pas panne. Autres sources inventoriées testées. Réserve restante précise : erreur/None de frame FFmpeg laisse caméra disponible via statut/contrôles Home valides ; pas de frame périmée renvoyée, mais pas modèle global séparant disponibilité vidéo et contrôle. Définir récupération vidéo sans lancer un nouveau polling FFmpeg coûteux ; ne pas déclarer règle entière done sur seul contrôle Home. |
| log-when-unavailable | Lot 11 : router.note_source mémorise transitions par source, INFO perte puis retour une seule fois ; labels fixes sans host/ID/payload. Tests vrais HA/SDK test_source_ownership_logs : trois échecs successifs et récupération Root/LAN, Wi-Fi config/BSS/AP/stations/interrupteur, Home/endpoints/nœuds/caméra, Remote/Player, capteurs/disques/RAID ; aucun secret synthétique dans logs. TNT utilise réellement DataUpdateCoordinator/UpdateFailed, une perte puis récupération testée. Canal image FFmpeg public conserve exception/None sans retry et annonce ses transitions. Pas de prétention de succès physique ni de nettoyage SDK garanti. |
| reauthentication-flow | tests/ha/test_config_flow.py prouve reauth_successful et reload unique de la même entrée sans doublon. Le serveur physique peut toutefois changer derrière le même host ; absence de contrôle MAC/identité avant réauth. Lié au choix de migration unique ID host vers identité physique, non imposé ici. |
| test-coverage | 511 tests HA 2026.10.4 (+21 au lot 11), 39 modules sans omit : 4582/6132 lignes (74,72 %), 1076/2046 branches (52,59 %), combiné 69,19 %. Deux suites JS et douze simulations historiques séparées. Deux passages locaux et artefact CI comparés en entier (lignes/branches exécutées par module). Seuil officiel non atteint. 17 lignes de typage exclues automatiquement par coverage.py (10 au lot 10), aucune exclusion personnalisée ; imports TYPE_CHECKING canoniques explicités, pas optimisation artificielle du périmètre. Aucune validation matérielle. |
| devices | media_player.py:90-103 et tnt_sensor.py:14-29 DeviceInfo ; cohérence des associations/subdevices et de toutes plateformes non vérifiée sur plusieurs modèles. |
| discovery | tests/ha/test_config_flow.py teste le flow zeroconf réel : préremplissage api_domain/https_port, formulaire utilisateur et rejet du même host configuré. L’identité physique, alias d’adresse et découverte de tous modèles restent non démontrés ; pas un passage en done sur seul préremplissage. |
| discovery-update-info | config_flow.py:390-405 découvre le host ; aucun test prouvant mise à jour sûre des entrées existantes après changement adresse. |
| docs-data-update | docs/guide-utilisateur.md (lié README) : Table code réel : timer central 40 s, Home 15 s/choix, TNT 5 min/fetch >=60 min, polling plateformes et watcher alarme 1 s avec réserve de charge. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-examples | docs/guide-utilisateur.md (lié README) : Liens exemples Lovelace et exemple get_reminder_status avec réponse ; syntaxe YAML vérifiée sans exécution. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-known-limitations | docs/guide-utilisateur.md (lié README) : POP sans API/id, absence métadonnées apps, logos pas miniatures, RTS, portée des diagnostics, rappels globaux/profils homonymes et SDK cleanup explicités. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-supported-devices | docs/guide-utilisateur.md (lié README) : Matrice par capacité et preuves : fixture Devialet, POP fbx8am non exploitable par cette API, Server/Home selon endpoints ; pas de matrice exhaustive physique/firmware inventée. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-supported-functions | docs/guide-utilisateur.md (lié README) : Fonctions par catégorie/capacité et distinctions guide vs statut de lecture ; limites de validation matérielle explicites. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-troubleshooting | docs/guide-utilisateur.md (lié README) : Table symptômes/tests minimaux/remarques, pas de publication secrets ni exposition Internet/ADB ; test demandé sans promesse POP. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-use-cases | docs/guide-utilisateur.md (lié README) : Cas guide vs Player, disponibilité Home/retour réseau, lecture préalable des rappels et adaptation entity_id ; aucun exemple exécuté. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| dynamic-devices | Code de découverte LAN/Home/répéteurs présent ; découverte runtime après setup et couverture de tous périphériques sans reload non démontrées. |
| entity-category | Revue sémantique globale des 30 familles et 81 variantes : docs/quality-scale-entity-inventory.md. Snapshot des constructeurs réels dans test_entity_inventory ; test_category_registry prouve la conservation des IDs, noms et choix utilisateur avec le vrai EntityPlatform HA. Classements diagnostic/config corrigés sans changer les activations ni les commandes. |
| entity-device-class | Revue 30 familles/81 variantes, docs/quality-scale-source-contracts.md. rate_* natif byte/s vérifié documentation Free indexée, source HA, SDK Access+Connection réel décodant une réponse HTTP JSON : /1000 en kB/s ; bandwidth_* bit/s distinct et non utilisé. IDs/unité/historique conservés. Pourcentage disque invalide, uptime absent et RAID absent deviennent unknown. Opener garage déduit du libellé non prouvé ; documentation Wi-Fi dit signal attenuation in dB, pas preuve dBm pour toutes sources. Ne pas changer silencieusement classe/unité/historique ; todo avec proposition requise. |
| entity-disabled-by-default | Lot 8 : revue des 81 variantes dans docs/quality-scale-entity-inventory.md. RSSI individuel bruyant off à la première création ; tracker, autoprotection et contrôles avancés opt-in conservés. Fonctions principales et supervision Server/Home/réseau gardées selon rôle, pas désactivation administrative des données des cartes. Vrai EntityPlatform : RSSI neuf disabled_by INTEGRATION, ancien activé reste activé, choix USER conservé. Les 81 variantes préservent préférences et IDs ; aucun dashboard modifié. Valeurs contextualisées du ScannerEntity HA explicitement distinguées des flags déclarés. |
| entity-translations | Inventaire global noms/icônes des 30 familles/81 variantes mis à jour au lot 11. Noms sources (chaînes, clients, appareils) ne doivent pas être traduits ; placeholder TNT channel préserve nom exact. Noms principaux/classes HA déjà corrects ; vrais noms utilisateur/IDs/icônes préservés. Restent libellés fixes des descriptions réseau/appels/disques, nom WiFi/inversion/autoprotection et repli RSSI nommé, masquant parfois translation_key via _attr_name ou propriété name Home. Corriger consommation par vrai moteur HA FR/EN sans modifier entrées historiques ni noms utilisateur ; clés seules ne prouvent pas traduction. |
| icon-translations | Lot 11 : icônes fixes des 30 familles/81 variantes auditées et déplacées dans icons.json : boutons, capteurs réseau/appels/disques, AP/LAN/RSSI, calendrier/TNT, inversion, types trackers. Descripteurs clonés avec icon=None, IDs/noms sources/préférences inchangés ; vrai chargeur HA async_get_icons et registre (icône/nom personnalisés) testés. Classes natives gardent icône HA. Reste icône principale Player dépendant de source YouTube/Netflix, pas du state on/off : comportement utilisateur conservé en Python. Étudier métadonnée dynamique via API publique du registre et cache/lifecycle avant done, pas supprimer fonctionnalité pour score. |
| reconfiguration-flow | Test HA de caractérisation confirme : nouveau host -> wrong_account, données inchangées, aucun appel SDK. Le changement de port seul manque aussi de probe. Corriger exige plan compatible identité physique/host/jeton ; aucune migration ni changement IDs imposé. |
| repair-issues | Pas de preuve de Repairs pour tous états actionnables nécessitant intervention ; logs et ConfigEntryAuthFailed ne suffisent pas. |
| stale-devices | router.py:941-994,1112-1123 nettoie certains registres ; stale sensor/client/disque/Home et garanties multi-intégrations non démontrées globalement. Aucun changement repeater/. |
| inject-websession | Source SDK v1.3.1 vérifiée : constructeur sans session publique, open crée son ClientSession (aiofreepybox.py:126). Test signature réelle. Autre limite amont démontrée : après open échoué, close peut lever AttributeError _access avant session.close ; après logout échoué, close ne passe pas dans finally. Ne pas promettre une fermeture garantie sur erreur. Pas de monkeypatch/private session ni modification dépendance pour score ; proposition amont dans le rapport. |
| strict-typing | Mypy 2.4.1 strict : 162 erreurs /23 fichiers/39 modules (167 au lot 10). Imports des classes HA canoniques pour typage avec réexports runtime compatibles anciens HA ; vrai handler web.Request -> web.Response et chemin StaticPathConfig str selon contrat public. Nouveau lecteur Player typé sans dette ajoutée. Aucun Any/cast/ignore ajouté pour masquer une erreur. Restent contrats SDK non annotés, schémas voluptuous/probatio, rappels et autres plateformes ; baselines et limites documentées. |

## Validation reproductible

Avec PyYAML et probatio installés dans l'environnement de test :

```sh
python3 -B tests/validate_quality_scale.py
curl -fsSL https://raw.githubusercontent.com/home-assistant/core/49693fc6644b3555fdaaf9fe30a973517a0a9d4e/script/hassfest/quality_scale.py -o /tmp/ha-quality-scale.py
python3 -B tests/validate_quality_scale.py --upstream-schema /tmp/ha-quality-scale.py
```

Le second mode exécute **l'affectation SCHEMA officielle inchangée** avec
probatio et vérifie la correspondance exacte de la liste des règles. Il
n'importe pas HA, ne lance pas hassfest et **ne valide pas les assertions
sémantiques** des règles `done`. Le premier mode valide hors réseau toutes les
clés, statuts et commentaires ; contrôles négatifs : règle manquante, inventée,
statut invalide. Le snapshot ne se met pas à jour automatiquement.

Tests ciblés exécutés sans HA ni appareils :

```sh
python3 -B tests/simulation_player_diagnostics.py
python3 -B tests/simulation_issue106_home_player.py
python3 -B tests/simulation_registre_partage.py
```

Leurs succès restent des preuves partielles de non-régression, pas une mesure
de couverture générale. L'audit ne revendique ni certification ni passage d'un
tier. Aucun merge ou publication n'est inclus dans cette PR.
