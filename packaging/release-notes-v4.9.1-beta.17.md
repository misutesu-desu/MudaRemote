**🆕 MudaRemote v4.9.1-beta.17**

### 🐛 Bug Fixes
- **Android Stop:** Fixed a cleanup issue that could leave the notification stuck on "Stopping" and prevent queued runs from starting.
- **Save while running:** Saving an active Android profile now restarts the active profiles to apply your changes. The app tells you when the restart is requested.
- **Account recovery:** Unexpected roll errors now trigger a fresh status check and retry, helping accounts recover instead of staying idle.
- **Sphere minigames:** Separate-use mode now plays one `$oh` board per use even with cached status. Boards run one at a time, combined uses stay within the 10-use limit, and an unfinished board pauses further minigames before retrying.
- **Separate Kakera filters:** Chaos Key Only and Perk 8 Only are now separate choices. Chaos Key requires 10+ keys on your own roll; Perk 8 requires the visible 💎 / 2 marker. To collect Perk 8 OR Shop 7, enable those two filters, choose Any and leave Chaos Key off. Choose All to require both. Your colors, power limits and free-Kakera settings still apply.

### ✨ New Features
- **Hourly status refresh:** Enable "Hourly $tu Refresh" on Windows or Android to request fresh status after an hour without a complete `$tu`. Active rolls finish first, and normal command pacing still applies.
