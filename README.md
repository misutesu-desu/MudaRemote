# ⚡ MudaRemote: The Ultimate Mudae Automation Tool ⚡

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.0.2-orange.svg)]()
[![Status](https://img.shields.io/badge/Status-Active-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Join%20Server-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

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
*   **Intelligent $rt Claiming**: 
    *   Detects if `$rt` (Reset Timer) is available and uses it automatically when a second high-value character appears in the same reset.
    *   *New:* **Wishlist RT Priority**: Optionally allow `$rt` to be used on wishlist characters regardless of their kakera value.
*   **Strategic Roll Timing**: 
    *   **Anti-Waste Logic**: If your claim is on cooldown, the bot holds rolls until precisely before the reset boundary, ensuring every roll counts towards a new claim.
*   **Auto-Update System**: 
    *   Automatically detects newer versions from the remote repository and updates the script locally, keeping you synced with the latest performance tweaks and features.
*   **Custom Emoji Configuration**: 
    *   *New:* Personalize your bot! Custom lists for claim hearts, kakera crystals, and chaos keys can now be defined per preset.
*   **Reset Timer ($rt) Optimization**: 
    *   Intelligent detection and automatic execution of `$rt` to secure multiple high-value targets.

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
    pip install discord.py-self inquirer requests
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
    "use_slash_rolls": true,               // Use /wa instead of $wa (Highly Recommended)
    "dk_power_management": true,           // Save $dk charges for when you really need them
    "snipe_ignore_min_kakera_reset": true, // Claim ANY character if claim reset is in < 1 hour.
    "key_mode": false,                     // Continue rolling for keys even if you can't claim?
    "time_rolls_to_claim_reset": true,    // Time rolls to finish exactly at claim reset (Maximize harem efficiency)
    "rt_ignore_min_kakera_for_wishlist": false, // Use $rt for wishlist even if value < min_kakera?

    "// --- CUSTOM EMOJIS (Optional) ---": "",
    "claim_emojis": ["💖", "💗"],          // Custom hearts to click
    "kakera_emojis": ["kakeraY", "kakeraO"], // Custom crystals to sniff
    "chaos_emojis": ["kakeraP"]            // Custom chaos keys (10+ key characters)

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
