# ✨ MudaRemote: Mudae Auto-Claim Bot ✨

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
3.  **📝 `presets.json`:** Create `presets.json` in the same folder. Configure bot presets here:

    ```json
    {
      "YourBotName": { // 🌟 Preset name (console menu)
        "token": "YOUR_DISCORD_TOKEN",   // 🔑 **REQUIRED:** Discord account token (get from browser, see Usage). **SECRET!**
        "channel_id": 123456789012345678, // 💬 **REQUIRED:** Discord channel ID (Developer Mode -> Copy ID).
        "roll_command": "wa",           // 🎲 **REQUIRED:** Mudae roll command (wa, wg, ha, hg, w, h).
        "delay_seconds": 1,             // ⏳ **REQUIRED:** Delay between actions (seconds, >0.8 for safety).
        "mudae_prefix": "$",            // 💰 **REQUIRED:** Mudae prefix ("$").
        "min_kakera": 50,               // 💎 **REQUIRED:** Min kakera to claim (0 for all).
        "key_mode": false,              // 🔑 **OPTIONAL:** Key Mode: Roll for kakera without claim rights. `true` to enable. Default: `false`.
        "start_delay": 0,               // ⏱️ **OPTIONAL:** Startup delay (seconds). Default: `0`.
        "snipe_mode": false,             // 🎯 **OPTIONAL:** Wishlist Snipe Mode. `true` to enable. Default: `false`.
        "snipe_delay": 2,               // ⏳ **OPTIONAL:** Snipe claim delay (seconds). Default: `2`.
        "snipe_ignore_min_kakera_reset": false, // 💎 **OPTIONAL:** Ignore `min_kakera` on claim reset (<1h). `true` to enable. Default: `false`.
        "wishlist": [],                 // 📝 **OPTIONAL:** Wishlist for sniping (character names). Example: `["Nezuko Kamado", "Rem"]`.
        "series_snipe_mode": false,      // 🎬 **OPTIONAL:** Series Snipe Mode. `true` to enable. Default: `false`.
        "series_snipe_delay": 3,        // ⏳ **OPTIONAL:** Series snipe claim delay (seconds). Default: `3`.
        "series_wishlist": [],            // 📝 **OPTIONAL:** Series Wishlist for sniping (series keywords). Example: `["Demon Slayer", "Re:Zero"]`.
        "roll_speed": 0.3,               // 💨 **OPTIONAL:** Roll Speed: Delay between rolls (seconds). Lower = faster. Default: `0.3`.
        "kakera_snipe_mode": false,      // 💎 **OPTIONAL:** Kakera Snipe Mode. `true` to enable. Default: `false`.
        "kakera_snipe_threshold": 100,   // 💎 **OPTIONAL:** Kakera Snipe Threshold: Min kakera value. Default: `100`.
        "kakera_snipe_delay": 2         // ⏳ **OPTIONAL:** Kakera snipe claim delay (seconds). Default: `2`.
      }
      // Add more presets for multiple accounts here.
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
