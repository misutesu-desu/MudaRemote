# ✨ MudaRemote: Minimal Mudae Auto-Claim Bot ✨

[![Discord TOS Violation - **USE CAUTIOUSLY**](https://img.shields.io/badge/Discord%20TOS-VIOLATION-red)](https://discord.com/terms) ⚠️ **ACCOUNT BAN RISK!** ⚠️

**🛑🛑🛑  WARNING: SELF-BOT - DISCORD TOS VIOLATION!  ACCOUNT BAN RISK! 🛑🛑🛑**

**🔥 USE AT YOUR OWN RISK! 🔥 WE ARE NOT RESPONSIBLE FOR ACCOUNT ACTIONS. 😱**

---

## 🚀  MudaRemote: Level Up Your Mudae (Responsibly!) 🚀

MudaRemote is a Python self-bot to automate Mudae tasks. It offers real-time sniping and kakera collection, but **violates Discord TOS and carries a risk of account ban.**  Use with extreme caution!

**✨ Key Features: ✨**

*   **🎯 Real-time Wishlist & Series Sniping:** Claims characters from your wishlist and series instantly.
*   **💎 Real-time Kakera Sniping:** Claims characters based on kakera value.
*   **👯‍♀️ Multi-Account Support:** Run multiple bots.
*   **🤖 Automated Rolling & Claiming:** Auto-rolls and claims.
*   **💎 Kakera-Smart Claiming:** Prioritizes high-kakera characters.
*   **🥇 Intelligent Claim Logic:** Uses `$rt` for second claims.
*   **🔄 Auto Roll Reset Detection:** Waits for roll resets.
*   **✅ Claim Rights Check:**  Efficient claiming.
*   **⏱️ Customizable Delays:** Mimic human behavior.
*   **🔑 Key Mode: Relentless Kakera Rolling, Even Without Claim Rights!** When enabled, the bot will continuously roll for kakera, **even when you have no claim rights left**.  This allows you to maximize kakera gain, regardless of claim availability.
*   **🗂️ Preset Config:**  Manage multiple accounts easily.
*   **📊 Real-time Console Logging:**  Clear, colored console output.
*   **⚙️ Roll Speed Control:** Adjust rolling pace.

---

## 🛠️ Quick Setup 💨

1.  **🐍 Python:** Install Python 3.8+. ([python.org](https://www.python.org/downloads/))
2.  **📦 Install:** `pip install discord.py-self inquirer`
3.  **📝 `presets.json`:** Create `presets.json` in the same folder. This file configures each bot preset. Here are all the possible arguments you can use within each preset definition:

    ```json
    {
      "YourBotName": { // 🌟  Give your preset a descriptive name. This will be shown in the console menu.
        "token": "YOUR_DISCORD_TOKEN",   // 🔑 **REQUIRED:** Your Discord account token. Get it from browser Discord (F12 -> Console, paste code below in Usage section). **KEEP THIS SECRET!**
        "channel_id": 123456789012345678, // 💬 **REQUIRED:** Discord Channel ID where the bot will operate. Enable Developer Mode in Discord (Settings -> Advanced), then right-click the channel and "Copy ID".
        "roll_command": "wa",           // 🎲 **REQUIRED:** Mudae roll command you want to use (e.g., "wa", "wg", "ha", "hg", "w", "h").
        "delay_seconds": 1,             // ⏳ **REQUIRED:** Delay in seconds between bot actions (like checking claim rights, rolling, claiming).  Keep this above 0.8 for safety to avoid rate limiting.
        "mudae_prefix": "$",            // 💰 **REQUIRED:** Mudae bot's command prefix (usually "$").
        "min_kakera": 50,               // 💎 **REQUIRED:** Minimum kakera value a character must have for the bot to claim it. Set to `0` to claim all characters regardless of kakera value.
        "key_mode": false,              // 🔑 **OPTIONAL:** Key Mode. Set to `true` to enable relentless kakera rolling. **When `key_mode` is true, the bot will continuously roll for kakera even if you have used up all your claim rights.** This is useful for maximizing kakera gain. Default is `false`.
        "start_delay": 0,               // ⏱️ **OPTIONAL:** Startup delay in seconds.  The bot will wait this many seconds after starting before beginning to roll. Useful for staggering bot start times when running multiple bots. Default is `0`.
        "snipe_mode": false,             // 🎯 **OPTIONAL:** Wishlist Snipe Mode. Set to `true` to enable real-time character sniping based on your `wishlist`. Default is `false`.
        "snipe_delay": 2,               // ⏳ **OPTIONAL:** Delay in seconds before claiming a sniped character from your wishlist. Adjust as needed. Default is `2`.
        "snipe_ignore_min_kakera_reset": false, // 💎 **OPTIONAL:** Ignore `min_kakera` on claim reset. If `true`, the bot will ignore the `min_kakera` limit when claim rights are low (less than 1 hour remaining until reset). Useful for more aggressive sniping before resets. Default is `false`.
        "wishlist": [],                 // 📝 **OPTIONAL:** Wishlist for sniping. A list of character names (case-insensitive) to snipe. Example: `["Nezuko Kamado", "Rem"]`.
        "series_snipe_mode": false,      // 🎬 **OPTIONAL:** Series Snipe Mode. Set to `true` to enable real-time series sniping based on your `series_wishlist`. Default is `false`.
        "series_snipe_delay": 3,        // ⏳ **OPTIONAL:** Delay in seconds before claiming a series-sniped character. Adjust as needed. Default is `3`.
        "series_wishlist": [],            // 📝 **OPTIONAL:** Series Wishlist for sniping. A list of series keywords (case-insensitive) to snipe characters from. Example: `["Demon Slayer", "Re:Zero"]`.
        "roll_speed": 0.3,               // 💨 **OPTIONAL:** Roll Speed. Delay in seconds between each roll command. Lower values for faster rolling (e.g., `0.1` or `0.2`), higher values for slower, more "human-like" rolling (e.g., `0.5`). Default is `0.3`.
        "kakera_snipe_mode": false,      // 💎 **OPTIONAL:** Kakera Snipe Mode. Set to `true` to enable real-time kakera sniping. The bot will snipe characters based on their kakera value exceeding `kakera_snipe_threshold`. Default is `false`.
        "kakera_snipe_threshold": 100,   // 💎 **OPTIONAL:** Kakera Snipe Threshold. Minimum kakera value for kakera sniping. Only used when `kakera_snipe_mode` is `true`. Default is `100`.
        "kakera_snipe_delay": 2         // ⏳ **OPTIONAL:** Delay in seconds before claiming a kakera-sniped character. Adjust as needed. Default is `2`.
      }
      // You can add more preset configurations here for multiple accounts.
    }
    ```

4.  **🚀 Run:** `python mudae_bot.py`
5.  **🕹️ Select Bots:** Choose bots from the interactive menu.

---

## 🎮 Usage: Get Discord Token 🔑

1.  **🌐 Open Discord in your WEB BROWSER (Chrome, Firefox, etc.)**
2.  **👨‍💻 Press F12** (Developer Tools) -> **Console** tab.
3.  **💻 Paste and Enter this code:**

    ```javascript
    window.webpackChunkdiscord_app.push([
      [Math.random()],
      {},
      req => {
        if (!req.c) return;
        for (const m of Object.keys(req.c)
          .map(x => req.c[x].exports)
          .filter(x => x)) {
          if (m.default && m.default.getToken !== undefined) {
            return copy(m.default.getToken());
          }
          if (m.getToken !== undefined) {
            return copy(m.getToken());
          }
        }
      },
    ]);
    console.log('%cWorked!', 'font-size: 50px');
    console.log(`%cToken in clipboard!`, 'font-size: 16px');
    ```
4.  **📝 Paste the copied token into `presets.json`.  KEEP TOKEN SECRET! 🔒**

---

## 🤝 Contribute

Contributions welcome! Report issues, suggest features, or submit pull requests.

**🙏 Use Responsibly & Ethically. Respect Discord TOS. 🙏**

**Happy (Careful!) Mudae-ing!** 😉

---

**Credits:** Based on "Mudae Auto-Claim Bot".

**License:** [MIT License](LICENSE)
