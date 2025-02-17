# Freebox Homexa - version beta testeurs
Version stable 25.2.17
# Freebox Homexa - Home Assistant Custom Component

Ce composant permet d'intégrer les équipements **Freebox** **Freebox Home** **Freebox Connect** dans Home Assistant sous le nom `freebox_homexa`.

## 🚀 Installation

1. Utilisez **HACS** pour installer automatiquement l'intégration ou copiez ce dépôt dans votre répertoire `custom_components/freebox_homexa`.
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
freebox_homexa:
  host: "192.168.X.X"
  token: "VOTRE_TOKEN"
```

## 📖 Autorisation d’accès

### 📌 Étape 1 : Vérifier votre Freebox Delta

Voici l’image de la **Freebox Delta** compatible avec cette intégration :

![Freebox Delta](https://www.mezabo.fr/wp-content/uploads/2023/06/freebox-delta-vs-revolution.png)

### 📌 Étape 2 : Activer les autorisations dans Freebox OS

1. Rendez-vous sur [mafreebox.freebox.fr](http://mafreebox.freebox.fr/#Fbx.os.app.settings.Accounts).
2. Allez dans l'onglet **Application**.
3. **Ajoutez tous les accès nécessaires** à Home Assistant.

Voici un aperçu de l’interface Freebox OS montrant où activer les autorisations :

![Interface Freebox OS - Gestion des accès](https://djynet.net/wp/wp-content/uploads/2013/09/Capture-du-2013-10-03-194332.png)

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


