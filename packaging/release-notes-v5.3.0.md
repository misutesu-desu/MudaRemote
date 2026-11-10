**🆕 MudaRemote v5.3.0**

### 🐛 Bug Fixes
- **`$dk` Confirmation Is Answered:** When Mudae asked whether you really wanted to use `$dk`, the bot stayed silent and believed the refill had worked. It now answers, and keeps the `$dk` when Mudae says you still have enough power.
- **`$dk` Lost To Another Command:** If Mudae was still waiting for an answer to a different command, the `$dk` was dropped. The bot now tries again.
- **Auto `$dk` Daily Schedule With Smart Power Refill:** The scheduled time was ignored while Smart Power Refill was on. Both now work together.
- **Event Card Rolls:** After the bot clicks an event card, it now uses the extra rolls the card gives.

### ⚡ Improvements
- **Kakera Cost Warning:** If your `$tu` does not show how much power a kakera reaction consumes, the bot now tells you what it assumes and how to fix it with `$tuarrange`.

Restart the bot after updating.
