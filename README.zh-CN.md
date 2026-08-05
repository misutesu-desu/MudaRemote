<p align="center">
  <h1 align="center">⚡ MudaRemote — Discord 高级 Mudae 自动化工具</h1>
  <p align="center">
    <strong>Mudae Auto Claim • Discord Mudae Sniper • Auto Roll Mudae • Mudae Auto Kakera • Mudae Slash Commands Bot</strong>
  </p>
  <p align="center">
    在一个桌面应用中管理抽卡、角色领取、Kakera 收集和多账号预设。<br>
    时间控制选项不保证规避检测或保障账号安全。
  </p>
</p>

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/releases/latest"><img src="https://img.shields.io/badge/Windows-独立_.exe-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows EXE"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/badge/Version-4.7.9-f97316?style=for-the-badge" alt="Version 4.7.9"></a>
  <a href="#"><img src="https://img.shields.io/badge/Status-Active_2026-10b981?style=for-the-badge" alt="Active 2026"></a>
  <a href="https://discord.gg/4WHXkDzuZx"><img src="https://img.shields.io/badge/Discord-Join_Server-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord Server"></a>
</p>

<p align="center">
  <a href="README.md">English</a> •
  <a href="README.fr.md">Français</a> •
  <a href="README.ja.md">日本語</a> •
  <a href="README.ko.md">한국어</a> •
  <a href="README.tr.md">Türkçe</a> •
  <a href="README.pt-BR.md">Português Brasileiro</a>
</p>

---

## 💖 支持 MudaRemote

MudaRemote 将始终保持**免费和开源**。如果它帮你节省了时间、建立了收藏或简化了 Kakera 收集，你可以自愿支持项目继续开发。

你是一个不断成长的 Discord 社区的一员；**310 多名成员**正在共同使用、测试和改进本项目。

### 第一个社区目标

**目标已完成 40% • 早期社区支持已筹集 40 / 100 美元 • 2026 年 8 月更新**

你的支持能让独立开发者投入更多时间用于：

- Discord 或 Mudae 变更后的兼容修复与回归测试；
- 经过验证的 Windows 版本、校验和与更安全的更新；
- 文档、翻译以及直接的社区支持；
- 处理积压的功能需求和错误。

任何金额都有帮助。如果需要参考，可以考虑价值约 **5 美元**、**15 美元**或**30 美元以上**的加密货币。这些只是建议，不是等级或最低金额；请只选择适合你的数额。

| 资产 | 网络 | 地址 |
| :--- | :--- | :--- |
| **Litecoin (LTC)** | Litecoin | `LM16i4Sf34zmnGU35AuCmtyMSL3M4Nfutt` |
| **USDT** | TRON — TRC20 | `TQWeEprEbJyk1EcSHDk1pnn7rkgcsTBazp` |

> [!IMPORTANT]
> 发送前请同时核对资产和网络；加密货币交易无法撤销。若要领取可选的 **Donator** 身份组，请通过 Discord 私信向开发者发送交易 ID 或截图。你可以遮盖无关的钱包信息。**绝不要分享助记词或私钥。** 任何经确认的金额都可领取身份组。

暂时不想捐赠？为 GitHub 项目点星、提交有帮助的错误报告或帮助其他社区成员，同样是在支持项目。

## 🆕 最新版本 — v4.7.9

- Chaos 与 Perk 8 的 Kakera 选择现在会正确继承普通 Kakera 设置。
- Discord 消息刷新后，四按钮 Perk 8 抽卡仍能稳定处理。
- 红色球体名称 `sp` 与 `spR` 会被识别为同一目标。
- 预设切换速度大幅提高，并能保留选择和未完成草稿。
- Quick Setup 现在支持 `wx`、`hx` 与 `mx` 抽卡池。

## ❓ 这是用来做什么的？

**MudaRemote** 是一个 **Mudae 机器人** —— 一个可以在 Discord 上**自动**帮你玩 Mudae 游戏的程序。

它能做什么：

