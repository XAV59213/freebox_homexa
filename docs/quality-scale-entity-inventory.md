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

- Naming (lot 8) : has_entity_name=True sans condition dans les 30 familles,
  noms relatifs de production revus, features principales Home et Player à None.
  Le tracker sans appareil reste nommé ; lié à un appareil, il reprend son nom.
  Le vrai HA suit le renommage appareil, conserve name_by_user et le nom custom
  d’une entité. Les 81 variantes passent le vrai registre en gardant IDs et
  préférences. Les nouvelles entités peuvent recevoir un nouvel entity_id par
  génération standard HA ; aucun entity_id déjà enregistré n’est régénéré.
- Device class : heuristique opener garage/portail non exhaustive ; todo, ne pas
  inventer un type matériel à partir du seul nom.
- Defaults (lot 8) : revue complète ci-dessous ; nouveau RSSI désactivé par défaut,
  préférences existantes conservées par le vrai HA. Pas de désactivation en masse.
- Availability : champs globaux présents ne démontrent pas toutes les pertes/retours
  des sous-systèmes ; todo. Les tests réseau sont mockés.
- Entity unique IDs : non vides dans l’inventaire, mais cela ne démontre pas
  toutes les collisions entre équipements/options ; todo.

`entity-category`, `has-entity-name` et `entity-disabled-by-default` sont démontrées
localement par la revue et les tests associés (pas certification officielle).
Le snapshot est un contrat de régression après revue, pas un validateur sémantique
automatique ; toute nouvelle famille/catégorie exige une nouvelle revue.

## Revue des activations par défaut (lot 8)

Référence relue : [entity-disabled-by-default](https://contributors.home-assistant.io/core/quality-scale/entity-disabled-by-default/).
C’est une décision de rôle/utilité revue, pas une statistique d’usage mesurée ni
l’affirmation que tous les diagnostics doivent être désactivés. Valeurs exactes
par variante dans le snapshot :

- RSSI Wi-Fi individuel : bruit fréquent de diagnostic secondaire, désormais **off
  à la première création**. Le capteur reste proposé ; activation dans les paramètres
  de l’entité. L’option de création ne signifie pas activation du nouvel RSSI.
- Trackers réseau : opt-in du ScannerEntity HA conservé, pas de nouvelle activation
  automatique. Deux modes appareils LAN inventoriés, gestion native du registre.
- Autoprotection Home : diagnostic secondaire opt-in existant conservé.
- Boutons : pavé numérique/couleurs/commandes avancées et apps secondaires opt-in
  selon tableaux de production ; navigation principale et raccourcis usuels gardés.
- Alarme, caméra, volets, Player/remote, capteurs porte/mouvement, configuration Wi-Fi
  et inversion : fonctionnalités principales immédiatement utilisables.
- Débits, compteurs/listes réseau par borne/groupe et inventaire répéteurs : cœur
  de la supervision réseau et données des cartes. Les supprimer par défaut pour
  le score retirerait une fonctionnalité principale. Débits variables intentionnels.
- Températures, uptime, IPv4, batterie, RAID et disque : supervision de santé du
  Server/Home, décisions de revue conservées ; pas de création d’une nouvelle
  désactivation de toute la surveillance de maintenance.
- Compteur/journal appels et acquittement, calendrier et TNT : contenu principal,
  restent utilisables ; les réglages de sélection TNT existants restent prioritaires.

Le vrai EntityPlatform prouve : nouveau RSSI disabled_by INTEGRATION, ancien RSSI
activé reste activé, désactivation USER reste USER. Les noms/IDs/hidden/disabled USER
sont aussi préservés pour les 81 variantes. Ce classement ne supprime aucun état
ni donnée de production existant. Le panneau RSSI facultatif d’une carte est vide
jusqu’à activation sur une nouvelle installation ; les anciens RSSI activés restent
visibles. Pas de modification du dashboard de l’utilisateur.

## Lacunes de disponibilité restant réellement traitables

Les 81 variantes sont vérifiées sous perte du routeur puis récupération et sous
fermeture. TNT dépend de son coordinateur XMLTV, pas de Freebox OS ; l’inversion
édite un fichier local et reste accessible hors ligne. Le tracker suit maintenant
la perte Freebox, sans prétendre « absent du domicile » quand le routeur est perdu.
Ces gardes globales ne suffisent pas à démontrer entity-unavailable : La source capteurs possède maintenant un flag de succès : HttpRequestError rend
les états indisponibles (logs uniques), puis le vrai HA retrouve unknown pour une
valeur manquante et une valeur valide pour zéro réel.

Lot 9 : [contrats de source et unités](quality-scale-source-contracts.md),
Storage/Home réels sur transport mocké, indisponibilité/récupération, collections
malformées distinctes d’une disparition, cache XMLTV conservé mais unavailable.
Restent Remote/boutons Player, Wi-Fi/LAN multi-sources et lectures individuelles
d’endpoints. Les gardes d’inventaire et quatre sources ne suffisent donc toujours
pas à valider la règle entière. Aucun changement de préférence, d’ID ou d’endpoint
`repeater/` pour augmenter un score.

## Lot 11 — icônes fixes et noms réellement consommés

Les 81 variantes sont réinventoriées ; seul `translation_key` change dans le
snapshot, aucune classe/unité/catégorie/activation. Descripteurs historiques
conservés pour leurs inputs d’ID, clones avec icon=None. Icônes fixes : boutons,
réseau/appels/disques, AP/RSSI/LAN, calendrier/TNT, inversion et types de trackers
dans icons.json. Vrai chargeur HA `async_get_icons`, vrai registre avec icône et
nom utilisateur, ancien entity_id/unique_id conservés ; pas seulement lecture JSON.
Les classes natives gardent leur icône HA ; l’icône Player dépendant de `source`
reste en Python pour préserver le comportement demandé, à transposer/tester via
métadonnées dynamiques compatibles avant de clôturer icon-translations.

Inventaire des noms restant à traduire : `FreeboxSensor` descriptions rate_down,
rate_up, ipv4, uptime, missed, calls_log ; `FreeboxDiskSensor` partition_free_space
avec placeholder de partition ; `FreeboxSwitch` WiFi ; Home autoprotection et
inversion via propriété name/attributs historiques ; RSSI sans appareil propre avec
placeholder client. Les noms propres appareils/clients/chaînes/partitions ne sont
pas du texte à traduire. TNT reçoit un placeholder channel identique FR/EN, sans
inventer de titre. Les entités principales Home/Player restent sans suffixe et les
états standards relèvent des classes HA. Les clés présentes mais masquées par
_attr_name/name ne suffisent pas à déclarer une traduction fonctionnelle.
