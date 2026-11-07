# Contrats de source et unités — lot 9 (2026-11-07)

Autoévaluation locale de PR119, préparation 28.8.90, **sans certification HA**.
Les IDs, unités enregistrées, préférences et historique ne sont pas migrés.

## Défaut de débit démontré et corrigé

- [API publique Connection](https://dev.freebox.fr/sdk/os/connection/) : `rate_down`
  et `rate_up` sont en **octets/s**, contrairement à `bandwidth_*` en bits/s.
- [Implémentation officielle HA, Freebox sensor](https://github.com/home-assistant/core/blob/dev/homeassistant/components/freebox/sensor.py)
  lue directement : `UnitOfDataRate.KILOBYTES_PER_SECOND` et division par **1000**.
- Homexa divisait par 8000 : valeur affichée huit fois trop petite. Le test
  `test_connection_byte_rate_and_missing_uptime_contract` injecte 8000 octets/s,
  vérifie 8 kB/s, le zéro réel, l'unité et l'ID historiques inchangés.
- Les prochains échantillons corrigés peuvent donc monter d'un facteur huit ;
  **l'ancien historique n'est pas réécrit**, pas de migration du recorder.

[API publique Storage](https://dev.freebox.fr/sdk/os/storage/) et capteur officiel
HA ci-dessus : `free_bytes / total_bytes * 100`, pas une conversion en Go.
Capacité absente/nulle/invalide, libre absent/incohérent : **unknown**, pas faux 0 %.
RAID `degraded` absent ou non booléen : **unknown**, pas faux état sain.
Uptime absent/invalide : **unknown**, pas fausse durée zéro/date de redémarrage.

## Pertes partielles : preuve par source, pas seulement un flag routeur

`tests/ha/test_partial_sources.py` utilise **Storage/Home du SDK 1.3.1 réels**
avec transport GET mocké et de vrais EntityPlatform/états HA. Aucun POST/PUT
n'est exécuté sur un appareil ; les transports d'écriture sont assertés inutilisés.

| Source | Échec / réponse malformée | Succès vide / disparition | Récupération |
|---|---|---|---|
| Disques/partitions | snapshot conservé, `disks_available=False`, entité unavailable | snapshot courant remplacé, membre absent unavailable | nouvelle lecture, même entité/ID, état HA rétabli |
| RAID | snapshot conservé, `raids_available=False` ; pas de `supports_raid=False` permanent sur erreur transitoire | membre absent unavailable | retry à l'intervalle existant, même ID |
| Home | snapshot conservé, `home_available=False` ; erreur transitoire ne supprime pas le droit | snapshot courant remplacé atomiquement ; dix variantes Home indisponibles sans suppression registre | signal dispatcher, entités conservées, retour sans changement d'ID |
| XMLTV | UpdateFailed même avec cache : données du coordinateur conservées mais capteurs unavailable | programme absent reste inconnu, aucun programme inventé | même coordinateur/capteur redevient disponible après téléchargement valide |

Une collection **None** n'est pas assimilée à `[]`. Les snapshots sont préparés
avant remplacement. Un refus explicite de droit Home conserve la barrière
historique `home_granted=False` : après attribution du droit, recharger l'intégration.
Les erreurs transitoires/absence non prouvée d'API n'invalident plus définitivement
le droit ou le support matériel. Les endpoints et intervalles restent les mêmes ;
un modèle sans endpoint peut donc être réessayé aux relevés habituels (pas de
nouvelle requête à haute fréquence ni de nouvelle API).

Les logs de source sont uniques par panne puis annoncent le retour, sans payload
SDK, nom, titre ni identifiant personnel. La traduction d'échec XMLTV ne reçoit
que le type de l'exception. Une fermeture SDK inattendue hors unload est traitée
comme panne, pas faussement comme relevé réussi. Aucun accès à la session privée.
L'inversion locale du volet reste utilisable hors connexion : préférence locale,
pas source matérielle. Aucun endpoint `repeater/` modifié.

## Classes et unités : revue des 30 familles / 81 variantes

Le snapshot détaillé reste `tests/fixtures/quality_scale_entity_inventory.json` ;
il n'est pas à lui seul une preuve sémantique.

| Familles | Classe / unité et justification | Réserve |
|---|---|---|
| FreeboxSensor | data_rate kB/s, duration s, temperature °C ; IPv4 sans classe/unité adaptée | conversion débit corrigée sur contrat public ; sources brutes SDK, pas mesure matérielle |
| FreeboxBatterySensor | battery %, signal Home battery, identique au capteur officiel HA | pas de mesure physique de batterie |
| FreeboxDiskSensor | % libre, aucune classe de capteur HA ne décrit un pourcentage d'espace disque | pas data_size pour un pourcentage |
| FreeboxWifiSignalSensor | signal_strength dBm, valeur RSSI normalisée par wifi_ap | extraction multi-firmware encore à qualifier sémantiquement sur tous replis |
| FreeboxCallSensor / FreeboxCallLogSensor | nombres d'appels, aucune classe HA spécifique | aucun numéro/nom ajouté aux états |
| FreeboxLanGroupClientsSensor / FreeboxRepeaterCountSensor / FreeboxWifiClientCountSensor / FreeboxWifiClientListSensor / FreeboxWifiTotalClientSensor | inventaires/comptages, sans classe spécifique ni unité physique | ne pas présenter un inventaire comme mesure matérielle |
| FreeboxPirSensor / FreeboxDwsSensor / FreeboxCoverSensor | motion / door / safety, signaux trigger/autoprotection Home | source Home maintenant gardée globalement |
| FreeboxRaidDegradedSensor / FreeboxWifiApSensor | problem / connectivity | RAID inconnu n'est plus faux sain ; provenance Wi-Fi multi-source encore à qualifier |
| FreeboxBasicShutter / FreeboxShutter | shutter pour volet, garage via heuristique du libellé opener | **bloque entity-device-class global** : libellé ne prouve pas sous-type garage/portail ; pas de changement implicite d'exposition vocale |
| FreeboxButton / FreeboxPlayerAppButton / FreeboxPlayerRemoteButton | restart pour redémarrage ; pas de classe button adaptée aux autres actions | aucune unité |
| FreeboxPlayerMediaPlayer | tv | pas de titre de lecture inventé |
| FreeboxRemote / FreeboxSwitch / FreeboxShutterInvertSwitchEntity | aucune classe/unité adaptée à ces actions/options | inversion locale indépendante de Home |
| FreeboxAlarm / FreeboxCamera / FreeboxDevice / FreeboxTvGuideCalendar / HomexaTntSensor | pas de classe/unité de capteur à ajouter à ces plateformes/texte de programme | ne pas inventer de classe pour augmenter un score |

## Minimum encore indépendant et réalisable

- `entity-unavailable` reste **todo** : statut Remote et boutons Player, données
  Wi-Fi/LAN multi-sources et lectures individuelles d'endpoints restent à vérifier
  pour tous les échecs/reprises, pas uniquement panne globale du routeur.
- `entity-device-class` reste **todo** : sous-types opener non prouvés et replis
  RSSI. Une classe neutre ou une option explicite changerait l'exposition vocale ;
  préparer effet/compatibilité avant décision, pas déduire un garage du nom.
- `strict-typing` : tables de classement réellement typées, Programme/datetime,
  résultat TMDB TypedDict et ClientTimeout public. Pas de casts/ignores ajoutés,
  pas de fichier omis. Appels SDK non annotés et schémas HA WebSocket restent
  du travail réel ; tester le vrai pipeline avant de modifier sa compatibilité.
- SDK : constructeur sans injection de session publique et close après failed-open
  restent limites prouvées par tests/source, non résolues par ces nouveaux flags.
- Le rollback refusé/exceptionnel et FFmpeg open avant try/finally hérités restent
  des caractérisations, pas des garanties de fermeture inventées.

## Lot 10 — débit, décodage SDK et prudence RSSI

`tests/ha/test_availability_sources.py::test_sdk_access_connection_router_rate_preserves_native_bytes`
utilise le
vrai `Access`, le vrai `Connection` et une réponse HTTP JSON simulée avec son
Content-Type. `rate_down=8000` donne 8 kB/s, 125000 donne 125 ; `bandwidth_*`,
en bits/s, reçoit volontairement une valeur différente. Le SDK retourne `result`
sans conversion. [Code HA Freebox sensor](https://github.com/home-assistant/core/blob/dev/homeassistant/components/freebox/sensor.py)
emploie aussi kB/s et /1000. Le [SDK officiel Connection](https://dev.freebox.fr/sdk/os/connection/)
indexé indique `rate_*` en byte/s et `bandwidth_*` en bit/s ; la tentative de
lecture directe a rendu HTTP 500, ne pas la présenter comme une page récupérée.
Aucune réécriture des statistiques historiques, aucun ID/unité changé.

**Réserve RSSI précise** : [documentation Wi-Fi Free](https://dev.freebox.fr/sdk/os/wifi/)
indexée décrit `signal` comme « signal attenuation (in dB) », exemple -38. Cela
ne prouve pas dBm pour toutes sources LAN/stations. L’unité historique est gardée
sans conversion arbitraire. Une donnée vendor/firmware et un plan compatible
pour l’historique sont requis avant changement. Booléens et valeurs non finies
ne deviennent plus un signal numérique plausible.

## Lot 10 — sources partielles et veille réellement contrôlable

`tests/ha/test_availability_sources.py` apporte 39 cas avec vrai HA/SDK :
- Home : absence de `value`/erreur = source indisponible ; `value=None` explicite
  = disponible mais unknown. Une autre lecture réussie n’efface pas l’échec.
- Remote/Player : panne puis récupération ; statut vide = unknown, pas idle/on.
  Boutons synchronisés par dispatcher existant, sans nouvelle collecte par bouton.
- Veille précédemment confirmée + code remote configuré : off/available via le
  canal Server déjà implémenté ; aucun code seul ne crée un premier état off.
  Le test n’envoie aucune touche ni commande. Sans code, panne = unavailable.
- LAN : vrai format SDK `Request failed (APIResponse: {…'error_code': 'nodev'…})`
  reconnu par `errors.api_error_code`, pas par l’ancienne regex erronée ; reprise
  au timer existant. Client absent d’une liste fraîche devient absent sans effacer
  son registre. Six familles dérivées LAN couvrent panne et récupération.
- Wi-Fi : absence d’AP et sources config/BSS/AP en panne distinctes d’un champ
  manquant dans une réponse valide. Échec station ne conserve pas son ancien RSSI ;
  un signal fraîchement reçu par LAN reste utilisable.
- Température disparue : ancienne mesure retirée du snapshot, pas gardée fraîche.

La règle globale reste todo : boutons seuls sans provider MediaPlayer actif et
cadres d’erreur image FFmpeg restent à qualifier. Les limites de session SDK et
rollback refusé ne sont pas cachées par ces tests.

## Provenance SDK vérifiée, conflit de pin custom/core établi au lot 10

La version réellement installée et testée est **1.3.1**, comme le [manifest officiel HA Freebox](https://github.com/home-assistant/core/blob/dev/homeassistant/components/freebox/manifest.json).
Le manifest garde **freebox-api>=1.3.1**, minimum requis pour un custom partageant
la dépendance avec HA ; voir conflit de pin ci-dessous. Aucun SDK mis à jour ou patché.

- Source publique GPL-3.0 : [tag v1.3.1](https://github.com/hacf-fr/freebox-api/tree/v1.3.1),
  commit `96322885f37df37e6f491ab889b27cf912cc293a` ; [licence](https://github.com/hacf-fr/freebox-api/blob/v1.3.1/LICENSE.rst).
- [PyPI 1.3.1 et hashes](https://pypi.org/pypi/freebox-api/1.3.1/json) :
  wheel `fb438c44d08293d7ca1a3d9ad55334a3e2905bdda270332345b7e30a1afbfa87` ;
  sdist `4499889cb32a734f7dd64c7256420041593421ead4a122d27a8cabcd88909433`.
- [Workflow public de release](https://github.com/hacf-fr/freebox-api/blob/v1.3.1/.github/workflows/release.yml)
  construit, atteste et publie. [Run effectif réussi](https://github.com/hacf-fr/freebox-api/actions/runs/23742463862/attempts/1),
  même commit. Les anciens logs détaillés des steps ne sont plus disponibles :
  aucune prétention de les avoir inspectés.
- **Vérification cryptographique réussie**, pas seulement workflow présent :
  `gh attestation verify freebox_api-1.3.1-py3-none-any.whl --repo hacf-fr/freebox-api --format json`.
  La provenance signée SLSA v1 lie les deux hashes ci-dessus au commit, au workflow
  `release.yml@refs/heads/main` et à ce run. Le commit est également celui du tag
  v1.3.1 ; ne pas présenter l’attestation comme exécutée sur une ref de tag.
  API publique reproductible :
  `gh api repos/hacf-fr/freebox-api/attestations/sha256:fb438c44d08293d7ca1a3d9ad55334a3e2905bdda270332345b7e30a1afbfa87`.
  Aucun lien signé temporaire, jeton ou credential n’est publié dans le dépôt.

Cette preuve établit la provenance du SDK testé, **pas un done formel**.
La [règle core](https://contributors.home-assistant.io/core/quality-scale/dependency-transparency/)
demande aussi pin exact. L’essai de pin a réellement échoué au
[hassfest custom](https://github.com/XAV59213/freebox_homexa/actions/runs/42400842458),
qui refuse de pinner une dépendance partagée avec HA et exige `>=1.3.1` pour
suivre ses mises à jour. [Source du validateur](https://github.com/home-assistant/core/blob/dev/script/hassfest/requirements.py),
`validate_custom_requirements`, distinct de `validate_requirements_format` core.
Le minimum original est rétabli : aucune validation désactivée ni code SDK patché
pour le score. Réserve formelle custom/core explicite, versions futures à réauditer.
Cette preuve ne fournit ni session injectable, ni close garanti, ni typings SDK,
ni validation matérielle.
