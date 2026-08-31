# Dépannage

| Erreur / symptôme | Cause probable | Correctif |
|---|---|---|
| `via_device` deprecated | HA 2026+ | Version **28.8.x** (`via_device_id`) |
| `bad_json` sur une commande Home | Payload API incomplet | 28.8+ envoie `{"value": ...}` |
| Alarme : 2 boutons seulement | Slot Présent non exposé | 28.8+ |
| Répéteur absent | Hôte LAN pas encore vu | Redémarrer HA, vérifier que le F-RP01A est allumé |
| Player introuvable | Droit API / version Player | Droits Player dans Freebox OS |
| HDMI ne change pas l’entrée TV | Limite CEC | Attendu : réveil TV seulement |
| Setup entry échoue au chargement d’une plateforme | Fichier plateforme manquant ou syntaxe | Mettre à jour + redémarrer |

Filtre de logs : `custom_components.freebox_homexa`.

Discute tes tests ici : https://github.com/XAV59213/freebox_homexa/issues/22
