<p align="center">
  <img src="icon.png" alt="MudaRemote Logo" width="120">
  <h1 align="center">⚡ MudaRemote: Mudae Automation for Discord</h1>
  <p align="center">
    <strong>A desktop tool for automating rolls, claims, Kakera collection, and multi-account presets.</strong>
  </p>
  <p align="center">
    Most settings can be managed from the included interface, without editing configuration files.<br>
    Windows users can download the app and get started with Quick Setup.
  </p>
</p>

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/releases/latest"><img src="https://img.shields.io/badge/Windows-Standalone_.exe-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows EXE"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/badge/Version-4.8.3-f97316?style=for-the-badge" alt="Version 4.8.3"></a>
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

MudaRemote is free and open source. If you use it regularly and would like to support the time spent maintaining it, donations are welcome but never required.

The Discord server now has **310+ members** who use the app, report problems, and share configurations.

### Current goal

**40% funded • $40 of $100 raised by early community supporters • Last updated August 2026**

Donations help cover the time spent on:

- compatibility fixes and regression tests when Discord or Mudae changes;
- Windows builds, checksums, and update testing;
- documentation, translations, and community support;
- open bug reports and feature requests.

Any amount is appreciated. If you want a reference, **$5**, **$15**, and **$30** are common starting points. There is no minimum.

| Asset | Network | Address |
| :--- | :--- | :--- |
| **Litecoin (LTC)** | Litecoin | `LM16i4Sf34zmnGU35AuCmtyMSL3M4Nfutt` |
| **USDT** | TRON (TRC20) | `TQWeEprEbJyk1EcSHDk1pnn7rkgcsTBazp` |

> [!IMPORTANT]
> Verify both the asset and network before sending; crypto transactions cannot be reversed. To receive the optional **Donator** role, send the developer a Discord DM with your transaction ID or a screenshot. You may redact unrelated wallet details. **Never share a seed phrase or private key.** Any confirmed amount qualifies.

You can also help by starring the repository, reporting a reproducible bug, or answering a question in the Discord server.

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/stargazers"><img src="https://img.shields.io/github/stars/misutesu-desu/MudaRemote?style=social" alt="GitHub Stars"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/github/downloads/misutesu-desu/MudaRemote/total?style=social&label=Downloads" alt="Downloads"></a>
</p>

---

## 🚀 What Is MudaRemote?

**MudaRemote** automates repetitive parts of the Mudae minigame on Discord.

It can send rolls, monitor wishlists, collect Kakera, and run several presets. It is configurable, but no self-bot can guarantee account safety.

Main features:

- 📦 **Windows App**: Download the `.exe` and configure it from the desktop interface.
- 🎲 **Automatic Rolls**: Sends `$wa`, `$ha`, `/wa`, or a custom roll command.
- 💍 **Automatic Claims**: Checks rolls against your rules and attempts matching claims.
- 💎 **Kakera Collection**: Clicks configured crystals while keeping track of Kakera power.
- 🎯 **Wishlist Monitoring**: Detects configured wishlist characters and attempts an eligible claim immediately.
- 🤖 **Slash Command Support**: Uses `/wa` where supported for the associated Kakera bonus.
- 👥 **Multi-Account Sync**: Runs multiple presets and coordinates claims between configured accounts.
- 🕒 **Timing Controls**: Optional random delays, sleep schedules, and channel-idle waits. These reduce repetitive timing only; they do not prevent detection or bans.
- 🖥️ **Settings Interface**: Configure common and advanced options from the included editor.
- 🔄 **Confirmed Updates**: The `.exe` shows the changelog and lets you install or skip each new version.

> [!WARNING]
> **This is a self-bot.** Self-bots violate Discord's Terms of Service. Using this software may result in your account being permanently banned. This project exists for **educational purposes only**. You assume all risk. See the [full disclaimer](#%EF%B8%8F-disclaimer).

---

## 🏆 Why Choose MudaRemote?

MudaRemote focuses on a straightforward setup and keeps advanced controls available when you need them.

| | Basic scripts | **MudaRemote** |
| :--- | :---: | :---: |
| **Setup** | Python and manual configuration | Windows app with a settings interface |
| **Rolling** | Usually text commands only | Text and supported slash commands |
| **Claiming** | Basic filters | Wishlist, series, value, rank, and ownership filters |
| **Timing** | Fixed schedules | Configurable delays, inactive hours, and channel activity checks |
| **Accounts** | Often one account per process | Multiple presets with shared coordination |
| **Interface** | Configuration files | Graphical preset editor with a live summary |
| **Updates** | Manual replacement | Verified in-app updates with confirmation |
| **Support** | Varies by project | Active development and a 310+ member Discord server |

---

## ✨ Features

### 🎯 Character Matching and Claims

The bot monitors eligible rolls in configured channels and applies your wishlist, series, value, rank, and ownership rules before attempting a claim.

