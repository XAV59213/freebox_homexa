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

## Résultat : 13 done / 39 todo / 2 exempt

Les 48 anciens `todo` ont tous été relus : **9 démontrés** depuis l’audit initial, **39
restent ouverts** avec réserve précise dans le YAML et ci-dessous. Pas de
transformation administrative pour atteindre un score. Les numéros de lignes
de l'audit initial se réfèrent à la base ; les preuves nouvelles utilisent les
noms de fonctions/tests pour éviter les décalages de lignes.

| Règle démontrée | Preuve locale |
|---|---|
| common-modules | const.py, entity.py, availability.py |
| config-flow | déclaration manifest + flow HA réel testé |
| runtime-data | alias ConfigEntry[FreeboxRouter] et affectation entry.runtime_data |
| parallel-updates | 11 plateformes + test AST de chaque export |
| action-setup (nouveau) | six services réellement enregistrés une seule fois dans HA après deux async_setup sans entrée, aucun appel d'action |
| test-before-configure (nouveau) | création après open/probe ; échecs réseau/auth/probe sans création, close public tenté |
| test-before-setup (nouveau) | open/probe avant forward, erreurs temporaires/auth converties ; nettoyage public tenté, limite SDK précisée ci-dessous |
| diagnostics (lot 1) | export chargé/non chargé, valeurs privées synthétiques et clés inconnues absentes, cache borné, timings validés/périmés |
| entity-event-setup (lot 2) | inventaire AST + vraies plateformes HA/dispatcher/CoordinatorEntity, retrait des listeners et timers, isolement deux entrées |
| exception-translations (lot 2) | toutes les 32 levées custom HA/sous-classes traduites, placeholders vérifiés strings/FR/EN, moteur HA français réel |
| async-dependency (lot 2) | SDK asyncio/aiohttp ; SSL/fichiers dans asyncio.to_thread, signature coroutine publique testée et source v1.3.1 vérifiée |
| action-exceptions (lot 5) | 42 frontières AST, 103 tests dédiés HA/SDK/Store, validation/annulation préservées, pas de succès silencieux démontré |
| integration-owner (lot 2) | propriétaires du manifest repris sans ajout de personne dans CODEOWNERS ; cohérence testée, mainteneur XAV59213 actif dans les cinq derniers commits main |

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

**342 tests passent** (68 au lot 1, +50 au lot 2, +69 au lot 3, +47 au lot 4, +108 au lot 5) : config initiale, réseau/auth, duplicate host, réauth avec
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
| Intégration entière | 3372/5812 = **58,02 %** | 590/1938 = **30,44 %** | **51,12 %** |
| config_flow.py | 437/438 = **99,77 %** | 145/148 = **97,97 %** | **99,32 %** |
| diagnostics.py | **100 %** | **100 %** | **100 %** |
| player_diagnostics.py | **100 %** | **100 %** | **100 %** |
| availability.py | **100 %** | **100 %** | **100 %** |

`test-coverage` et `config-flow-test-coverage` restent **todo**, loin des exigences.
Imports exécutés comptés dans les lignes ; ces chiffres ne signifient donc pas
58 % des fonctionnalités validées. Pas de seuil abaissé pour déclarer un niveau.
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

