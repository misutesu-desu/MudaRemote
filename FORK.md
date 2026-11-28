# MudaFork — how this fork is kept

MudaFork is a fork of MudaRemote (MIT). It is Android-first: the Android app is the product, the desktop build is kept working.

## Two kinds of update

- **Code update (in-app, no reinstall).** The bot logic is Python that the app downloads and swaps itself, checking each file's hash. The app reads `version.json` from this repository's `main` branch. To ship one: raise `CURRENT_VERSION` in `mudae_core/versioning.py`, run `python build.py --update-source-manifest`, write the notes file under `packaging/`, merge to `main`.
- **App update (APK).** Needed only when the Android shell changes (service, UI, updater). Raise `versionCode` and `versionName` in `android/app/build.gradle.kts`, then run the «Android Release» workflow. The in-app updater offers `MudaFork-<version>.apk` from this repository's releases and installs it only if it is signed with the same key.

The app never downloads anything from the original repository.

## Borrowing from the original

```
git remote add upstream https://github.com/misutesu-desu/MudaRemote.git
git fetch upstream
git checkout -b sync-upstream work-mudafork
git merge --no-ff upstream/main
```

Expect conflicts only where the rename touched the original's files: `mudae_core/versioning.py` (links and version), `README.md`, `.github/workflows/`, `version.json` (always regenerate it instead of merging by hand), `android/app/build.gradle.kts` (application id, version) and visible strings in `MainActivity.kt` / `UiTheme.kt`. Keep the fork's side for links and names, take the original's side for logic. Then run the tests and let CI compile.

## What the fork adds (each in its own module, thin hooks in `mudae_bot.py`)

| Feature | Module |
|---|---|
| Side accounts rolling for the main | profile roles in `mudae_core/bot_config.py`, coordinator hooks |
| Totals from the existing `$tu` and sphere results | `mudae_core/totals.py`, `account_state.py` |
| Fast setup (sent once) | `mudae_core/fast_setup.py` |
| Kakera give | `mudae_core/kakera_give.py` |
| Character give and the list reader | `mudae_core/harem_give.py`, `harem_list.py` |
| Perk 10 upgrade | `mudae_core/perk_upgrade.py` |
| Sphere give | `mudae_core/sphere_give.py` |
| Logs and TXT export | `mudae_core/logs.py` |
| Keep running, app updater, theme (Android) | `KeepAlive.kt`, `AppUpdate*.kt`, `UiTheme.kt` |

The Python modules carry no fork naming, so any of them can be offered to the original as a patch together with its test file.
