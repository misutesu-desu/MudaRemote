**🆕 MudaRemote v4.9.1-beta.12**

### 🐛 Bug Fixes
- **Sphere button retries:** Fixed repeated sphere clicks and misleading "not confirmed" warnings caused by waiting for a kakera reward message after a sphere click.
- **Daily sphere limits:** The bot now reads the sphere-button count from $tu separately from the Perk 8 and Perk 9 counters, accounts for clicks awaiting verification, and picks up the refreshed allowance from a new status check.
- **Daily commands before rolling:** Normal roll batches now require a fresh status check, so newly available $dk, $daily, and enabled $p commands can run before rolling starts. Existing automatic DK power-management preferences still apply.
- **Channel patience:** The bot checks the roll channel again before starting a batch and respects the configured quiet period even when an earlier $tu check reached its waiting limit.

### ⚡ Improvements
- **Clearer sphere status:** Logs distinguish a click being sent from the daily count confirmed by $tu, making it easier to see actual usage.
