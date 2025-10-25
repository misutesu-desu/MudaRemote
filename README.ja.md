# ✨ MudaRemote：高度なMudae自動化 ✨

[![Discord TOS違反 - **注意して使用してください**](https://img.shields.io/badge/Discord%20TOS-VIOLATION-red)](https://discord.com/terms) ⚠️ **アカウントBANのリスクあり！** ⚠️

**🛑🛑🛑 警告：セルフボット - Discord TOSに違反する可能性あり！アカウントBANのリスクあり！ 🛑🛑🛑**
**🔥 自己責任でご使用ください！ 🔥 アカウントに対して行われたいかなる措置についても、私たちは責任を負いません。 😱**

---

私たちの [Discordサーバーに参加](https://discord.gg/4WHXkDzuZx)

## 🚀 MudaRemote：Mudae体験を向上させる（責任を持って使用してください！）

MudaRemoteは、DiscordボットMudaeのさまざまなタスクを自動化するために設計されたPythonベースのセルフボットです。リアルタイムスナイピングやインテリジェントなクレームなどの機能を提供します。**しかし、セルフボットの使用はDiscordの利用規約（TOS）に違反しており、アカウントの停止やBANにつながる可能性があります。** 極度の注意を払って使用し、関連するリスクを理解してください。

### ✨ 主な機能：

*   **🎯 外部スナイピング（ウィッシュリスト、シリーズ、カケラ値）：** *他のユーザー*がロールしたキャラクターをクレームします。
*   **🟡 外部カケラ反応スナイピング：** *任意の* Mudaeメッセージのカケラ反応ボタンを自動的にクリックします。
*   **😴 スナイプ専用モード：** ロールコマンドを送信せずに、外部スナイプを*のみ*リッスンして実行するようにボットインスタンスを設定します。
*   **⚡ リアクティブなセルフロールスナイピング：** *自分の*ロールからのキャラクターが基準に一致した場合、即座にクレームします。
*   **🤖 自動ローリングと一般クレーム：** ロールコマンドを処理し、最小カケラに基づいてクレームします。
*   **🥇 インテリジェントなクレームロジック：** `$tu`を解析して`$rt`の利用可能性を確認し、高価値ロールに対して潜在的な2回目のクレームに使用します。
*   **🔄 自動リセット検出：** Mudaeのクレームおよびロールのリセットタイマーを監視し、待ちます。
*   **🚶‍♂️ 人間化された待機 (NEW!)：** リセット後にランダムな期間およびチャンネルの非アクティブ状態を待ってからアクションを再開することで、人間の行動をシミュレートし、予測可能性を大幅に減らします。
*   **💡 DKパワー管理 (NEW!)：** `$tu`を介してカケラ反応パワーをインテリジェントにチェックし、反応にパワーが不十分な場合に*のみ* `$dk`を使用して、チャージを節約します。
*   **🔑 キーモード：** キャラクターのクレームがクールダウン中でも、カケラ収集のために連続してロールできるようにします。
*   **⏩ スラッシュロールディスパッチ (NEW!)：** テキストコマンドの代わりに、Discordのスラッシュコマンドインフラストラクチャを使用してロールコマンド（`wa`、`h`、`m`など）を送信するオプション機能。
*   **👯 マルチアカウントサポート：** 複数のボットインスタンスを同時に実行します。
*   **⏱️ カスタマイズ可能な遅延とロール速度：** すべてのアクション遅延とロールコマンドの速度を細かく調整します。
*   **🗂️ 簡単なプリセット設定：** すべての設定を単一の `presets.json` ファイルで管理します。
*   **📊 コンソールロギング：** クリアで色分けされたリアルタイム出力。
*   **🌐 ローカリゼーションサポート：** 英語とポルトガル語（PT-BR）の両方のMudae応答に対する解析を改善。

---

## 🛠️ セットアップガイド

1.  **🐍 Python：** Python 3.8以降がインストールされていることを確認してください。 ([Pythonをダウンロード](https://www.python.org/downloads/))
2.  **📦 依存関係：** ターミナルまたはコマンドプロンプトを開き、以下を実行します。
    ```bash
    pip install discord.py-self inquirer
    ```
    *注意: `use_slash_rolls: true`を使用する予定がある場合は、`discord.py-self`のバージョンに `Route` オブジェクトが含まれていることを確認してください（通常、新しいバージョンには含まれています）。*
3.  **📝 `presets.json`：** スクリプトのディレクトリに `presets.json` ファイルを作成します。ここにボット構成を追加します。利用可能なすべてのオプションについては、以下の例を参照してください。
4.  **🚀 実行：** ターミナルからスクリプトを実行します。
    ```bash
    python mudae_bot.py
    ```
5.  **🕹️ プリセットの選択：** 対話型メニューから、実行する構成済みボットを選択します。

---

### `presets.json` 設定例：

*(技術的な構成のため、JSON設定内容はオリジナルと同じです。)*

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
    "skip_initial_commands": false,        // (デフォルト: false) trueの場合、起動時に$limroul、$dk、$dailyをスキップし、直接$tuに移動します。
    "use_slash_rolls": false,              // (デフォルト: false) trueの場合、DiscordのスラッシュコマンドAPIを使用してロールコマンドを送信します。
    "dk_power_management": true,           // (デフォルト: false) trueの場合、$tuでkakeraパワーをチェックし、必要な場合のみ$dkを使用します。

    // 新機能: Chaosキーのみフィルター
    "only_chaos": false,                   // (デフォルト: false) trueの場合、10+キー（chaos keys）を持つキャラクターのみかkakeraボタンをクリックします。           

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

    // --- リアクティブスナイプ（自分のロールからのキャラクター用） ---
    "reactive_snipe_on_own_rolls": true,   // (デフォルト: true) 自分のロール中の即座クレームを有効/無効にします（WL、シリーズWL、Kakeraしきい値に基づく）。
    "reactive_snipe_delay": 0,             // (デフォルト: 0) 自分のロール中のリアクティブスナイプ時にクレームする前の遅延（秒）。より自然に見せるのに便利です。   

    // --- OTHER ---
    "start_delay": 0,                      
    "snipe_ignore_min_kakera_reset": false 
  }
}
```

---

## 🎮 Discordトークンの取得 🔑

セルフボットはあなたのDiscordアカウントトークンを必要とします。**このトークンはあなたのアカウントへの完全なアクセスを許可します – 極秘に保ってください！共有することはパスワードを教えるようなものです。** このボットは代替アカウントで使用することを推奨します。

1.  **ウェブブラウザでDiscordを開きます**（例：Chrome、Firefox）。*デスクトップアプリではない。*
2.  **F12**を押して開発者ツールを開きます。
3.  **`Console`** タブに移動します。
4.  以下のコードスニペットをコンソールに貼り付け、Enterを押します。

    ```javascript
    // [同じJavascriptコードスニペットがここに挿入されます]
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
5.  あなたのトークンがクリップボードにコピーされます。それを慎重に `presets.json` ファイルの `"token"` フィールドに貼り付けます。

---

## 🤝 貢献

貢献を歓迎します！問題の報告、機能の提案、またはプロジェクトリポジトリへのプルリクエストの提出を自由に行ってください。

**🙏 Discordアカウントへの潜在的なリスクを十分に認識し、責任を持って倫理的にこのツールを使用してください。 🙏**

**ハッピー（かつ注意深い！）Mudae-ing！** 😉

---
**ライセンス:** [MITライセンス](LICENSE)
