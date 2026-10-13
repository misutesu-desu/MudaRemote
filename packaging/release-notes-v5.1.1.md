**🆕 MudaRemote v5.1.1**

### 🐛 Bug Fixes
- **No More Login Crash With `list index out of range`:** When the Discord info service the bot uses at login was down, the bot could crash on start and keep crashing on every restart. It now logs in normally even when that service is down.
- **Spanish Wishes Are Recognized:** On servers where Mudae is set to Spanish, characters showing "Deseado por" with your name were not treated as your wish. The bot now sees them as your own wishes.

Restart the bot after updating.
