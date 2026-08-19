<p align="center">
  <h1 align="center">⚡ MudaRemote: Discord Mudae 自动化工具</h1>
  <p align="center">
    <strong>在一个应用中管理抽卡、角色领取、Kakera 收集和多账号预设。</strong>
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
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/badge/Version-4.8.10-f97316?style=for-the-badge" alt="Version 4.8.10"></a>
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

MudaRemote 是免费开源软件。如果你经常使用，并希望支持维护所花费的时间，可以选择捐赠。捐赠并非必需。

Discord 服务器已有 **310 多名成员**，大家会分享配置、报告问题并讨论使用方法。

### 当前目标

**目标已完成 40% • 早期社区支持已筹集 40 / 100 美元 • 2026 年 8 月更新**

捐赠会用于支持以下工作所需的时间：

- Discord 或 Mudae 变更后的兼容修复与回归测试；
- 经过验证的 Windows 版本、校验和与更安全的更新；
- 文档、翻译以及直接的社区支持；
- 处理积压的功能需求和错误。

金额没有下限。如果需要参考，可以选择价值约 **5 美元**、**15 美元**或**30 美元**的加密货币。

| 资产 | 网络 | 地址 |
| :--- | :--- | :--- |
| **Litecoin (LTC)** | Litecoin | `LM16i4Sf34zmnGU35AuCmtyMSL3M4Nfutt` |
| **USDT** | TRON (TRC20) | `TQWeEprEbJyk1EcSHDk1pnn7rkgcsTBazp` |

> [!IMPORTANT]
> 发送前请同时核对资产和网络；加密货币交易无法撤销。若要领取可选的 **Donator** 身份组，请通过 Discord 私信向开发者发送交易 ID 或截图。你可以遮盖无关的钱包信息。**绝不要分享助记词或私钥。** 任何经确认的金额都可领取身份组。

暂时不想捐赠？为 GitHub 项目点星、提交有帮助的错误报告或帮助其他社区成员，同样是在支持项目。

## ❓ 这是用来做什么的？

**MudaRemote** 用于自动处理 Discord Mudae 中的重复操作。

主要功能：

- 🎲 **自动抽卡**: 发送 `$wa`、`$ha` 或其他已配置的指令。
- 💍 **自动领取**: 按照设定规则检查角色并尝试领取。
- 💎 **Kakera 收集**: 根据剩余能量点击选定类型的 Kakera。
- 🎯 **愿望单监控**: 检测设定角色，并在满足条件时尝试领取。
- 🤖 **Mudae slash commands bot**: 支持 `/wa` 斜杠指令，额外获得 10% 碎片奖励。
- 👥 **多账号支持**: 运行多个预设并协调账号之间的领取操作。
- 🕒 **时间控制**: 延迟、停用时段与频道等待可减少重复时间模式，但不提供安全保证。
- 🖥️ **简单图形界面**: 无需改代码，点点鼠标即可完成配置。

> **⚠️ 警告:** 这是一个“自用机器人（Self-bot）”。使用 Self-bot **违反 Discord 服务条款**。你的账号**可能会被永久封禁**。本工具仅供**学习研究**使用。使用风险由你承担。

---

## 🏆 MudaRemote 的特点

| 特性 | 基础脚本 | **MudaRemote** |
| :--- | :---: | :---: |
| 抽卡方式 | 通常仅支持文本 | 文本与受支持的斜杠指令 |
| 领取条件 | 基础筛选 | 愿望单、系列、价值、排名和所有者筛选 |
| 时间设置 | 固定循环 | 可配置延迟和停用时段 |
| 账号支持 | 通常每个进程一个账号 | 多预设协同运行 |
| 软件配置 | 手动修改配置文件 | 图形化预设编辑器 |
| 自动更新 | 手动替换文件 | 带确认步骤的校验更新 |

---

## ✨ 功能

### 🎯 角色匹配与领取

