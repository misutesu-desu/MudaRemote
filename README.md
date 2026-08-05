<p align="center">
  <img src="icon.png" alt="MudaRemote Logo" width="120">
  <h1 align="center">⚡ MudaRemote — Advanced Mudae Automation for Discord</h1>
  <p align="center">
    <strong>Automate rolls, claims, Kakera collection, and multi-account presets from one polished desktop app.</strong>
  </p>
  <p align="center">
    Built for people who want powerful controls without editing code or configuration files.<br>
    Download the Windows app, review your settings, and start from the guided Quick Setup.
  </p>
</p>

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/releases/latest"><img src="https://img.shields.io/badge/Windows-Standalone_.exe-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows EXE"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/badge/Version-4.7.9-f97316?style=for-the-badge" alt="Version 4.7.9"></a>
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

## 💖 Support MudaRemote

MudaRemote will remain **free and open source**. If it has saved you time, helped you build your collection, or made Kakera farming easier, you can voluntarily support its continued development.

You are part of a growing Discord community of **310+ members** using, testing, and improving the project together.

### Our first community milestone

**40% funded • $40 of $100 raised by early community supporters • Last updated August 2026**

Your support gives one independent developer more time for:

- compatibility fixes and regression testing when Discord or Mudae changes;
- verified Windows releases, checksums, and safer updates;
- documentation, translations, and hands-on community support;
- working through the feature and bug backlog.

Every amount helps. If you would like a reference point, consider the crypto equivalent of **$5**, **$15**, or **$30+**. These are suggestions, not tiers or minimums—choose only what feels right for you.

| Asset | Network | Address |
| :--- | :--- | :--- |
| **Litecoin (LTC)** | Litecoin | `LM16i4Sf34zmnGU35AuCmtyMSL3M4Nfutt` |
| **USDT** | TRON — TRC20 | `TQWeEprEbJyk1EcSHDk1pnn7rkgcsTBazp` |

> [!IMPORTANT]
> Verify both the asset and network before sending; crypto transactions cannot be reversed. To receive the optional **Donator** role, send the developer a Discord DM with your transaction ID or a screenshot. You may redact unrelated wallet details. **Never share a seed phrase or private key.** Any confirmed amount qualifies.

Not ready to donate? A GitHub star, a useful bug report, or helping another community member also supports the project.

## 🛠️ Kakera & Preset Stability — v4.7.9

### 🐛 Bug Fixes

- **Exact Kakera colours:** Missing Chaos or Perk 8 overrides now inherit your regular Kakera selection, so a disabled colour cannot silently return through an all-colours default.
- **Reliable Perk 8 collection:** The configured Perk 8 list is honored on both own and external rolls, and repeated four-button rolls remain correctly matched after each Discord message refresh.
- **Red sphere compatibility:** Both `sp` and `spR` button names map to the same red sphere target, including doubled variants.
- **Sphere filters stay explicit:** Clearing every sphere target now disables sphere collection instead of restoring defaults.
- **Stable preset transitions:** Presets load on the click, keep their selection when focus moves, and incomplete drafts can be saved before switching without snapping back to the previous preset. Runtime credentials are still required by **Save & Start Bot**.

### ✨ Improvements

- **More Quick Setup pools:** `wx`, `hx`, and `mx` are now available alongside the existing roll commands.
- **Clearer context overrides:** The editor states when Chaos and Perk 8 emoji lists inherit the regular Kakera selection.
- **Faster editor switching:** Chip updates are batched and emoji cards reuse their loaded artwork instead of rebuilding every option during each preset change.

## 🆕 Advanced Automation & Multi-Account Presets — v4.7.0

### ✨ New Features

- Restrict Kakera clicks to wished/starwished characters; a starwish is detected by an emoji on the character's series line.
- Optionally wait for full Kakera power before using `$mk`, with regeneration/reset-aware status refreshes.
- Auto-divorce can protect wished/starwished characters and series automatically.
- Configure multiple farm characters and multiple encrypted Discord tokens in one preset.
- Apply a preset's settings to every preset while optionally preserving each account's identity and channels.
- Define `$oh` and post-red `$oc` reward priorities, including `$oh` exploration depth and `$oc` stop/continue behavior.
- Inactive-hour windows now support minute precision such as `01:30-07:15`.
- Send a configurable chat message after a successful Kakera snipe.
- Forward selected log types to a Discord webhook and filter Expert Logs by category.

### 🐛 Bug Fixes

