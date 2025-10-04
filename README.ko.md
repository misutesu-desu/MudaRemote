# ✨ MudaRemote: 고급 Mudae 자동화 ✨

[![Discord TOS 위반 - **주의해서 사용하세요**](https://img.shields.io/badge/Discord%20TOS-VIOLATION-red)](https://discord.com/terms) ⚠️ **계정 BAN 위험!** ⚠️

**🛑🛑🛑 경고: 셀프봇 - 잠재적인 Discord TOS 위반! 계정 BAN 위험! 🛑🛑🛑**
**🔥 사용자 본인의 책임 하에 사용하세요! 🔥 귀하의 계정에 취해지는 어떠한 조치에 대해서도 당사는 책임지지 않습니다. 😱**

---

[디스코드 서버에 참여](https://discord.gg/4WHXkDzuZx)

## 🚀 MudaRemote: Mudae 경험 향상 (책임감 있게 사용하세요!)

MudaRemote는 디스코드 봇 Mudae의 다양한 작업을 자동화하도록 설계된 Python 기반 셀프봇입니다. 실시간 스나이핑 및 지능적인 클레임과 같은 기능을 제공합니다. **그러나 셀프봇을 사용하는 것은 Discord의 서비스 약관(TOS)에 위배되며, 계정 정지 또는 BAN으로 이어질 수 있습니다.** 극도의 주의를 기울여 사용하고 관련 위험을 이해하시기 바랍니다.

### ✨ 주요 기능:

*   **🎯 외부 스나이핑 (위시리스트, 시리즈 및 카케라 값):** *다른 사용자*가 굴린 캐릭터를 클레임합니다.
*   **🟡 외부 카케라 반응 스나이핑:** *모든* Mudae 메시지의 카케라 반응 버튼을 자동으로 클릭합니다.
*   **😴 스나이프 전용 모드:** 롤 명령을 보내지 않고 외부 스나이프를 *만* 듣고 실행하도록 봇 인스턴스를 구성합니다.
*   **⚡ 반응형 자체 롤 스나이핑:** *자신의* 롤에서 나온 캐릭터가 기준과 일치하면 즉시 클레임합니다.
*   **🤖 자동화된 롤링 및 일반 클레임:** 롤링 명령을 처리하고 최소 카케라를 기준으로 클레임합니다.
*   **🥇 지능적인 클레임 로직:** `$tu`를 분석하여 `$rt` 사용 가능성을 확인하고, 고가치 롤에 대한 잠재적인 두 번째 클레임에 사용합니다.
*   **🔄 자동 재설정 감지:** Mudae의 클레임 및 롤 재설정 타이머를 모니터링하고 기다립니다.
*   **🚶‍♂️ 인간화된 대기 (NEW!):** 재설정 후 무작위 기간 동안, 그리고 채널 비활성화 상태를 기다린 후 작업을 재개하여 인간의 행동을 시뮬레이션하고 예측 가능성을 크게 줄입니다.
*   **💡 DK 파워 관리 (NEW!):** `$tu`를 통해 카케라 반응 파워를 지능적으로 확인하고, 반응에 파워가 부족할 경우에만 `$dk`를 사용하여 차지를 절약합니다.
*   **🔑 키 모드:** 캐릭터 클레임이 쿨다운 중일 때도 카케라 수집을 위해 지속적인 롤링을 활성화합니다.
*   **⏩ 슬래시 롤 디스패치 (NEW!):** 텍스트 명령 대신 Discord의 슬래시 명령 인프라를 사용하여 롤 명령(`wa`, `h`, `m` 등)을 보내는 선택적 기능.
*   **👯 다중 계정 지원:** 여러 봇 인스턴스를 동시에 실행합니다.
*   **⏱️ 사용자 정의 가능한 지연 및 롤 속도:** 모든 동작 지연과 롤 명령의 속도를 미세 조정합니다.
*   **🗂️ 쉬운 사전 설정 구성:** 모든 설정을 단일 `presets.json` 파일에서 관리합니다.
*   **📊 콘솔 로깅:** 선명하고 색상으로 구분된 실시간 출력.
*   **🌐 현지화 지원:** 영어 및 포르투갈어(PT-BR) Mudae 응답 모두에 대한 구문 분석 개선.

---

## 🛠️ 설정 가이드

1.  **🐍 Python:** Python 3.8 이상이 설치되어 있는지 확인하세요. ([Python 다운로드](https://www.python.org/downloads/))
2.  **📦 종속성:** 터미널 또는 명령 프롬프트를 열고 다음을 실행합니다.
    ```bash
    pip install discord.py-self inquirer
    ```
    *참고: `use_slash_rolls: true`를 사용할 계획이라면, `discord.py-self` 버전에 `Route` 객체가 포함되어 있는지 확인하세요 (일반적으로 최신 버전에는 포함되어 있습니다).*
3.  **📝 `presets.json`:** 스크립트 디렉토리에 `presets.json` 파일을 만듭니다. 여기에 봇 구성을 추가합니다. 사용 가능한 모든 옵션은 아래 예제를 참조하세요.
4.  **🚀 실행:** 터미널에서 스크립트를 실행합니다.
    ```bash
    python mudae_bot.py
    ```
5.  **🕹️ 사전 설정 선택:** 대화형 메뉴에서 실행할 구성된 봇을 선택합니다.

---

### `presets.json` 구성 예제:

*(기술 구성이므로 JSON 설정 내용은 원본과 동일하게 유지됩니다.)*

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
    "skip_initial_commands": false,        
    "use_slash_rolls": false,              
    "dk_power_management": true,           

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

    // --- REACTIVE SNIPING (For characters from YOUR OWN rolls) ---
    "reactive_snipe_on_own_rolls": true,   

    // --- OTHER ---
    "start_delay": 0,                      
    "snipe_ignore_min_kakera_reset": false 
  }
}
```

---

## 🎮 Discord 토큰 얻기 🔑

셀프봇은 Discord 계정 토큰을 필요로 합니다. **이 토큰은 귀하의 계정에 대한 전체 액세스 권한을 부여합니다. – 극도로 비밀로 유지하십시오! 공유하는 것은 비밀번호를 알려주는 것과 같습니다.** 이 봇을 대체 계정에서 사용하는 것이 좋습니다.

1.  **웹 브라우저에서 Discord를 엽니다** (예: Chrome, Firefox). *데스크톱 앱 아님.*
2.  **F12**를 눌러 개발자 도구를 엽니다.
3.  **`Console`** 탭으로 이동합니다.
4.  다음 코드 스니펫을 콘솔에 붙여넣고 Enter를 누릅니다.

    ```javascript
    // [동일한 Javascript 코드 스니펫이 여기에 삽입됩니다]
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
5.  토큰이 클립보드에 복사됩니다. 이를 `presets.json` 파일의 `"token"` 필드에 조심스럽게 붙여넣습니다.

---

## 🤝 기여

기여를 환영합니다! 문제 보고, 기능 제안 또는 프로젝트 저장소에 풀 리퀘스트를 제출하는 것을 주저하지 마세요.

**🙏 Discord 계정에 대한 잠재적 위험을 완전히 인지하고 이 도구를 책임감 있고 윤리적으로 사용하십시오. 🙏**

**행복하고 (조심스러운!) Mudae-ing 하세요!** 😉

---
**라이센스:** [MIT 라이센스](LICENSE)
