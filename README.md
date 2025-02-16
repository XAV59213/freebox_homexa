Test En cour ...
# Freebox Home Add-on pour Home Assistant

Cette intégration prend en charge les volets de base ainsi que tout le système d’alarme intégré (panneau de commande d’alarme, caméra, détecteur de mouvement, lecteur d’ouvre-porte, télécommande)

## Installer
Utilisez HACS pour installer ou copier dans votre répertoire HA

## Accorder le droit d’accès
Comme expliqué lors de la configuration, vous devez vous rendre dans : http://mafreebox.freebox.fr/#Fbx.os.app.settings.Accounts, ouvrir l’onglet « application » et ajouter tous les accès à l’application Home assistant
# Freebox Homex - Home Assistant Custom Component

Ce composant permet d'intégrer les équipements **Freebox Home** dans Home Assistant sous le nom `freebox_homex`.

## Installation

1. Téléchargez ce dépôt et placez-le dans le dossier `custom_components/freebox_homex` de votre installation Home Assistant.
2. Redémarrez Home Assistant.
3. Ajoutez l'intégration via l'interface UI.

## Fonctionnalités

- 📡 Détection des équipements Freebox Home
- 🎛 Gestion des interrupteurs connectés
- 📷 Accès aux caméras Freebox Home
- 📍 Suivi des appareils connectés au Wi-Fi

## Configuration

Ajoutez ceci à votre `configuration.yaml` :

```yaml
freebox_homex:
  host: "192.168.X.X"
  token: "VOTRE_TOKEN"
```

## Contributions

Les contributions sont les bienvenues ! Forkez le projet et soumettez vos pull requests.

## Licence

MIT - Utilisation libre sous conditions de mention du projet d'origine.