- 🎲 **Auto roll Mudae** — 自动发送抽卡指令（如 `$wa`, `$ha` 等）。
- 💍 **Mudae auto claim** — 发现好角色？立马自动“娶”回家。
- 💎 **Mudae auto kakera** — 自动点击抽卡中的碎片，帮你赚钱。
- 🎯 **Discord Mudae sniper** — 别人抽到了你想要的角色？脚本会帮你“偷妻”（拦截）。
- 🤖 **Mudae slash commands bot** — 支持 `/wa` 斜杠指令，额外获得 10% 碎片奖励。
- 👥 **Mudae multi-account sync** — 多个小号协同作战，自动同步愿望单。
- 🕒 **时间控制** — 延迟、停用时段与频道等待可减少重复时间模式，但不提供安全保证。
- 🖥️ **简单图形界面** — 无需改代码，点点鼠标即可完成配置。

> **⚠️ 警告:** 这是一个“自用机器人（Self-bot）”。使用 Self-bot **违反 Discord 服务条款**。你的账号**可能会被永久封禁**。本工具仅供**学习研究**使用。使用风险由你承担。

---

## 🏆 为什么它比其他脚本更好用？

| 特性 | 普通宏指令/脚本 | **MudaRemote** |
| :--- | :---: | :---: |
| 抽卡方式 | 仅限文本 (`$wa`) | ✅ 斜杠指令 (`/wa`) — 10% 碎片加成 |
| 娶妻逻辑 | 胡乱抓取 | ✅ 只娶你想要的（愿望单/高价） |
| 时机把控 | 固定循环 | ✅ 完美同步冷却是时间，防止浪费 |
| 安全性 | 极易被发现 | ✅ 模拟真人延迟和行为 |
| 账号支持 | 仅限单号 | ✅ 多账号同时运行 |
| 软件配置 | 修改 JSON 代码 | ✅ 简单易用的图形化窗口 |
| 自动更新 | 需手动下载 | ✅ 程序自动检测并更新 |

---

## ✨ 功能清单（简单版说明）

### 🎯 自动娶妻 — Mudae Auto Claim

脚本会监控已配置频道中的适用抽卡，并按照愿望单、系列、价值和所有者规则尝试领取角色。

| 功能 | 描述 |
| :--- | :--- |
| **愿望单自动娶** | 设置你想要的角色，一出现脚本就会立刻娶走。 |
| **按系列自动娶** | 喜欢“火影忍者”？脚本会自动娶下该系列的所有角色。 |
| **高价值自动娶** | 自动拦截（偷）别人抽到的高价角色（例如 500+ 片以上的）。 |
| **即时自娶** | 自己抽卡时，如果出了好角色，脚本会立刻娶下，不再等待后序。 |
| **补刀模式** | 娶妻冷却快结束时，如果没有遇到好的，会自动娶一个价值最低的防止朗费次数。 |
| **免费活动卡** | 自动抓取圣诞、新年等活动的免费卡片（不扣次数）。 |
| **自动 $rt** | 自动使用 `$rt` 刷新娶妻次数，确保不漏掉任何好角色。 |
| **愿望单同步** | 小号检测到主账号愿望角色时，会按设定规则立即尝试领取。 |

---

### 💎 碎片采集 — Mudae Auto Kakera

自动点击卡片下方的彩色碎片按钮，智能管理能量。

| 功能 | 描述 |
| :--- | :--- |
| **自动点击** | 自动点掉自己和他人抽卡里出的碎片。 |
| **优先级排序** | 如果出的碎片多，脚本会先点价值最高的。 |
| **能量监控** | 根据剩余电量决定是否点击，电量过低时会自动停手。 |
| **自动 $dk** | 电量不足时自动使用 `$dk` 恢复。 |
| **混沌碎片模式** | 针对 10+ key 角色，点击碎片享受 50% 能量减免。 |
| **仅 MK 模式** | 只点击 `$mk` 抽出来的碎片，极其省电。 |
| **球体检测** | 球体（Sphere）点击不需要能量，脚本看到必点。 |

---

### 🎲 自动抽卡 — Auto Roll Mudae

在最聪明的时间点发送抽卡指令。