脚本会监控已配置频道中的适用抽卡，并按照愿望单、系列、价值和所有者规则尝试领取角色。

| 功能 | 描述 |
| :--- | :--- |
| **愿望单自动娶** | 设置你想要的角色，一出现脚本就会立刻娶走。 |
| **按系列领取** | 对已设置系列中符合条件的角色尝试领取。 |
| **按价值领取** | 对超过 Kakera 阈值的角色尝试领取。 |
| **即时自娶** | 自己抽卡时，如果出了好角色，脚本会立刻娶下，不再等待后序。 |
| **补刀模式** | 在领取时间结束前，可从符合条件的候选中选择优先级最高的角色。 |
| **免费活动卡** | 自动抓取圣诞、新年等活动的免费卡片（不扣次数）。 |
| **自动 $rt** | 在设定流程需要额外领取次数时使用 `$rt`。 |
| **愿望单同步** | 小号检测到主账号愿望角色时，会按设定规则立即尝试领取。 |

---

### 💎 碎片采集: Mudae Auto Kakera

自动点击卡片下方的彩色碎片按钮，智能管理能量。

| 功能 | 描述 |
| :--- | :--- |
| **自动点击** | 自动点掉自己和他人抽卡里出的碎片。 |
| **优先级排序** | 如果出的碎片多，脚本会先点价值最高的。 |
| **能量监控** | 根据剩余电量决定是否点击，电量过低时会自动停手。 |
| **自动 $dk** | 电量不足时自动使用 `$dk` 恢复。 |
| **混沌碎片模式** | 针对 10+ key 角色，点击碎片享受 50% 能量减免。 |
| **仅 MK 模式** | 将 Kakera 收集限制在 `$mk` 抽卡。 |
| **球体检测** | 检测不消耗能量的受支持球体。 |

---

### 🎲 自动抽卡: Auto Roll Mudae

在最聪明的时间点发送抽卡指令。

| 功能 | 描述 |
| :--- | :--- |
| **自动抽卡** | 自动发送抽词，支持所有模式。 |
| **斜杠指令** | 使用受支持的斜杠指令，并在需要时回退到文本指令。 |
| **同步冷却时间** | 可根据下一次领取重置安排一轮抽卡。 |
| **定时抽卡** | 可以设置“每天 14:00 和 18:30 准时开抽”。 |
| **自动 $us** | 自动把上一小时没抽完的次数抽掉。 |
| **潜水员模式** | 监控设定频道，并在领取时段结束前使用自己的抽卡次数。 |

---

### 🕒 时间与活动控制

这些选项只会改变操作时间，不能保证避免检测或封号，也不会让 self-bot 符合 Discord 规则。

| 功能 | 描述 |
| :--- | :--- |
| **随机延迟** | 每次循环后随机等待 0-40 分钟，没有固定规律。 |
| **频道活动检测** | 如果设定频道最近有对话，可以暂时等待。 |
| **随机表情** | 娶妻时随机使用不同的心形表情，避免重复点击。 |
| **按键延迟** | 可设置点击 Kakera 前的等待时间。 |
| **作息计划** | 在设定时段暂停自动操作。 |
| **维护自停** | Mudae 处于维护状态时暂停操作。 |

---

### 🖥️ 简单的配置工具 (GUI)

无需写代码。运行 `mudae_preset_editor.py` 即可看到图形窗口：
- ✅ 输入 Token 和频道 ID
- ✅ 勾选需要的开关
- ✅ 填写愿望单角色
- ✅ 一键保存、一键启动
- ✅ 支持设置“开机自启动”

---

## 🛠️ 安装步骤

### 准备工作
- **[Python 3.8 或更高版本](https://www.python.org/downloads/)**: 安装时务必勾选 ✅ **"Add to PATH"**
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
  <strong>⭐ 如果项目对你有帮助，可以在 GitHub 上点个 Star。</strong>
</p>
