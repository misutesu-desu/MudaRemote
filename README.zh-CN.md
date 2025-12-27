# ⚡ MudaRemote: 终极 Mudae 自动化工具 ⚡

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![版本](https://img.shields.io/badge/Version-3.0.2-orange.svg)]()
[![Status](https://img.shields.io/badge/Status-Active-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-加入-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

> **⚠️ 严重警告 ⚠️**
> 
> **MudaRemote 是一个 SELF-BOT。** 自动化用户账户违反了 [Discord 的服务条款](https://discord.com/terms)。
> 使用此工具存在账户被暂停或封禁的风险。**请自行承担使用风险。** 开发人员对任何后果概不负责。

---

## 🚀 概述

**MudaRemote** 是一款专为 Discord 机器人 Mudae 设计的高性能、功能丰富的自动化引擎。它远不止简单的自动滚动宏，还提供智能状态管理、精准的狙击（Sniping）功能和高级人性化设置，在最大限度提高后宫效率的同时保护您的账户安全。

与基本宏不同，MudaRemote 实时解析 Mudae 的响应（$tu、消息、嵌入），从而智能地决定何时滚动、何时休眠以及领取什么。

---

## ✨ 核心功能

### 🎯 高级狙击生态系统
*   **心愿单狙击 (Wishlist Sniping)**：立即领取*其他用户*滚出的您 `wishlist` 中的角色。
*   **系列狙击 (Series Sniping)**：以此系列为目标！如果有人滚出受追踪系列中的角色，它就是您的了。
*   **Kakera 价值狙击**：即使角色不在心愿单中，如果其 Kakera 价值超过您设定的阈值，也会自动狙击。
*   **全局 Kakera 耕作**：机器人会监视**每条**消息中的 Kakera 反应按钮。
    *   *新功能:* **智能过滤**：配置为仅从特定用户（例如您的小号）那里窃取 Kakera，以避免服务器纠纷。
    *   *新功能:* **混沌模式**：智能处理混沌钥匙 (Chaos Keys) 与普通 Kakera 的区别。

### 🤖 智能自动化
*   **智能滚动**：自动处理每小时滚动（$wa、$hg、$ma 等）并追踪您的 $daily 重置。
*   **斜杠命令引擎**：可选使用现代 Discord `/commands` 进行滚动，这比传统文本命令更快，且通常更少受到速率限制。
*   **自动更新系统**： 
    *   自动检测远程存储库中的新版本并本地更新脚本。
*   **自定义表情符号配置**： 
    *   *新功能:* 个性化您的机器人！现在可以按预设定义领取心形、Kakera 水晶和混沌钥匙 python 的自定义列表。
*   **Reset Timer ($rt) 优化**： 
    *   智能检测并自动执行 `$rt` 以确保获得多个高价值目标。

### 🛡️ 隐身与安全
*   **人性化间隔**：不再有机械式的 60 分钟计时器。机器人会在每个等待期增加随机的“抖动 (jitter)”。
*   **不活跃观察者**：检测频道何时繁忙，并等待对话平息后再发送滚动，模拟有礼貌的人类用户。
*   **钥匙限制检测**：如果您达到 Mudae 钥匙限制，自动暂停滚动。

---

## 🛠️ 安装

1.  **先决条件**：
    *   安装 [Python 3.8](https://www.python.org/downloads/) 或更高版本。
2.  **安装依赖项**：
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **设置**：
    *   下载此存储库。
    *   创建 `presets.json` 文件（参见下面的配置）。

---

## ⚙️ 配置 (`presets.json`)

所有设置均在 `presets.json` 中管理。您可以定义多个机器人配置文件（例如，“主账号”、“小号”）并同时运行它们。

```json
{
  "我的超级Muda机器人": {
    "token": "在此处输入您的DISCORD令牌",
    "channel_id": 123456789012345678,
    "prefix": "!", 
    "mudae_prefix": "$",
    "roll_command": "wa",

    "// --- 核心设置 ---": "",
    "rolling": true,                       // 设置为 false 以进入“仅狙击”模式（不滚动，仅监视）
    "min_kakera": 200,                     // 在您自己滚动期间领取角色的最低值
    "delay_seconds": 2,                    // 基础处理延迟
    "roll_speed": 1.5,                     // 滚动命令之间的秒数

    "// --- 狙击配置 ---": "",
    "snipe_mode": true,                    // 心愿单狙击的主开关
    "wishlist": ["Makima", "Rem"],         // 要狙击的确切角色名称列表
    "snipe_delay": 0.5,                    // 狙击速度（秒）
    
    "series_snipe_mode": true,
    "series_wishlist": ["Chainsaw Man"],   // 要狙击的系列名称列表
    "series_snipe_delay": 1.0,

    "// --- KAKERA 耕作 ---": "",
    "kakera_reaction_snipe_mode": true,    // 点击任何消息上的 kakera 按钮？
    "kakera_reaction_snipe_delay": 0.8,
    "kakera_reaction_snipe_targets": [     // 可选：仅从这些特定用户（例如您的小号）那里窃取
        "my_alt_account_username"
    ],
    "only_chaos": false,                   // 如果为 true，则仅对混沌钥匙（紫色）水晶做出反应。

    "// --- 高级逻辑 ---": "",
    "use_slash_rolls": true,               // 使用 /wa 代替 $wa（强烈推荐）
    "dk_power_management": true,           // 保留 $dk 充能以备不时之需
    "snipe_ignore_min_kakera_reset": true, // 如果领取重置在 < 1 小时内，领取任何角色。
    "key_mode": false,                     // 即使没有领取权也继续滚动以获取钥匙？
    "time_rolls_to_claim_reset": true,    // 将滚动时机对齐领取重置（效率最大化）
    "rt_ignore_min_kakera_for_wishlist": false, // 即使价值 < min_kakera，也对心愿单使用 $rt？

    "// --- 自定义表情符号 (可选) ---": "",
    "claim_emojis": ["💖", "💗"],          // 要点击的自定义心形
    "kakera_emojis": ["kakeraY", "kakeraO"], // 自定义 Kakera 水晶
    "chaos_emojis": ["kakeraP"]            // 自定义混沌钥匙 (10+ key 角色)

    "// --- 人性化 ---": "",
    "humanization_enabled": true,
    "humanization_window_minutes": 30,     // 重置后随机额外等待 0-30 分钟
    "humanization_inactivity_seconds": 10  // 在滚动前等待频道静默 10 秒
  }
}
```

---

## 🎮 用法

1.  在机器人文件夹中打开终端。
2.  运行脚本：
    ```bash
    python mudae_bot.py
    ```
3.  从菜单中选择您的预设。
4.  坐下来，看着后宫壮大。📈

---

## 🔒 获取您的令牌

1.  在浏览器（Chrome/Firefox）中登录 Discord。
2.  按 **F12**（开发者工具）-> **Console**（控制台）选项卡。
3.  粘贴此代码以显示您的令牌：
    ```javascript
    window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
    ```
    *（注意：切勿与任何人共享此令牌。它给予了对您帐户的完全访问权限。）*

---

**祝狩猎愉快！** 💖
