# ⚡ MudaRemote: 궁극의 Mudae 봇 자동화 도구

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.0.3-orange.svg)](https://github.com/misutesu-desu/MudaRemote/releases)
[![Status](https://img.shields.io/badge/Status-Active_2025-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Join%20Server-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

[English](README.md) | [Français](README.fr.md) | [日本語](README.ja.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Português Brasileiro](README.pt-BR.md)

**MudaRemote**는 **Mudae Discord 봇**을 위해 설계된 가장 정교하고 기능이 풍부한 자동화 엔진입니다. 단순한 매크로를 넘어 실시간 데이터($tu, 임베드, 컴포넌트)를 분석하여 사람과 유사한 동작을 시뮬레이션하고 하렘 효율성을 극대화합니다.

> **⚠️ 중요 경고:** MudaRemote는 **셀프 봇(SELF-BOT)**입니다. 셀프 봇 사용은 Discord 이용 약관(ToS) 위반이며 계정 영구 정지 위험이 있습니다. **모든 책임은 사용자 본인에게 있습니다.**

---

## 🏆 왜 MudaRemote인가? (비교)

과거의 스크립트에 안주하지 마세요. 2025년 표준으로 업그레이드하십시오.

| 기능 | 일반적인 Mudae 봇 | **MudaRemote v3.0.3** |
| :--- | :--- | :--- |
| **롤 타이밍** | 일정/랜덤 타이머 | **전략적 경계 동기화 (완벽한 클레임)** |
| **커맨드 엔진** | 텍스트 전용 | **슬래시 커맨드 (현대적 API 지원)** |
| **$rt 관리** | 없음 / 수동 | **완전 자동화된 지능형 관리** |
| **업데이트** | 수동 재다운로드 | **통합 자동 업데이트 시스템** |
| **스텔스** | 정적 지연 시간 | **인간과 유사한 지터 및 활동 감시** |
| **다국어 지원** | 영어 전용 | **3개 국어 이상 지원** |

---

## ✨ 핵심 주요 기능

### 🎯 고급 스나이핑 생태계
*   **위시리스트 및 시리즈 스나이핑:** 다른 사용자가 뽑은 캐릭터나 특정 애니메이션 시리즈 전체를 즉시 클레임합니다.
*   **지능형 카케라(Kakera) 스나이퍼:** 임계값(예: 200+)을 설정하면 자동으로 가치 있는 카케라를 확보합니다.
*   **글로벌 카케라 파밍:** 모든 메시지에서 크리스탈을 스캔합니다. 특정 사용자(예: 부계정)에게서만 가져오도록 설정하는 **스마트 필터링**을 통해 탐지 위험을 낮춥니다.
*   **카오스 모드:** 카오스 키(10개 이상의 키 캐릭터)를 위한 특화된 로직을 제공합니다.

### 🤖 지능형 자동화 (브레인)
*   **전략적 롤 타이밍:** 클레임 초기화 직전까지 롤을 아껴두어, 클레임 쿨타임 중에 롤을 낭비하는 일이 없도록 합니다.
*   **슬래시 커맨드 엔진:** 선택적으로 `/wa`, `/ha` 등을 사용합니다. 이는 더 빠를 뿐만 아니라 Discord의 탐지로부터 훨씬 안전합니다.
*   **스마트 $rt 활용:** `$rt` 사용 가능 여부를 자동으로 감지하고, 우선순위가 높은 위시리스트 대상에게만 사용합니다.
*   **DK 파워 관리:** 카케라 파워 사용을 최적화하여 고가치 리액트를 위한 파워를 항상 확보합니다.

### 🛡️ 스텔스 및 밴 방지 기술
*   **인간화된 간격:** 랜덤 "지터(jitter)"를 구현하여 60분 주기의 반복적인 기계 활동처럼 보이지 않게 합니다.
*   **비활동 감시:** 채널이 바쁠 때를 감지하고, 대화가 뜸해질 때까지 기다렸다가 롤을 돌리는 예의 바른 사용자처럼 행동합니다.
*   **키 제한 보호:** 일일 1,000키 제한에 도달하면 자동으로 일시 중지하여 계정 플래깅을 방지합니다.

---

## 🛠️ 빠른 시작

1.  **요구 사항**: [Python 3.8 이상](https://www.python.org/downloads/)
2.  **설치**:
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **실행**:
    ```bash
    python mudae_bot.py
    ```
    *대화형 메뉴에서 프리셋을 선택하면 준비 완료!*

---

## ⚙️ 설정 (`presets.json`)

여러 계정이나 서버를 위한 다양한 프로필을 정의할 수 있습니다.

```json
{
  "MainAccount": {
    "token": "YOUR_TOKEN",
    "channel_id": 123456789,
    "rolling": true,
    "use_slash_rolls": true,            // 권장 설정
    "time_rolls_to_claim_reset": true, // 독보적인 기능
    "min_kakera": 200,
    "humanization_enabled": true,
    "wishlist": ["Makima", "Rem"]
  }
}
```
📖 **설정에 도움이 필요하신가요?** 자세한 내용은 [설정 가이드(위키)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide)를 확인하세요.

---

## 🔒 토큰 획득 방법
1. 브라우저에서 Discord를 엽니다.
2. `F12`를 눌러 개발자 도구를 열고 `Console` 탭으로 이동합니다.
3. 다음 코드를 붙여넣습니다:
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
4. **이 토큰을 절대 타인과 공유하지 마세요!**

---

**⭐ 이 도구가 하렘을 키우는 데 도움이 되었다면 스타(Star)를 눌러주세요! 프로젝트 유지와 업데이트에 큰 힘이 됩니다.**
