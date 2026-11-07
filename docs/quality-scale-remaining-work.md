# Inventaire fini des travaux restants — jalon 14

**21 done / 31 todo / 2 exempt, préparation 28.8.90 ; aucune certification HA.**
Une ligne par todo, pas une liste infinie de tests. La règle A est du
travail local indépendant ; B mêle travail local et réserve de compatibilité ou
dépendance ; C exige proposition compatible ou action amont avant conformité.
D contient du contenu local présent, pas treize documents manquants ; E mesure
la qualité transversale. Le mandat continue, ce document n’en annonce pas la fin.

## A — une règle localement traitable, sans migration ni appareil réel

| Règle | Minimum fini avant validation entière |
|---|---|
| repair-issues | Home insufficient_rights est couvert par Repair FR/EN natif entry-scoped, ignore conservé et suppression sur récupération ou retrait définitif. Restent autres sources de droits et liaison moderne config_entry_id absente de HA2026.10.4 ; aucune alerte sur panne transitoire, auth racine reste reauth. |

## B — quatre règles mixtes : travail indépendant possible, réserve précise

| Règle | Travail / limite avant done |
|---|---|
| entity-unavailable | Observation snapshot distincte Home prouvée (video_available, EOF/None/erreur, vraie reprise foreground, pas de write après unload). Reste projection globale des deux canaux : unavailable sur panne vidéo seule désactive les services Home via HA ; état Camera final ne doit pas être overridé. API image vérifie is_on, pas available, donc ne pas inventer blocage d’accès. Concevoir reprise UI et compatibilité sans nouveau polling FFmpeg coûteux ni migration imposée. |
| dependency-transparency | Source/tag/GPL/PyPI et attestation cryptographique du wheel 1.3.1 vérifiés. Guide core exige pin exact ; hassfest custom refuse exactement ce pin partagé (run 42400842458) et exige >=. Minimum original conservé, pas de désactivation CI. Réserve formelle pas défaut de provenance ; réauditer les versions futures, pas une exemption. |
| entity-device-class | Inventaire classes/unités déjà présent. Reste opener déduit du libellé (pas preuve garage), signal Free documenté dB mais historique dBm. Obtenir contrat vendor précis puis proposer mapping/option et compatibilité historique avant modifier classe/unité/exposition vocale. /1000 débit est maintenant démontré par documentation et HTTP JSON du vrai SDK ; ne pas rouvrir arbitrairement ce facteur. |
| config-entry-unloading | Maintenir tests réels forward onze domaines, rollback partiel, lectures en vol et fermeture. Restent HA refusant rollback (plateformes peuvent rester), partial-open FFmpeg avant try/finally parent et SDK close échoué sans finally. Préparer stratégie explicite de récupération via API publique, pas prétendre rollback atomique ni toucher une session privée. Tests supplémentaires n’effacent pas ces contrats amont. |

## C — onze décisions de compatibilité / réserves externes, pas exemptions

Les recherches, caractérisations et propositions restent possibles. En revanche,
implémenter arbitrairement une migration ou publier dans un autre dépôt n’est
pas autorisé par ce mandat. Pas de demande cosmétique bloquante.