- **Spanish Claim Status:** Spanish cooldown messages such as `no puedes reclamar` can no longer be mistaken for `Claim: Ready`, preventing repeated claim attempts.
- **Reliable Farm Restores:** A confirmed forcedivorce now lets the next farm-character roll use `$rt` normally instead of being blocked as a duplicate.
- **No Rejected-Claim `$tu` Loops:** Failed stale claims stay closed when neither a claim right nor `$rt` can retry them.
- **Localized Sphere Boards:** `$oh` and `$oc` now recognize localized 25-button boards without requiring English descriptions.
- **Reliable PT-BR `$p`:** Portuguese ready messages are recognized, and cooldown completion schedules a fresh status check.

### ⚡ Improvements

- **Dark-to-Purple Bonus Clicks:** Separate `spD turns into spP` result messages now add the earned extra `$oh` click.

## 🆕 Safer Automation Controls — v4.6.9

### ✨ New Features

- **Own-Rolls-Only Series Claims:** Series Sniping can now claim matching characters only from your own rolls, without claiming from other players' rolls.
- **Separate Forcedivorce Channel:** Farm forcedivorce commands can now be sent in a dedicated channel instead of the main rolling channel.
- **Update Confirmation:** New updates now show their changelog first, letting you choose whether to install or skip them.

### 🐛 Bug Fixes

- **Sphere Game Limits:** `$oh` and `$oc` now respect Mudae's maximum of 10 uses per command. For example, 11 uses will be sent as `$oc 10` followed by `$oc 1`.

### ⚡ Improvements

- **Safer Updates:** Skipping an update leaves your current installation unchanged.
- **Preset Protection:** Update files can no longer overwrite your saved `presets.json` configurations.

## 🛠️ Status & Sphere Hotfix — v4.6.8

- **No more `/tu` loops:** Manual status checks and responses created by another running MudaRemote instance no longer trigger another `/tu` query.
- **Correct free clicks:** Purple sphere variants grant their extra `$oh` click without consuming one of the five paid clicks.
- **Localized stored uses:** Stored `$oh` and `$oc` counts are detected even when Mudae translates labels such as `stored` to `armazenados`.
- **Better guaranteed rewards:** Revealed green-or-better spheres are collected before the bot continues exploring blue and teal reveal paths.

## 🔴 Sphere Mini-Games — v4.6.6

- **Auto `$oh`:** Reads daily and stored Sphere Harvest uses from `$tu`, spends them together for the active multiplier, explores unknown cells early, claims free purple clicks immediately, saves dark spheres for the endgame, and preserves enough clicks for guaranteed high-value rewards.
- **Auto `$oc`:** Uses every revealed orange, yellow, green, teal, and blue clue to locate the red sphere, then spends every remaining click on the best visible or expected-value reward instead of stopping early.
- **Stored uses:** Bonus `(+N stored)` `$oh` and `$oc` uses earned from tutorials, hidden spheres, or other rewards are included automatically.
- **Safe recovery:** Delayed board edits are verified through both Discord events and fresh message fetches; one failed click is retried before the mini-game stops safely.
- **Preset controls:** Both automations are separate opt-in settings and remain disabled until you enable them.

## ⚙️ Runtime Reliability — v4.6.6

- **Active-only automated stagger:** Selected runnable presets receive compact `0s`, `20s`, `40s` offsets in launch order. Closed, unselected, missing, and tokenless presets no longer add empty delay slots.
- **Consistent launch modes:** GUI launches, multi-select headless runs, `--all`, and Windows autostart now pass the active stagger position explicitly.
- **Cleaner failures:** Invalid tokens stop with one actionable `401 Unauthorized` message, while accidental unknown control-prefix commands are ignored silently.

## 🔐 Termux Token Storage — v4.6.2

- **No shell commands required:** Termux users enter the token once in the editor and save normally.
- **Persistent private storage:** Tokens survive restarts inside Android's Termux-private app directory instead of `presets.json` or shared storage.
- **Restricted access:** The storage directory and token file are locked to owner-only permissions (`0700`/`0600`).
- **Automatic migration:** Existing tokens left in `presets.json` move into the private store on the next editor launch.
- **Reliable forcedivorce confirmation:** Kakera farming now sends the required `y` confirmation through the same paced command queue.
- **No hidden `$rt` usage:** Forcedivorce no longer enables `$rt` on its own; farm claims only use it when **Auto $rt After Claim** is enabled.

## 🚀 Command Pacing & Farming Controls — v4.6.1

