# Lot19 — contrats démontrés et décisions restantes finies

Autoévaluation locale, préparation28.8.90. 21done/31todo/2exempt ; aucune
certification, contribution amont, migration ou commande physique.

## Corrections locales désormais démontrées, pas des blocages répétés

### DUMMY et classe legacy

`git show 5e42e63:custom_components/freebox_homexa/const.py` montre DUMMY=False.
Le commit `7cf0c60d901441a4280a91910e96c0a53a8dc8ab` (20février2025, Europe/Paris)
retire ce symbole pendant le remplacement des constantes. La classe legacy le
référençait toujours : restaurer ce **même défaut historique** répare l'import,
sans inventer réglage ni supprimer la branche sandbox. Aucun import de cette
classe par les plateformes actives n'a été trouvé ; cela ne prouve pas absence
d'utilisateurs externes. Le fichier n'a donc pas été supprimé.

`git grep 'set_home_endpoint_value(' 5e42e63 -- custom_components/freebox_homexa`
montre les anciens appelants alarme/caméra/volets transmettant des dictionnaires
`{"value": ...}`. L'annotation de payload correspond à ces appels, pas à un Any.
Le SDK1.3.1 installé transmet exactement ce corps via son Home public vers
`home/endpoints/{node}/{endpoint}` ; tests ne remplacent que le transport.
Les quatre combinaisons DUMMY true/false et ID42/1001 prouvent le court-circuit
uniquement au-dessus du seuil historique, y compris priorité sur VALUE_NOT_SET.
Lectures absentes/None, sous-nœuds, catégories/héritages et erreurs sont testés.

94/94 lignes,28/28 branches de base_class couvertes dans vrai HA : le résidu
n'est plus «callbacks ordinaires ou DUMMY non étudié». LegacyDeviceInfo décrit
exactement le payload réel, sans prétendre satisfaire le DeviceInfo HA.

### Caméra : composition du transport public FFmpeg

L'entité reste FreeboxHomeEntity+Camera. Un FFmpegCamera privé délègue uniquement
image, source et MJPEG ; jamais enregistré comme seconde entité. Ses méthodes
publiques et leur cleanup sont exécutés contre sous-processus/HTTP mockés.
Le nom relatif peut rester None ; aucune chaîne vide/source n'est imposée.
Les features restent STREAM comme dans la base FFmpeg antérieure. Identifiants,
entité/objet registre, nom choisi, icône, visibilité utilisateur survivent au
reset/rechargement natif. Le helper n'a aucun rôle de registre/préférences.
La limite amont partial-open avant try/finally demeure caractérisée, non corrigée
ou masquée. Aucun polling/retry, modification confidentialité ou accès appareil.

### Config flow : contrat validé plutôt que garde inaccessible

Le manager HA valide effectivement le schéma public avant le callback : entrée
malformée produit InvalidData sans mutation ; la même session corrige puis
termine. Un TypedDict décrit désormais cette entrée validée ; les valeurs de
profils sauvegardées restent séparément opaques/préservées. La validation interne
dupliquée inaccessible est retirée, pas masquée par pragma ni couverte par appel
direct artificiel. Config_flow477/477lignes et164/164branches100% : seuil spécifique
[officiel100%](https://contributors.home-assistant.io/core/quality-scale/config-flow-test-coverage/)
relue en ce lot, distinct du >95% de chaque module pour la règle couverture globale.

## Deux diagnostics réels : même décision, deux endroits

- `sensor.py` : tuple domaine/IDentier face au domaine/str attendu par DeviceInfo.
  Le constructeur est maintenant annoté et borne données SDK/partition/modèle.
- `base_class.py` : override LegacyDeviceInfo différent du DeviceInfo HA,
  notamment IDentier et via_device_id nullable. Le payload est conservé tel quel.

Le DeviceRegistry HA2026.10.4 exécuté dans les tests accepte effectivement ces
entiers. Lookup scoped avec la chaîne équivalente retourne None : ce sont **deux
identités distinctes**, pas une simple correction de présentation. Le même ID
numérique réutilisé conserve l'objet device et son name_by_user. Aucune donnée
existante n'est transformée ni registre nettoyé.

### Choix A — compatibilité actuelle, diagnostics explicites

Conserver IDs et parent nullable, accepter que strict-typing global reste todo.
C'est le comportement de ce lot et le seul choix sans action supplémentaire.
Continuer d'autres lacunes locales est possible ; ne pas refaire cette analyse
ni promettre qu'une annotation/protocole corrigera ces deux erreurs.

### Choix B — contribution au contrat HA, autorisation externe nécessaire

Proposer à HA un contrat de registre acceptant les identifiants historiques
entiers et parent None, avec preuves de stockage/rechargement/ownership.
Ce n'est pas seulement élargir un stub local : les types publics, dictionnaires
internes et invariants de registre sont concernés ; l'amont peut refuser de
supporter ce qui est toléré au runtime. Pas de garantie d'acceptation ni délai.
Aucun message/issue/PR amont n'a été publié. Sans acceptation et version supportée,
aucun faux done via monkeypatch/stub local/cast/ignore n'est acceptable.

### Choix C — migration explicite, hors autorisation actuelle

Préparer un plan distinct : snapshot, collisions int/str existants, ownership
multi-Servers/versions HA, mise à jour des identifiants sur les mêmes objets
registry.id, maintien des entity_id/unique_id/settings/history et rollback.
Remplacer int par str dans DeviceInfo seul crée des doublons/orphelins ; interdit.
Même une migration préservant les IDs d'objets change les identifiants et nécessite
une décision utilisateur. Le parent nullable requiert aussi spécifier préserver
ou retirer le lien, omission et None n'étant pas à confondre arbitrairement.

## Travail encore local / amont / autorisation

- Local sûr : scénarios réellement manquants de rappels voix/volume/échecs,
  associations par familles et multi-entrées ;20/42 modules encore <=95% lignes.
  Repairs et vidéo n'avancent que sur observation disponible, pas commande-probe
  ni nouveau polling de reprise fictif. Ces règles globales restent todo.
- SDK externe : injection/ownership de session publique et close partiellement
  initialisé ; pas d'accès aux attributs privés pour fabriquer conformité.
- Décision architecture/migration : choix ci-dessus, identité physique/host/token,
  options de polling et unités historiques ; pas de modification imposée.
- Publication/revue officielle :13 réserves documentaires distinctes du contenu
  local disponible ; brands/core/contribution HA hors mandat sans autorisation.

## Cohérence des preuves

Quatre commentaires YAML étaient périmés : config-flow-test-coverage,
test-coverage, entity-translations, strict-typing. La matrice et le YAML sont
maintenant comparés pour les54statuts/commentaires, avec contrôle négatif
explicitement périmant une preuve. Cela corrige une lacune d'audit locale,
pas un nouveau critère officiel done ni une certification.
