**🆕 MudaRemote v4.9.3**

### 🐛 Bug Fixes
- **Reliable Rolling:** Old roll timers no longer restart status checks while a batch is already running or waiting for a claim or reset.
- **Quieter Logs:** Repeated ambiguity and coalesced-status messages no longer flood the logs while the same status update is pending.
- **Smarter Reset Checks:** When no rolls remain and a known reset is within three minutes, the bot avoids an extra routine `$tu` or `/tu` check. Rolling still gets a fresh status check after the reset.
- **Extra Roll Availability:** Ready Auto `$rolls`, Auto `$us`, and Auto `$mk` actions are checked before reusing cached status, so available work is not overlooked.