- **Reliable claiming and pause:** Claims are verified from live Discord evidence, reset timing is preserved to the second, and pause now stops active rolls, delayed actions, reactions, and button clicks across every account.
- **Far fewer `$tu` commands:** Authoritative cooldowns, completed roll cycles, and exact bonus-roll messages update only the affected local state; fresh-response matching, bounded retries, and backoff prevent query spam without sacrificing recovery.
- **Safer configuration and updates:** Tokens use Windows DPAPI, the operating system keyring, or Termux-private app storage, JSON writes are atomic, and the manifest-based modular updater verifies every downloaded file before applying the release.
- **More resilient automation:** Multi-account claim coordination, scheduled rolls, Kakera cost handling, empty embeds, zero-valued thresholds, and retry exhaustion have been corrected.
- **Flexible Kakera farming:** Independent pre-roll and post-claim forcedivorce controls can be enabled separately or together, and forcedivorce commands can use their own optional channel.
- **Correct stacked power discounts:** The 10+ key discount and visible `💎/2` Perk 8 discount now stack independently, including fractional power costs such as 7.5%.
- **Improved preset editor and diagnostics:** Presets are validated and persisted consistently, dynamic values survive edits, child-process status is visible, logs rotate with tracebacks, and automated regression tests protect the critical flows.

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/stargazers"><img src="https://img.shields.io/github/stars/misutesu-desu/MudaRemote?style=social" alt="GitHub Stars"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/github/downloads/misutesu-desu/MudaRemote/total?style=social&label=Downloads" alt="Downloads"></a>
</p>

---

## 🚀 What Is MudaRemote?

**MudaRemote** is an advanced **Mudae automation tool** that can handle repetitive parts of the Mudae minigame on Discord.

While you sleep, study, or touch grass — MudaRemote can roll characters, watch wishlists, farm Kakera, and manage multiple presets. It is free and configurable, but no self-bot can guarantee account safety.

Here's what you get out of the box:

- 📦 **1-Click Windows App** — Download `.exe`, double-click, done. No Python, no terminal, no headaches.
- 🎲 **Auto Roll Engine** — Sends `$wa`, `$ha`, `/wa`, or any custom roll command on autopilot.
- 💍 **Instant Auto Claim** — Sees a character you want? Claims it in milliseconds — faster than any human.
- 💎 **Smart Kakera Farming** — Clicks crystals automatically while respecting your power limits. Never waste power again.
- 🎯 **Wishlist Monitoring** — Detects configured wishlist characters and attempts an eligible claim immediately.
- 🤖 **Slash Command Support** — Uses `/wa` where supported for the associated Kakera bonus.
- 👥 **Multi-Account Sync** — Run alt accounts simultaneously. Main + alts working in perfect coordination.
- 🕒 **Timing Controls** — Optional random delays, sleep schedules, and channel-idle waits. These reduce repetitive timing only; they do not prevent detection or bans.
- 🖥️ **Beautiful GUI** — No config files. No code. Just a clean settings window with buttons and dropdowns.
- 🔄 **Confirmed Updates** — The `.exe` shows the changelog and lets you install or skip each new version.

> [!WARNING]
> **This is a self-bot.** Self-bots violate Discord's Terms of Service. Using this software may result in your account being permanently banned. This project exists for **educational purposes only**. You assume all risk. See the [full disclaimer](#%EF%B8%8F-disclaimer).

---

## 🏆 Why Choose MudaRemote?

Still using a janky Python script from 2022 that makes you edit JSON files in Notepad? Here's reality:

| | 💀 Old Terminal Bots | ⚡ **MudaRemote** |
| :--- | :---: | :---: |
| **Setup** | Install Python, pip, edit config files, pray | ✅ Download `.exe` → Double-click → Play |
| **Rolling** | Text commands only (`$wa`) | ✅ Slash commands (`/wa`) — **+10% Kakera bonus** |
| **Claiming** | Claims random garbage | ✅ Surgically claims only YOUR wishlist & high-value targets |
| **Timing** | Rolls at the same second every hour | ✅ Configurable random delays and inactive hours; no safety guarantee |
| **Timing controls** | Fixed repetitive timing | ✅ Configurable delays, inactive hours, and channel awareness; no safety guarantee |
| **Accounts** | One account, one terminal | ✅ Multiple accounts running simultaneously in sync |
| **Interface** | Scary black terminal window | ✅ Beautiful graphical settings editor with live preview |
| **Updates** | Re-download the whole repo | ✅ Verified in-app updates with changelog and confirmation |
| **Support** | Abandoned repo, no Discord | ✅ Active development + 310+ member Discord community |

---

## ✨ Full Feature Breakdown

### 🎯 Claiming — Fast, Configurable Character Matching

The bot monitors eligible rolls in configured channels and applies your wishlist, series, value, rank, and ownership rules before attempting a claim.

