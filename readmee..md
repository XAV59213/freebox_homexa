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

## ⚙️ Setup  

Shortcut:  
[![](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=freebox_homexa)  

- Allez dans **Paramètres -> Intégrations -> Ajouter une intégration**  
- Cherchez **"Freebox Homexa"** et suivez les instructions dans le **config flow**.  

---

## ⚙️ Configuration manuelle

Ajoutez cette ligne dans votre `configuration.yaml` si nécessaire :

```yaml
freebox_homexa:
  host: "192.168.X.X"
  token: "VOTRE_TOKEN"