| Règle | Condition de conformité et conséquence à anticiper |
|---|---|
| appropriate-polling | Déprécier le champ home_poll_interval avec conservation des valeurs existantes, mesures d’intervalles et absence de doublons ; ne pas retirer une option utilisateur pour le score. |
| brands | Assets du domaine freebox_homexa acceptés dans home-assistant/brands. Logos apps locaux ≠ marque intégration. Aucun dépôt/PR amont autorisé ici. |
| entity-unique-id | IDs RAID/disques liés à libellés et collisions multientrées à caractériser ; migration réversible préservant registre/historique/automatisations, aucun renommage forcé. |
| unique-config-entry | Dédupliquer même Server via host/IP/URL par identité physique vérifiée, pas host ; migration doit conserver chemin des jetons et entrées existantes. |
| reauthentication-flow | Vérifier même matériel derrière le host avant changer credentials ; conserver codes remote/entrée/IDs et refuser autre appareil. Dépend du plan d’identité stable. |
| devices | Associations/parents des trente familles, Home non préfixé et multi-Servers à vérifier ; pas fusion arbitraire de devices ni perte des choix utilisateur. |
| discovery | Vérifier annonces réellement supportées et parcours complet, pas seulement formulaire prérempli ; dédupliquer alias d’un même matériel sans inventer propriétés zeroconf absentes. |
| discovery-update-info | Même matériel à nouvelle adresse met à jour endpoint sans doublon/perte de token ; identité stable et migration compatibles requises. |
| reconfiguration-flow | Probe du nouveau host/port puis validation même matériel ; caractérisation actuelle wrong_account ou port sans probe n’est pas conformité. Dépend du même plan identité/jeton. |
| stale-devices | Distinguer disparition durable/panne transitoire ; offrir retrait utilisateur et préserver registres/automatisations/multi-intégrations. Pas de nettoyage destructif automatique pour faire passer le critère. |
| inject-websession | Signature publique SDK 1.3.1 sans session injectable ; open crée sa ClientSession. SDK amont doit proposer ownership/session publics. Pas de session privée, patch externe ou contournement ; problème close distinct prouvé par tests réels. |

## D — treize réserves formelles documentaires, contenu local disponible

Chaque règle ci-dessous a sa preuve précise et ses limites dans la
[matrice](quality-scale-proof-matrix.md) et le [guide](guide-utilisateur.md).
Leur réserve est **placement/revue home-assistant.io explicitement demandé par
les sources officielles**, pas absence générale du contenu. L’autoévaluation
custom peut décrire sa conformité locale sans revendiquer certification ou
modifier artificiellement le sens du YAML. Aucune soumission amont ici.

1. docs-actions — six actions/champs/réponses, YAML et traductions testés.
2. docs-high-level-description — rôle Server/Player/Home/TNT et lien Free.
3. docs-installation-instructions — HACS/manuelle, prérequis/appairage.
4. docs-removal-instructions — suppression et conservation réelle des données.
5. docs-configuration-parameters — options/defaults/effets/confidentialité.
6. docs-installation-parameters — host/port et Server cible.
7. docs-data-update — fréquences, polling et charge.
8. docs-examples — exemples YAML vérifiés, pas exécutés contre appareil.
9. docs-known-limitations — POP/API, apps, RTS, session SDK, rappels.
10. docs-supported-devices — capacités prouvées et limitations, aucune liste
    firmware/matériel inventée ni preuve de fonctionnement physique universel.
11. docs-supported-functions — distinction capacité/API et lecture réelle.
12. docs-troubleshooting — test minimal, pas secrets/exposition Internet.
13. docs-use-cases — cas pratiques et limites, IDs exemples à adapter.

## E — deux critères transversaux, aucune dispense de mesure

| Règle | Minimum restant |
|---|---|
| test-coverage | Seuil officiel intégration entière encore non atteint (75,74 % lignes / 54,34 % branches / 70,38 % combiné). Cibler erreurs/récupération et comportements manquants via A/B, pas tests sans assertions ni exclusion opportuniste. Deux passages locaux et CI doivent donner mêmes 39 modules/totaux. |
| strict-typing | 122 erreurs réelles/16 fichiers/41 modules ; résoudre contrats/narrowing/structures et appels SDK non annotés, sans Any/cast/ignore pour score. Conflit héritage FFmpeg et typage SDK doivent être distingués des défauts locaux corrigeables. |

## Exemptions inchangées : deux, pas une façon de masquer des défauts

`docs-conditions` et `docs-triggers` : aucune plateforme HA spécifique de
conditions/triggers, ni fichiers correspondants. Les événements dispatcher ou
rappels ordinaires ne créent pas une telle plateforme. Exemption explicite des
deux règles ; un ajout de plateforme imposera réévaluation. Ce ne sont pas des
exemptions de tests, de documentation générale ou d’absence de certification.
