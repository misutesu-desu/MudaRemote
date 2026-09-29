**🆕 MudaRemote v4.10.0**

### ✨ New Features
- **Manage Bot Sessions (Opt-In):** Use the runtime API to start, stop, restart, and update individual bot sessions without disrupting your other accounts.
- **Live Update Feedback:** When using the runtime API, see whether a preset change is waiting, applied, rejected, or requires a restart.

### 🐛 Bug Fixes
- **Safer Stops and Restarts:** Prevent sessions from staying active in the background after shutdown or overlapping during a restart.
- **Clearer Connection Failures:** Connection problems now produce a clear failure status after limited retries instead of leaving a session appearing active indefinitely.

### ⚡ Improvements
- **Protected Account Details:** Account credentials stay hidden in runtime messages and are not saved to local preset or log files during bot sessions.
- **Familiar Bot Behavior:** Keep the same claim, roll, kakera, wishlist, and scheduling behavior, including the Smart Timing fix from v4.9.8.

Restart the bot after updating.
