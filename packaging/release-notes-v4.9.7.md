**🆕 MudaRemote v4.9.7**

### ⚡ Improvements
- **Live Preset Updates:** Changes to supported settings now reach running accounts without reconnecting the bot. Settings that affect account or channel lifecycles still clearly indicate when a restart is required.
- **Scheduled Auto $dk:** Auto $dk can now be limited to a daily local-time window, preventing repeated use during later status checks.
- **Background Actions During Long Waits:** Independent sphere and reward actions can be processed before long claim or roll waits, so available resources are not left idle.
- **Android Runtime Controls:** Mobile runtime updates and live preset changes now use the same guarded lifecycle flow, reducing unnecessary restarts and keeping active sessions consistent.

### 🐛 Bug Fixes
- **Rolls Before Claim Reset:** When rolls are available shortly before a claim reset, the bot now starts the roll batch after its planned timing wait instead of repeatedly sending `$tu` and waiting on the rounded `1 min` response.

Restart the bot after updating to apply the release.
