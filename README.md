# ✨ MudaRemote: Advanced Mudae Automation ✨

[![Discord TOS Violation - **USE CAUTIOUSLY**](https://img.shields.io/badge/Discord%20TOS-VIOLATION-red)](https://discord.com/terms) ⚠️ **ACCOUNT BAN RISK!** ⚠️

**🛑🛑🛑 WARNING: SELF-BOT - POTENTIAL DISCORD TOS VIOLATION! ACCOUNT BAN RISK! 🛑🛑🛑**
**🔥 USE AT YOUR OWN RISK! 🔥 WE ARE NOT RESPONSIBLE FOR ANY ACTIONS TAKEN AGAINST YOUR ACCOUNT. 😱**

---

Join our [discord server](https://discord.gg/4WHXkDzuZx)

## 🚀 MudaRemote: Enhance Your Mudae Experience (Use Responsibly!)

MudaRemote is a Python-based self-bot designed to automate various tasks for the Discord bot Mudae. It offers features like real-time sniping and intelligent claiming. **However, using self-bots is against Discord's Terms of Service and may lead to account suspension or ban.** Please use with extreme caution and understand the risks involved.

### ✨ Core Features:

*   **🎯 External Sniping (Wishlist, Series & Kakera Value):** Claims characters rolled by *others*.
*   **🟡 External Kakera Reaction Sniping:** Automatically clicks kakera reaction buttons on *any* Mudae message.
*   **😴 Snipe-Only Mode:** Configure bot instances to *only* listen for and execute external snipes, without sending roll commands.
*   **⚡ Reactive Self-Roll Sniping:** Instantly claims characters from *your own* rolls if they match criteria.
*   **🤖 Automated Rolling & General Claiming:** Handles rolling commands and claims based on minimum kakera.
*   **🥇 Intelligent Claim Logic:** Parses `$tu` to check for `$rt` availability and uses it for a potential second claim on high-value rolls.
*   **🔄 Auto Reset Detection:** Monitors and waits for Mudae's claim and roll reset timers.
*   **🚶‍♂️ Humanized Waiting (NEW!):** Simulates human behavior by waiting for a random period and for channel inactivity before resuming actions after a reset, significantly reducing predictability.
*   **💡 DK Power Management (NEW!):** Intelligently checks your kakera reaction power via `$tu` and only uses `$dk` when power is insufficient for a reaction, saving charges.
*   **🔑 Key Mode:** Enables continuous rolling for kakera collection, even when character claims are on cooldown.
*   **⏩ Slash Roll Dispatch (NEW!):** Optional feature to send roll commands (`wa`, `h`, `m`, etc.) using Discord's Slash Command infrastructure instead of text commands.
*   **👯 Multi-Account Support:** Run multiple bot instances simultaneously.
*   **⏱️ Customizable Delays & Roll Speed:** Fine-tune all action delays and the speed of roll commands.
*   **🗂️ Easy Preset Configuration:** Manage all settings in a single `presets.json` file.
*   **📊 Console Logging:** Clear, color-coded real-time output.
*   **🌐 Localization Support:** Improved parsing for both English and Portuguese (PT-BR) Mudae responses.

---

## 🛠️ Setup Guide

1.  **🐍 Python:** Ensure Python 3.8+ is installed. ([Download Python](https://www.python.org/downloads/))
2.  **📦 Dependencies:** Open your terminal or command prompt and run:
    ```bash
    pip install discord.py-self inquirer
    ```
    *Note: If you plan to use `use_slash_rolls: true`, ensure your `discord.py-self` version includes the `Route` object (newer versions usually do).*
3.  **📝 `presets.json`:** Create a `presets.json` file in the script's directory. Add your bot configurations here. See the example below for all available options.
4.  **🚀 Run:** Execute the script from your terminal:
    ```bash
    python mudae_bot.py
    ```
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
    "rolling": true,                       // (Default: true) If false, bot enters SNIPE-ONLY mode: no rolling, only external snipes.

    // --- ADVANCED ROLLING / CLAIMING ---
    "roll_speed": 0.4,                     // (Default: 0.4) Delay (seconds) between individual text roll commands.
    "key_mode": false,                     // (Default: false) If true, rolls for kakera even without a claim right.
    
    // NEW: Control initial commands
    "skip_initial_commands": false,        // (Default: false) If true, skips $limroul, $dk, and $daily on startup, going straight to $tu.

    // NEW: Slash Command Dispatch (faster rolls)
    "use_slash_rolls": false,              // (Default: false) If true, attempts to send roll commands using Discord's slash command API. 
                                           // WARNING: Can be unstable. If failures occur, the bot automatically reverts to text commands.
                                           
    // NEW: DK Power Management
    "dk_power_management": true,           // (Default: false) If true, checks kakera power in $tu and only uses $dk if necessary (needs $tu access).

    // NEW: Only Chaos Keys Filter
    "only_chaos": false,                   // (Default: false) If true, only clicks kakera buttons on characters with 10+ keys (chaos keys).

    // --- HUMANIZATION (Recommended for high-risk accounts) ---
    "humanization_enabled": true,          // (Default: false) If true, uses humanized waiting after resets.
    "humanization_window_minutes": 40,     // (Default: 40) Add a random wait up to this duration after the reset time.
    "humanization_inactivity_seconds": 5,  // (Default: 5) Wait until the channel is inactive for this duration before resuming rolls.

    // --- EXTERNAL SNIPING (For characters rolled by OTHERS) ---
    "snipe_mode": true,                    // (Default: false) Enable external wishlist sniping.
    "wishlist": ["Character Name 1", "Character Name 2"],
    "snipe_delay": 2,                      // (Default: 2) Delay (seconds) before sniping (wishlist/kakera value).

    "series_snipe_mode": true,             // (Default: false) Enable external series sniping.
    "series_wishlist": ["Series Name 1"],
    "series_snipe_delay": 3,               // (Default: 3) Delay (seconds) before sniping a series character.

    "kakera_reaction_snipe_mode": false,   // (Default: false) Enable sniping of kakera reaction buttons on any Mudae message.
    "kakera_reaction_snipe_delay": 0.75,   // (Default: 0.75) Delay (seconds) before clicking an external kakera reaction.
    "kakera_reaction_snipe_targets": [],   // (Default: []) List of usernames to target. If empty, snipes all users. If set, only snipes characters owned by these users.

    // --- KAKERA THRESHOLD (Used for both External and Reactive Sniping) ---
    "kakera_snipe_mode": true,             // (Default: false) Enable heart claims based on kakera value for both external and reactive snipes.
    "kakera_snipe_threshold": 100,         // (Default: 0) Minimum kakera value to trigger the heart claims.

    // --- REACTIVE SNIPING (For characters from YOUR OWN rolls) ---
    "reactive_snipe_on_own_rolls": true,   // (Default: true) Enable/disable INSTANT claims during your own rolls (based on WL, Series WL, or Kakera Threshold).
    "reactive_snipe_delay": 0,             // (Default: 0) Delay (seconds) before claiming during reactive snipe on own rolls. Useful for appearing more natural.

    // --- OTHER ---
    "start_delay": 0,                      // (Default: 0) Delay (seconds) before the bot starts after being selected.
    "snipe_ignore_min_kakera_reset": false // (Default: false) Sets post-roll min_kakera to 0 if your claim reset is <1hr away.
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
