**🆕 MudaRemote v4.9.4**

### 🐛 Bug Fixes
- **Light Kakera:** Collected Light Kakera now confirms correctly, preventing unnecessary retries and keeping your remaining reaction power accurate.
- **Auto `$dk`:** Power refills now respect your configured threshold after confirmed Kakera collection, without waiting for the next `$tu` check. Auto `$dk` and power management must be enabled, with a `$dk` available.
- **No Repeated Auto `$rolls`:** A missing confirmation no longer causes repeated `$rolls` attempts or redundant status checks during the same roll cycle.
- **Rolling Resumes After Reset:** Roll batches postponed because the next reset is too close, including saved rolls from `$us`, now resume automatically in the next cycle instead of remaining idle. Shared reset timing from another account no longer makes an account skip its pending reset.
- **Timing Variation:** Setting the random wait before `$tu` to `0`, or disabling Timing Variation, no longer adds an unwanted delay before status checks and stacked rolls. Configured random waits no longer receive an extra account-based delay either.

### ⚡ Improvements
- **Sleep Schedule Without Extra Waiting:** Keep Timing Variation enabled with random wait and patience both at `0` to use your sleep schedule without extra waiting outside sleeping hours. Startup staggering and normal command pacing remain unchanged.
- **Clearer Sphere Logs:** Sphere clicks are clearly labeled and no longer appear as duplicate Kakera clicks, making collection activity easier to follow.

Restart your bot after updating to apply these fixes.
