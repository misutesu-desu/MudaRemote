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
3.  **📝 `presets.json`:** Create `presets.json` in the same folder:

    ```json
    {
      "YourBotName": {
        "token": "YOUR_DISCORD_TOKEN",   // 🔑 Get token from browser Discord (F12 -> Console, paste code below)
        "channel_id": 123456789012345678, // 💬 Discord Channel ID (Developer Mode -> Right-click channel -> Copy ID)
        "roll_command": "wa",           // 🎲 Mudae roll command (wa, wg, ha, hg, w, h)
        "delay_seconds": 1,             // ⏳ Delay (seconds, >0.8 for safety)
        "mudae_prefix": "$",            // 💰 Mudae prefix ($)
        "min_kakera": 50,               // 💎 Min kakera to claim (0 for all)
        "key_mode": false,              // 🔑 Key Mode: Roll for kakera even without claim rights.  Set to `true` to enable relentless kakera rolling.
        "wishlist": ["Character Name"], // 📝 Wishlist for sniping
        "series_wishlist": ["Series Name"], // 🎬 Series Wishlist for sniping
        "kakera_snipe_threshold": 100   // 💎 Min kakera for kakera sniping
      }
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
