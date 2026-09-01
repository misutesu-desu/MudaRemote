<p align="center">
  <img src="icon.png" alt="MudaRemote" width="120">

  <h1 align="center">⚡ MudaRemote</h1>

  <p align="center">
    Mudae automation without babysitting config files all day
  </p>
</p>

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/releases/latest"><img src="https://img.shields.io/badge/Download-Windows_.exe-0078D6?style=for-the-badge&logo=windows&logoColor=white"></a>
  <a href="https://discord.gg/4WHXkDzuZx"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white"></a>
  <a href="https://github.com/sponsors/misutesu-desu"><img src="https://img.shields.io/badge/Support-%E2%9D%A4-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white"></a>
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

MudaRemote handles the repetitive parts of Mudae for you.

Rolls, claims, Kakera, wishlists, `$mk`, `$rt`, multiple accounts and a bunch of the annoying little cases that come with trying to automate Mudae reliably.

If you're on Windows you can just download the `.exe`, open it and set everything up from the interface. You don't need Python and you don't need to edit JSON files just to get started.

> [!WARNING]
> MudaRemote is a self-bot. Self-bots are against Discord's Terms of Service and using one can get your account banned.
>
> There is no magic "safe mode" that makes a self-bot undetectable. Use it at your own risk and preferably not on an account you aren't willing to lose.

## ❤️ If you use MudaRemote a lot

MudaRemote is free and I want to keep it that way.

There isn't a paid version and I'm not planning to lock useful features behind a subscription.

I spend quite a bit of my free time fixing weird Mudae behavior, Discord changes, regressions, packaging problems and whatever new edge case somebody manages to find in the Discord server.

So if MudaRemote has been useful to you and you feel like helping me keep working on it, you can sponsor me here:

### [❤️ Support MudaRemote on GitHub Sponsors](https://github.com/sponsors/misutesu-desu)

Even $2 genuinely helps. Monthly support is great but one time support is completely fine too.

And seriously, don't feel like you have to pay to use the project. A star, a useful bug report or helping somebody in the Discord server helps as well.

A few people from the community have already chipped in toward the current goal and I'm really grateful for that ❤️

**Current community goal: $60 / $100**

Sponsors can also ask me for the **Donator** role in the MudaRemote Discord server.

<details>
<summary>Prefer crypto?</summary>

<br>

That's fine too.

| Asset    | Network    | Address                              |
| :------- | :--------- | :----------------------------------- |
| Litecoin | Litecoin   | `LM16i4Sf34zmnGU35AuCmtyMSL3M4Nfutt` |
| USDT     | TRON TRC20 | `TQWeEprEbJyk1EcSHDk1pnn7rkgcsTBazp` |

If you want the Donator role after sending crypto, DM me on Discord with the transaction ID or a screenshot.

You can hide unrelated wallet information.

Never send anyone your seed phrase or private key.

</details>

---

## So what does it actually do?

A lot at this point 😅

The short version:

* 🎲 rolls automatically
* 💍 claims characters based on your rules
* 🎯 watches wishlists and series
* 💎 collects the Kakera you want
* 🔋 keeps track of Kakera power
* ♻️ handles `$dk`, `$rt`, `$us`, `$mk` and related flows
* 👥 can run and coordinate multiple presets
* 🕒 supports schedules and different roll timings
* 💤 can stay inactive during configured hours
* 💬 can wait when people are actively talking in the channel
* 🖥️ most settings are available through the desktop interface
* 🔄 checks for updates when the app starts

There are a lot more settings than that but you don't need to understand all of them before using the app.

---

## 🚀 Getting started on Windows

The easiest way to use MudaRemote is the standalone Windows build.

### 1. Download it

