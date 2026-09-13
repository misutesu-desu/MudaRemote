**🆕 MudaRemote v4.9.1-beta.18**

### 🐛 Bug Fixes
- **Hourly Rolls:** Fixed an issue near the hourly reset that could make the bot try to spend the same roll allowance twice.
- **Roll Limit Recovery:** The bot now stops the current roll batch when Mudae reports that the account has no rolls left, then checks its status before continuing.
- **Multiple Accounts:** Roll-limit warnings are matched to the affected account, so another account's warning does not stop your rolls.