| 功能 | 描述 |
| :--- | :--- |
| **自动抽卡** | 自动发送抽词，支持所有模式。 |
| **斜杠指令** | 强制使用 `/wa` 而非 `$wa`，更安全且钱更多。 |
| **同步冷却时间** | 自动计算时间，让最后一发抽卡刚好落在娶妻冷却刷新的那一秒。 |
| **定时抽卡** | 可以设置“每天 14:00 和 18:30 准时开抽”。 |
| **自动 $us** | 自动把上一小时没抽完的次数抽掉。 |
| **潜水员模式** | 先看别人抽并偷走好货，等到娶妻冷却快结束前再狂刷自己的次数。 |

---

### 🕒 时间与活动控制

这些选项只会改变操作时间，不能保证避免检测或封号，也不会让 self-bot 符合 Discord 规则。

| 功能 | 描述 |
| :--- | :--- |
| **随机延迟** | 每次循环后随机等待 0-40 分钟，没有固定规律。 |
| **频道静默检测** | 如果频道里有人在聊天，脚本会等待直到没人说话再动，防止引起怀疑。 |
| **随机表情** | 娶妻时随机使用不同的心形表情，避免重复点击。 |
| **按键延迟** | 点击碎片前会有 0.3-1.0 秒随机延迟，模仿人类反应。 |
| **作息计划** | 设置“凌晨 1 点到 7 点睡觉”，脚本会完全停止，像人在睡觉一样。 |
| **维护自停** | 全方位检测 Mudae 维护状态，结束维护后模拟真人延迟上线。 |

---

### 🖥️ 简单的配置工具 (GUI)

无需写代码。运行 `mudae_preset_editor.py` 即可看到图形窗口：
- ✅ 输入 Token 和频道 ID
- ✅ 勾选需要的开关
- ✅ 填写愿望单角色
- ✅ 一键保存、一键启动
- ✅ 支持设置“开机自启动”

---

## 🛠️ 安装步骤（小白版）

### 准备工作
- **[Python 3.8 或更高版本](https://www.python.org/downloads/)** — 安装时务必勾选 ✅ **"Add to PATH"**
- Discord 账号 Token ([下文有获取方法](#-如何获取-discord-token))

### 第 1 步：下载脚本
在 GitHub 点击 **"Code" → "Download ZIP"** 并解压，或者使用命令：
```bash
git clone https://github.com/misutesu-desu/MudaRemote.git
cd MudaRemote
```

### 第 2 步：安装环境
在文件夹内打开终端（CMD），输入：
```bash
pip install -r requirements.txt
```

### 第 3 步：打开设置窗口
```bash
python mudae_preset_editor.py
```
填好 **Token** 和 **频道 ID**，然后点击 **💾 Save Changes**。

### 第 4 步：启动
点击窗口里的 **▶ Launch Bot**。这就大功告成了！ 🎉

---

## 🔑 如何获取 Discord Token
1. 使用**电脑浏览器**登录 Discord (网页版)。
2. 按 **F12**。
3. 点击 **Console** 选项卡。
4. 粘贴下面的代码并回车：
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
5. 出现的一大串乱码就是 Token。 **🚨 绝对不要把 Token 发给任何人，否则他们能控你的号。**

---

## ⚠️ 免责声明（必读！）
> **本程序仅用于教育目的。**
> 使用自用机器人（Self-bot）违反 Discord 规则，可能导致：
> - ❌ **账号被永久封禁**
> - ❌ **被踢出频道**
> - ❌ **所有 Mudae 进度被清空**
> 我们不对您的账号风险负责。请仅在即使丢了也不心疼的账号上使用。

---

<p align="center">
  <strong>⭐ 如果对你有帮助，请给本项目点个 Star！ ⭐</strong>
</p>

<p align="center">
  <sub>MudaRemote — Mudae bot, Mudae auto claim, Discord Mudae sniper, Mudae auto kakera, Mudae slash commands bot, auto roll Mudae, Mudae macro, Mudae script, Mudae multi-account sync, Mudae automation, Mudae selfbot, Mudae helper, Mudae tool, Mudae farming bot, Mudae key farming, Mudae power management, Mudae wishlist bot, Mudae Discord tool 2026</sub>
</p>