**[⬇️ Download the latest MudaRemote.exe](https://github.com/misutesu-desu/MudaRemote/releases/latest)**

You don't need to install Python for this version.

### 2. Put it somewhere

Create a folder for MudaRemote and put the `.exe` inside it.

Desktop is fine.

### 3. Open it

Double click `MudaRemote.exe`.

Quick Setup will ask for the important stuff first.

You'll mainly need:

* your Discord token
* the channel you want to use
* what kind of rolls you want
* what you want MudaRemote to claim
* which Kakera you want it to collect

### 4. Save and start

Check the summary and hit:

**▶ Save & Start Bot**

That's basically it.

You can mess with all the more specific settings later.

---

## 🎯 Claims

MudaRemote doesn't just click every character it sees.

You can decide what is worth claiming.

It supports things like:

* wishlist characters
* specific series
* minimum Kakera value
* rank filters
* ownership filters
* avoid lists
* own-roll-only rules
* instant matching claims
* end of window fallback claims
* event cards

It can also use `$rt` as part of configured claim flows when another claim right is needed.

---

## 💎 Kakera

You can choose which Kakera MudaRemote should collect and when.

It keeps track of power instead of blindly clicking until you're empty.

There is support for:

* Kakera priority
* separate power thresholds
* `$dk`
* `$mk`
* MK-only collection
* Chaos Mode
* sphere detection
* `$oh`
* `$oc`

If multiple eligible Kakera show up together, MudaRemote can use your configured priority instead of just clicking randomly.

---

## 🎲 Rolls

You can use normal text rolls or supported slash commands.

Examples:

```text
$wa
$ha
$ma
/wa
```

Custom roll commands are supported too.

Roll batches can run:

* immediately
* on a schedule
* around claim resets
* after waiting for channel activity to calm down
* with configurable delays

You can also keep rolling for keys even when claiming isn't available.

---

## 👥 Multiple accounts

MudaRemote can run multiple presets at once.

Each preset keeps its own state but configured accounts can coordinate things like claim reservations and reset information.

This is useful if you're already managing multiple Mudae accounts and don't want to run completely separate copies of everything.

---

## 🕒 Timing stuff

There are quite a few timing controls because Mudae automation gets messy very quickly once you stop assuming everything happens at exactly the expected second.

MudaRemote supports:

* random waits
* scheduled rolls
* sleep hours
* channel activity checks
* claim reset timing
* maintenance detection
* slash command fallback

These settings exist to control when the bot acts.

They do **not** make self-botting safe and they do not guarantee protection from Discord bans.

---

## 🔄 Updates

The Windows app checks for updates when it starts.

If a new version exists you'll see the changelog first.

You can install it or keep using your current version.

I don't like apps silently replacing themselves behind your back so the update is still your choice.

MudaRemote also verifies published builds and protects your presets while updating.

---

## 🧑‍💻 Running from source

If you're on Mac/Linux or you just prefer running the Python version:

```bash
git clone https://github.com/misutesu-desu/MudaRemote.git
cd MudaRemote
pip install -r requirements.txt
python mudae_preset_editor.py
```

Python 3.8+ is required.

You can also start a preset directly:

```bash
python mudae_preset_editor.py --preset "MyAccount"
```

---

## 🔑 About your Discord token

Your Discord token is basically your Discord password.

Treat it like one.

Don't post it in issues.

Don't send it to people in the Discord server.

Don't send it to me either.

MudaRemote stores tokens separately from your normal preset configuration.

On Windows it uses DPAPI encryption.

macOS and Linux use the system keyring where available.

Termux uses app-private storage with restricted permissions.

If you're not sure how to get your token or set things up, check the wiki or ask in the Discord server.

---

## 💬 Discord

There are **310+ people** in the MudaRemote Discord now.

People use it for:

* setup help
* reporting bugs
* comparing settings
* requesting features
* testing beta versions
* figuring out why Mudae decided to do something weird again

### [💬 Join the MudaRemote Discord](https://discord.gg/4WHXkDzuZx)

If something is broken, reporting it properly helps me much more than just saying "bot doesn't work" 😭

Useful links:

* 📖 [Troubleshooting & FAQ](https://github.com/misutesu-desu/MudaRemote/wiki/Troubleshooting)
* ⚙️ [Configuration Guide](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide)
* 🐛 [Report a Bug](https://github.com/misutesu-desu/MudaRemote/issues)

---

## ⭐ Help other people find it

GitHub stars aren't money but they actually do help.

More stars means more people find the repo, more people test it and more bugs get found before they hit everyone else.

So if you've been using MudaRemote for a while:

### [⭐ Star MudaRemote](https://github.com/misutesu-desu/MudaRemote)

And if the project has saved you enough time that you want to throw a couple bucks my way:

### [❤️ Sponsor me on GitHub](https://github.com/sponsors/misutesu-desu)

No pressure either way.

I'm just glad people are actually using this thing.

---

## 📜 License

MudaRemote is released under the MIT License.

You're free to use, modify and redistribute it under the terms of the license.

See [LICENSE](LICENSE).

---

## ⚠️ One last reminder

MudaRemote is a self-bot.

Self-bots violate Discord's Terms of Service.

Using one can result in things like:

* your Discord account being banned
* removal from servers
* losing access to your Mudae progress

I can't guarantee your account will be safe and I can't take responsibility for what happens to an account using MudaRemote.

Use it because you understand the risk, not because somebody told you it's undetectable.

---

<p align="center">
  made by someone who got tired of doing repetitive Mudae stuff manually ❤️
</p>
