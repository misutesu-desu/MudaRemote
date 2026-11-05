**🆕 MudaRemote v5.2.7**

### 🐛 Bug Fixes
- **Correct Power With Spaced Numbers:** When Mudae writes numbers with spaces, like 7 210 keys, the bot missed the 10+ key discount and counted double the power for each kakera click. It now reads those numbers, kakera values and ranks correctly.
- **`$oh` No Longer Waits An Hour After The Refill:** If the daily refill showed up while the bot was playing `$oc` or `$oq`, it skipped `$oh` until the next hour. It now plays it in the same round.

Restart the bot after updating.
