**🆕 MudaRemote v5.1.6**

### 🐛 Bug Fixes
- **Smart Timing Works Again:** Smart Timing finished your rolls more than a minute before the claim reset, so the characters it rolled were gone by the time your claim came back. It now ends the rolls a few seconds before the reset and claims the best one as soon as your claim is back.
- **Correct Power Above 100%:** If your power was above your Maximum DK Power setting, the bot lowered its own estimate to that setting a few minutes after `$tu` and skipped Kakera it could afford. It now keeps the power `$tu` reported.

Restart the bot after updating.
