# ⚡ MudaRemote: The Ultimate Mudae Automation Tool ⚡

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-success.svg)]()

[Français](README.fr.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Português Brasileiro](README.pt-BR.md)

> **⚠️ CRITICAL WARNING ⚠️**
> 
> **MudaRemote is a SELF-BOT.** Automating user accounts is a violation of [Discord's Terms of Service](https://discord.com/terms). 
> Using this tool carries a risk of account suspension or banning. **Use at your own risk.** The developers accept no responsibility for any consequences.

---

## 🚀 Overview

**MudaRemote** is a high-performance, feature-rich automation engine designed specifically for the Mudae Discord bot. It goes far beyond simple auto-rolling, offering intelligent state management, surgical sniping capabilities, and advanced humanization to keep your account safe while maximizing your harem efficiency.

Unlike basic macros, MudaRemote parses Mudae's responses in real-time ($tu, messages, embeds) to make smart decisions about when to roll, when to sleep, and what to claim.

---

## ✨ Key Features

### 🎯 Advanced Sniping Ecosystem
*   **Wishlist Sniping**: Instantly claims characters from your `wishlist` that are rolled by *other users*.
*   **Series Sniping**: Target entire series! If anyone rolls a character from a tracked series, it's yours.
*   **Kakera Value Sniping**: Automatically snipe *any* character (even non-wishlisted ones) if their kakera value exceeds your threshold.
*   **Global Kakera Farming**: The bot watches **every** message for kakera reaction buttons.
    *   *New:* **Smart Filtering**: Configure it to only steal kakera from specific users (e.g., your alt accounts) to avoid server drama.
    *   *New:* **Chaos Mode**: Intelligent handling of Chaos Keys vs Normal Kakera.

### 🤖 Intelligent Automation
*   **Smart Rolling**: Automatically handles hourly rolls ($wa, $hg, $ma, etc.) and tracks your $daily reset.
*   **Slash Command Engine**: optionally uses modern Discord `/commands` for rolling, which is faster and often less rate-limited than classic text commands.
*   **Optimized Claiming**:
    *   **$rt Integration**: Automatically checks if you own the Refund Wish ($rt) perk and uses it to secure a second high-value claim in the same reset.
    *   **Panic Mode**: If your claim reset is less than 60 minutes away (`snipe_ignore_min_kakera_reset`), the bot drops its standards and claims *anything* to avoid wasting the cooldown.
*   **DK Power Management**: analyzes your current reaction power and stock. It only consumes a `$dk` (Daily Kakera) charge when your power is actually too low to react, preventing waste.

### 🛡️ Stealth & Safety
*   **Humanized Intervals**: No more robotic 60-minute timers. The bot adds random "jitter" to every wait period.
*   **Inactivity Watcher**: detecting when a channel is busy and waiting for a lull in conversation before spamming rolls, simulating a polite human user.
*   **Key Limit Detection**: Automatically pauses rolling if you hit the Mudae key limit.

---

## 🛠️ Installation

1.  **Prerequisites**:
    *   Install [Python 3.8](https://www.python.org/downloads/) or higher.
2.  **Install Dependencies**:
    ```bash
    pip install discord.py-self inquirer
    ```
3.  **Setup**:
    *   Download this repository.
    *   Create a `presets.json` file (see configuration below).

---

## ⚙️ Configuration (`presets.json`)

All settings are managed in `presets.json`. You can define multiple bot profiles (e.g., "MainAccount", "AltAccount") and run them simultaneously.

```json
{
  "MyProMudaBot": {
    "token": "YOUR_DISCORD_TOKEN_HERE",
    "channel_id": 123456789012345678,
    "prefix": "!", 
    "mudae_prefix": "$",
    "roll_command": "wa",

    "// --- CORE SETTINGS ---": "",
    "rolling": true,                       // Set to false for "Snipe Only" mode (no rolling, just watching)
    "min_kakera": 200,                     // Minimum value to claim a character during your own rolls
    "delay_seconds": 2,                    // Base processing delay
    "roll_speed": 1.5,                     // Seconds between roll commands

    "// --- SNIPING CONFIGURATION ---": "",
    "snipe_mode": true,                    // Master switch for Wishlist sniping
    "wishlist": ["Makima", "Rem"],         // List of exact character names to snipe
    "snipe_delay": 0.5,                    // How fast to snipe (seconds)
    
    "series_snipe_mode": true,
    "series_wishlist": ["Chainsaw Man"],   // List of series names to snipe
    "series_snipe_delay": 1.0,

    "// --- KAKERA FARMING ---": "",
    "kakera_reaction_snipe_mode": true,    // Click kakera buttons on ANY message?
    "kakera_reaction_snipe_delay": 0.8,
    "kakera_reaction_snipe_targets": [     // OPTIONAL: Only steal from these specific users (e.g., your alts)
        "my_alt_account_username"
    ],
    "only_chaos": false,                   // If true, only reacts to Chaos Key crystals (purple).

    "// --- ADVANCED LOGIC ---": "",
    "use_slash_rolls": true,               // Use /wa instead of $wa (Recommended)
    "dk_power_management": true,           // Save $dk charges for when you really need them
    "snipe_ignore_min_kakera_reset": true, // Claim ANY character if claim reset is in < 1 hour.
    "key_mode": false,                     // Continue rolling for keys even if you can't claim?

    "// --- HUMANIZATION ---": "",
    "humanization_enabled": true,
    "humanization_window_minutes": 30,     // Randomly wait 0-30 mins extra after reset
    "humanization_inactivity_seconds": 10  // Wait for 10s of silence in channel before rolling
  }
}
```

---

## 🎮 Usage

1.  Open your terminal in the bot folder.
2.  Run the script:
    ```bash
    python mudae_bot.py
    ```
3.  Select your preset from the menu.
4.  Sit back and watch the harem grow. 📈

---

## 🔒 Obtaining Your Token

1.  Log into Discord in your browser (Chrome/Firefox).
2.  Press **F12** (Developer Tools) -> **Console** tab.
3.  Paste this code to reveal your token:
    ```javascript
    window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
    ```
    *(Note: Never share this token with anyone. It gives full access to your account.)*

---

**Happy Hunting!** 💖
