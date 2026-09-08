**🆕 MudaRemote v4.9.1-beta.4**

### ✨ New Features
- **Target Version Picker (PC & Android):** You can now easily choose and switch to any MudaRemote release directly from the app!
  - **PC Preset Editor:** Click the new **"🎯 Switch / Pick Version..."** button in the sidebar to browse available releases or enter any version tag to install it instantly.
  - **Android App:** Tap **"🎯 Switch / Pick Version..."** in the Python Engine card to select and install any Python runtime release or download new APK versions.
- **Beta / Stable Channel Toggle:** Choose whether you want to receive preview releases or stay only on official stable updates with a single click.

### 🐛 Bug Fixes & Improvements
- **Fixed Preset Editor Startup Crash:** Resolved an `AttributeError` on `settings_container` during GUI initialization so the editor opens smoothly.
- **Safe & Reliable Windows Updates:** Complete update rewrite with automatic backup and rollback. If an update or launch fails, your previous version is restored automatically with your original settings and arguments intact.
- **Android Running Session Safety:** Background updates are staged cleanly without interrupting active bot sessions.
- **Protected Settings:** Your saved presets (`presets.json`) and update preferences (`settings.json`) are strictly protected and never touched during updates.
