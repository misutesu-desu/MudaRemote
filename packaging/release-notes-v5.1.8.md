**🆕 MudaRemote v5.1.8**

### 🐛 Bug Fixes
- **Spheres No Longer Ignored After the Quota Resets:** Once your sphere quota was full, the bot kept skipping spheres until you restarted it, even after the quota came back. It now clicks a sphere when one shows up and checks `$tu` to confirm.
- **Skipped Spheres Show in the Log:** When the bot leaves a sphere alone because your quota is used up, it now says so.
- **`$mk` Keeps Going After a Fast Reply:** If Mudae answered `/mk` very quickly, the bot could miss the reply, wait 45 seconds and skip the rest of your `$mk` rolls. Fast replies are now matched correctly.
- **Claim Emoji Warning:** If a wished or valuable roll uses a heart that is not in your Claim Emojis, the bot now writes a warning instead of skipping it silently.

Restart the bot after updating.
