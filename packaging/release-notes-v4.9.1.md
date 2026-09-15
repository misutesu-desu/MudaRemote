**🆕 MudaRemote v4.9.1**

### ✨ New Features
- **Update Channels & Version Picker:** Choose stable or beta updates on Windows and Android, and upgrade, reinstall or return to a specific published version from the app.
- **All / Any Kakera Filters:** Decide whether paid Kakera must match every selected condition or just one. Combine Wish/Starwish, OP Perk 5, MK, Chaos Key, Perk 8 and Shop 7 rules to suit your collection goals.
- **Separate Perk Controls:** Chaos Key and Perk 8 now have separate options, giving you more control over which Kakera bonuses to collect.
- **Shop 7 Support:** Added a dedicated filter for Shop 7 double-reward Kakera, so you can focus your collection on crystals that give twice the rewards.
- **Hourly Status Refresh:** Enable an hourly status check to keep idle accounts up to date without interrupting an active roll batch.

### 🐛 Bug Fixes
- **Roll Resets & Recovery:** Fixed duplicate roll attempts near hourly resets and accounts getting stuck idle. When Mudae reports no rolls left, the affected account stops and checks its status before continuing.
- **Claims & Wishes:** Claims are recognized more reliably when Discord responds slowly. Wishes revealed through edited cards can now be claimed, and eligible pending claims resume after your manual `$rt` is confirmed.
- **Auto `$rt`:** Automatic `$rt` now works correctly on shorter claim cycles, including hourly claim resets.
- **Kakera Collection:** Dark Kakera transformations confirm correctly, free green Kakera and free bonus clicks remain collectible, and Perk 8 color choices keep working after its discount marker disappears.
- **Daily Commands & Sphere Games:** Ready daily commands are checked before rolling. Sphere games wait for rolls and claims to finish, track click limits more accurately, and respect the option to use `$oh` individually.
- **Android Presets:** Import shared single presets or full preset collections without prefix errors. Saving an active profile applies its changes through a controlled restart.
- **Slash Command Recovery:** Temporary slash-command failures fall back to text commands so rolls and status checks can continue.

### ⚡ Improvements
- **Clearer Timing:** The first status check runs promptly. Later random waits happen before `$tu`; eligible rolls start after its response once the channel is quiet, without a second random wait.
- **Smoother Windows Updates:** Version selection stays responsive, installs use the release you selected, and interrupted updates can recover while preserving your presets.
- **Consistent Android Updates:** Downloaded Python updates stay staged until you restart the bot, keeping the running session on one engine version. Version selection and stopping the bot are more reliable.
