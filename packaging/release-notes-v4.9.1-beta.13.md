**🆕 MudaRemote v4.9.1-beta.13**

### 🐛 Bug Fixes
- **Idle account recovery:** Exhausted status snapshots now expire, and an empty roll count no longer teaches the bot to expect zero rolls after future resets. This prevents a path that could leave accounts stuck skipping $tu and rolling.
- **Sphere games and rolls:** Bonus rolls wait for an active sphere game to finish, and new games wait while bonus rolls are pending. Puzzles and roll commands no longer interrupt each other.
- **Perk 8 after 40 clicks:** The four-button spawn with doubled sphere rewards now uses your Perk 8 color selection even after the gem disappears. Power checks still reflect the discounts actually available.

### ⚡ Improvements
- **Faster multi-account status checks:** Reduced the extra wait between queued $tu checks from 20 seconds to 2 seconds, helping large account groups resume sooner after resets. Your configured activity and quiet-channel settings still apply.