| Feature | What You Get |
| :--- | :--- |
| **Wishlist Claim** | Attempts to claim characters that match your configured wishlist. |
| **Series Claim** | Love "Naruto"? "Jujutsu Kaisen"? The bot claims characters from your favorite series automatically, with an optional own-rolls-only mode. |
| **Value Snipe** | Set a Kakera threshold (e.g., 500+) and attempt eligible claims on high-value characters. |
| **Instant Self-Claim** | Checks matching characters during a roll batch instead of waiting for the batch to finish. |
| **Panic Claim** | Can use the best available eligible character near the end of a claim window. |
| **Event Card Grab** | Attempts to collect eligible free characters from supported seasonal events. |
| **Auto $rt** | Uses `$rt` when the configured claim flow requires another claim right. |
| **Auto $rt After Claim** | Can use `$rt` after a verified claim. |
| **Avoid List** | Skips characters included in your avoid list. |

---

### 💎 Kakera Collection

The bot can collect selected Kakera buttons and track the power used by each click.

| Feature | What You Get |
| :--- | :--- |
| **Auto Click** | Clicks eligible Kakera buttons according to your settings. |
| **Priority Order** | Multiple crystals on one roll? The bot clicks the most valuable one first. You set the priority. |
| **Power Tracking** | Clicking costs power. The bot monitors your power in real-time and stops clicking before you hit zero. |
| **Auto $dk** | Can use `$dk` when power needs to be restored. |
| **Chaos Mode** | Can limit Kakera clicks to eligible characters with 10 or more keys. |
| **MK Only Mode** | Limits Kakera collection to `$mk` rolls. |
| **Sphere Detection** | Detects supported sphere buttons, which do not consume Kakera power. |
| **Sphere Mini-Games** | Optional Auto `$oh` harvests valuable spheres, while Auto `$oc` solves the red-sphere clue board; `$oh` uses can run as multiplier batches or as separate boards. |
| **Custom Thresholds** | Sets a separate minimum power level for each Kakera type. |

---

### 🎲 Automatic Rolls

Rolls can run immediately, at scheduled times, or relative to the next claim reset.

| Feature | What You Get |
| :--- | :--- |
| **Auto Roll** | Sends `$wa`, `$ha`, `$ma`, or another configured roll command. |
| **Slash Commands** | Uses supported slash commands and falls back to text commands when needed. |
| **Smart Timing** | Can time a roll batch around the next claim reset. |
| **Scheduled Rolls** | Runs at specific times such as 14:00 and 18:30. |
| **Auto $us & $mk** | Supports saved rolls (`$us`) and bonus Kakera rolls (`$mk`). |
| **Lurker Mode** | Watches configured channels before using your own rolls near the end of the claim window. |
| **Key Farming** | Can continue rolling when a claim is unavailable. |

---

### 🕒 Timing & Activity Controls

These controls vary timing and avoid configured inactive periods. They cannot make a self-bot invisible or compliant with Discord's Terms of Service.

| Feature | What You Get |
| :--- | :--- |
| **Random Delays** | Every cycle can use a configurable randomized wait (0-40 min). This does not guarantee account safety. |
| **Channel Awareness** | Can wait while recent conversation is active in the configured channel. |
| **Random Reactions** | Can vary the reaction emoji used for claims. |
| **Sleep Schedule** | Pauses automated actions during a configured time window. |
| **Maintenance Detection** | Pauses commands when Mudae reports maintenance. |
| **Reliable Slash Fallback** | Slash commands are preferred; if Discord's slash endpoint is unavailable, the bot falls back to text commands so rolls and `$tu` state tracking do not stall. |

---

### 🔄 Auto Updates & Multi-Account Sync

Every time you launch MudaRemote, it checks for updates. When a newer version exists, the changelog is shown first and you can install it or continue without updating. Frozen builds require a published SHA-256 checksum; source installs use a complete per-file manifest, protect `presets.json`, and apply all modules transactionally. Git checkouts are never overwritten and instead ask you to run `git pull`.

Configured accounts can share claim reservations and selected reset information while keeping personal account state separate.

---

## 🛠️ Installation

### 🚀 Windows App

The Windows build does not require a separate Python installation.

1. **[⬇️ Download `MudaRemote.exe`](https://github.com/misutesu-desu/MudaRemote/releases/latest)** from the Releases page.
2. Put it in a new folder (e.g., on your Desktop).
3. **Double-click** `MudaRemote.exe` to open the settings window.
4. In **Quick Setup**, paste your **Discord Token** and **Channel ID**, choose what the bot should do, and review the live summary.
5. Click **▶ Save & Start Bot**. Advanced Settings contains the remaining options.

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
5. Copy the token shown in the console into MudaRemote.

---

## 💬 Join the Community

The Discord server has **310+ members** and includes setup help, strategy discussion, feature requests, and release updates.

<p align="center">
  <a href="https://discord.gg/4WHXkDzuZx"><img src="https://img.shields.io/badge/💬_Join_Our_Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord"></a>
</p>

If you find the project useful, you can leave a GitHub star or use one of the support options above.

**Got an issue?**

- 📖 **[Troubleshooting & FAQ (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Troubleshooting)**: Common setup and claim-related problems.
- 📖 **[Configuration Guide (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide)**: Details for each setting.
- 🐛 **[Report a Bug](https://github.com/misutesu-desu/MudaRemote/issues)**: Open an issue with steps to reproduce the problem.

---

## 📜 License

MIT License: free to use, copy, modify, and distribute. See [LICENSE](LICENSE) for details.

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
