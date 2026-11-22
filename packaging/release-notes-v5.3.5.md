**🆕 MudaRemote v5.3.5**

### ✨ New Features
- **Seconds in Time Settings:** Bot Sleep Schedule and Scheduled Roll Times now take seconds too, like `12:00:00-15:00:00` or `18:30:15`.

### 🐛 Bug Fixes
- **No More `$tu` Spam After a Missed Claim:** After a refused claim the bot could get stuck sending `$tu` every few seconds. It now waits for the next reset like it should.
- **Auto `$dk` Stops Wasting Refills:** Auto `$dk` no longer fires at full power on startup. Without a schedule it keeps the `$dk` until your power can't pay for a kakera anymore. A scheduled `$dk` still goes out at its time.

Restart the bot after updating.
