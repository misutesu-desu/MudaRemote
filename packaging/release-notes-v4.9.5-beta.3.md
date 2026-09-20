**🆕 MudaRemote v4.9.5-beta.3**

### 🐛 Bug Fixes
- **Kakera Collection:** Selected non-purple Kakera no longer gets blocked just because reaction readiness is unknown. The bot still checks your available power, colour selections, filters, and confirmed cooldowns.
- **Sphere Collection Recovery:** Selected spheres, including doubled variants, can resume after a fresh usage check when unconfirmed clicks have filled the local allowance or a known daily refill has passed. Actual daily limits are still respected.
- **Chaos Kakera Power Discount:** The bot now recognizes the reported 50% Chaos power-discount message and refreshes your power from Mudae, instead of continuing with the old estimate. Extra-roll bonuses remain independent, and Auto `$dk` waits for the discount check before spending a refill.
- **Reaction Status Recognition:** Plain and formatted reaction-status messages are recognized correctly, and Portuguese or Spanish cooldown messages are no longer mistaken for permission to react.

Your existing Normal, Chaos, Perk 8, and sphere selections remain unchanged. Excluded colours are not enabled automatically.

Restart your bot after updating to apply these changes.
