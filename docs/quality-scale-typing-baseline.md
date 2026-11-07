# Typage strict — baseline réelle du lot 6

Autoévaluation locale, pas certification. `strict-typing` reste **todo**.

## Mesure

- Mypy **2.4.1**, Python **3.14.9**, interpréteur de dépendances HA **2026.10.4**,
  SDK **freebox-api 1.3.1**, environnement `tests/requirements-ha.txt`.
- Commande stricte sur **38 fichiers**, sans fichier omis, blanket ignore,
  `ignore-missing-imports`, stub SDK fictif ou baisse de seuil.
- Première mesure du lot 6, avant correction du type de décorateur : **268 erreurs
  dans 29 fichiers**. Après correction : **230 erreurs dans 28 fichiers**.
- `async_action_errors` renvoie maintenant `Callable[..., Coroutine[Any, Any, T]]`,
  pas simplement `Awaitable[T]` : ses fonctions sont bien des coroutines comme les
  méthodes entités HA qu’elles remplacent. `Any` est ici le protocole standard de
  send/yield de Coroutine, pas une désactivation du contrôle du résultat `T`.
- Le SDK installé **contient `freebox_api/py.typed`**, vérifié avec les métadonnées
  de distribution. Ne pas invoquer une absence de marqueur pour justifier ces todo.
  Certaines signatures restent partielles ; session publique injectable absente est
  un problème séparé, pas une preuve que toutes ses interfaces sont non typées.

| Code mypy restant | Nombre |
|---|---:|
| `type-arg` | 38 |
| `no-untyped-def` | 29 |
| `attr-defined` | 28 |
| `no-untyped-call` | 25 |
| `assignment` | 22 |
| `union-attr` | 22 |
| `arg-type` | 20 |
| `no-any-return` | 9 |
| `dict-item` | 9 |
| `misc` | 6 |
| `override` | 6 |
| `typeddict-item` | 5 |
| `name-defined` | 4 |
| `var-annotated` | 4 |
| `valid-type` | 2 |
| `operator` | 1 |

Les diagnostics sont statiques, **pas 230 bugs runtime affirmés**. Exemples :
réexports HA non explicites sous le réglage strict, génériques nus, méthodes sans
annotation, retours Any et compatibilité d’overrides. Le fichier historique
`base_class.py` signale aussi un import `DUMMY` absent ; ne pas inventer ce réglage
ni exclure le fichier pour effacer le diagnostic. Usage/compatibilité à vérifier
avant modernisation de ce module. Les noms/IDs historiques ne sont pas migrés.

## Reproduction

```sh
uv venv --python 3.14 /tmp/homexa-quality-typing
uv pip install --python /tmp/homexa-quality-typing/bin/python mypy==2.4.1
/tmp/homexa-quality-typing/bin/python -m mypy --strict \
  --python-executable /tmp/homexa-ha-quality/bin/python \
  custom_components/freebox_homexa
```

Le second interpréteur doit contenir les versions `tests/requirements-ha.txt`.
La commande **sort actuellement en échec** ; elle n’est pas maquillée en check CI
vert. Traiter les erreurs par module/famille après inventaires de comportements,
avec tests de régression, avant d’ajouter un gate strict global. Le contrat du
SDK doit rester réel ; pas de patch dépendance ni lecture de session privée.

## Lot 7

Mesure finale : **227 erreurs / 27 fichiers / 38 analysés**. Les trois erreurs
des types génériques diagnostics sont corrigées : TimingSample TypedDict,
listes d’observations typées, dictionnaire d’entrée arbitraire explicitement
object et sortie list[dict[str, object]]. Aucun cast/ignore ajouté. Le contenu
filtré et les tests privacy restent identiques ; strict-typing reste todo.

## Lot 8

**186 erreurs / 25 fichiers / 38 analysés**, contre 227 au lot 7. Aucun Any,
cast ou ignore ajouté pour masquer un contrat : metadata XMLTV TypedDict,
Programme annoté, datetime/time/Iterator précis, retours dict[str, object],
overloads d’entrée non vide, validation/narrowing des événements XMLPullParser
selon les événements start/end demandés. Module tnt_coordinator : zéro erreur
strict, sans exclusion. DeviceInfo directement typé ; IDs de commande acceptés
uniquement comme int non bool ; valeurs de débit optionnelles numériques.

La base disponibilité est un vrai Entity HA avec routeur typé, pas un super Any
ignoré. Cela expose aussi des appels SDK auparavant masqués par Any implicite.
Le contrat FFmpegCamera.name -> str hérité est plus étroit que le nom principal
None légitime côté Entity ; conflit de bases signalé, pas casté. Des imports
canoniques, API de registre, structures et fonctions restantes doivent encore
être typés. py.typed du SDK présent ne signifie pas que chaque méthode est annotée.

Coverage.py exclut automatiquement 8 lignes purement typing (TYPE_CHECKING et
surcharges ellipsis) ; aucun omit/paramètre d’exclusion ajouté, aucun seuil abaissé.
Ce n’est pas une prétention à la conformité strict-typing globale.

## Lot 9 — 167 erreurs / 24 fichiers / 38 analysés

186→167 erreurs strictes réelles : tables de classement tuple homogènes,
Programme/datetime/Callable Awaitable[None], TmdbResult TypedDict, timeout
ClientTimeout(total=10) équivalent à la conversion aiohttp précédente.
tnt_tmdb et tnt_coordinator : aucune erreur stricte. Pas de casts/ignores ajoutés,
pas de Any de confort ni d’omit ; appels SDK non annotés encore visibles.
Le pipeline WebSocket HA et ses schémas voluptuous/probatio doivent être testés
avant changement de compatibilité, pas masqués par un type Any.

## Lot 10 — disponibilité sans dette de typage masquée

Mypy strict : **167 erreurs / 24 fichiers / 38 modules**, ensemble normalisé
identique au lot 9 (positions seules décalées). Aucun Any/cast/ignore ajouté pour
masquer ces contrats. Les nouveaux guards de sources, flags et états inconnus
restent testés sous le vrai HA ; ce lot ne prétend pas clôturer strict-typing.

## Lot 11 — 162 erreurs / 23 fichiers / 39 modules

167→162 par contrats réels : handler aiohttp web.Request -> web.Response,
StaticPathConfig reçoit str et non Path ; imports de classes HA canoniques en
TYPE_CHECKING avec réexports runtime historiques conservés pour compatibilité.
Nouveau lecteur Player partagé entièrement typé, zéro nouvelle erreur. Aucun
Any/cast/ignore ajouté pour masquer les contrats SDK/HA. La couverture exclut
automatiquement 17 lignes typing (10 avant), sans règle personnalisée ; variation
de périmètre explicitée, pas présentée comme une hausse de couverture fonctionnelle.
