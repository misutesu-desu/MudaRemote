**🆕 MudaRemote v5.2.1**

### 🐛 Bug Fixes
- **Spheres No Longer Skipped Mid-Batch:** On your own rolls, sphere clicks that were still waiting for `$tu` counted as used, so the bot skipped every sphere until the batch ended. It now goes by the real count from `$tu` and keeps clicking.
- **No More Claim Loop on Edited Wishes:** Mudae edits a roll every time someone clicks a button on it, and the bot rechecked the claim and paused your rolls on each edit. It now checks a wished roll once, and your own rolls are no longer treated as snipes.
- **Lurker Panic Dump Starts in Time:** With a short Panic Roll time, the dump began too late to finish before the reset and the rolls were pushed to the next cycle. The panic window now opens early enough for all your rolls.

Restart the bot after updating.
