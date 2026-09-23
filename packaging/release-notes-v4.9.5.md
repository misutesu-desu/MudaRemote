**🆕 MudaRemote v4.9.5**

### ✨ New Features
- **Kakera Loot on Mobile and Desktop:** Choose KL or GiveScrap in your profile, set the amount and cooldown, and let the bot handle confirmations and release duplicate pins with `$arlp`. Loot mode replaces normal rolling and sniping for that profile.
- **Shared Claim-Based Roll Switching:** Start with slash rolls for the claim bonus, then switch to faster text rolls once your running accounts have claimed your chosen character a total of X times in the same channel. The default window is three hours. Accounts must run in the same bot process; manual claims and other devices are not counted. The window starts when the feature is enabled and resets when the app closes, independently of Mudae's claim timer.
- **Optional Key Limit Pause:** Turn off Pause on Key Limit to keep rolling and collecting Kakera after reaching the key cap. The pause remains enabled by default, and Mudae's limits still apply.

### 🐛 Bug Fixes
- **Rolls Resume Reliably:** Fixed repeated `$tu` checks and stuck rolls around scheduled times, claim resets, and Auto `$rolls` recovery. Available rolls resume while respecting your patience settings, without immediately repeating an uncertain refill request.
- **More Accurate Claims:** Old messages, wish pings, and unrelated confirmations no longer count as successful claims. Server nicknames are recognized, stale or disabled claim cards are skipped, and uncertain claims recover sooner.
- **Daily Rolls in the Right Hour:** The claim-hour option now follows your current reset timer, preventing Auto `$rolls` from being used too early.
- **Kakera Colours and Collection:** Perk 8 overrides require the correct marker, collectible Kakera survives key-limit notices, and unknown reaction status no longer blocks otherwise eligible collection. Your selected colours, filters, and power limits remain respected.
- **Sphere and Power Recovery:** Selected spheres can resume after refreshed usage information, Chaos power discounts trigger a fresh power check, and reaction cooldowns are recognized more reliably.

### ⚡ Improvements
- **Android Controls:** KL/GiveScrap and shared claim-switch settings are available directly in the Android profile editor, with pause, stop, and reconnect support.
- **Existing Settings Preserved:** Your presets, tokens, colour selections, and update preferences stay intact. New automation features are opt-in.

Save your profile and restart the bot after updating.
