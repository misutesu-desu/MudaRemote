**🆕 MudaRemote v4.9.4-beta.1**

### 🐛 Bug Fixes
- **Light Kakera:** Collected Light Kakera now confirms correctly, preventing unnecessary retries and keeping your remaining reaction power accurate.
- **Auto `$dk`:** Refills now respond to your configured power threshold after a confirmed Kakera click, without waiting for the next `$tu` check. Auto `$dk` and power management must be enabled, with a `$dk` available.
- **Sphere Logs:** Sphere clicks are clearly labeled and no longer appear as duplicate Kakera clicks.
- **Quieter Auto `$rolls`:** A missing Discord acknowledgement no longer makes the bot repeat the same `$rolls` attempt or request redundant status checks in that roll interval.
