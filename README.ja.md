# ⚡ MudaRemote: 究極のMudae自動化ツール ⚡

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-success.svg)]()

> **⚠️ 重大な警告 ⚠️**
> 
> **MudaRemoteはセルフボット（Self-Bot）です。** ユーザーアカウントを自動化することは、[Discordの利用規約](https://discord.com/terms)に違反します。
> このツールを使用すると、アカウントの一時停止やBANのリスクがあります。**自己責任で使用してください。** 開発者は一切の責任を負いません。

---

## 🚀 概要

**MudaRemote** は、Discordボット「Mudae」専用に設計された、高性能で機能豊富な自動化エンジンです。単純な自動ロールマクロを超え、ハーレム効率を最大化しつつアカウントを安全に保つための、インテリジェントな状態管理、精密なスナイプ機能、高度な人間化機能を提供します。

基本的なマクロとは異なり、MudaRemoteはMudaeの応答（$tu、メッセージ、埋め込み）をリアルタイムで解析し、いつロールするか、いつ休むか、何をクレームするかを賢く判断します。

---

## ✨ 主な機能

### 🎯 高度なスナイプエコシステム
*   **ウィッシュリストスナイプ**: *他のユーザー*がロールした、あなたの `wishlist` にあるキャラクターを即座にクレームします。
*   **シリーズスナイプ**: シリーズ全体をターゲットに！ 追跡中のシリーズからキャラクターが出れば、それはあなたのものです。
*   **カケラ値スナイプ**: ウィッシュリストになくても、カケラ値が設定したしきい値を超えれば、自動的にスナイプします。
*   **グローバルカケラファーミング**: ボットはカケラリアクションボタンのために**すべての**メッセージを監視します。
    *   *New:* **スマートフィルタリング**: サーバーでのトラブルを避けるため、特定のユーザー（例：自分のサブ垢）からのみカケラを盗むように設定できます。
    *   *New:* **カオスモード**: カオスキー（Chaos Keys）と通常のカケラの違いをインテリジェントに処理します。

### 🤖 インテリジェントオートメーション
*   **スマートローリング**: 毎時のロール（$wa, $hg, $ma など）を自動的に処理し、$dailyのリセットを追跡します。
*   **スラッシュコマンドエンジン**: オプションで、ロールに最新のDiscord `/commands` を使用できます。これは従来のテキストコマンドよりも高速で、レート制限にかかりにくい場合があります。
*   **最適化されたクレーム**:
    *   **$rt統合**: Refund Wish ($rt) パークを持っているかを自動的に確認し、同じリセット期間内に2体目の高価値キャラクターを確保するために使用します。
    *   **パニックモード**: クレームリセットまで60分を切っている場合 (`snipe_ignore_min_kakera_reset`)、ボットは基準を下げて、クールダウンを無駄にしないために*何でも*クレームします。
*   **DKパワー管理**: 現在のリアクションパワーと在庫を分析します。パワーが実際に低すぎて反応できない場合にのみ `$dk` (Daily Kakera) チャージを消費し、無駄を防ぎます。

### 🛡️ ステルス & 安全性
*   **人間化されたインターバル**: ロボットのような正確な60分タイマーはもうありません。ボットはすべての待機時間にランダムな「揺らぎ（jitter）」を加えます。
*   **非アクティブ監視**: チャンネルが忙しいことを検出し、会話が途切れるのを待ってからロールを開始することで、礼儀正しい人間のユーザーをシミュレートします。
*   **キー制限検出**: Mudaeのキー制限に達した場合、自動的にロールを一時停止します。

---

## 🛠️ インストール

1.  **前提条件**:
    *   [Python 3.8](https://www.python.org/downloads/) 以上をインストールしてください。
2.  **依存関係のインストール**:
    ```bash
    pip install discord.py-self inquirer
    ```
3.  **セットアップ**:
    *   このリポジトリをダウンロードします。
    *   スクリプトと同じディレクトリに `presets.json` ファイルを作成します（下記の設定を参照）。

---

## ⚙️ 設定 (`presets.json`)

すべての設定は `presets.json` で管理されます。複数のボットプロファイル（例：「メイン垢」、「サブ垢」）を定義し、同時に実行することができます。

```json
{
  "MyProMudaBot": {
    "token": "YOUR_DISCORD_TOKEN_HERE",
    "channel_id": 123456789012345678,
    "prefix": "!", 
    "mudae_prefix": "$",
    "roll_command": "wa",

    "// --- 基本設定 ---": "",
    "rolling": true,                       // 「スナイプ専用」モードにする場合は false に設定（ロールせず、監視のみ）
    "min_kakera": 200,                     // 自分のロール中にキャラクターをクレームするための最低値
    "delay_seconds": 2,                    // 基本処理遅延
    "roll_speed": 1.5,                     // ロールコマンド間の秒数

    "// --- スナイプ設定 ---": "",
    "snipe_mode": true,                    // ウィッシュリストスナイプのマスタースイッチ
    "wishlist": ["Makima", "Rem"],         // スナイプする正確なキャラクター名リスト
    "snipe_delay": 0.5,                    // スナイプ速度（秒）
    
    "series_snipe_mode": true,
    "series_wishlist": ["Chainsaw Man"],   // スナイプするシリーズ名リスト
    "series_snipe_delay": 1.0,

    "// --- カケラファーミング ---": "",
    "kakera_reaction_snipe_mode": true,    // *任意の*メッセージのカケラボタンをクリックしますか？
    "kakera_reaction_snipe_delay": 0.8,
    "kakera_reaction_snipe_targets": [     // オプション: 特定のユーザー（例：自分のサブ垢）からのみ盗む
        "my_alt_account_username"
    ],
    "only_chaos": false,                   // trueの場合、カオスキー（紫）のクリスタルにのみ反応します。

    "// --- 高度なロジック ---": "",
    "use_slash_rolls": true,               // $wa の代わりに /wa を使用（推奨）
    "dk_power_management": true,           // 本当に必要なときのために $dk チャージを節約する
    "snipe_ignore_min_kakera_reset": true, // クレームリセットまで1時間未満なら*何でも*クレームする。
    "key_mode": false,                     // クレーム権がなくてもキーのためにロールを続ける？

    "// --- 人間化設定 ---": "",
    "humanization_enabled": true,
    "humanization_window_minutes": 30,     // リセット後、ランダムに0〜30分余分に待機
    "humanization_inactivity_seconds": 10  // ロールする前にチャンネルで10秒間の静寂を待つ
  }
}
```

---

## 🎮 使い方

1.  ボットのフォルダでターミナルを開きます。
2.  スクリプトを実行します:
    ```bash
    python mudae_bot.py
    ```
3.  メニューからプリセットを選択します。
4.  あとはリラックスして、ハーレムが成長するのを見守りましょう。📈

---

## 🔒 トークンの取得方法

1.  ブラウザ（Chrome/Firefox）でDiscordにログインします。
2.  **F12**（開発者ツール）を押し、**Console**タブに移動します。
3.  以下のコードを貼り付けてトークンを表示させます:
    ```javascript
    window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
    ```
    *(注: このトークンは誰にも教えないでください。アカウントへの完全なアクセス権を与えてしまいます。)*

---

**よい狩りを！** 💖