Provenance partielle supplémentaire : licence GPL-3.0 du tag, commit
`96322885f37df37e6f491ab889b27cf912cc293a` et
[workflow de publication](https://github.com/hacf-fr/freebox-api/blob/v1.3.1/.github/workflows/release.yml)
vérifiés. Les runs verts trouvés sur ce commit correspondent à Tests/CodeQL,
pas une preuve d'exécution du publish PyPI. La dépendance reste `>=1.3.1`,
pas épinglée exactement ; `dependency-transparency` reste donc todo.

Proposition amont (non appliquée, personne contactée) : `close` doit fermer en
finally même sans authentification complète, et une future injection de session
publique doit préciser qui possède/ferme la session. Attendre une version publique
corrigée et réexécuter ces contrats avant changement de dépendance ; pas de lecture
ou monkeypatch de `_session` dans le runtime pour cocher une règle.

## Plan complet des lots suivants et frontières de sécurité

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
| config-flow-test-coverage | 342 tests HA au total ; config_flow.py : 437/438 lignes (99,77 %), 145/148 branches (97,97 %). Les erreurs de link testées sont suivies de la correction de leur cause et de la finalisation du même flow avec unique_id vérifié. Options répéteurs (registre uniquement), conflits Alexa, doublons de libellés, defaults privés synthétiques et conservation des codes vérifiés. Reste ligne 369 et trois branches ; guard reauth/user à justifier, sans forcer un chemin artificiel. 100 % non atteint, donc todo. |
| dependency-transparency | SDK 1.3.1 installé depuis PyPI ; source publique tag v1.3.1 et GPL-3.0 vérifiés via GitHub (commit 96322885f37df37e6f491ab889b27cf912cc293a), fichier client installé identique au raw. Workflow public release.yml de ce tag prévoit build/attestation/publication PyPI, mais exécution effective de publication non établie : les runs verts trouvés sont Tests/CodeQL, pas preuve de publish. Manifest reste freebox-api>=1.3.1, pas pin exact. Aucune dépendance changée ; todo reste justifié. |
| docs-actions | docs/guide-utilisateur.md (lié README) : Les six actions et tous leurs champs, ciblage multi-entrées et réponse scheduled_minutes sont documentés ; inventaire metadata/strings/FR/EN et YAML exemples testé. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-high-level-description | docs/guide-utilisateur.md (lié README) : Description Server/Player, usage réseau/Home/guide et lien officiel Free dans le guide. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-installation-instructions | docs/guide-utilisateur.md (lié README) : Installation HACS/manuelle, redémarrage et appairage pas à pas, prérequis locaux et confidentialité dans le guide. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-removal-instructions | docs/guide-utilisateur.md (lié README) : Suppression entrée/ressources/HACS et limites de conservation jetons, rappels et sauvegardes explicitement documentées. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| entity-unique-id | IDs historiques conservés ; plateformes multientrées, retour/disparition et variantes boutons testés. La stabilité RAID au renommage n’est prouvée que dans la même instance, pas au rechargement (constructeur utilise le nom). ScannerEntity fournit MAC client. Audit collisions/partitions et proposition de migration réversible restent nécessaires ; aucune migration imposée. |
| has-entity-name | tnt_sensor.py:28 et sensor.py:371 mettent has_entity_name=False ; règle globale non satisfaite. |
| unique-config-entry | config_flow.py:222 unique ID basé sur host ; hostname/IP/URL du même Server peuvent différer. Test de déduplication identité physique manquant. |
| action-exceptions | errors.py:async_action_errors garde les 42 frontières explicites inventoriées par AST sur 11 modules (actions entités, six services, lecture calendrier et reboot routeur). Validation HA et annulation préservées ; erreurs SDK/données traduites sans payload, état optimiste non changé en échec. tests/ha/test_action_errors.py : 103 cas vrai HA, succès/échec/récupération des familles, appels services réels, contrats SDK Remote et Store publics. False du SDK remote = commande non confirmée (elle peut avoir été exécutée), erreur distincte sans retry automatique. Écriture rappel relue via API publique et sérialisée ; annulation ne supprime pas le timer si persistance échoue. Tests camera/cover/local inversion du lot 4 conservés ; aucune preuve de réussite physique revendiquée. |
| config-entry-unloading | Les 11 domaines ont maintenant au moins une vraie EntityPlatform ajoutée/retirée (incluant boutons/camera/cover/switch), hooks coopératifs et listeners vérifiés ; isolement deux entrées et shutdown coordinator propriétaire testés. Restent discovery/forward complet, rollback partiel et tâches en vol. SDK close peut échouer avant fermeture session : limitation source démontrée, pas contournée. Lot 5 : fermeture publique aussi tentée après probe réussi si registre/relevé initial échoue, via callback possédé par HA (quatre tests du vrai ConfigEntriesManager, dont close en échec). Onze EntityPlatforms simultanées possédées par entrée + TNT : retrait états/listeners/watcher et close vérifiés ; dispatcher forward/unload substitué, pas une preuve de setup complet transactionnel. Limite SDK amont reste ouverte. |
| docs-configuration-parameters | docs/guide-utilisateur.md (lié README) : Table des options général/groupes/types/répéteurs/TNT/profils, valeurs, défauts, effets et données privées ; conservation des codes Player absents testée. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| docs-installation-parameters | docs/guide-utilisateur.md (lié README) : Table host/port initiaux, Server plutôt que Player et appairage physique ; limite host/identité expliquée. Preuve documentaire locale renforcée ; reste todo au sens formel, la règle officielle visant une page/revue home-assistant.io non soumise. Aucune certification custom revendiquée. |
| entity-unavailable | Vraies plateformes couvrent perte/retour centraux, TNT, Player, télécommande, caméra, volets et Wi-Fi. Caméra remplace son node au signal, disparaît/récupère sans nouvelle identité ; Wi-Fi invalide devient indisponible ; inversion disque illisible inconnue, position incertaine sans commande ambiguë. Reste vérifier toutes variantes, événements/autorisation et erreurs partielles avant règle globale done. |
| log-when-unavailable | tests/ha/test_router_recovery.py prouve une seule annonce INFO de perte puis retour sur trois erreurs du relevé central. __init__.py ne double plus les logs avant NotReady/AuthFailed. Les chemins Home/Player/TNT peuvent encore répéter des logs ; pas de preuve globale. |
| reauthentication-flow | tests/ha/test_config_flow.py prouve reauth_successful et reload unique de la même entrée sans doublon. Le serveur physique peut toutefois changer derrière le même host ; absence de contrôle MAC/identité avant réauth. Lié au choix de migration unique ID host vers identité physique, non imposé ici. |
| test-coverage | 342 tests HA 2026.10.4 ; 38 modules sans omit : lignes 3372/5812 (58,02 %), branches 590/1938 (30,44 %), combiné 51,12 %. Rapports JSON/XML CI ; seuil officiel non atteint. Certaines variantes sont des inventaires explicitement distincts du runtime. Les tests ne valident pas le matériel. |
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
| entity-category | Descriptions nombreuses dans sensor.py/button.py ; classement config/diagnostic non audité exhaustivement. |
| entity-device-class | Classes présentes dans media_player.py et descriptions capteurs ; unités/classes de chaque variante de périphérique non validées. |
| entity-disabled-by-default | button.py pavé numérique désactivé par défaut ; pas de revue exhaustive de tous capteurs bruyants/secondaires. |
| entity-translations | sensor.py:371 et tnt_sensor.py:28 noms historiques sans has_entity_name ; traductions globales incomplètes. |
| icon-translations | icons.json existe ; tnt_sensor.py:27 et autres plateformes gardent des icônes statiques ; inventaire complet non effectué. |
| reconfiguration-flow | Test HA de caractérisation confirme : nouveau host -> wrong_account, données inchangées, aucun appel SDK. Le changement de port seul manque aussi de probe. Corriger exige plan compatible identité physique/host/jeton ; aucune migration ni changement IDs imposé. |
| repair-issues | Pas de preuve de Repairs pour tous états actionnables nécessitant intervention ; logs et ConfigEntryAuthFailed ne suffisent pas. |
| stale-devices | router.py:941-994,1112-1123 nettoie certains registres ; stale sensor/client/disque/Home et garanties multi-intégrations non démontrées globalement. Aucun changement repeater/. |
| inject-websession | Source SDK v1.3.1 vérifiée : constructeur sans session publique, open crée son ClientSession (aiofreepybox.py:126). Test signature réelle. Autre limite amont démontrée : après open échoué, close peut lever AttributeError _access avant session.close ; après logout échoué, close ne passe pas dans finally. Ne pas promettre une fermeture garantie sur erreur. Pas de monkeypatch/private session ni modification dépendance pour score ; proposition amont dans le rapport. |
| strict-typing | router.py:1199 alias typé mais aucun résultat mypy strict/py.typed de toutes dépendances ni pipeline strict global. |

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