| Feature | What You Get |
| :--- | :--- |
| **Wishlist Claim** | Build your dream list. The moment a wishlist character appears, it's yours — claimed in under a second. |
| **Series Claim** | Love "Naruto"? "Jujutsu Kaisen"? The bot claims characters from your favorite series automatically, with an optional own-rolls-only mode. |
| **Value Snipe** | Set a Kakera threshold (e.g., 500+) and attempt eligible claims on high-value characters. |
| **Instant Self-Claim** | Mid-roll and something incredible appears? Claimed on the spot — no waiting for the batch to finish. |
| **Panic Claim** | Claim timer expiring and nothing good showed up? The bot grabs the best available so you never waste a claim. |
| **Event Card Grab** | Attempts to collect eligible free characters from supported seasonal events. |
| **Auto $rt** | Automatically uses `$rt` to unlock extra claims exactly when you need them most. |
| **Auto $rt After Claim** | Immediately fires `$rt` after claiming — reloads your claim so you can double-tap back-to-back. |
| **Avoid List** | Certain characters you'd never want? Blacklist them forever. The bot won't touch them. |

---

### 💎 Kakera — Automated Crystal Farming on Autopilot

Kakera crystals are money. The bot clicks them **instantly** on every roll — but it's smart enough to manage your power budget so you never go broke.

| Feature | What You Get |
| :--- | :--- |
| **Auto Click** | Every Kakera crystal, every roll, every time — clicked instantly without you lifting a finger. |
| **Priority Order** | Multiple crystals on one roll? The bot clicks the most valuable one first. You set the priority. |
| **Power Tracking** | Clicking costs power. The bot monitors your power in real-time and stops clicking before you hit zero. |
| **Auto $dk** | Power running low? The bot automatically uses `$dk` to refill — keeps the farm running non-stop. |
| **Chaos Mode** | Characters with 10+ keys have "Chaos Kakera" that costs 50% less power. Target only these for maximum efficiency. |
| **MK Only Mode** | Only farm Kakera from `$mk` rolls. Ignore everything else. Surgical power conservation. |
| **Sphere Detection** | Spheres cost **zero** power. The bot **always** clicks them — free money, no exceptions. |
| **Sphere Mini-Games** | Optional Auto `$oh` harvests valuable spheres, while Auto `$oc` solves the red-sphere clue board; stored uses are sent in batches of at most 10. |
| **Custom Thresholds** | Fine-tune per crystal type: *"Only click Purple Kakera if I have 80%+ power."* The bot obeys. |

---

### 🎲 Rolling — The Smartest Roll Engine Ever Built

The bot doesn't just spam rolls. It calculates the **optimal moment** to roll so your last roll lands right when your claim resets — maximizing every single cycle.

| Feature | What You Get |
| :--- | :--- |
| **Auto Roll** | Sends `$wa`, `$ha`, `$ma`, or any custom command — fully automatic, fully configurable. |
| **Slash Commands** | Uses `/wa` instead of `$wa` for a **10% Kakera bonus** and reduced detection footprint. |
| **Smart Timing** | Calculates roll timing so your final roll finishes exactly when your claim resets. Perfect sync, every cycle. |
| **Scheduled Rolls** | Set specific times — *"Roll at 14:00 and 18:30 every day."* The bot shows up on time, every time. |
| **Auto $us & $mk** | Automatically fires your saved rolls (`$us`) and bonus Kakera rolls (`$mk`). Nothing goes to waste. |
| **Lurker Mode** | Watches configured channels before using your own rolls near the end of the claim window. |
| **Key Farming** | No claim available? The bot keeps rolling anyway — farming keys so your next claimed character is worth even more. |

---

### 🕒 Timing & Activity Controls

These controls vary timing and avoid configured inactive periods. They cannot make a self-bot invisible or compliant with Discord's Terms of Service.

| Feature | What You Get |
| :--- | :--- |
| **Random Delays** | Every cycle can use a configurable randomized wait (0–40 min). This does not guarantee account safety. |
| **Channel Awareness** | People chatting in the channel? The bot waits for silence. Just like a real player would. |
| **Random Reactions** | Claims with emoji reactions? It picks a different heart emoji each time. No patterns. |
| **Sleep Schedule** | Set a sleep window — *"Go dark from 1 AM to 7 AM."* The bot shuts off completely, like you're actually sleeping. |
| **Maintenance Detection** | Mudae goes offline for maintenance? The bot detects it and pauses automatically. No wasted commands. |
| **Reliable Slash Fallback** | Slash commands are preferred; if Discord's slash endpoint is unavailable, the bot falls back to text commands so rolls and `$tu` state tracking do not stall. |

---

### 🔄 Auto Updates & Multi-Account Sync

