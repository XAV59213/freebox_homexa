# Revue globale des métadonnées — lot 7

Autoévaluation locale, pas certification Home Assistant. Revue des 30 familles
concrètes actives, 81 variantes construites sous HA réel, toutes les descriptions
et les 41 boutons inclus. Le test découvre les classes de production et refuse
une famille absente. Le snapshot JSON ne contient pas d’identités ni de données
personnelles. Il ne prouve pas le comportement matériel ni toutes les variantes
possibles de modèles/données reçues.

Références : [entity-category](https://contributors.home-assistant.io/core/quality-scale/entity-category/),
[source officielle Freebox](https://github.com/home-assistant/core/blob/dev/homeassistant/components/freebox/sensor.py).
Les catégories concernent le rôle, pas le niveau d’importance ni la disponibilité.
Une intégration de supervision réseau a aussi des observations métier principales ;
une liste de clients n’est pas automatiquement un diagnostic technique secondaire.

| Famille | Variantes | Catégorie observée | Justification revue |
|---|---:|---|---|
| FreeboxAlarm | 1 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxBasicShutter | 1 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxBatterySensor | 1 | diagnostic | État de santé de l’alimentation du périphérique Home. |
| FreeboxButton | 2 | config, diagnostic | Reboot configure le serveur ; effacer les appels acquitte un compteur de diagnostic. |
| FreeboxCallLogSensor | 1 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxCallSensor | 1 | diagnostic | Compteur technique des appels manqués ; distinct du journal métier des appels. |
| FreeboxCamera | 1 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxCoverSensor | 1 | diagnostic | Autoprotection du boîtier : état technique distinct de l’ouverture/mouvement. |
| FreeboxDevice | 2 | diagnostic | Présence technique du client LAN, catégorie diagnostic existante conservée. |
| FreeboxDiskSensor | 1 | diagnostic | Capacité libre : contrôle de santé du stockage. |
| FreeboxDwsSensor | 1 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxLanGroupClientsSensor | 1 | principale (aucune) | Inventaire métier des clients par groupe utilisé par la carte réseau. |
| FreeboxPirSensor | 1 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxPlayerAppButton | 8 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxPlayerMediaPlayer | 3 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxPlayerRemoteButton | 31 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxRaidDegradedSensor | 1 | diagnostic | Dégradation du stockage. |
| FreeboxRemote | 1 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxRepeaterCountSensor | 1 | principale (aucune) | Inventaire métier des bornes, pas leur état de santé individuel. |
| FreeboxSensor | 5 | diagnostic, principale (aucune) | Débits = usage réseau principal ; IPv4, uptime et températures = informations techniques de diagnostic. |
| FreeboxShutter | 3 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxShutterInvertSwitchEntity | 1 | config | Réglage de la convention de position, pas une commande du volet. |
| FreeboxSwitch | 1 | config | Activation du Wi-Fi : configuration du serveur. |
| FreeboxTvGuideCalendar | 1 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |
| FreeboxWifiApSensor | 2 | diagnostic | Joignabilité technique de la borne, pas action de configuration. |
| FreeboxWifiClientCountSensor | 2 | principale (aucune) | Comptage métier par borne associé à ces inventaires. |
| FreeboxWifiClientListSensor | 2 | principale (aucune) | Inventaire métier des clients par borne utilisé par la carte réseau. |
| FreeboxWifiSignalSensor | 2 | diagnostic | Puissance du signal : diagnostic radio. |
| FreeboxWifiTotalClientSensor | 1 | diagnostic | Agrégat technique global existant, distinct des listes métier par borne. |
| HomexaTntSensor | 1 | principale (aucune) | Fonction principale : commande, contenu ou observation métier ; pas un réglage ni un contrôle de santé. |

## Changements et garde de compatibilité

Ajout diagnostic : IPv4, uptime, températures, batterie, appels manqués, espace
libre, joignabilité AP. Ajout config : inversion volet. Aucun ID, nom,
activation par défaut, attribut de contenu ni endpoint modifié par ce classement.
Le vrai EntityPlatform met à jour la catégorie de huit entités représentatives
sans changer unique_id, entity_id, nom utilisateur, hidden_by USER ni disabled_by
USER ; une entité désactivée reste non ajoutée. Les autres variantes utilisent
les mêmes descriptions/attributs de classe et sont vérifiées par le snapshot.

## Autres règles : pas de validation par association

- Naming : plusieurs familles restent sans has_entity_name ; todo. Une
  modernisation doit démontrer la conservation des noms/IDs et des noms personnalisés.
- Device class : heuristique opener garage/portail non exhaustive ; todo, ne pas
  inventer un type matériel à partir du seul nom.
- Defaults : valeurs contextuelles observées (LAN avec/sans devices, registry HA) ;
  il reste à justifier entièrement l’utilité par défaut de chaque variante et les
  dépendances des cartes. Snapshot ≠ preuve suffisante pour passer done.
- Availability : champs globaux présents ne démontrent pas toutes les pertes/retours
  des sous-systèmes ; todo. Les tests réseau sont mockés.
- Entity unique IDs : non vides dans l’inventaire, mais cela ne démontre pas
  toutes les collisions entre équipements/options ; todo.

`entity-category` seule est démontrée par cette revue et les tests associés.
Le snapshot est un contrat de régression après revue, pas un validateur sémantique
automatique ; toute nouvelle famille/catégorie exige une nouvelle revue.
