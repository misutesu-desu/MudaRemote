# ⚡ MudaRemote: The Ultimate Mudae Bot Automation Tool

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.3.3-orange.svg)](https://github.com/misutesu-desu/MudaRemote/releases)
[![Status](https://img.shields.io/badge/Status-Active_2026-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Join%20Server-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

[Français](README.fr.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Português Brasileiro](README.pt-BR.md)

**MudaRemote** is the most sophisticated, feature-rich automation engine designed specifically for the **Mudae Discord Bot**. It goes far beyond simple macros by parsing real-time data ($tu, embeds, components) to simulate human-like behavior while maximizing harem efficiency.

> **⚠️ CRITICAL WARNING:** MudaRemote is a **SELF-BOT**. Use of self-bots violates Discord's ToS and carries a risk of permanent ban. **Use at your own risk.**

---

## 🏆 Why MudaRemote? (Comparison)

Don't settle for 2021-era scripts. Upgrade to the 2025 standard.

| Feature | Ordinary Mudae Bots | **MudaRemote v3.3.3** |
| :--- | :--- | :--- |
| **Roll Timing** | Constant/Random Timers | **Strategic Boundary Sync (Claims perfectly)** |
| **Command Engine** | Text Only | **Slash Commands (Modern API Support)** |
| **$rt Management** | None / Manual | **Fully Automated Intelligence** |
| **Updates** | Manual Re-download | **Integrated Auto-Update System** |
| **Stealth** | Static Delays | **Human-Like Jitter & Inactivity Watcher** |
| **Localization** | English Only | **4 Languages Fully Supported** |

---

## ✨ Key High-Impact Features

### 🎨 Brand New: Graphical Preset Editor
*   **Visual Configuration:** No more manual JSON editing! Use `mudae_preset_editor.py` to manage all your presets through a sleek dark-themed GUI.
*   **Easy Customization:** Toggle individual claim and kakera emojis with smart fallback logic.
*   **One-Click Start:** Launch the bot directly from the editor.

### 🎯 Advanced Sniping Ecosystem
*   **Wishlist & Series Sniping:** Instantly claims characters or entire anime series rolled by others.
*   **Intelligent Kakera Sniper:** Set a threshold (e.g., 200+) and let the bot secure value automatically (Now supports **Kakera D & C**).
*   **Sphere Specialist:** Detects and secures **Spheres** (SpU, SpD, etc.) using a zero-power bypass mechanism—ensuring you never miss these rare drops.
*   **Global Kakera Farming:** Scans all messages for crystals. Includes **Smart Filtering** to only take from specific users (like your alts) to stay under the radar.
*   **Chaos Mode:** Specialized logic for Chaos Keys (10+ key characters).

### 🤖 Intelligent Automation (The "Brain")
*   **Strategic Roll Timing:** The bot holds rolls until just before your claim reset, ensuring you never waste a roll while your claim is on cooldown.
*   **Slash Command Engine:** optionally uses `/wa`, `/ha`, etc., which are faster and significantly safer from Discord's detection.
*   **Smart $rt Utilization:** Automatically detects if `$rt` is available and uses it only for high-priority wishlist targets.
*   **DK Power Management:** Optimizes your Kakera power usage to ensure you always have enough for high-value reacts.

### 🛡️ Stealth & Anti-Ban Technology
*   **Humanized Intervals:** Implements random "jitter" so your activity never looks like a 60-minute loop.
*   **Inactivity Watcher:** Detects when a channel is busy and waits for a conversation lull before rolling—acting like a polite user.
*   **Key Limit Protection:** Automatically pauses if you hit the 1,000-key daily limit to prevent flagging.

---

## 🛠️ Quick Start

1.  **Requirements**: [Python 3.8+](https://www.python.org/downloads/)
2.  **Installation**:
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **Run**:
    ```bash
    python mudae_preset_editor.py
    ```
    *Use the sleek New GUI to manage presets, then click **Run Bot**!*
    
    *(Alternatively, run `python mudae_bot.py` for the classic console menu)*

---

## ⚙️ Configuration (`presets.json`)

Define multiple profiles for different accounts or servers.

```json
{
  "MainAccount": {
    "token": "YOUR_TOKEN",
    "channel_id": 123456789,
    "rolling": true,
    "use_slash_rolls": true,            // Recommended
    "time_rolls_to_claim_reset": true, // Unique Feature
    "min_kakera": 200,
    "humanization_enabled": true,
    "wishlist": ["Makima", "Rem"]
  }
}
```
📖 **Need help with settings?** Check out our detailed [Configuration Guide (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide)
---

## 🔒 Obtaining Your Token
1. Open Discord in your Browser.
2. Press `F12` -> `Console`.
3. Paste:
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
4. **Never share this token!**

---

**⭐ If this tool helped you grow your harem, please give it a Star! It helps the project grow and stay updated.**





