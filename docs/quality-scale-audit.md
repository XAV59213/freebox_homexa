# Integration Quality Scale — autoévaluation Freebox Homexa

Audit du 7 novembre 2026, base `b6a2599` (28.8.89). Aucun niveau officiel
Bronze/Silver/Gold/Platinum n'est attribué ou revendiqué. L'acceptation dans HACS
ne vaut pas certification Integration Quality Scale. Aucun champ `quality_scale`
n'est ajouté au manifeste ; aucune version ni fonctionnalité n'est modifiée.

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

## Résultat : 4 done / 48 todo / 2 exempt

Chaque règle contient sa preuve ou sa réserve dans le YAML. Les références
fichier/ligne se rapportent à la base runtime ci-dessus (pas à une garantie de
stabilité de numérotation après un prochain correctif).

`done` est limité aux constats structurels directement vérifiables :

| Règle | Preuve locale |
|---|---|
| common-modules | const.py, entity.py et availability.py centralisent constantes et bases communes |
| config-flow | manifest.json:12 et config_flow.py:180-225 ; flow UI déclaré et implémenté |
| runtime-data | router.py:1199 alias ConfigEntry typé ; __init__.py:220 affecte runtime_data |
| parallel-updates | constante explicite sur les 11 plateformes (lignes dans YAML) |

Deux exemptions seulement : pas de conditions ni de triggers **propres à
l'intégration** (inventaire du paquet et const.py:52-64). Les événements usuels
et automatismes externes ne sont pas ces plateformes.

### Réserves principales

- `todo` signifie également **preuve insuffisante**, pas nécessairement bug.
  Reauthentication, reconfigure, diagnostics, unloading et discovery existent ;
  leur existence ne démontre pas le respect global de chaque règle.
- Pas de couverture runtime HA mesurée, ni couverture complète du config flow,
  ni preuve de >95 %. Les simulations et tests JS ne sont pas de tels rapports.
  CI syntax, HACS et hassfest ne prouvent pas les tests runtime.
- Noms historiques, traductions, catégories, classes, identités multi-entrées,
  découverte dynamique et retrait des appareils requièrent un inventaire et
  des tests plus complets. Les exceptions loguées/absorbées côté Player ne sont
  pas toutes des erreurs utilisateur traduites.
- Les règles `docs-*` officielles visent la documentation home-assistant.io.
  Le README custom contient des éléments utiles, cités sans les assimiler à
  une validation documentaire core. Les deux exceptions restent motivées.
- Le SDK Freepybox et ses dépendances n'ont pas fait l'objet d'une revue async,
  session injectée et typage strict complète. TNT utilise une session HA, mais
  cela ne prouve pas que le SDK fait de même.
- `brands` et `integration-owner` ne sont pas validés par la présence de logos
  locaux, de codeowners ou l'acceptation HACS.
- Confidentialité des diagnostics : aucun contenu nouveau exporté, aucun titre
  ni donnée privée collectés pour cet audit. Une revue exhaustive reste `todo`.
- Aucun endpoint, comportement ou code `repeater/` modifié ; les réserves de
  registre ne proposent aucune nouvelle API ni régression des gardes existantes.

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
