[![GitHub Release](https://img.shields.io/github/v/release/XAV59213/freebox_homexa?style=flat-square)](https://github.com/XAV59213/freebox_homexa/releases) [![hacs](https://img.shields.io/badge/HACS-Custom_Component-orange.svg?style=flat-square)](https://hacs.xyz/) [![GitHub Activity](https://img.shields.io/github/commit-activity/m/XAV59213/freebox_homexa?style=flat-square)](https://github.com/XAV59213/freebox_homexa/commits/main) [![Installs](https://img.shields.io/github/downloads/XAV59213/freebox_homexa/total?style=flat-square)](https://github.com/XAV59213/freebox_homexa/releases)  


☕ Soutiens nos codeurs et évite-leur une panne de caféine !
Parce que coder sans café, c’est comme une Freebox sans WiFi... ça ne fonctionne pas ! 😅

@gvigroux<a href="https://www.buymeacoffee.com/gvigroux"> <img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=gvigroux&button_colour=5F7FFF&font_colour=ffffff&font_family=Cookie&outline_colour=000000&coffee_colour=FFDD00" /> </a>
@XAV59213<a href="https://www.buymeacoffee.com/XAV59213"> <img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=XAV59213&button_colour=5F7FFF&font_colour=ffffff&font_family=Cookie&outline_colour=000000&coffee_colour=FFDD00" /> </a>

# Freebox Homexa - Home Assistant Custom Component

🚀 **Version Bêta - Testeurs**  
📌 **Version stable :** 25.2.17  

---

## 🔹 Présentation

Vous rêvez d’une **intégration complète de votre Freebox et des services Free** dans Home Assistant ?  
**Freebox Homexa** est là pour ça ! 🎉  

Ce **custom component** a pour objectif de **compiler et centraliser toutes les applications et services Free** au sein de Home Assistant. Que ce soit la gestion de votre Freebox, la télévision, le réseau ou encore d'autres services liés à l’écosystème Free, **tout est réuni en un seul composant** pour une expérience fluide et optimisée.

> 💡 **Ce projet est une initiative indépendante et n'est ni affilié ni supporté par Free.**  
> Tous les logos et marques mentionnés sont la propriété de leurs détenteurs respectifs.

---

## 🚀 Fonctionnalités principales

- ✅ **Contrôle total de votre Freebox** (réseau, WiFi, équipements, état système)
- ✅ **Gestion des chaînes TV** directement depuis Home Assistant
- ✅ **Pilotage des équipements connectés** compatibles Freebox
- ✅ **Statistiques avancées** sur votre connexion Internet
- ✅ **Notifications intelligentes** pour rester informé sur l’état de votre réseau et de vos services
- ✅ **Détection automatique** des équipements **Freebox Home**
- ✅ **Gestion des interrupteurs connectés**
- ✅ **Accès aux caméras Freebox Home**
- ✅ **Contrôle des volets roulants**
- ✅ **Intégration du système d’alarme Freebox** (panneau d’alarme, détecteurs, télécommande, etc.)
- ✅ **Suivi des appareils connectés au Wi-Fi**
- ✅ **Notifications en cas de détection de mouvement**

🔧 **En cours de développement :** Ajout d’intégrations avancées pour enrichir encore plus l’expérience !  

---

## 📌 Intégration actuelle

À ce jour, **Freebox Home** est déjà intégré avec :  
- 🔹 **Freebox Serveur** : Gestion complète de la box, réseau, WiFi, et équipements connectés  
- 🔹 **Freebox Player** : Contrôle du lecteur multimédia et des chaînes TV  

D’autres fonctionnalités sont en cours d’ajout pour offrir une expérience encore plus complète et fluide dans Home Assistant !

⚠️ **Version Bêta - Tests en cours** ⚠️  
Le projet est actuellement en **phase de test**, avec une **version bêta disponible**.  
Nous travaillons activement pour améliorer la stabilité et ajouter encore plus de fonctionnalités.  
📢 **Vos retours sont les bienvenus** pour perfectionner l’intégration !  

---

## 📥 Installation

### 1️⃣ Installation via HACS (recommandé)
- Ouvrez **HACS** dans Home Assistant.
- Cherchez **Freebox Homexa** et installez-le.
- Redémarrez Home Assistant.
- Ajoutez l’intégration via l’interface UI.

### 2️⃣ Installation manuelle
- Copiez ce dépôt dans votre répertoire `custom_components/freebox_homexa`.
- Redémarrez Home Assistant.
- Ajoutez l’intégration via l’interface UI.

---

### ⚙️ Setup  

Shortcut:  
[![](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=freebox_homexa)  

- Allez dans **Paramètres -> Intégrations -> Ajouter une intégration**  
- Cherchez **"Freebox Homexa"** et suivez les instructions dans le **config flow**.  

---

### ⚙️ Configuration manuelle

### 📌 Configuration de Freebox Homexa

Ajoutez cette ligne dans votre fichier **`configuration.yaml`** :  

```yaml
freebox_homexa:
  host: "192.168.X.X"
  token: "VOTRE_TOKEN"
```


### 📖 Autorisation d’accès

### 📌 Étape 1 : Vérifier votre Freebox Delta

Voici l’image de la **Freebox Delta** compatible avec cette intégration :

![Freebox Delta](https://www.mezabo.fr/wp-content/uploads/2023/06/freebox-delta-vs-revolution.png)

#### 📌 Étape 2 : Activer les autorisations dans Freebox OS

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


