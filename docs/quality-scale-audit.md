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

## Résultat : 8 done / 44 todo / 2 exempt

Les 48 anciens `todo` ont tous été relus : **4 démontrés** dans ce lot, **44
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
| test-before-configure (nouveau) | création après open/probe ; échecs réseau/auth/probe sans création et fermeture SDK |
| test-before-setup (nouveau) | open/probe avant forward, erreurs temporaires/auth converties, session fermée sur échec/annulation |
| diagnostics (nouveau) | export chargé/non chargé, valeurs privées synthétiques et clés inconnues absentes, cache borné, timings validés/périmés |

### Exemptions réexaminées, pas supprimées artificiellement

`docs-conditions` et `docs-triggers` restent **exempt**, pas `done` : aucune
plateforme spécifique condition/trigger/device_condition/device_trigger ni fichier
conditions.yaml/triggers.yaml. `test_specific_trigger_condition_exemptions` vérifie
cet inventaire. Les événements HA ordinaires ne constituent pas une telle plateforme.
Les deux exceptions sont expressément prévues par les documents officiels liés ci-dessus.

## Correctif réellement réalisé

Dans `__init__.py:async_setup_entry`, l'ouverture et le premier `system.get_config`
partagent désormais une garde de nettoyage : fermeture de la session sur échec ou
annulation, y compris si `close` échoue, sans masquer la cause initiale. Timeout,
ClientError, OSError et HttpRequestError deviennent `ConfigEntryNotReady` ; token
invalide/droits insuffisants deviennent `ConfigEntryAuthFailed`, comme le refus
d'autorisation. Un timeout d'autorisation conserve le retry. Plus de journal
warning/error juste avant ces exceptions : HA les signale déjà.

Aucune nouvelle API, aucune commande HA/Player, aucun endpoint `repeater/` modifié.
Le nettoyage d'erreurs **après** le probe (premiers relevés routeur/forward de
plateformes) n'est pas rendu transactionnel par ce correctif ; c'est une réserve
pour le prochain lot de lifecycle, pas une garantie d'absence universelle de fuite.

## Tests réels et mesure, pas simulations présentées comme couverture

Environnement isolé : Python **3.14.9**, Home Assistant **2026.10.4**,
pytest-homeassistant-custom-component **0.13.375**, freebox-api **1.3.1**.
Versions reproductibles : `tests/requirements-ha.txt`. L'environnement ne prétend
pas tester toute version HA ≥2026.8 ; un job minimum supporté reste à établir.
Le plugin HA bloque sockets externes et DNS ; toutes les réponses appareil sont
synthétiques/mocks. Aucun secret/token de production, aucun appareil connecté.

**68 tests passent** : config initiale, réseau/auth, duplicate host, réauth avec
reload de l'entrée existante, options général/groupes, conservation options,
migration LAN, setup/unload succès/refus, erreurs close/annulation, confidentialité,
bornes cache/timings, Entity HA et signaux dispatcher/perte-retour, logs centraux
non répétés, garde de concurrence Home et enregistrement services idempotent.

| Périmètre (38 modules, aucun omit) | Lignes exécutées | Branches | Combiné |
|---|---:|---:|---:|
| Intégration entière | 1222/5710 = **21,40 %** | 143/1910 = **7,49 %** | **17,91 %** |
| config_flow.py | 182/431 = **42,23 %** | 27/146 = **18,49 %** | **36,22 %** |
| diagnostics.py | **100 %** | **100 %** | **100 %** |
| player_diagnostics.py | **100 %** | **100 %** | **100 %** |
| availability.py | **100 %** | **100 %** | **100 %** |

`test-coverage` et `config-flow-test-coverage` restent **todo**, loin des exigences.
Imports exécutés comptés dans les lignes ; ces chiffres ne signifient donc pas
21 % des fonctionnalités validées. Pas de seuil abaissé pour déclarer un niveau.
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
   évolution amont du SDK, pas monkeypatch interne. Exigences de licence/CI/tag
   PyPI et pin exact non démontrées. Audit I/O tokens et typage strict complet requis.
