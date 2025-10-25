# ✨ MudaRemote：高级 Mudae 自动化 ✨

[![Discord TOS 违规 - **谨慎使用**](https://img.shields.io/badge/Discord%20TOS-VIOLATION-red)](https://discord.com/terms) ⚠️ **账号封禁风险！** ⚠️

**🛑🛑🛑 警告：自用机器人 (Self-Bot) - 潜在的 Discord TOS 违规！账号封禁风险！ 🛑🛑🛑**
**🔥 风险自负！ 🔥 对于您的账号采取的任何行动，我们概不负责。 😱**

---

加入我们的 [Discord 服务器](https://discord.gg/4WHXkDzuZx)

## 🚀 MudaRemote：增强您的 Mudae 体验（请负责任地使用！）

MudaRemote 是一个基于 Python 的自用机器人 (self-bot)，旨在自动化 Discord 机器人 Mudae 的各种任务。它提供实时狙击和智能认领等功能。**然而，使用自用机器人违反了 Discord 的服务条款 (TOS)，可能导致账号暂停或封禁。** 请务必谨慎使用，并理解所涉及的风险。

### ✨ 核心功能：

*   **🎯 外部狙击（许愿单、系列和卡克拉值）：** 认领 *其他用户* 掷出的角色。
*   **🟡 外部卡克拉反应狙击：** 自动点击 *任何* Mudae 消息中的卡克拉反应按钮。
*   **😴 仅狙击模式：** 配置机器人实例，使其 *仅* 监听和执行外部狙击，而不发送掷骰命令。
*   **⚡ 反应式自我掷骰狙击：** 如果 *您自己* 掷出的角色符合标准，则立即认领。
*   **🤖 自动化掷骰与一般认领：** 处理掷骰命令，并根据最小卡克拉值进行认领。
*   **🥇 智能认领逻辑：** 解析 `$tu` 以检查 `$rt` 的可用性，并用于高价值掷骰的潜在第二次认领。
*   **🔄 自动重置检测：** 监控并等待 Mudae 的认领和掷骰重置计时器。
*   **🚶‍♂️ 人性化等待 (NEW!)：** 通过在重置后等待随机时间段和频道不活动状态，模拟人类行为，从而显著降低可预测性。
*   **💡 DK 力量管理 (NEW!)：** 通过 `$tu` 智能检查您的卡克拉反应力量，并且仅在力量不足以进行反应时才使用 `$dk`，从而节省充能。
*   **🔑 钥匙模式：** 即使角色认领处于冷却状态，也允许持续掷骰以收集卡克拉。
*   **⏩ 斜杠掷骰调度 (NEW!)：** 可选功能，使用 Discord 的斜杠命令基础设施而不是文本命令来发送掷骰命令（`wa`、`h`、`m` 等）。
*   **👯 多账号支持：** 同时运行多个机器人实例。
*   **⏱️ 可自定义的延迟和掷骰速度：** 微调所有动作延迟和掷骰命令的速度。
*   **🗂️ 简易预设配置：** 在单个 `presets.json` 文件中管理所有设置。
*   **📊 控制台日志记录：** 清晰、彩色编码的实时输出。
*   **🌐 本地化支持：** 改进了对英语和葡萄牙语 (PT-BR) Mudae 响应的解析。

---

## 🛠️ 设置指南

1.  **🐍 Python：** 确保安装了 Python 3.8+。 ([下载 Python](https://www.python.org/downloads/))
2.  **📦 依赖项：** 打开您的终端或命令提示符并运行：
    ```bash
    pip install discord.py-self inquirer
    ```
    *注意：如果您计划使用 `use_slash_rolls: true`，请确保您的 `discord.py-self` 版本包含 `Route` 对象（较新版本通常包含）。*
3.  **📝 `presets.json`：** 在脚本的目录中创建一个 `presets.json` 文件。在此处添加您的机器人配置。有关所有可用选项，请参阅下面的示例。
4.  **🚀 运行：** 从终端执行脚本：
    ```bash
    python mudae_bot.py
    ```
5.  **🕹️ 选择预设：** 从交互式菜单中选择要运行的已配置机器人。

---

### `presets.json` 配置示例：

*(由于是技术配置，JSON 配置内容与原文保持一致。)*

```json
{
  "YourBotAccountName": {
    // --- REQUIRED SETTINGS ---
    "token": "YOUR_DISCORD_ACCOUNT_TOKEN", 
    "channel_id": 123456789012345678,     
    "roll_command": "wa",                  
    "delay_seconds": 1,                    
    "mudae_prefix": "$",                   
    "min_kakera": 50,                      

    // --- CORE OPERATIONAL MODE ---
    "rolling": true,                       

    // --- ADVANCED ROLLING / CLAIMING ---
    "roll_speed": 0.4,                     
    "key_mode": false,                     
    "skip_initial_commands": false,        // (默认: false) 如果为true，启动时跳过$limroul、$dk和$daily，直接进入$tu。
    "use_slash_rolls": false,              // (默认: false) 如果为true，尝试使用Discord的斜杠命令API发送抽卡命令。
    "dk_power_management": true,           // (默认: false) 如果为true，在$tu中检查kakera力量，仅在必要时使用$dk。

    // 新功能: 仅Chaos钥匙过滤器
    "only_chaos": false,                   // (默认: false) 如果为true，仅在拥有10+钥匙（chaos keys）的角色上点击kakera按钮。           

    // --- HUMANIZATION (Recommended for high-risk accounts) ---
    "humanization_enabled": true,          
    "humanization_window_minutes": 40,     
    "humanization_inactivity_seconds": 5,  

    // --- EXTERNAL SNIPING (For characters rolled by OTHERS) ---
    "snipe_mode": true,                    
    "wishlist": ["Character Name 1", "Character Name 2"],
    "snipe_delay": 2,                      

    "series_snipe_mode": true,             
    "series_wishlist": ["Series Name 1"],
    "series_snipe_delay": 3,               

    "kakera_reaction_snipe_mode": false,   
    "kakera_reaction_snipe_delay": 0.75,   

    // --- KAKERA THRESHOLD (Used for both External and Reactive Sniping) ---
    "kakera_snipe_mode": true,             
    "kakera_snipe_threshold": 100,         

    // --- 响应式狙击（用于您自己抽卡中的角色） ---
    "reactive_snipe_on_own_rolls": true,   // (默认: true) 启用/禁用在您自己抽卡期间的即时领取（基于WL、系列WL或Kakera阈值）。
    "reactive_snipe_delay": 0,             // (默认: 0) 在您自己抽卡期间响应式狙击时领取前的延迟（秒）。有助于显得更自然。   

    // --- OTHER ---
    "start_delay": 0,                      
    "snipe_ignore_min_kakera_reset": false 
  }
}
```

---

## 🎮 获取您的 Discord Token 🔑

自用机器人需要您的 Discord 账号 Token。**此 Token 授予对您账号的完全访问权限 – 请务必将其保持绝对机密！分享它就像泄露您的密码一样。** 建议在备用账号上使用此机器人。

1.  **在您的网络浏览器中打开 Discord**（例如 Chrome、Firefox）。*而不是桌面应用程序。*
2.  按 **F12** 打开开发者工具。
3.  导航到 **`Console`**（控制台）选项卡。
4.  将以下代码片段粘贴到控制台中，然后按 Enter：

    ```javascript
    // [同样的 Javascript 代码片段在此处插入]
    window.webpackChunkdiscord_app.push([
    	[Symbol()],
    	{},
    	req => {
    		if (!req.c) return;
    		for (let m of Object.values(req.c)) {
    			try {
    				if (!m.exports || m.exports === window) continue;
    				if (m.exports?.getToken) return copy(m.exports.getToken());
    				for (let ex in m.exports) {
    					if (m.exports?.[ex]?.getToken && m.exports[ex][Symbol.toStringTag] !== 'IntlMessagesProxy') return copy(m.exports[ex].getToken());
    				}
    			} catch {}
    		}
    	},
    ]);

    window.webpackChunkdiscord_app.pop();
    console.log('%cWorked!', 'font-size: 50px');
    console.log(`%cYou now have your token in the clipboard!`, 'font-size: 16px');
    ```
5.  您的 Token 将被复制到剪贴板。小心地将其粘贴到 `presets.json` 文件中的 `"token"` 字段。

---

## 🤝 贡献

欢迎贡献！随时报告问题、建议功能或向项目存储库提交拉取请求 (pull requests)。

**🙏 请以负责任和道德的方式使用此工具，并充分意识到对您的 Discord 账号的潜在风险。 🙏**

**祝您 Mudae 愉快（并保持警惕！）** 😉

---
**许可证：** [MIT 许可证](LICENSE)
