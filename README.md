# Freebox Homex - Home Assistant Custom Component

Ce composant permet d'intégrer les équipements **Freebox Home** dans Home Assistant sous le nom `freebox_homex`.

## 🚀 Installation

1. Utilisez **HACS** pour installer automatiquement l'intégration ou copiez ce dépôt dans votre répertoire `custom_components/freebox_homex`.
2. Redémarrez Home Assistant.
3. Ajoutez l'intégration via l'interface UI.

## 🎛️ Fonctionnalités

Cette intégration prend en charge :
- 📡 **Détection automatique des équipements Freebox Home**
- 🎛️ **Gestion des interrupteurs connectés**
- 📷 **Accès aux caméras Freebox Home**
- 🚪 **Contrôle des volets roulants**
- 🚨 **Intégration du système d’alarme Freebox (panneau d’alarme, détecteurs, télécommande, etc.)**
- 📍 **Suivi des appareils connectés au Wi-Fi**
- 🔔 **Notifications en cas de détection de mouvement**

## ⚙️ Configuration

Ajoutez ceci à votre `configuration.yaml` :

```yaml
freebox_homex:
  host: "192.168.X.X"
  token: "VOTRE_TOKEN"
```

## 📖 Autorisation d’accès

Comme expliqué lors de la configuration, vous devez accorder les droits d’accès à Home Assistant :
1. Rendez-vous sur [mafreebox.freebox.fr](http://mafreebox.freebox.fr/#Fbx.os.app.settings.Accounts).
2. Allez dans l'onglet **Application**.
3. Ajoutez **tous les accès** nécessaires à Home Assistant.

## 💡 Astuces

- **Activez l’API Freebox Home** dans les paramètres de votre Freebox.
- **Utilisez des automatisations Home Assistant** pour déclencher des actions en fonction de l’état des capteurs.
- **Mettez à jour régulièrement** ce composant pour profiter des dernières améliorations.

## 🛠️ Dépannage

Si vous rencontrez des problèmes :
- Vérifiez que votre **Freebox Server est bien sur le même réseau** que Home Assistant.
- Consultez les logs Home Assistant (`Paramètres > Journaux`) pour voir les éventuelles erreurs.
- Redémarrez Home Assistant après toute mise à jour du composant.

## 🤝 Contributions

Les contributions sont les bienvenues ! Forkez le projet, ajoutez vos améliorations et soumettez une Pull Request.

## 📜 Licence

MIT - Utilisation libre sous conditions de mention du projet d'origine.

