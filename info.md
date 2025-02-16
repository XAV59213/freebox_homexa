# Freebox Homexa - Home Assistant Custom Component

This integration allows you to integrate **Freebox Home** devices into Home Assistant under the name `freebox_homexa`.

## 🚀 Installation

1. Use **HACS** to install automatically or manually copy this repository into your `custom_components/freebox_homexa` directory.
2. Restart Home Assistant.
3. Add the integration via the UI.

## 🎛️ Features

This integration supports:

- 📡 **Automatic detection of Freebox Home devices**
- 🎛️ **Control of connected switches**
- 📷 **Access to Freebox Home cameras**
- 🚪 **Shutter control**
- 🚨 **Full integration with the Freebox Home alarm system (alarm panel, motion detectors, door opener detectors, remote control, etc.)**
- 📍 **Tracking of Wi-Fi connected devices**
- 🔔 **Notifications for motion detection**

## ⚙️ Configuration

Add this to your `configuration.yaml`:

```yaml
freebox_homexa:
  host: "192.168.X.X"
  token: "YOUR_TOKEN"
```

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

## 🛠️ Troubleshooting

If you encounter issues:

- Check that your **Freebox Server is on the same network** as Home Assistant.
- Look at the Home Assistant logs (`Settings > Logs`) for any errors.
- Restart Home Assistant after updating the component.

## 🤝 Contributions

Contributions are welcome! Fork the project, add your improvements, and submit a Pull Request.

## 📜 License

MIT - Free use under the condition of mentioning the original project.

