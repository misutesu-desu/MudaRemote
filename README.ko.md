# ⚡ MudaRemote: 최고의 Mudae 자동화 도구 ⚡

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.8.0-orange.svg)]()
[![Status](https://img.shields.io/badge/Status-Active-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-참여하기-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

> **⚠️ 중대 경고 ⚠️**
> 
> **MudaRemote는 셀프봇(Self-Bot)입니다.** 사용자 계정을 자동화하는 것은 [Discord 이용 약관](https://discord.com/terms)을 위반하는 행위입니다. 
> 이 도구를 사용하면 계정이 정지되거나 차단될 위험이 있습니다. **사용에 따른 위험은 본인이 감수해야 합니다.** 개발자는 어떠한 결과에 대해서도 책임을 지지 않습니다.

---

## 🚀 개요

**MudaRemote**는 Discord 봇 Mudae를 위해 특별히 설계된 고성능 다기능 자동화 엔진입니다. 단순한 자동 롤링 매크로를 넘어, 하렘 효율성을 극대화하면서 계정을 안전하게 보호하기 위한 지능형 상태 관리, 정밀한 스나이핑 기능, 고급 인간화(Humanization) 기능을 제공합니다.

기본적인 매크로와 달리, MudaRemote는 Mudae의 응답($tu, 메시지, 임베드)을 실시간으로 분석하여 언제 롤을 돌릴지, 언제 쉴지, 무엇을 클레임할지 똑똑하게 결정합니다.

---

## ✨ 핵심 기능

### 🎯 고급 스나이핑 생태계
*   **위시리스트 스나이핑**: *다른 사용자*가 롤한 캐릭터 중 내 `wishlist`에 있는 캐릭터를 즉시 낚아챕니다.
*   **시리즈 스나이핑**: 시리즈 전체를 타겟팅하세요! 추적 중인 시리즈의 캐릭터가 나오면 바로 당신의 것입니다.
*   **카케라 가치 스나이핑**: 위시리스트에 없더라도, 카케라 가치가 설정한 기준을 초과하면 *무엇이든* 자동으로 스나이핑합니다.
*   **글로벌 카케라 파밍**: 봇이 카케라 반응 버튼이 있는 **모든** 메시지를 감시합니다.
    *   *New:* **스마트 필터링**: 서버 내 분쟁을 피하기 위해 특정 사용자(예: 내 부계정)의 카케라만 훔치도록 설정할 수 있습니다.
    *   *New:* **카오스 모드**: 카오스 열쇠(Chaos Keys)와 일반 카케라의 차이를 지능적으로 처리합니다.

### 🤖 지능형 자동화
*   **스마트 롤링**: 시간별 롤($wa, $hg, $ma 등)을 자동으로 처리하고 $daily 리셋을 추적합니다.
*   **슬래시 커맨드 엔진**: 선택적으로 롤링에 최신 Discord `/명령어`를 사용합니다. 이는 기존 텍스트 명령보다 빠르며 속도 제한(rate-limit)에 덜 걸립니다.
*   **자동 업데이트 시스템**: 
    *   원격 저장소에서 새 버전을 자동으로 감지하고 로컬 스크립트를 업데이트합니다.
*   **커스텀 이모지 설정**: 
    *   *New:* 봇을 개인화하세요! 클레임 하트, 카케라 크리스탈, 카오스 키에 대한 커스텀 리스트를 프리셋별로 정의할 수 있습니다.
*   **Reset Timer ($rt) 최적화**: 
    *   여러 고가치 타겟을 확보하기 위한 `$rt`의 지능적 감지 및 자동 실행.

### 🛡️ 스텔스 & 보안
*   **인간화된 간격**: 로봇 같은 정확한 60분 타이머는 이제 그만. 봇은 모든 대기 시간에 무작위 "지연(jitter)"을 추가합니다.
*   **비활동 감지**: 채널이 바쁠 때를 감지하고 대화가 잠잠해질 때까지 기다렸다가 롤을 시작하여 예의 바른 사람처럼 행동합니다.
*   **키 제한 감지**: Mudae 키 제한에 도달하면 자동으로 롤링을 일시 중지합니다.

---

## 🛠️ 설치 방법

1.  **필수 조건**:
    *   [Python 3.8](https://www.python.org/downloads/) 이상을 설치하세요.
2.  **의존성 설치**:
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **설정**:
    *   이 저장소를 다운로드하세요.
    *   스크립트와 같은 디렉토리에 `presets.json` 파일을 만드세요 (아래 설정 참조).

---

## ⚙️ 설정 (`presets.json`)

모든 설정은 `presets.json`에서 관리됩니다. 여러 봇 프로필(예: "본계정", "부계정")을 정의하고 동시에 실행할 수 있습니다.

```json
{
  "내슈퍼Muda봇": {
    "token": "여기에_디스코드_토큰_입력",
    "channel_id": 123456789012345678,
    "prefix": "!", 
    "mudae_prefix": "$",
    "roll_command": "wa",

    "// --- 기본 설정 ---": "",
    "rolling": true,                       // "스나이핑 전용" 모드로 하려면 false로 설정 (롤링 안 함, 감시만 함)
    "min_kakera": 200,                     // 내 롤에서 캐릭터를 클레임하기 위한 최소 가치
    "delay_seconds": 2,                    // 기본 처리 지연 시간
    "roll_speed": 1.5,                     // 롤 명령어 간 간격 (초)

    "// --- 스나이핑 설정 ---": "",
    "snipe_mode": true,                    // 위시리스트 스나이핑 마스터 스위치
    "wishlist": ["Makima", "Rem"],         // 스나이핑할 정확한 캐릭터 이름 목록
    "snipe_delay": 0.5,                    // 스나이핑 속도 (초)
    
    "series_snipe_mode": true,
    "series_wishlist": ["Chainsaw Man"],   // 스나이핑할 시리즈 이름 목록
    "series_snipe_delay": 1.0,

    "// --- 카케라 파밍 ---": "",
    "kakera_reaction_snipe_mode": true,    // *아무* 메시지의 카케라 버튼을 클릭할까요?
    "kakera_reaction_snipe_delay": 0.8,
    "kakera_reaction_snipe_targets": [     // 선택 사항: 특정 사용자(예: 내 부계정)에게서만 훔치기
        "my_alt_account_username"
    ],
    "only_chaos": false,                   // true일 경우, 카오스 열쇠(보라색) 수정에만 반응합니다.

    "// --- 고급 로직 ---": "",
    "use_slash_rolls": true,               // $wa 대신 /wa 사용 (강력 권장)
    "dk_power_management": true,           // 정말 필요할 때를 위해 $dk 충전 아끼기
    "snipe_ignore_min_kakera_reset": true, // 클레임 리셋이 1시간 미만이면 *무엇이든* 클레임하기.
    "key_mode": false,                     // 클레임 권한이 없어도 열쇠를 위해 계속 롤링할까요?
    "time_rolls_to_claim_reset": true,    // 리셋에 맞춰 롤링 종료 타이밍 조절 (효율 극대화)
    "rt_ignore_min_kakera_for_wishlist": false, // 위시리스트 캐릭터면 카케라 < min_kakera 라도 $rt 사용할까요?

    "// --- 커스텀 이모지 (선택 사항) ---": "",
    "claim_emojis": ["💖", "💗"],          // 클릭할 커스텀 하트
    "kakera_emojis": ["kakeraY", "kakeraO"], // 커스텀 카케라
    "chaos_emojis": ["kakeraP"]            // 커스텀 카오스 키 (10+ key 캐릭터)

    "// --- 인간화 설정 ---": "",
    "humanization_enabled": true,
    "humanization_window_minutes": 30,     // 리셋 후 0-30분 무작위 추가 대기
    "humanization_inactivity_seconds": 10  // 롤링 전 채널에서 10초간 정적 기다리기
  }
}
```

---

## 🎮 사용 방법

1.  봇 폴더에서 터미널을 엽니다.
2.  스크립트를 실행합니다:
    ```bash
    python mudae_bot.py
    ```
3.  메뉴에서 프리셋을 선택합니다.
4.  편안하게 하렘이 성장하는 것을 지켜보세요. 📈

---

## 🔒 토큰 얻는 법

1.  브라우저(Chrome/Firefox)에서 Discord에 로그인합니다.
2.  **F12** (개발자 도구) -> **Console** 탭을 누릅니다.
3.  아래 코드를 붙여넣어 토큰을 확인합니다:
    ```javascript
    window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
    ```
    *(참고: 이 토큰은 절대 누구와도 공유하지 마세요. 계정에 대한 모든 권한을 주는 것입니다.)*

---

**즐거운 사냥 되세요!** 💖
