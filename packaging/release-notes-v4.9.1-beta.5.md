**🆕 MudaRemote v4.9.1-beta.5**

### 🐛 Bug Fixes
- **Startup "Update check failed" message fixed:** The editor no longer errors out before checking for updates. A proper update check now runs every time MudaRemote starts, on your selected channel.
- **All releases are listed now:** The version picker loads the complete release history from GitHub instead of only the first page. Older versions are reachable again, and Android-only releases no longer crowd out PC releases.
- **Beta checkbox is respected in the version picker:** "Switch / Pick Version" now shows exactly what your update channel allows — stable-only on the Stable channel, previews when Beta is included. The picker also has its own beta toggle that refreshes the list instantly.
- **No more phantom releases:** If GitHub cannot be reached, the picker shows the real error with a Reload button instead of a fake short list that would fail to install.
- **Mouse wheel no longer scrolls the background:** Scrolling now affects only the panel your mouse is actually over. Lists and dialogs keep their own scrolling, and the settings page behind a popup stays put.
- **Old versions are installable again:** Picking an earlier release now fetches that release's own frozen files, so downgrading or reinstalling completes instead of failing with download mismatch errors.

### ⚡ Improvements
- **Clear results after installing or switching versions:** Git-managed folders get a friendly "use git pull" notice, script installs fully restart with the new files, and the EXE updater restarts the app for you instead of leaving mixed old/new code running.
- **Smarter Android version picker:** It respects your beta/stable setting, tells you honestly when nothing was found or the fetch failed, and APK rows open the actual published APK file instead of a guessed page.
- **Safer recovery after an interrupted update:** If a Windows update was killed halfway, the next start repairs or rolls back the leftover files automatically before the app opens.

### 🛠️ Technical Changes
- Stricter release manifest validation: manifests without a version or in a bad shape are rejected before anything is downloaded, and every checksum rule still applies to all installs.
