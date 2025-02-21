# Changelog

## 2025.2.17 (Dernière mise à jour)
- Intégration du Freebox Player
- Ajout de la gestion des commandes `remote`
- Mise à jour de `services.yaml`
- Optimisation du dépôt Git avec `.gitignore`

## 2025.2.18 (modification structurelle)
'''code
--from homeassistant.components.device_tracker import SOURCE_TYPE_ROUTER, ScannerEntity
-+from homeassistant.components.device_tracker import SourceType, ScannerEntity
'''
