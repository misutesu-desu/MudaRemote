**🆕 MudaRemote v5.0.1**

### 🐛 Bug Fixes
- **Claim Falls Back to the Next Best Roll:** If the bot's claim on the best roll of a batch didn't go through, it used to give up for that round. Now it tries the next best rolls from the same batch, wishes first, so you don't lose your claim.
- **Wish/Starwish Only Kakera Fixed:** Rolls that show their value as `+613` could be mistaken for a starwish, so the bot clicked their kakera even with Wish/Starwish Only on. Only real wishes and starwishes count now.
- **`$oq` Takes the Rainbow or White Reward:** When the 4th purple turned into a rainbow or white sphere instead of red, the bot left it on the board. It now clicks it like the red one.
- **`$oh` Clicks Dark Spheres Right Away:** A dark sphere that showed up on the board was sometimes held back and lost when the game ended early. The bot now clicks it as soon as it appears.

### ⚡ Improvements
- **Clearer `$tu` Reasons in the Log:** The log now says why each `$tu` was sent, like a claim check, a scheduled roll or an old status, instead of just "required".

Restart the bot after updating.
