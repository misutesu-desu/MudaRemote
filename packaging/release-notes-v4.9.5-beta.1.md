**🆕 MudaRemote v4.9.5-beta.1**

### 🐛 Bug Fixes
- **Scheduled Rolls:** Scheduled roll times now wake rolls that were waiting for a claim reset instead of silently leaving them paused. The safety pause near a roll reset remains in place.
- **Fewer Repeated `$tu` Checks:** Fixed an extra-status-check loop caused by a scheduled roll remaining marked as due after it had already been picked up.
- **Accurate Snipe Results:** Wish pings, ordinary roll messages, and old or unrelated confirmations no longer count as successful claims. A delayed Discord acknowledgement alone will not trigger a duplicate claim click.

### ⚡ Improvements
- **Kakera Filter Check:** Verified the reported Mai Sakurajima preset: paid Kakera must still match your selected colors and enabled filters. Selected spheres, purple Kakera, and free green-background buttons retain their existing exceptions; `min_kakera` controls character claims, not Kakera reactions.

Restart your bot after updating to apply these fixes.
