**🆕 MudaRemote v4.9.8**

### 🐛 Bug Fixes
- **Smart Timing Near Claim Reset:** Fixed an issue where the bot could wait until shortly before your claim reset, then skip available rolls and postpone them to the next cycle. Smart Timing now leaves enough time to start rolling safely instead of missing the opportunity because of its own planned wait.

### ⚡ Improvements
- **Clearer Timing Messages:** Roll-wait messages now make it clear that Smart Timing also respects the safe rolling window, rather than promising that every batch will finish after the reset.

Restart the bot after updating to apply the fix.
