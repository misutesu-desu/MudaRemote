**🆕 MudaRemote v4.10.1**

### 🐛 Bug Fixes
- **Kakera Reactions No Longer Get Stuck:** If Mudae told the bot it couldn't react to kakera right now and the bot couldn't read how long to wait, it could stop clicking kakera completely until you restarted it, and with no clicks your power was never used and `$dk` never ran. The bot now retries on its own after a few minutes, so you no longer need to restart it.
- **More Reliable `$dk` Refills:** When Mudae refused a `$dk` sent right after collecting kakera, the bot assumed it worked and didn't try again until the next status check, missing the kakera in your rolls. The bot now gives Mudae a brief moment before refilling, notices when `$dk` is refused, and retries right away.

Restart the bot after updating.
