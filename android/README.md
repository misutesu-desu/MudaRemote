# MudaRemote Android

`app-debug.apk` packages the actual desktop `mudae_bot.py` runtime through
Chaquopy. The foreground service only stages the selected profiles and invokes
the same Python CLI entry point (`run_cli --all`), so Android and desktop share
the bot behavior. A notification-visible foreground service and partial wake
lock keep it running while another app is open or the screen is off. Android
force-stop always stops it, and some manufacturers also require excluding the
app from battery optimization.

## Install and run

1. Download `Mudaremote.apk` from the latest
   [Android pre-release](https://github.com/misutesu-desu/MudaRemote/releases)
   (or build it locally as below) on an Android 8.0 or newer device. Android
   will ask you to allow installs from the file manager used to open the APK.
2. Open MudaRemote and use **Import presets.json**. Every top-level preset is
   added to the profile selector, and every field in each preset becomes an
   editable Android control. Tokens are kept in a separate encrypted store.
3. Use **Import secrets** for an Android/Termux-compatible secrets JSON. A
   Windows `.mudae-secrets.json` normally contains DPAPI blobs, which are tied
   to the original Windows account and cannot be decrypted on Android; those
   profiles are listed and ask for token re-entry instead of pretending the
   encrypted blob is a Discord token.
4. Choose a profile and tap **Save and start selected profile**, or use **Save
   and start all profiles** to launch every saved profile. The **Runtime logs**
   panel updates while the service is running. Accept notification permission
   and leave the persistent MudaRemote notification enabled. Use **Battery settings** to
   exempt the app where your phone provides that option.
5. **Self-Updating Python Engine**: MudaRemote Android includes an automatic
   self-updater for the Python runtime. When starting or tapping **Check for Python updates**,
   it downloads, SHA-256 verifies, and loads the latest Python scripts directly into app
   storage without requiring a full APK reinstall. Use **Revert Python** to reset back to the
   bundled base version at any time.

Use the **Stop** button or the notification action to disconnect the active
Discord session. Do not share the APK, screen recordings, or exported JSON
while they contain a token.

## Build

On Windows with Android SDK Platform 35 installed, run:

```powershell
cd android
.\build-apk.ps1
```

The debug APK is signed with the local debug certificate. A production release
should be signed with a separate private upload key and tested on a physical
ARM64 phone, especially through screen-off and battery-optimization behavior.

## CI pre-releases

`.github/workflows/android-release.yml` builds `Mudaremote.apk` on GitHub
runners and publishes it as a pre-release. Trigger it from the Actions tab via
**Android Pre-Release → Run workflow** and provide a unique tag (for example
`android-pre1`). Re-running with an existing tag replaces the APK asset on
that release.
