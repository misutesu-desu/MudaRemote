**🆕 MudaRemote v4.9.5-beta.4**

### 🐛 Bug Fixes
- **Key Limit Pause:** Reaching your server's key limit, including 2,200 keys, now holds the recovery pause instead of repeatedly checking `$tu` and trying another roll. Queued rolls and automatic roll refills stay paused until recovery, then the bot checks your status before resuming.
- **Ready Rolls Getting Stuck:** Fixed a pre-roll `$tu` loop where a pending Kakera power update could keep available rolls waiting even with a claim ready. Normal rolling can continue while power is reconciled; Auto `$mk` still waits for confirmed power.

Restart your bot after updating to apply these changes.
