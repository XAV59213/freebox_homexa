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
