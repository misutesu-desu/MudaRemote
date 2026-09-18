**🆕 MudaRemote v4.9.4-beta.3**

### 🐛 Bug Fixes
- **No Repeated Auto `$rolls`:** Fixed extra `$rolls` attempts after the available rolls and roll item were already used. A missing confirmation no longer causes repeated attempts during the same roll cycle.
- **Rolling Resumes After Reset:** Fixed a freeze when a roll batch, including saved rolls from `$us`, was postponed because the next reset was too close. The bot now resumes automatically in the next cycle instead of remaining idle.

Restart your bot after updating to apply these fixes.
