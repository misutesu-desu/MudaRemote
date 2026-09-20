**🆕 MudaRemote v4.9.5-beta.2**

### 🐛 Bug Fixes
- **Perk 8 Kakera Colours:** Your Ouroperk 8 colour override now requires the visible Perk 8 marker. A four-button layout alone no longer makes the bot collect orange or other colours excluded from your normal/Chaos selection.
- **Kakera at the Key Limit:** Key-limit notices no longer discard collectible Kakera on that roll, and limits such as 2,200 keys are recognized. Your selected filters, colours, and power requirements still apply.
- **Auto `$rolls` Claim Hour:** The final-claim-hour option now follows the current claim-reset timer instead of a stale round number, preventing daily rolls from being used early.
- **Claims After Extra Rolls:** Before claiming from a collected batch, the bot checks that the card is still available and skips stale cards for the next eligible candidate. Disabled claim buttons are no longer clicked.
- **Faster Claim Recovery:** Uncertain claims and manual `$rt` acknowledgement timeouts no longer wait behind the normal randomized `$tu` delay, including in snipe-only mode.
- **More Accurate Claim Results:** Server nicknames are recognized during claim verification. A consumed claim shown by `$tu` alone no longer announces a successful character claim or triggers post-claim actions.
- **Fewer Unnecessary `$tu` Checks:** Finishing a roll batch no longer revives status requests that were already resolved. Checks needed for uncertain counts or newly added rolls remain in place.

### ⚡ Improvements
- **Updated Preset Example:** The shipped example now includes the Perk 8, Shop 7, All/Any filter, and hourly `$tu` options. Existing personal presets and tokens are preserved.

Restart your bot after updating to apply these changes.
