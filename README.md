# ✨ MudaRemote: Advanced Mudae Automation ✨

[![Discord TOS Violation - **USE CAUTIOUSLY**](https://img.shields.io/badge/Discord%20TOS-VIOLATION-red)](https://discord.com/terms) ⚠️ **ACCOUNT BAN RISK!** ⚠️

**🛑🛑🛑 WARNING: SELF-BOT - POTENTIAL DISCORD TOS VIOLATION! ACCOUNT BAN RISK! 🛑🛑🛑**
**🔥 USE AT YOUR OWN RISK! 🔥 WE ARE NOT RESPONSIBLE FOR ANY ACTIONS TAKEN AGAINST YOUR ACCOUNT. 😱**

---

Join our [discord server](https://discord.gg/4WHXkDzuZx)

## 🚀 MudaRemote: Enhance Your Mudae Experience (Use Responsibly!)

MudaRemote is a Python-based self-bot designed to automate various tasks for the Discord bot Mudae. It offers features like real-time sniping and intelligent claiming. **However, using self-bots is against Discord's Terms of Service and may lead to account suspension or ban.** Please use with extreme caution and understand the risks involved.

### ✨ Core Features:

*   **🎯 External Sniping (Wishlist, Series & Kakera Value):**
    *   **Wishlist Sniping:** Claims characters from your wishlist when rolled by *others*.
    *   **Series Sniping:** Claims characters from your series wishlist when rolled by *others*.
    *   **Kakera Value Sniping:** Claims characters based on their kakera value when rolled by *others*.
*   **🟡 External Kakera Reaction Sniping:** Automatically clicks kakera reaction buttons on *any* Mudae message from anyone.
*   **😴 Snipe-Only Mode:** Configure bot instances to *only* listen for and execute external snipes, without sending roll commands.
*   **⚡ Reactive Self-Roll Sniping:** Instantly claims characters from *your own* rolls if they match criteria (wishlist, series, kakera value). Interrupts the current rolling batch to secure the claim.
*   **🤖 Automated Rolling & General Claiming:** Handles rolling commands and makes claims based on minimum kakera after rolls are complete.
*   **🥇 Intelligent Claim Logic:** Parses `$tu` to check for `$rt` availability and uses it for a potential second claim on high-value characters.
*   **🔄 Auto Reset Detection:** Monitors and waits for Mudae's claim and roll reset timers.
*   **🚶‍♂️ Humanized Waiting (New!):** Simulates human behavior by waiting for a random period and for channel inactivity before resuming actions after a reset, reducing predictability.
*   **💡 DK Power Management (New!):** Intelligently checks your kakera reaction power and only uses `$dk` when necessary, saving charges.
*   **🔑 Key Mode:** Enables continuous rolling for kakera collection, even when character claims are on cooldown.
*   **👯 Multi-Account Support:** Run multiple bot instances simultaneously from a single terminal, each with its own configuration.
*   **⏱️ Customizable Delays & Roll Speed:** Fine-tune all action delays and the speed of roll commands.
*   **🗂️ Easy Preset Configuration:** Manage all settings for multiple accounts in a single `presets.json` file.
*   **📊 Console Logging:** Clear, color-coded real-time output of bot actions and status.
*   **🌐 Localization Support:** Improved parsing for both English and Portuguese (PT-BR) Mudae responses.

---

## 🛠️ Setup Guide

1.  **🐍 Python:** Ensure Python 3.8+ is installed. ([Download Python](https://www.python.org/downloads/))
2.  **📦 Dependencies:** Open your terminal or command prompt and run:
    ```bash
    pip install discord.py-self inquirer
    ```
3.  **📝 `presets.json`:** Create a `presets.json` file in the script's directory. Add your bot configurations here. See the example below for all available options.
4.  **🚀 Run:** Execute the script from your terminal:
    ```bash
    python mudae_bot.py
    ```
    (Replace `mudae_bot.py` with your script's actual filename if different).
5.  **🕹️ Select Presets:** Choose which configured bot(s) to run from the interactive menu.

---

### `presets.json` Configuration Example:

```json
{
  "YourBotAccountName": {
    // --- REQUIRED SETTINGS ---
    "token": "YOUR_DISCORD_ACCOUNT_TOKEN", // Your Discord account token. KEEP THIS EXTREMELY SECRET!
    "channel_id": 123456789012345678,     // ID of the Discord channel for Mudae commands.
    "roll_command": "wa",                  // Your preferred Mudae roll command (e.g., wa, hg, w, ma).
    "delay_seconds": 1,                    // General delay for some bot actions (e.g., after $tu).
    "mudae_prefix": "$",                   // The prefix Mudae uses in your server (usually "$").
    "min_kakera": 50,                      // Minimum kakera value for general (post-roll batch) claims.

    // --- CORE OPERATIONAL MODE ---
    "rolling": true,                       // (Default: true) If true, bot performs rolling, claiming, $tu checks.
                                           // If false, bot enters SNIPE-ONLY mode: no rolling, only listens for external snipes.

    // --- HUMANIZATION (RECOMMENDED) ---
    "humanization_enabled": true,          // (Default: false) If true, waits more naturally after resets. Reduces predictability.
    "humanization_window_minutes": 40,     // (Default: 40) The bot will wait for the reset time + a random time up to this many minutes.
    "humanization_inactivity_seconds": 5,  // (Default: 5) After waiting, the bot proceeds only when the channel has been inactive for this many seconds.

    // --- OPTIONAL SETTINGS (Most depend on "rolling: true") ---
    "key_mode": false,                     // (Default: false) If true, rolls for kakera even without a claim right.
    "start_delay": 0,                      // (Default: 0) Delay (seconds) before the bot starts after being selected.
    "roll_speed": 0.4,                     // (Default: 0.4) Delay (seconds) between individual roll commands.
    "dk_power_management": true,           // (Default: false) If true, checks kakera power in $tu and only uses $dk if needed.
                                           // NOTE: This is most effective when your gold badge is maxed out, as it prevents wasting full charges.

    // --- EXTERNAL SNIPING (For characters rolled by OTHERS) ---
    // These are always active if enabled, regardless of the "rolling" status.
    "snipe_mode": true,                    // (Default: false) Enable external wishlist sniping.
    "wishlist": ["Character Name 1", "Character Name 2"],
    "snipe_delay": 2,                      // (Default: 2) Delay (seconds) before sniping an external wishlist or kakera value character.

    "series_snipe_mode": true,             // (Default: false) Enable external series sniping.
    "series_wishlist": ["Series Name 1"],
    "series_snipe_delay": 3,               // (Default: 3) Delay (seconds) before sniping an external series character.

    "kakera_reaction_snipe_mode": false,   // (Default: false) Enable sniping of kakera reaction buttons on any Mudae message.
    "kakera_reaction_snipe_delay": 0.75,   // (Default: 0.75) Delay (seconds) before clicking an external kakera reaction.

    // --- REACTIVE SNIPING (For characters from YOUR OWN rolls) ---
    // Only active if "rolling: true".
    "reactive_snipe_on_own_rolls": true,   // (Default: true) Enable/disable INSTANT claims during your own rolls.
                                           // If false, all claims happen after the roll batch is complete.

    // --- KAKERA THRESHOLD (Used for both External and Reactive Sniping) ---
    "kakera_snipe_mode": true,             // (Default: false) If true, enables heart claims based on kakera value for:
                                           //    1. INSTANT reactive claims on your own rolls.
                                           //    2. DELAYED external snipes on others' rolls.
    "kakera_snipe_threshold": 100,         // (Default: 0) Minimum kakera value to trigger the heart claims above.

    // --- OTHER ---
    "snipe_ignore_min_kakera_reset": false // (Default: false) If true, sets post-roll min_kakera to 0 if your claim reset is <1hr away.
  }
  // Add more presets for other accounts here, separated by commas.
}
```

---

## 🎮 Obtaining Your Discord Token 🔑

Self-bots require your Discord account token. **This token grants full access to your account – keep it extremely private! Sharing it is like giving away your password.** It is recommended to use this bot on an alternative account.

1.  **Open Discord in your web browser** (e.g., Chrome, Firefox). *Not the desktop app.*
2.  Press **F12** to open Developer Tools.
3.  Navigate to the **`Console`** tab.
4.  Paste the following code snippet into the console and press Enter:
    ```javascript
    window.webpackChunkdiscord_app.push([
    	[Symbol()],
    	{},
    	req => {
    		if (!req.c) return;
    		for (let m of Object.values(req.c)) {
    			try {
    				if (!m.exports || m.exports === window) continue;
    				if (m.exports?.getToken) return copy(m.exports.getToken());
    				for (let ex in m.exports) {
    					if (m.exports?.[ex]?.getToken && m.exports[ex][Symbol.toStringTag] !== 'IntlMessagesProxy') return copy(m.exports[ex].getToken());
    				}
    			} catch {}
    		}
    	},
    ]);

    window.webpackChunkdiscord_app.pop();
    console.log('%cWorked!', 'font-size: 50px');
    console.log(`%cYou now have your token in the clipboard!`, 'font-size: 16px');
    ```
5.  Your token will be copied to your clipboard. Carefully paste it into the `"token"` field in your `presets.json` file.

---

## 🤝 Contributing

Contributions are welcome! Feel free to report issues, suggest features, or submit pull requests to the project repository.

**🙏 Please use this tool responsibly and ethically, with full awareness of the potential risks to your Discord account. 🙏**

**Happy (and Cautious!) Mudae-ing!** 😉

---
**License:** [MIT License](LICENSE)