5. **Documentation/évaluation officielle** : README/exemples custom utiles mais
   ne remplacent pas la documentation home-assistant.io formellement visée. Logos
   locaux/codeowners/HACS ne prouvent pas brands ou integration-owner officiels.
   Aucun dépôt/acceptation core effectué au nom de l'utilisateur.

Les quatre nouveaux done n'annulent pas ces réserves. Les 44 restants sont tous
listés dans le tableau suivant ; celui-ci reprend le YAML, il n'est pas un second score.

| Règle encore todo | Preuve manquante / prochain travail |
|---|---|
| appropriate-polling | __init__.py:211 relève central, tnt_const.py:12 intervalle TNT 5 min. Audit des fréquences, doublons et charge toutes plateformes non achevé. |
| brands | Logos locaux présents ; ni acceptation HACS ni fichiers brand locaux ne prouvent la conformité du domaine dans home-assistant/brands. |
| config-flow-test-coverage | tests/ha teste le vrai flow manager HA 2026.10.4 (user, erreurs, duplicate host, reauth, options général/groupes). Couverture globale de config_flow mesurée dans docs/quality-scale-audit.md, encore très loin de 100 %. Restent découverte, reconfigure, profils, types/groupes complets, options TNT/télécommandes et autres erreurs. |
| dependency-transparency | manifest requirements freebox-api>=1.3.1 non épinglé exactement. Environnement tests fixé à 1.3.1, source et session SDK inspectées. Restent preuve licence OSI/public CI/tag PyPI pour chaque version ; ne pas revendiquer done sur seule installation réussie. |
| docs-actions | README.md:130-171 actions et remote : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-high-level-description | README.md:22-48 description et fonctions : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-installation-instructions | README.md:50-66 installation HACS : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-removal-instructions | README.md:255-261 suppression : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| entity-event-setup | entity.py:214-225 ajoute/retire les listeners. Pas de preuve exhaustive absence de fuite sur toutes les entités, notamment coordinateurs TNT et reload. |
| entity-unique-id | sensor.py:217,285 et tnt_sensor.py:40 définissent des IDs. Pas de test exhaustif stabilité/collisions multi-entrées, partitions, clients et tous modèles. |
| has-entity-name | tnt_sensor.py:28 et sensor.py:371 mettent has_entity_name=False ; règle globale non satisfaite. |
| unique-config-entry | config_flow.py:222 unique ID basé sur host ; hostname/IP/URL du même Server peuvent différer. Test de déduplication identité physique manquant. |
| action-exceptions | media_player.py:217-221,389-390 journalise/absorbe certains échecs au lieu de lever une erreur utilisateur ; tous services à auditer. |
| config-entry-unloading | tests/ha/test_lifecycle.py vérifie succès/échec unload, conservation ressources si plateforme refuse, fermeture routeur et sauvegarde. Timers callbacks traités sur succès. Restent vraies plateformes simultanées, multi-entrées et rappels en vol ; pas de conformité globale revendiquée. |
| docs-configuration-parameters | README.md:79-119 options LAN et appareils : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-installation-parameters | README.md:68-77 configuration initiale : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| entity-unavailable | tests/ha/test_privacy_availability.py valide le mixin avec une vraie Entity HA (perte/retour, disponibilité héritée, exception RTS). tests/ha/test_router_recovery.py couvre signaux réels et récupération. Disponibilité de toutes variantes tracker/Player/TNT/disques/Home non démontrée. |
| integration-owner | manifest.json codeowners présent ; ne prouve pas le rôle officiel de mainteneur core ni son acceptation. Projet custom HACS. |
| log-when-unavailable | tests/ha/test_router_recovery.py prouve une seule annonce INFO de perte puis retour sur trois erreurs du relevé central. __init__.py ne double plus les logs avant NotReady/AuthFailed. Les chemins Home/Player/TNT peuvent encore répéter des logs ; pas de preuve globale. |
| reauthentication-flow | tests/ha/test_config_flow.py prouve reauth_successful et reload unique de la même entrée sans doublon. Le serveur physique peut toutefois changer derrière le même host ; absence de contrôle MAC/identité avant réauth. Lié au choix de migration unique ID host vers identité physique, non imposé ici. |
| test-coverage | 68 tests réels HA 2026.10.4 ; 38 modules inclus, lignes 1222/5710 (21,40 %), branches 143/1910 (7,49 %), combiné 17,91 %. Config flow lignes 182/431 (42,23 %). Rapports JSON/XML en artefact CI ; seuil officiel non atteint, reste todo. Simulations séparées non incluses dans ces chiffres. |
| devices | media_player.py:90-103 et tnt_sensor.py:14-29 DeviceInfo ; cohérence des associations/subdevices et de toutes plateformes non vérifiée sur plusieurs modèles. |
| discovery | manifest.json zeroconf et config_flow.py:390-405 ; découverte sans interaction et tous cas réseau non testés sous HA. |
| discovery-update-info | config_flow.py:390-405 découvre le host ; aucun test prouvant mise à jour sûre des entrées existantes après changement adresse. |
| docs-data-update | README.md:173-191 disponibilité/journal ; intervalle de toutes sources non inventorié : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-examples | README.md:193-249 et examples/lovelace/ exemples de cartes : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-known-limitations | README.md:120-129 Player et 263-287 dépannage ; matrice modèles/apps incomplète : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-supported-devices | README.md:34-48 fonctions ; liste précise modèles/firmwares supportés non validée : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-supported-functions | README.md:34-48 et 130-171 ; matrice fonctions par modèle manquante : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-troubleshooting | README.md:263-287 dépannage : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| docs-use-cases | examples/lovelace/ et README.md:193-249 ; scénarios utilisateurs complets non vérifiés : documentation custom utile, mais conformité complète à la règle de documentation officielle home-assistant.io non prouvée. Pas de classement core revendiqué. |
| dynamic-devices | Code de découverte LAN/Home/répéteurs présent ; découverte runtime après setup et couverture de tous périphériques sans reload non démontrées. |
| entity-category | Descriptions nombreuses dans sensor.py/button.py ; classement config/diagnostic non audité exhaustivement. |
| entity-device-class | Classes présentes dans media_player.py et descriptions capteurs ; unités/classes de chaque variante de périphérique non validées. |
| entity-disabled-by-default | button.py pavé numérique désactivé par défaut ; pas de revue exhaustive de tous capteurs bruyants/secondaires. |
| entity-translations | sensor.py:371 et tnt_sensor.py:28 noms historiques sans has_entity_name ; traductions globales incomplètes. |
| exception-translations | translations/fr.json et en.json existent ; media_player.py:390 erreurs seulement journalisées. Pas de preuve traduction de toutes erreurs utilisateur. |
| icon-translations | icons.json existe ; tnt_sensor.py:27 et autres plateformes gardent des icônes statiques ; inventaire complet non effectué. |
| reconfiguration-flow | config_flow.py:async_step_reconfigure fixe le nouvel unique ID au nouveau host puis _abort_if_unique_id_mismatch ; un changement de host diffère donc de l’ancien unique ID et est refusé. Aucun probe avant sauvegarde du host/port. Correction liée à migration identité et jetons par host : décision de compatibilité nécessaire avant refonte. |
| repair-issues | Pas de preuve de Repairs pour tous états actionnables nécessitant intervention ; logs et ConfigEntryAuthFailed ne suffisent pas. |
| stale-devices | router.py:941-994,1112-1123 nettoie certains registres ; stale sensor/client/disque/Home et garanties multi-intégrations non démontrées globalement. Aucun changement repeater/. |
| async-dependency | SDK freebox-api 1.3.1 utilise aiohttp pour réseau ; constructeur/open/chargement-écriture des tokens et dépendances transitives à auditer contre les I/O bloquantes. get_api passe ses propres accès fichiers via exécuteur. Pas de qualification async complète sans audit des chemins SDK. |
| inject-websession | TNT/TMDB injectent la session HA. SDK freebox-api 1.3.1 aiofreepybox.py:Freepybox.__init__ ne prend pas de session ; open crée son propre ClientSession et close la ferme. Pas de paramètre public d’injection au constructeur. Exige amélioration amont du SDK plutôt que monkeypatch de _session. |
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
