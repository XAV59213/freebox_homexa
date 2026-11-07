# Jalon16 — convergence, sans certification ni migration

## Les31 TODO ne sont pas31 défauts locaux interchangeables

Le statut officiel reste **21done /31todo /2exempt**. Aucune réserve n'est
convertie en exemption pour augmenter le score. Pour cette intégration HACS,
la publication/revue de documentation home-assistant.io est hors du livrable
local actuel, pas une absence des treize contenus déjà écrits et vérifiés.

| Nature principale | Règles TODO (comptées une seule fois) | Suite réellement nécessaire |
|---|---|---|
| Placement/revue documentaire officielle,13 | docs-actions, docs-high-level-description, docs-installation-instructions, docs-removal-instructions, docs-configuration-parameters, docs-installation-parameters, docs-data-update, docs-examples, docs-known-limitations, docs-supported-devices, docs-supported-functions, docs-troubleshooting, docs-use-cases | Guide local lié au README et preuves existantes ; pas de soumission officielle autorisée, pas de certification/exemption inventée. La matrice matériel exhaustive n'est pas démontrée. |
| Livraison/contrainte amont,3 | brands, dependency-transparency, inject-websession | Branding officiel non publié ; provenance1.3.1 démontrée mais pin exact incompatible avec hassfest custom ; session/close publics SDK à améliorer en amont. Aucun accès nouveau ni contournement privé. |
| Identité/migration sensible,7 | entity-unique-id, unique-config-entry, reauthentication-flow, discovery, discovery-update-info, reconfiguration-flow, stale-devices | Préparer contrat physique/MAC/adresses/jetons et plan réversible avant toute migration. Le nettoyage global demande encore preuves multi-intégrations ; ce n'est pas intégralement un blocage SDK. Aucun ID/nom RAID modifié. |
| Architecture/compatibilité,4 | appropriate-polling, config-entry-unloading, entity-unavailable, entity-device-class | Option polling et fréquences à déprécier sans perdre les réglages ; refus de rollback HA, FFmpeg partiellement ouvert et SDK close non garanti ; projection vidéo/Home à concevoir ; dB/dBm/garage non déduits du libellé. Des propositions et caractérisations restent locales, pas des impossibilités universelles. |
| Lacunes locales encore traitables,4 | devices, repair-issues, strict-typing, test-coverage | Associations multi-modèles ; inventaire Repairs appareil/action sans commande-probe ; modules stricts restants ; scénarios natifs utiles et couverture par module. Ne pas bloquer ces travaux indépendants en étendant indéfiniment la caméra/Repairs. |

Les catégories totalisent13+3+7+4+4=31. Plusieurs réserves ont des dépendances
transversales ; cette partition sert la priorité, pas une preuve de conformité.
Les seules exemptions restent l'absence de conditions et de triggers.

## Seuil de couverture effectivement relu

Source officielle ouverte pendant ce jalon :
https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/test-coverage/
(redirige vers contributors.home-assistant.io/core/quality-scale/test-coverage/).
Elle demande **plus de95% du code dans chaque module**, sans exception ;
un total global à95% ne suffirait donc pas. L'exemple officiel utilise le
rapport de lignes. Les branches restent mesurées et publiées séparément ;
on ne leur invente pas un seuil officiel distinct absent de cette page.
Les changements de config_flow.py et diagnostics.py ont en outre des attentes
spécifiques de couverture du diff. Aucun module n'est omis du rapport local/CI.

## Typage : contrat réel, pas faux schéma

Les protocoles SDK locaux décrivent uniquement les appels publics existants de
Home, Wi-Fi, appels, programmes TV et configuration système. Tous renvoient
`object`, **pas** un dictionnaire promis par un SDK non annoté. Les réponses
Home/TV sont bornées avant consommation ; setup valide dictionnaire à clés
texte, MAC texte et nom de modèle texte avant de déclarer sa sonde réussie.
Les valeurs valides restent exactes : pas de str() sur une MAC invalide,
pas de migration d'identité, copie des autres champs système sans conversion.
Le callback de sauvegarde est réellement `None`, le Store déclare sa donnée
persistée `dict[str, object]`. Aucune session SDK privée n'est touchée.

SDK1.3.1 réel avec transport synthétique : corps et chemins Wi-Fi/appels
inchangés, erreur traduite puis reprise ; TV dictionnaire/liste, timestamp
millisecondes, collection invalide/None puis vraie reprise (vraie liste vide disponible) ; identité ScannerEntity
native conservée (MAC réelle, et non `_attr_unique_id` ignoré par HA).
La MAC est validée **avant** calcul du nom, sans convertir une valeur invalide.

Imports canoniques HA réels : ScannerEntity dans device_tracker.entity,
CameraEntityFeature dans camera.const et constantes dans ffmpeg. Le module
ScannerEntity existe également dans le minimum déclaré HA2026.8.0 (source
publique vérifiée). Les simulations héritées exposent désormais ce même module
canonique ; elles ne remplacent pas les tests du vrai framework.

Restes exacts : config_flow25, router20, tnt_reminders17, tnt_ws16,
base_class16, calls_ws9, sensor1, camera1 = **105 diagnostics /8 fichiers**.
Six modules précédemment en erreur n'en ont plus : __init__, entity, calendar,
button, switch, device_tracker ; sdk_contracts est aussi vérifié. Cela ne
supprime pas leurs frontières `Any` historiques par magie et ne ferme pas la
règle globale strict-typing. Aucun Any/cast/ignore ajouté.

- Schémas : minimum HA2026.8 utilise voluptuous ; HA2026.10.4 utilise probatio
  et son shim runtime. Il faut une vraie stratégie multiversion testée, pas un
  alias TYPE_CHECKING différent du runtime ou un import dynamique cachant Any.
- Ancien base_class : DUMMY importé mais absent, `any` utilisé comme type,
  contrat historique DeviceInfo avec ID entier. Ne pas supprimer ce module ou
  convertir cet ID pour le score ; dette locale à réhabiliter/caractériser.
- Disques : ID entier historique incompatible avec annotation DeviceInfo str ;
  une annotation générique Any ne constitue pas une correction.
- Caméra : FreeboxHomeEntity.name peut réellement être None (nom relatif),
  FFmpegCamera.name promet str. Ne pas forcer un nom vide ou réintroduire un
  libellé source pour faire disparaître ce conflit d'héritage.

Repairs global et disponibilité globale caméra restent TODO avec les limites
de docs/quality-scale-repair-inventory.md. Une image foreground n'est pas un
état vidéo continuellement observé. Pas de polling inventé, pas de commande
réelle, pas de modification repeater/privacy/préférences/historiques.

## Concordance et ordre réel des plateformes

Deux runs ont révélé une ligne/branche media_player initialisant le cache partagé
présente seulement selon l'ordre concurrent de forwarding HA. Comme pour Remote
au jalon15, le test impose par l'API publique un scénario media_player-first puis
les autres plateformes, en plus de remote-first. Chaque scénario prouve un seul
fetch metadata et le cycle setup/unload réel, sans forger le cache ni omettre la
branche. Les runs antérieurs609tests ne sont pas des preuves finales610tests.
