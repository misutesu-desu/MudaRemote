# ⚡ MudaRemote: 究極のMudae Bot自動化ツール

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.0.3-orange.svg)](https://github.com/misutesu-desu/MudaRemote/releases)
[![Status](https://img.shields.io/badge/Status-Active_2025-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Join%20Server-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

[Français](README.fr.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Português Brasileiro](README.pt-BR.md)

**MudaRemote** は、**Mudae Discord Bot** 専用に設計された、最も洗練され、機能が豊富な自動化エンジンです。単なるマクロの域を超え、リアルタイムデータ（$tu、埋め込み、コンポーネント）を解析して人間のような挙動をシミュレートし、ハーレムの効率を最大化します。

> **⚠️ 重要な警告:** MudaRemoteは**セルフボット**です。セルフボットの使用はDiscordの利用規約（ToS）に違反し、アカウントの永久凍結のリスクを伴います。**自己責任で使用してください。**

---

## 🏆 なぜ MudaRemote なのか？（比較）

2021年時代の古いスクリプトで妥協しないでください。2025年のスタンダードにアップグレードしましょう。

| 機能 | 一般的なMudae Bot | **MudaRemote v3.0.3** |
| :--- | :--- | :--- |
| **ロールのタイミング** | 固定/ランダムタイマー | **戦略的な境界同期（完璧なクレーム）** |
| **コマンドエンジン** | テキストのみ | **スラッシュコマンド（最新APIサポート）** |
| **$rt 管理** | なし / 手動 | **全自動インテリジェンス** |
| **アップデート** | 手動で再ダウンロード | **統合オートアップデートシステム** |
| **隠密性** | 静的な遅延 | **人間らしい「ゆらぎ」＆ アクティビティ監視** |
| **ローカライズ** | 英語のみ | **3言語をサポート** |

---

## ✨ 主要なハイインパクト機能

### 🎯 高度なスナイプエコシステム
*   **ウィッシュリスト＆シリーズスナイプ:** 他人がロールしたキャラクターやアニメシリーズ全体を即座に取得（クレーム）します。
*   **インテリジェント・カケラスナイパー:** 閾値（例：200以上）を設定し、価値のあるカケラを自動的に確保します。
*   **グローバル・カケラファーミング:** 全メッセージをスキャンしてクリスタルを探します。特定のユーザー（サブ垢など）からのみ取得する**スマートフィルタリング**を搭載し、検知を回避します。
*   **カオスモード:** カオスキー（10個以上のキーを持つキャラ）専用のロジック。

### 🤖 インテリジェント・オートメーション（「頭脳」）
*   **戦略的ロールタイミング:** クレームのリセット直前までロールを保持し、クレーム権がクールダウン中の無駄なロールを防ぎます。
*   **スラッシュコマンドエンジン:** `/wa`、`/ha` などをオプションで使用可能。テキストコマンドより高速で、Discordの検知に対しても大幅に安全です。
*   **スマートな$rt活用:** `$rt` が使用可能かどうかを自動検出し、優先度の高いウィッシュリスト対象にのみ使用します。
*   **DKパワー管理:** カケラパワーの使用を最適化し、高価値なリアクトに必要なパワーを常に確保します。

### 🛡️ ステルス＆アンチバン技術
*   **人間味のあるインターバル:** ランダムな「ゆらぎ（ジッター）」を実装。60分周期のループのような機械的な動きを見せません。
*   **非アクティブ・ウォッチャー:** チャンネルが混雑している（会話が盛んな）ことを検知し、会話が途切れるのを待ってからロールを開始する「礼儀正しいユーザー」のように振る舞います。
*   **キー制限保護:** 1日の上限（1,000キー）に達すると自動的に停止し、フラグが立つのを防ぎます。

---

## 🛠️ クイックスタート

1.  **必須環境**: [Python 3.8以上](https://www.python.org/downloads/)
2.  **インストール**:
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **実行**:
    ```bash
    python mudae_bot.py
    ```
    *インタラクティブメニューからプリセットを選択すれば準備完了です！*

---

## ⚙️ 設定 (`presets.json`)

複数のアカウントやサーバー用に複数のプロファイルを定義できます。

```json
{
  "MainAccount": {
    "token": "YOUR_TOKEN",
    "channel_id": 123456789,
    "rolling": true,
    "use_slash_rolls": true,            // 推奨
    "time_rolls_to_claim_reset": true, // 独自機能
    "min_kakera": 200,
    "humanization_enabled": true,
    "wishlist": ["Makima", "Rem"]
  }
}
```
📖 **設定の詳細は？** [設定ガイド (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide) をご確認ください。
---

## 🔒 トークンの取得方法
1. ブラウザでDiscordを開きます。
2. `F12` キーを押して「コンソール（Console）」を開きます。
3. 以下を貼り付けます：
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
4. **このトークンは絶対に誰にも教えないでください！**

---

**⭐ このツールがあなたのハーレム作りに役立ったら、ぜひスターをお願いします！プロジェクトの成長と継続的なアップデートの励みになります。**
