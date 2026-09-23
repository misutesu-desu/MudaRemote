**🆕 MudaRemote v4.9.5-beta.6**

### 🐛 Bug Fixes
- **Repeated $tu Checks:** Fixed a loop that could keep checking status instead of using available rolls after Auto $rolls crossed a reset or Mudae updated the reset timer. This stops the repeated status messages and unnecessary Discord requests from this loop.
- **Rolling with Patience:** Available rolls now resume after the channel becomes quiet in this recovery path, without getting stuck checking $tu. Your configured patience setting stays respected.
- **Safe Auto $rolls Recovery:** A missing acknowledgement no longer leaves rolling stuck across a reset. The bot checks the available rolls and continues without immediately sending the same $rolls request again.

Restart your bot after updating to apply these changes.
