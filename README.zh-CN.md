# ⚡ MudaRemote：终极 Mudae 机器人自动化工具

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.0.7-orange.svg)](https://github.com/misutesu-desu/MudaRemote/releases)
[![Status](https://img.shields.io/badge/Status-Active_2026-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Join%20Server-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

[Français](README.fr.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [English](README.md) | [Português Brasileiro](README.pt-BR.md)

**MudaRemote** 是一款专为 **Mudae Discord 机器人** 设计的精密且功能丰富的自动化引擎。它远不止是简单的宏脚本，通过解析实时数据（$tu、嵌入内容、组件）来模拟真人行为，同时最大化您的后宫（Harem）收集效率。

> **⚠️ 关键警告：** MudaRemote 是一个**自号机器人 (Self-bot)**。使用自号机器人违反了 Discord 的服务条款 (ToS)，并存在被永久封号的风险。**请自行承担风险。**

---

## 🏆 为什么选择 MudaRemote？（对比）

不要满足于 2021 年的老旧脚本。请升级到 2025 年的新标准。

| 功能 | 普通 Mudae 机器人 | **MudaRemote v3.0.7** |
| :--- | :--- | :--- |
| **抽卡时机** | 固定/随机定时器 | **战略性边界同步（完美认领）** |
| **命令引擎** | 仅限文本 | **斜杠命令 Slash Commands（支持现代 API）** |
| **$rt 管理** | 无 / 手动 | **全自动智能管理** |
| **更新** | 手动重新下载 | **集成自动更新系统** |
| **隐身性** | 静态延迟 | **模拟真人抖动 & 闲置状态监视器** |
| **本地化** | 仅限英文 | **完美支持 4 种语言** |

---

## ✨ 核心高影响力功能

### 🎯 先进的狙击生态系统
*   **愿望单与系列狙击：** 立即认领他人抽出的角色或整个动漫系列。
*   **智能 Kakera 狙击：** 设置阈值（例如 200+），让机器人自动获取高价值 Kakera。
*   **全局 Kakera 刷取：** 扫描所有消息中的晶体。包含**智能过滤**功能，仅从特定用户（如您的副号）处获取，以保持低调。
*   **混沌模式 (Chaos Mode)：** 针对混沌钥匙（10+ 钥匙角色）的专门逻辑。

### 🤖 智能自动化（“大脑”）
*   **战略性抽卡时机：** 机器人会持有抽卡次数，直到您的认领（Claim）重置前夕才使用，确保您永远不会在认领冷却时浪费抽卡。
*   **斜杠命令引擎：** 可选择使用 `/wa`, `/ha` 等命令，这些命令速度更快，且在 Discord 的检测机制下显著更安全。
*   **智能 $rt 利用：** 自动检测 `$rt` 是否可用，并仅针对高优先级的愿望单目标使用。
*   **DK 能量管理：** 优化您的 Kakera Power 使用情况，确保您始终有足够的能量进行高价值反应。

### 🛡️ 隐身与反封号技术
*   **人性化间隔：** 实施随机“抖动”延迟，使您的活动看起来永远不像是一个 60 分钟的死循环。
*   **闲置监视器：** 检测频道是否繁忙，并在对话间隙（冷场时）再进行抽卡——表现得像一个有礼貌的用户。
*   **钥匙上限保护：** 如果您达到每日 1,000 把钥匙的限制，将自动暂停以防止被标记。

---

## 🛠️ 快速开始

1.  **环境要求**：[Python 3.8+](https://www.python.org/downloads/)
2.  **安装**：
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **运行**：
    ```bash
    python mudae_bot.py
    ```
    *从交互式菜单中选择您的预设，即可准备就绪！*

---

## ⚙️ 配置 (`presets.json`)

为不同的账号或服务器定义多个配置文件。

```json
{
  "MainAccount": {
    "token": "YOUR_TOKEN",
    "channel_id": 123456789,
    "rolling": true,
    "use_slash_rolls": true,            // 推荐开启
    "time_rolls_to_claim_reset": true, // 独特功能
    "min_kakera": 200,
    "humanization_enabled": true,
    "wishlist": ["Makima", "Rem"]
  }
}
```
📖 **需要设置方面的帮助吗？** 请查看我们详细的 [配置指南 (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide)

---

## 🔒 获取您的 Token
1. 在浏览器中打开 Discord。
2. 按下 `F12` -> 进入 `Console` (控制台)。
3. 粘贴以下代码：
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
4. **切勿将此 Token 分享给任何人！**

---

**⭐ 如果这个工具帮您壮大了后宫，请给它点个 Star！这有助于项目的发展和持续更新。**
