# Freebox Homexa - Home Assistant Custom Component

This integration allows you to integrate **Freebox Home** devices into Home Assistant under the name `freebox_homexa`.

**Version:** 28.8.0 — requires Home Assistant **2026.8.0** or newer (`via_device_id`).

## 🚀 Installation

1. Use **HACS** to install automatically or manually copy this repository into your `custom_components/freebox_homexa` directory.
2. Restart Home Assistant.
3. Add the integration via the UI.

## 🎧 Features

This integration supports:

- 📡 **Automatic detection of Freebox Home devices**
- 🎧 **Control of connected switches**
- 📷 **Access to Freebox Home cameras**
- 🚪 **Shutter control**
- 🚨 **Freebox Home alarm** (Présent / Absent / Désarmé, detectors, remote)
- 📍 **Tracking of Wi-Fi connected devices**
- 📡 **Free Wi-Fi repeaters (F-RP01A)** as connectivity sensors
- 📺 **Freebox Player Devialet / Mini 4K / Pop** as media players
- 📹 **Player remote + sources TV / HDMI (CEC) / YouTube / Netflix**
- 🔔 **Notifications for motion detection**

## ⚡ Configuration

Add this to your `configuration.yaml`:

```yaml
freebox_homexa:
  host: "192.168.X.X"
  token: "YOUR_TOKEN"
```

HDMI on the Player is the **output toward the TV** (CEC One Touch Play), not a TV HDMI input switch.

## 📖 Granting Access Rights

### 📌 Step 1: Verify your Freebox Delta

Here is the **Freebox Delta**, which is compatible with this integration:

![Freebox Delta](https://www.mezabo.fr/wp-content/uploads/2023/06/freebox-delta-vs-revolution.png)

### 📌 Step 2: Enable Permissions in Freebox OS

As explained during setup, follow these steps:

1. Go to [mafreebox.freebox.fr](http://mafreebox.freebox.fr/#Fbx.os.app.settings.Accounts).
2. Open the **Application** tab.
3. **Grant all necessary permissions** to the Home Assistant application.

Here is a preview of the Freebox OS interface showing where to enable permissions:

![Freebox OS - Access Management](https://djynet.net/wp/wp-content/uploads/2013/09/Capture-du-2013-10-03-194332.png)

## 💡 Tips

- **Enable the Freebox Home API** in your Freebox settings.
- **Use Home Assistant automations** to trigger actions based on sensor states.
- **Regularly update this component** to benefit from the latest improvements.
- Player remote code: on the Player go to **Réglages → Système → Informations**.

## 🛠️ Troubleshooting

If you encounter issues:

- Check that your **Freebox Server is on the same network** as Home Assistant.
- Look at the Home Assistant logs (`Settings > Logs`) for any errors.
- Restart Home Assistant after updating the component.

## 🤝 Contributions

Contributions are welcome! Fork the project, add your improvements, and submit a Pull Request.

## 📜 License

MIT - Free use under the condition of mentioning the original project.
