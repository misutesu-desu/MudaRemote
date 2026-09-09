**🆕 MudaRemote v4.9.1-beta.6**

### 🐛 Bug Fixes
- **Version switching no longer freezes the window:** Installing or switching to any release now runs in the background with a live progress bar and status text — fetching release info, downloading each file, verifying, applying. MudaRemote stays responsive the whole time.
- **Old releases install correctly again (v4.6.4 and similar):** Some historical releases pointed their executable download at the moving "latest" alias, so selecting them compared an old checksum against the newest build and failed. Selecting a past release now always fetches that release's own executable, and downgrading completes normally.
- **Precise download mismatch reporting:** If a download ever fails its integrity check, the error now names the exact file, its download address, and the full expected versus received checksums — so the problem is obvious at a glance instead of a truncated mystery.

### ⚡ Improvements
- **One update at a time:** While an install or update check is running, the update buttons are locked and a progress indicator is shown; a second attempt cannot be started accidentally. Controls are restored automatically on failure, cancellation, or any outcome that does not restart the app.
- **Real error messages in the popup:** A failed version switch now shows the actual reason (including which file failed verification) in the error dialog instead of only a "check logs" hint.

### 🛠️ Technical Changes
- Exact release selection now validates that the fetched manifest identifies the same version as the selected tag, and refuses manifests whose executable points at a different published release — before anything is downloaded. All SHA-256 verification remains fully enforced.
