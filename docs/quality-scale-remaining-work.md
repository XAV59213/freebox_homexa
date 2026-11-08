# Inventaire fini des travaux restants — jalon22

**22 done / 30 todo / 2 exempt, préparation 28.8.90 ; aucune certification HA.**
Jalon22 mesuré : 695 tests, 6530/6653 lignes (98,15 %), 2078/2248 branches (92,44 %),
combiné 96,71 %. Le critère officiel, relu le 2026-11-08, est plus de 95 % du code
dans chaque module. L'exemple pytest est la couverture de lignes, pas un second
seuil de branches. Les 42 modules dépassent 95 % de lignes. `test-coverage` passe
done sur ce seuil. Les branches restent publiées : tnt_tmdb est à 79,46 %, wifi_ap
à 90,51 %, device_groups à 93,23 %, router à 92,53 %. Deux passages locaux
concordent avec l'artefact CI
[42431543845](https://github.com/XAV59213/freebox_homexa/actions/runs/42431543845)
du SHA c8f5d76 : 6530/6653 lignes et 2078/2248 branches. Les chiffres
5928/6653 et 1699/2248 sont ceux de 09b1782 / 43c0323, pas de ce jalon.
Une ligne par todo, pas une liste infinie de tests. La règle A est du
travail local indépendant ; B mêle travail local et réserve de compatibilité ou
dépendance ; C exige proposition compatible ou action amont avant conformité.
D contient du contenu local présent, pas treize documents manquants ; E mesure
la qualité transversale. Le mandat continue, ce document n’en annonce pas la fin.

Quatre modules config/TNT/WS et caméra désormais sans diagnostic. **Deux erreurs**
restent : LegacyDeviceInfo avec IDentier/parent nullable et DeviceInfo disque avec
IDentier. DUMMY et contrat de payload ne sont plus des blocages non étudiés :
historique/source/SDK/branches sandbox démontrés ; base_class100% lignes/branches.
Ne pas proposer à nouveau des annotations ordinaires pour ces deux résidus : voir
[choix finis et conséquences](quality-scale-lot19-contract-decisions.md).

Le seuil officiel de lignes est atteint sur les 42 modules. Le typage strict reste
à deux erreurs d'identité, non masquées. Repairs et la projection caméra
unavailable ne sont pas étendus pour fabriquer un done. Les branches sous 95 %
restent visibles et ne sont pas un second seuil officiel.
La partition complète et les réserves exactes sont dans
[convergence jalon16](quality-scale-lot16-convergence.md). Le contenu documentaire
local n’est pas confondu avec une publication officielle hors périmètre.

## A — une règle localement traitable, sans migration ni appareil réel

| Règle | Minimum fini avant validation entière |
|---|---|
| repair-issues | Home +12scopes lectures couverts par Repairs SDK structurés FREN natifs, ignore et ownership conservés. Restent lectures d’état par appareil et droits écriture/résolution sans commande-probe, disparition volontaire de capacités et liaison moderne config_entry_id absente de HA2026.10.4. Inventaire détaillé quality-scale-repair-inventory.md. |

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
| devices | Jalon24 prouve l'isolation de deux serveurs pour le nœud entier, le disque entier, player_3 et le service TNT, sans réécrire les identifiants. Le dict FFmpeg est le flux, pas le registre. Reste la revue des familles d'entités non réexécutées. Pas de série ni de version matérielle inventées. Pas de migration. |
| discovery | Vérifier annonces réellement supportées et parcours complet, pas seulement formulaire prérempli ; dédupliquer alias d’un même matériel sans inventer propriétés zeroconf absentes. |
| discovery-update-info | Même matériel à nouvelle adresse met à jour endpoint sans doublon/perte de token ; identité stable et migration compatibles requises. |
| reconfiguration-flow | Probe du nouveau host/port puis validation même matériel ; caractérisation actuelle wrong_account ou port sans probe n’est pas conformité. Dépend du même plan identité/jeton. |
| stale-devices | Jalon23 : la page appareil peut supprimer un appareil seulement après une liste complète réussie. Refus si la liste manque, si l'appareil est encore là, s'il s'agit du routeur, d'un groupe, du guide TNT ou d'une autre intégration. Reste le retrait automatique sûr des disques, clients et capteurs vraiment disparus, sans confondre une panne avec une absence. Pas de nettoyage destructif pour le score. |
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
| test-coverage | Done au jalon22 : 695 tests, 6530/6653 lignes (98,15 %), 2078/2248 branches (92,44 %), 42/42 modules au-dessus de 95 % de lignes. Branches publiées à part, plusieurs sous 95 %. Artefact CI 42431543845 identique aux deux passages locaux. |
| strict-typing | Deux erreurs réelles/2fichiers/42modules : contrat HA identifiants str contre entiers historiques et parent legacy nullable. Caméra/DUMMY/callbacks résolus. Choix explicite décrit séparément ; pas de migration, cast, stub élargi ou Any implicite pour fabriquer un done. |

## Exemptions inchangées : deux, pas une façon de masquer des défauts

`docs-conditions` et `docs-triggers` : aucune plateforme HA spécifique de
conditions/triggers, ni fichiers correspondants. Les événements dispatcher ou
rappels ordinaires ne créent pas une telle plateforme. Exemption explicite des
deux règles ; un ajout de plateforme imposera réévaluation. Ce ne sont pas des
exemptions de tests, de documentation générale ou d’absence de certification.