Every time you launch MudaRemote, it checks for updates. When a newer version exists, the changelog is shown first and you can install it or continue without updating. Frozen builds require a published SHA-256 checksum; source installs use a complete per-file manifest, protect `presets.json`, and apply all modules transactionally. Git checkouts are never overwritten and instead ask you to run `git pull`.

Running multiple accounts? Your **main account and alts sync in real-time**. If an alt rolls your wishlist character, your main claims it instantly. Full coordination, zero effort.

---

## 🛠️ Installation

### 🚀 The Easy Way — For Gamers (Takes 30 Seconds)

**No coding. No Python. No terminal. Just click and play.**

1. **[⬇️ Download `MudaRemote.exe`](https://github.com/misutesu-desu/MudaRemote/releases/latest)** from the Releases page.
2. Put it in a new folder (e.g., on your Desktop).
3. **Double-click** `MudaRemote.exe` — the settings window opens instantly.
4. In **Quick Setup**, paste your **Discord Token** and **Channel ID**, choose what the bot should do, and review the live summary.
5. Click **▶ Save & Start Bot**. Use **Advanced Settings** only when you need detailed control. 🎉

New profiles use a recommended baseline: `/wa` rolls with text fallback, automatic matching claims at 100+ Kakera, free-claim collection, and Kakera collection on your own rolls. Claiming or collecting from other players is always opt-in in Quick Setup.

---

### 🧑‍💻 The Developer Way (Python / Mac / Linux)

For developers or non-Windows users who want to run from source:

1. Install **[Python 3.8+](https://www.python.org/downloads/)**.
2. Clone and install:
   ```bash
   git clone https://github.com/misutesu-desu/MudaRemote.git
   cd MudaRemote
   pip install -r requirements.txt
   ```
3. Launch the GUI:
   ```bash
   python mudae_preset_editor.py
   ```
   > **💡 Pro tip:** Run a specific preset headlessly with `python mudae_preset_editor.py --preset "MyAccount"`

---

## 🔑 How to Get Your Discord Token

> [!CAUTION]
> **Your token is your password.** Anyone who has it can fully access your Discord account. **NEVER share it with anyone.**

MudaRemote stores tokens outside `presets.json`: Windows uses DPAPI encryption, macOS/Linux use the system keyring, and Termux uses Android's app-private storage with owner-only directory/file permissions (`0700`/`0600`). Termux users can save once in the editor and restart without shell commands. Headless environments may still override storage with `MUDAREMOTE_TOKEN_<PRESET_NAME>`.

1. Open **Discord in your web browser** (not the desktop app).
2. Press **`F12`** to open Developer Tools.
3. Click the **Console** tab.
4. Paste this snippet and press **Enter**:
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
5. A long string will appear — **that's your token**. Copy it into MudaRemote.

---

## 💬 Join the Community

**You're not alone.** Join our community of **310+ members** on Discord for setup help, strategy discussion, feature requests, and release updates.

<p align="center">
  <a href="https://discord.gg/4WHXkDzuZx"><img src="https://img.shields.io/badge/💬_Join_Our_Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord"></a>
</p>

If MudaRemote helps you, **leave a GitHub star** to help other players discover the project—or support development through the crypto options above.

**Got an issue?**

- 📖 **[Troubleshooting & FAQ (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Troubleshooting)** — Fixes for common setup issues, claiming problems, and more.
- 📖 **[Configuration Guide (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide)** — Deep dive into every single setting.
- 🐛 **[Report a Bug](https://github.com/misutesu-desu/MudaRemote/issues)** — Found something broken? Let us know.

---

## 📜 License

MIT License — free to use, copy, modify, and distribute. See [LICENSE](LICENSE) for details.

---

## ⚠️ Disclaimer

> **This software is provided for educational and research purposes only.**
>
> MudaRemote is a **self-bot**. Self-bots are a direct violation of **[Discord's Terms of Service](https://discord.com/terms)**. By using this software, you acknowledge and accept the following risks:
>
> - ❌ **Permanent ban** from Discord
> - ❌ **Removal** from Discord servers
> - ❌ **Loss** of all Mudae characters and progress
>
> **The developers of MudaRemote assume zero liability** for any consequences resulting from the use of this software. Use at your own discretion and **only on accounts you are willing to lose**.

---

<p align="center">
  <strong>⭐ Find MudaRemote useful? Star the repository and help more players discover the project. ⭐</strong>
</p>

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/stargazers"><img src="https://img.shields.io/github/stars/misutesu-desu/MudaRemote?style=for-the-badge&color=f59e0b&label=%E2%AD%90%20Stars" alt="Star this repo"></a>
</p>
