**🆕 MudaRemote v5.2.3**

### 🐛 Bug Fixes
- **Event Cards Get Claimed Again:** Free event cards like the Halloween Art Contest ones are clicked whether your claim is up or not, and you no longer need the event emojis in Claim Emojis. This also fixes the crash some desktop users saw when an event card appeared.
- **No More Stalls on a Character You Just Claimed:** If a character with the same name as your last claim showed up again, the bot kept stopping your rolls for nothing. It now skips it and keeps rolling.
- **`$kl` Retries a Stop Sign:** When Mudae puts a 🛑 on your `$kl`, the bot sends it again instead of waiting for the next cycle.
- **Faster `$kl` Cycles:** When Mudae posts the `$kl` result without replying to you, the bot now picks it up right away instead of waiting 8 seconds.
- **Pin Release Is Recognized:** The bot now confirms `$arlp` when Mudae's reply starts with the number of released pins.
- **Android Asks for a Restart Less:** Saving a setting no longer asks for a restart because of empty channel or target fields you never touched.

Restart the bot after updating.
