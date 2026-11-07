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
