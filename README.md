<p align="center">
  <h1 align="center">⚡ MudaRemote — The #1 Mudae Bot for Discord</h1>
  <p align="center">
    <strong>Advanced Mudae Auto Claim • Discord Mudae Sniper • Auto Roll Mudae • Mudae Auto Kakera • Mudae Slash Commands Bot</strong>
  </p>
  <p align="center">
    The most powerful open-source <strong>Mudae bot</strong> automation engine. Auto roll, auto claim, auto kakera, character sniping,<br>multi-account sync, anti-ban stealth, and a full graphical UI — all in one <strong>Mudae script</strong>.
  </p>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/badge/Version-4.0.3-f97316?style=for-the-badge" alt="Version 4.0.3"></a>
  <a href="#"><img src="https://img.shields.io/badge/Status-Active_2026-10b981?style=for-the-badge" alt="Active 2026"></a>
  <a href="https://discord.gg/4WHXkDzuZx"><img src="https://img.shields.io/badge/Discord-Join_Server-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord Server"></a>
</p>

<p align="center">
  <a href="README.fr.md">Français</a> •
  <a href="README.ja.md">日本語</a> •
  <a href="README.ko.md">한국어</a> •
  <a href="README.tr.md">Türkçe</a> •
  <a href="README.zh-CN.md">简体中文</a> •
  <a href="README.pt-BR.md">Português Brasileiro</a>
</p>

---

## 🔥 What is MudaRemote?

**MudaRemote** is the most advanced **Mudae bot** automation tool for Discord. Unlike basic **Mudae macros** or scripts that blindly spam roll commands, MudaRemote acts as a full **Mudae auto claim** and **Mudae auto kakera** engine — it parses `$tu` responses in real-time, tracks your claim/roll/kakera cooldowns, detects character values from embeds, and executes humanized actions that mimic a real player.

Whether you need a **Discord Mudae sniper** to steal high-value characters from other players, **auto roll Mudae** to execute your rolls at the optimal time, or **Mudae multi-account sync** to coordinate wishlists across alts — MudaRemote does it all through a beautiful **Tkinter GUI** with zero JSON editing required.

> **⚠️ IMPORTANT DISCLAIMER:** MudaRemote is a **self-bot** tool. Using self-bots **violates Discord's Terms of Service** and can result in a **permanent account ban**. This project is provided for **educational purposes only**. The developers are not responsible for any consequences resulting from the use of this software. **Use entirely at your own risk.**

---

## 🏆 Why MudaRemote? Feature Comparison

Stop using outdated 2021-era **Mudae scripts**. Here's how MudaRemote compares:

| Feature | Basic Mudae Bots / Scripts | **MudaRemote v4.0** |
| :--- | :---: | :---: |
| **Roll Execution** | Text commands only | ✅ **Slash commands** (`/wa`, `/ha`, `/mx`) — 10% kakera bonus |
| **Claim Intelligence** | Claim anything above threshold | ✅ **Wishlist + Series + Value + "Wished by" detection** |
| **Timing Strategy** | Fixed interval timers | ✅ **Strategic Boundary Sync** — rolls finish exactly at claim reset |
| **Anti-Ban Stealth** | Static delays | ✅ **Humanized jitter, inactivity watcher, sleep schedules, randomized reactions** |
| **Multi-Account** | None | ✅ **Main account wishlist sync** across alts |
| **Kakera Management** | Click everything | ✅ **Priority ordering, power tracking, DK management, chaos/sphere specialization** |
| **Configuration** | Edit JSON manually | ✅ **Full dark-themed GUI** with one-click bot launch |
| **Updates** | Manual re-download | ✅ **Built-in auto-updater** with backup + restart |
| **Localization** | English only | ✅ **EN, PT-BR, ES, FR** — parses Mudae in all 4 languages |
| **Recovery** | Crashes and stays dead | ✅ **Auto-restart, health monitor, maintenance detection** |

---

## ✨ Core Features

### 🎯 Advanced Character Sniping & Mudae Auto Claim

MudaRemote's **Mudae auto claim** system is built around a layered sniping ecosystem that handles every claiming scenario:

| Snipe Mode | How It Works |
| :--- | :--- |
| **Wishlist Snipe** | Instantly claims any character on your wishlist — from your own rolls or other players' rolls. Detects Mudae's native `Wished by @You` tags. |
| **Series Snipe** | Auto-claims ANY character from specific anime/manga/game series (substring matching: "naruto" catches "Naruto Shippūden"). |
| **Value Snipe** | Steals characters above a kakera threshold from other players (e.g., snipe anything ≥ 500 ka). |
| **Reactive Self-Claim** | Monitors your own rolls in real-time and **instantly** claims wishlist/high-value characters mid-roll — no waiting for the batch to finish. |
| **Panic Claim** | When your claim timer is about to expire (< 60min), the bot drops all value restrictions and claims **anything** to avoid wasting a claim right. |
| **Free Event Card Snipe** | Detects seasonal event cards (Christmas Art Contest, New Year's Contest) with the `"it's free!"` tag and claims them without consuming a claim right. |
| **$rt Auto-Utilization** | Detects `$rt` availability and automatically uses it for high-priority targets. Configurable to only use on your own rolls (`rt_only_self_rolls`). |
| **Auto $rt After Claim** | Instantly sends `$rt` after a successful claim to regain your claim right mid-roll (skips if reset < 60m or no rolls left). |

**Avoid List (Anti-Wishlist):** Blacklist characters you never want to claim, even if they pass every other filter.

**Smart Snipe Verifier:** After every claim attempt, the bot reads Mudae's marriage confirmation messages to determine if you won or if someone beat you — and updates internal state accordingly. No extra `$tu` needed.

---

### 💎 Mudae Auto Kakera & Smart Power Management

MudaRemote doesn't just click every kakera crystal blindly. It uses an intelligent **Mudae auto kakera** system with local power tracking:

- **🔋 DK Power Regeneration Tracking** — Locally simulates your kakera power regeneration (1% every 3 minutes), so the bot knows if it can afford to click before wasting a reaction.
- **⚡ Auto $dk Management** — Automatically uses `$dk` when your power drops below the reaction cost. Respects `only_chaos` mode by halving the expected cost. Configurable max power cap (`max_dk_power`) for late-game users with upgrades (e.g., 320%).
- **🎯 Configurable Kakera Priority Order** — Choose which kakera types to click first when multiple buttons appear. Default priority: `kakeraP > kakeraC > kakeraL > kakeraW > kakeraR > kakeraO > kakeraD > kakeraY`. Spheres are **always** top priority.
- **💎 Sphere Specialist** — Detects `💎/2` sphere perks on characters and applies half-cost calculation. Spheres (`spP`, `spB`, `spT`, `spG`, etc.) consume **zero** power and are always clicked.
- **🔑 Chaos Kakera Mode** — Targets characters with 10+ keys (Chaos Keys). Chaos reactions cost 50% less power. When `only_chaos` is enabled, normal kakera is skipped entirely (except free kakeraP and spheres).
- **🔒 MK Kakera Only** — An exclusive mode that ignores ALL normal kakera buttons. Only clicks crystals generated by `$mk` rolls — perfect for conserving power when you have limited `$dk`.
- **📊 Per-Kakera Power Thresholds** — Set minimum power requirements per emoji (e.g., `kakeraY: 80`, `chaos_kakeraY: 50`). The bot skips a kakera type if your power is below its custom threshold.
- **🛡️ Double-Click Prevention** — Tracks every reacted message ID to ensure the bot never clicks the same kakera twice, preventing wasted power deductions.

---

### 🤖 Intelligent Auto Roll Mudae Engine

The rolling engine is where MudaRemote separates itself from every other **Mudae macro** or **auto roll Mudae** tool:

- **📡 Real-Time `$tu` Parser** — Parses `$tu` responses multilinguistically (EN, PT-BR, ES, FR) to extract: rolls remaining, `$us` stacked rolls, `$mk` kakera rolls, claim status, `$rt` availability, next reset timers, kakera power, and `$dk` stock.
- **⏱️ Strategic Boundary Sync** — The bot calculates how long your rolls will take (rolls × speed), then delays the start so your **last roll finishes exactly 1 second after your claim resets**. This gives you a fresh claim right for anything good from your own batch.
- **🗓️ Scheduled Roll Times** — Instead of rolling on a fixed interval loop, set exact times (e.g., `14:00`, `18:30`) in 24-hour format. The bot sleeps until the scheduled time, applies humanization jitter, then executes. 
- **🔄 Auto $us (Stacked Rolls)** — Automatically spends leftover rolls from the previous cycle. Configurable limit per hour, with auto-stop when a claim becomes available.
- **🎰 Auto $mk (Kakera Rolls)** — Uses `$mk` rolls before normal rolls when power is sufficient. Finds and clicks the kakera on each `$mk` response automatically.
- **📦 Auto $rolls (Daily Rolls)** — Automatically uses the `$rolls` command when normal rolls run out. Configurable limit and optional key-mode support.
- **🎯 Bonus Roll Detection** — When clicking certain kakera grants bonus rolls (e.g., `+5 rolls this hour`), the bot detects the message and triggers a status sync to use them immediately.
- **😈 Lurker Strategy** — The bot stays silent while others roll, sniping valuable characters. Then, in the final minutes before your claim expires (`panic_roll_minutes`), it dumps all rolls at once with `min_kakera = 0` to guarantee a claim.
- **📡 Slash Command Engine** — Sends rolls as Discord interactions (`/wa`, `/ha`, `/mx`) instead of text commands. Never falls back to text mode — if slash fails, the bot stays silent (pure stealth). Includes automatic rate-limit handling and retry logic.

---

### 🛡️ Ghost Mode / Anti-Ban Stealth Technology

MudaRemote's stealth system is what makes it safe for long-term use. Every other **Mudae bot** or **Mudae script** exposes you with perfectly timed, robotic behavior. MudaRemote doesn't:

| Stealth Feature | Description |
| :--- | :--- |
| **Humanized Timing Jitter** | After every reset, waits a random 0–N extra minutes (configurable window, default 40min) before the next cycle. No perfectly timed loops. |
| **Channel Inactivity Watcher** | Before rolling, checks if the channel has been quiet for X seconds. If people are chatting, the bot waits — just like a real user would. |
| **Randomized Claim Reactions** | When the bot falls back to emoji reactions (no buttons), it randomly selects from a configurable pool (`💖`, `💗`, `💘`, `❤️`, `👍`, `🔥`) instead of always using the same emoji. |
| **Reactive Kakera Delay** | On your own rolls, applies a random humanized delay (default 0.3–1.0s) before clicking kakera — not instant, not fixed. |
| **Configurable Sleep Schedule** | Set `inactive_hours` (e.g., `1-7, 23-6`) and the bot goes fully silent during those hours — like you're sleeping. Supports overnight ranges. |
| **Post-Maintenance Inactivity Gate** | After Mudae maintenance ends, the bot doesn't immediately resume. It waits for the channel to go quiet first, then resumes with a humanized delay. |
| **Key Limit Protection** | If you hit the 1,000-key daily cap, the bot auto-pauses for 1 hour + random jitter. No suspicious immediate retries. |
| **Slash-Only Mode** | When slash commands are enabled, the bot **never** falls back to text commands — even if slash fails. Your account never sends `$wa` in chat. |

---

### 🔗 Mudae Multi-Account Sync

Run MudaRemote on multiple accounts simultaneously with **Mudae multi-account sync** — the `presets.json` system supports unlimited account profiles:

- **Main Account Wishlist Syncing** — Set `main_account_id` on your alt accounts. When the main account rolls a character flagged as `Wished by @MainAccount`, all configured alts instantly priority-claim it with near-zero delay — bypassing the normal sniping flow.
- **Per-Account Profiles** — Each preset has its own token, channel, wishlist, series list, avoid list, roll settings, and stealth configuration.
- **Simultaneous Execution** — Run all presets at once with `--all` or select multiple from the console menu. Each account runs in its own thread with auto-restart on crash.
- **Staggered Starts** — Use `start_delay` to offset each account's boot time, preventing suspiciously synchronized activity.

---

### 🎨 Graphical Preset Editor (Tkinter GUI)

No more manual JSON editing. MudaRemote includes `mudae_preset_editor.py` — a full-featured **dark-themed GUI** built with Tkinter:

- **Visual Configuration** — Every setting has a human-readable label, organized into logical sections: Connection, Rolling, Stacked Rolls, Claim Rules, Sniping & Stealing, Wishlists, Custom Emojis, Anti-Ban, and Power & Expert Settings.
- **One-Click Bot Launch** — Save your preset and launch the bot directly from the editor. Opens in a new console window.
- **Preset Management** — Create, duplicate, and delete presets. Each preset is a complete independent configuration.
- **Windows Autostart** — Toggle `Start with Windows` to create a startup script that launches your preset automatically on boot.
- **Smart Defaults** — Every field shows its default value. Boolean settings have clear descriptive labels (e.g., *"Lurker Strategy: Wait for others to roll while sniping — Panic dump at the end"*).

---

### 🔄 Auto-Update System

MudaRemote checks for updates on every launch:

1. Fetches `version.json` from the GitHub repository.
2. If a newer version exists, downloads the updated `mudae_bot.py` and `mudae_preset_editor.py`.
3. Creates `.bak` backups of your current files.
4. Replaces the scripts and **restarts in a new console window** — zero downtime.

---

## 🛠️ Setup & Installation

### Prerequisites

- **[Python 3.8+](https://www.python.org/downloads/)** (check `Add to PATH` during installation)
- A Discord account token ([see below](#-how-to-get-your-discord-token))

### Step 1: Download MudaRemote

```bash
git clone https://github.com/misutesu-desu/MudaRemote.git
cd MudaRemote
```

Or download the [latest release](https://github.com/misutesu-desu/MudaRemote/releases) as a ZIP.

### Step 2: Install Dependencies

```bash
pip install discord.py-self inquirer requests
```

### Step 3: Launch the Preset Editor

```bash
python mudae_preset_editor.py
```

This opens the graphical configuration tool. Fill in your **token**, **channel ID**, and desired settings, then click **💾 Save Changes**.

### Step 4: Start the Bot

**Option A — From the GUI:** Click **▶ Launch Bot** in the Preset Editor.

**Option B — From the terminal:**
```bash
# Run a specific preset
python mudae_bot.py --preset "MyAccount"

# Run all presets simultaneously
python mudae_bot.py --all

# Interactive menu
python mudae_bot.py
```

---

## 🔑 How to Get Your Discord Token

1. Open **Discord in your browser** (not the desktop app).
2. Press `F12` → go to the **Console** tab.
3. Paste this snippet and press Enter:
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
4. Copy the token that appears. **Never share this token with anyone.**

---

## ⚙️ Configuration Reference

All settings are managed through `presets.json` (or the GUI). Here's a sample configuration:

```json
{
  "MainAccount": {
    "token": "YOUR_TOKEN_HERE",
    "prefix": "/////////////",
    "mudae_prefix": "$",
    "channel_id": 123456789012345678,
    "roll_command": "wa",
    "rolling": true,
    "use_slash_rolls": true,
    "min_kakera": 200,
    "humanization_enabled": true,
    "humanization_window_minutes": 40,
    "humanization_inactivity_seconds": 5,
    "time_rolls_to_claim_reset": true,
    "wishlist": ["Makima", "Rem", "Zero Two"],
    "series_wishlist": ["Jujutsu Kaisen"],
    "avoid_list": ["Character I Hate"],
    "snipe_mode": true,
    "snipe_delay": 1.5,
    "kakera_reaction_snipe_mode": true,
    "dk_power_management": true,
    "auto_dk_enabled": true,
    "key_mode": false,
    "claim_interval": 180,
    "roll_interval": 60,
    "inactive_hours": [[1, 7]],
    "auto_us_enabled": true,
    "auto_us_limit": 20,
    "auto_mk_enabled": true,
    "lurker_mode": false,
    "kakera_priority_order": ["kakeraP", "kakeraC", "kakeraL", "kakeraW", "kakeraR", "kakeraO", "kakeraD", "kakeraY"]
  }
}
```

📖 **Full configuration documentation →** [Configuration Guide (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide)

---

## 📊 All Settings at a Glance

<details>
<summary><strong>🟢 Connection Settings</strong></summary>

| Setting | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `token` | string | — | Your Discord account token |
| `channel_id` | int | — | Target channel ID for rolling |
| `prefix` | string | `"/////////////"` | Self-bot command prefix |
| `mudae_prefix` | string | `"$"` | Mudae's command prefix on your server |
| `roll_command` | string | `"wa"` | Roll command (`wa`, `ha`, `ma`, `wg`, etc.) |
| `autostart` | bool | `false` | Create Windows startup script |

</details>

<details>
<summary><strong>🎲 Rolling Options</strong></summary>

| Setting | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `rolling` | bool | `true` | Master rolling switch. `false` = Ghost Mode (snipe only) |
| `use_slash_rolls` | bool | `false` | Use slash commands for +10% kakera bonus |
| `roll_speed` | float | `0.4` | Seconds between each roll (0.4 text, 2.0+ slash) |
| `roll_interval` | int | `60` | Roll reset interval in minutes |
| `time_rolls_to_claim_reset` | bool | `false` | Strategic Boundary Sync |
| `scheduled_roll_times` | list | `[]` | Exact roll times (e.g., `["14:00", "18:30"]`) |
| `auto_rolls_enabled` | bool | `false` | Auto `$rolls` when out of rolls |
| `auto_us_enabled` | bool | `false` | Auto `$us` stacked rolls |
| `auto_mk_enabled` | bool | `true` | Auto `$mk` kakera rolls |

</details>

<details>
<summary><strong>🎯 Claiming & Sniping</strong></summary>

| Setting | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `min_kakera` | int | `100` | Minimum kakera value to auto-claim |
| `snipe_mode` | bool | `false` | Snipe wishlist characters from other players |
| `snipe_delay` | float | `2` | Seconds before sniping (humanization) |
| `series_snipe_mode` | bool | `false` | Snipe by anime/game series name |
| `kakera_snipe_mode` | bool | `false` | Value-based sniping above threshold |
| `kakera_reaction_snipe_mode` | bool | `false` | Auto-click kakera on others' rolls |
| `lurker_mode` | bool | `false` | Wait and snipe, panic-roll at end |
| `key_mode` | bool | `false` | Keep rolling for keys without claim right |
| `auto_rt_after_claim` | bool | `false` | Auto `$rt` after successful claim |
| `main_account_id` | string | `""` | Alt-to-main wishlist sync ID |

</details>

<details>
<summary><strong>🛡️ Anti-Ban & Stealth</strong></summary>

| Setting | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `humanization_enabled` | bool | `false` | Enable all humanization features |
| `humanization_window_minutes` | int | `40` | Random extra wait time after reset |
| `humanization_inactivity_seconds` | int | `5` | Wait for channel silence before rolling |
| `inactive_hours` | list | `[]` | Sleep schedule (e.g., `[[1, 7], [23, 6]]`) |
| `reactive_kakera_delay_range` | list | `[0.3, 1.0]` | Random kakera click delay range |
| `randomized_claim_reactions` | list | `["💖","💗","💘","❤️","👍","🔥"]` | Randomized fallback claim emojis |

</details>

<details>
<summary><strong>⚡ Power & Advanced</strong></summary>

| Setting | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `dk_power_management` | bool | `false` | Auto `$dk` when power is low |
| `auto_dk_enabled` | bool | `true` | Master `$dk` toggle |
| `max_dk_power` | int | `100` | Your max power cap (late-game: 320+) |
| `only_chaos` | bool | `false` | Only click Chaos Kakera (50% power cost) |
| `mk_only` | bool | `false` | Only click kakera from `$mk` rolls |
| `kakera_priority_order` | list | `[see docs]` | Kakera click priority (highest first) |
| `kakera_power_thresholds` | dict | `{}` | Per-emoji min power (e.g., `kakeraY: 80`) |
| `debug_mode` | bool | `false` | Log every incoming roll |

</details>

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!  
Feel free to check the [Issues page](https://github.com/misutesu-desu/MudaRemote/issues).

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Disclaimer

> **This software is provided for educational and research purposes only.** MudaRemote automates interactions with the Mudae Discord bot through a self-bot, which **violates Discord's Terms of Service**. Using this tool may result in:
> - **Permanent account suspension** by Discord
> - **Server bans** from communities that prohibit automation
> - Loss of all characters, kakera, and progress in Mudae
>
> The authors of MudaRemote are **not responsible** for any bans, data loss, or other consequences arising from the use of this software. By using MudaRemote, you acknowledge and accept these risks entirely.
>
> **Do not use this on accounts you are not willing to lose.**

---

<p align="center">
  <strong>⭐ If MudaRemote helped you build your harem, give it a Star! It helps others discover the project. ⭐</strong>
</p>

<p align="center">
  <sub>MudaRemote — Mudae bot, Mudae auto claim, Discord Mudae sniper, Mudae auto kakera, Mudae slash commands bot, auto roll Mudae, Mudae macro, Mudae script, Mudae multi-account sync, Mudae automation, Mudae selfbot, Mudae helper, Mudae tool, Mudae farming bot, Mudae key farming, Mudae power management, Mudae wishlist bot, Mudae Discord tool 2026</sub>
</p>
