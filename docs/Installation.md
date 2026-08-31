# Installation

## Via HACS (recommandé)

Pas encore dans le store HACS officiel. Dépôt custom :

1. HACS → **Dépôts personnalisés**
2. URL : `https://github.com/XAV59213/freebox_homexa`
3. Type : **Integration**
4. Installer **Freebox Homexa**
5. Redémarrer Home Assistant

## Manuelle

Copier `custom_components/freebox_homexa` vers `/config/custom_components/freebox_homexa` puis redémarrer.

## Appairage

1. Paramètres → Appareils et services → Ajouter une intégration → **Freebox Homexa**
2. Indiquer l’hôte (`mafreebox.freebox.fr` ou `xxxxx.fbxos.fr`)
3. Valider sur l’écran de la Freebox
4. Freebox OS → Applications : accorder Home, Player, LAN, etc.

Raccourci : [ajouter l’intégration](https://my.home-assistant.io/redirect/config_flow_start/?domain=freebox_homexa)
