**🆕 MudaRemote v5.2.4**

### 🐛 Bug Fixes
- **Sphere Games No Longer Get Skipped on Big Roll Counts:** If your rolls took about as long as the reset, `$oh`, `$oc`, `$oq` and `$ot` kept waiting and never got played. The bot now plays them before it starts rolling, so your stored uses finally get spent. With Lurker Strategy or rolls timed to the claim reset, they still wait until after your rolls. The first run can delay your rolls for a few minutes if you have a lot stored.

### ⚡ Improvements
- **Clearer Sleep Schedule Text:** The setting now says that the bot also stops sniping and clicking Kakera during sleep hours, not just rolling.

Restart the bot after updating.
