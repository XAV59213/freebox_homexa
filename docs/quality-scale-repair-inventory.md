# Repairs — inventaire vérifié au jalon15

Ce document distingue un inventaire des **lectures existantes** d'une conformité
`repair-issues` globale. Aucun nouvel accès réseau, timer, test de droit en écriture
ou commande appareil n'est ajouté. Réseau réel bloqué dans les tests HA.

## Refus explicites observés

| Scope stable | Lecture existante | Résolution prouvée |
|---|---|---|
| home | SDK Home `home/nodes` | Collection Home valide ; gate historique et recharge conservés |
| wifi_config | SDK Wifi `wifi/config/` | Configuration valide |
| wifi_bss | SDK Wifi `wifi/bss/` | Collection BSS valide |
| wifi_ap | SDK Wifi `wifi/ap/` | Collection AP valide |
| wifi_stations | SDK Wifi `wifi/ap/{id}/stations/` | Au moins un relevé de stations et tous les relevés tentés réussis ; ni liste AP vide ni seul autre AP sain ne prouvent la reprise |
| repeaters | Transport existant `repeater/` | Collection valide ; endpoint inchangé |
| disks | SDK Storage `storage/disk/` | Collection validée |
| raids | SDK Storage `storage/raid/` | Collection validée, capacité RAID conservée |
| system | SDK System `system/` | Métadonnées requises lues |
| connection | SDK Connection `connection/` | Collection de valeurs lue |
| calls | SDK Call `call/log/` | Liste, y compris vraie liste vide ; None n'est plus un faux zéro |
| lan | SDK Lan `lan/browser/pub` | Vraie collection ; bridge/nodev n'est pas preuve de droits rétablis |
| players | SDK Player `player` | Snapshot metadata validé |

Les12 nouveaux scopes ont chacun un cas **vrai SDK + transport mocké + registre
HA natif** dans `test_source_permission_repairs.py` : refus, ignorer, refus répété,
timeout, collection invalide, lecture réussie. Home possède les preuves du lot14.
Les messages FR/EN sont chargés par l'API native de traductions, pas seulement
recherchés dans JSON. Le scope affiché est une constante technique, jamais un
hostname, numéro, SSID, ID d'AP, nom d'appareil, jeton ou message SDK brut.

Seuls `InsufficientPermissionsError` ou un `HttpRequestError` au code structuré
`insufficient_rights` déclenchent une alerte. Un timeout dont le texte imite ce
code, `nodev`, une erreur de valeur ou « access denied » non structuré n'en créent
pas. Le gate Home historique reste compatible même pour une ancienne erreur
ambiguë, mais sans inventer de Repair. Auth racine garde le flow reauth existant.

Les erreurs transitoires et réponses invalides ne créent **ni ne suppriment**
l'alerte. Une permission se résout par observation valide du même scope, non par
un autre endpoint sain. Les choix d'ignorer et identifiants restent stables ;
unload ne nettoie pas les alertes. Le retrait définitif nettoie tous les scopes
**de cette seule entrée**, testé avec deux vraies entrées et même scope disque.
Un résultat Home tardif d'un SDK qui absorbe l'annulation ne peut plus effacer
une alerte ignorée après fermeture. Le payload d'erreur repeater n'est plus stocké
ni journalisé : seul le type l'est, sans changer l'endpoint ou le regroupement.

## Pourquoi la règle entière reste todo

- L'API de HA2026.10.4 testée n'accepte pas `config_entry_id` dans
  `async_create_issue`. Scope opaque d'entrée et hook public `async_remove_entry`
  fonctionnent ; le masquage natif d'issue pendant désactivation n'est pas prouvé.
  Ne pas simuler une signature moderne ni déclarer une liaison native absente.
- Les lectures d’état par appareil (valeurs endpoints Home, statut local Player,
  image caméra) et certaines lectures directes de handlers ne sont pas toutes
  enrôlées dans cet inventaire de lectures partagées. Une metadata de hub saine
  ne prouve pas les droits d’un endpoint individuel. Aucun inventaire exhaustif
  de tous les callsites SDK n’est revendiqué.
- Les refus **d'actions en écriture** ont les erreurs HA traduites existantes,
  mais pas encore un inventaire Repairs persistant/résolution par une action
  ultérieure réussie. Une lecture saine ne prouve pas l'autorisation d'écrire.
  Ne pas envoyer une commande ni ajouter une sonde pour résoudre cette réserve.
- Les cas où une capacité disparaît volontairement (bridge/AP absent) demandent
  une politique explicite « ne s'applique plus », distincte d'une reprise de droit.
  Le présent lot préfère ne pas inventer la reprise à partir d'un relevé vide.
- Options volontaires, outages temporaires, source non supportée ou erreurs de
  saisie ne sont pas transformés en Repairs pour augmenter un compteur.

## Caméra : réserve architecturale maintenue

Aucun code caméra ni polling vidéo modifié. `video_available` reste le dernier
snapshot demandé, pas un état continu. `Camera.state` natif est final et les
services HA filtrent `available` : déclarer toute l'entité indisponible pour une
panne vidéo seule couperait les contrôles Home encore sains. Le helper image
vérifie `is_on`, pas `available` ; aucune impossibilité de lecture image inventée.
Une projection UI compatible/reprise utilisateur reste du travail de conception,
pas un manque de tests à masquer ni un nouveau poll à ajouter pour le score.

## Reproductibilité CI

La première CI e6be91a était verte mais son artefact manquait la branche où Remote
est le premier consommateur du cache metadata, l'ordre concurrent des plateformes
étant variable. Aucun résultat n'a été déclaré concordant sur cette base. Un test
utilise désormais le vrai forwarding public HA avec Remote en premier, puis les
autres plateformes : une unique lecture partagée est prouvée sans forger le cache
ni omettre la branche. Les deux runs finaux et la CI du commit de suivi doivent
être comparés intégralement avant livraison.
