**🆕 MudaRemote v5.2.0**

### 🐛 Bug Fixes
- **Lurker Holds The Last Round Again:** With Lurker Strategy on, a roll batch planned in an earlier round could still go out at the start of the last round. The bot now holds those rolls and dumps them at Panic Roll Start, with min kakera dropped like a normal panic dump.

### ⚡ Improvements
- **Clearer Snipe Channel Setting:** Character Snipe Channels now says that rolls outside your main channel are only sniped if that channel is listed.
- **Clearer `$rt` Warning:** When your `$tu` has no `$rt` line, the warning now mentions that you may not have `$rt` unlocked yet.

Restart the bot after updating.
