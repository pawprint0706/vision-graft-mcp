# Vision-Graft MCP (VGMCP)

[English](README.md) · **한국어**

> ⚠️ **개발 진행 중입니다.** 이 프로젝트는 아직 활발히 개발 중이며, 이 README도
> 다시 다듬을 예정입니다. 설치 단계·명령어·동작이 변경될 수 있습니다.



"앞이 안 보이는" AI 코딩 모델에게 **눈**을 달아 줍니다. 빠른 모델이나 로컬
LLM 중에는 이미지를 보지 못하는 경우가 많습니다. 이런 모델은 HTML/CSS/JSX
코드만 읽기 때문에, 버튼이 잘렸거나 요소가 겹친 걸 알아채지 못합니다. VGMCP는
화면을 캡처해 **이미지를 볼 수 있는 비전 모델**에 보내고, 그 결과를 **글로 된
리포트**로 AI에게 돌려줍니다. 그러면 AI도 시각적 버그를 실제로 고칠 수 있습니다.

두 가지 방식으로 동시에 쓸 수 있습니다.

- **AI가 사용**: [MCP](https://modelcontextprotocol.io) 표준을 통해
  (Cursor, Claude Desktop, oh-my-pi 등에서).
- **사용자가 사용**: 작은 **메뉴바 아이콘**에서 직접 (화면/창/영역 캡처,
  마지막 이미지 분석, 붙여넣기용 프롬프트 복사).

> 지원 플랫폼: **macOS 14 (Sonoma) 이상**. (Windows는 예정.)

---

## 목차

1. [동작 방식 (30초 요약)](#동작-방식)
2. [시작하기 전에](#시작하기-전에)
3. [1단계 — 설치](#1단계--설치)
4. [2단계 — 비전 백엔드(API 키) 등록](#2단계--비전-백엔드api-키-등록)
5. [3단계 — 화면 기록 권한 부여](#3단계--화면-기록-권한-부여)
6. [4단계 — 앱 실행](#4단계--앱-실행)
7. [5단계 — AI 도구에 연결 (MCP)](#5단계--ai-도구에-연결-mcp)
8. [일상적인 사용법](#일상적인-사용법)
9. [명령어 모음](#명령어-모음)
10. [문제 해결](#문제-해결)
11. [프라이버시 & 저장 위치](#프라이버시--저장-위치)
12. [개발자용](#개발자용)

---

## 동작 방식

```
내 AI 도구 (Cursor / Claude / oh-my-pi)
        │  스크린샷 + 분석 요청 (MCP)
        ▼
  vgmcp-adapter  ── 연결 ──▶  VGMCP 앱 (메뉴바, 항상 실행 중)
                                • 화면 캡처
                                • 비전 모델에 전송
                                • 글로 된 리포트 반환
        ▲
        └─ 메뉴바 아이콘에서 사용자가 직접 같은 기능을 쓸 수도 있음
```

AI 쪽이 작동하려면 **메뉴바 앱이 실행 중**이어야 합니다. 이 앱이 카메라와
설정을 들고 있는 핵심이기 때문입니다.

---

## 시작하기 전에

설치에는 **터미널(Terminal)** 앱을 사용합니다 (응용 프로그램 → 유틸리티 →
터미널, 또는 `⌘ Space`를 누르고 "터미널" 입력 후 Enter). 걱정 마세요 — 몇 줄을
복사해서 붙여넣기만 하면 됩니다.

**Python 3.11 이상이 있는지 확인**하세요. 아래를 붙여넣고 Enter:

```bash
python3 --version
```

- `Python 3.11.x` 이상이 나오면 → 준비 완료.
- 더 낮거나 "command not found"가 나오면 →
  [python.org/downloads](https://www.python.org/downloads/)에서 최신 Python을
  설치(또는 Homebrew 사용 시 `brew install python`)한 뒤 다시 확인하세요.

비전 제공자 한 곳의 **API 키**도 필요합니다 (하나만 고르세요):

| 제공자 | 키 발급처 | 비고 |
|---|---|---|
| **OpenRouter** | <https://openrouter.ai/keys> | 키 하나로 여러 모델. 추천 기본값. |
| **Anthropic (Claude)** | <https://console.anthropic.com/> | |
| **OpenAI (GPT-4o)** | <https://platform.openai.com/api-keys> | |
| **Ollama (로컬)** | *키 불필요* — <https://ollama.com> | 내 Mac에서 실행, 무료, 외부 전송 없음. |

---

## 1단계 — 설치

**가장 쉬운 방법 — 설치 스크립트 더블클릭.** 프로젝트를 clone 하거나
다운로드 후 압축을 풀고, Finder에서 폴더를 열어 **`install.command`를
더블클릭**하세요. 터미널 창이 열리며 설치가 진행됩니다(독립 파이썬 환경 생성 +
VGMCP 설치). **"✅ 설치 완료"**가 표시되면 끝입니다.

> macOS가 실행을 막으면(우클릭만 되거나 "권한 거부"): `install.command`를
> **우클릭 → 열기**(확인) 하거나, 터미널에서
> `chmod +x install.command && ./install.command` 를 실행하세요.

**터미널을 선호한다면:**

```bash
cd <프로젝트 폴더>
./install.command
```

**완전 수동(고급):**

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[macos]"
```

(아래에서 `.venv/bin/` 접두사는 "이 폴더에 설치한 버전을 쓰라"는 뜻입니다.
생략하려면 터미널 창마다 한 번 `source .venv/bin/activate` 실행 후 `vgmcp`만
입력하면 됩니다.)

---

## 2단계 — 비전 백엔드(API 키) 등록

**두 가지 방법** 중 편한 쪽을 쓰면 됩니다.

> **🖱️ 클릭이 편하면? 메뉴바로 등록 (터미널 불필요).**
> 먼저 앱을 실행한 뒤([4단계](#4단계--앱-실행)), 메뉴바 아이콘 →
> **설정 → 비전 백엔드 관리 → 추가…**를 엽니다. 제공자 유형, 이름, 모델,
> (custom인 경우) 엔드포인트 URL, API 키를 한 칸씩 차례로 물어봅니다(키 입력
> 칸은 가려집니다). 동의는 같은 하위 메뉴의 **외부 전송 동의** 항목이고,
> 기본값 지정도 거기서 할 수 있습니다. 이 방법을 쓰면 아래 명령은 건너뛰어도
> 됩니다.

**⌨️ 또는 터미널 사용.** 고른 제공자를 등록합니다. `--key -`를 쓰면 터미널이
**가려진 입력**으로 키를 물어보므로, 비밀이 화면이나 기록에 남지 않습니다.

**OpenRouter (추천):**

```bash
.venv/bin/vgmcp provider add --type openrouter --model "openai/gpt-4o" --key - --set-default
.venv/bin/vgmcp provider consent openrouter
```

**Anthropic (Claude):**

```bash
.venv/bin/vgmcp provider add --type anthropic --key - --set-default
.venv/bin/vgmcp provider consent anthropic
```

**OpenAI:**

```bash
.venv/bin/vgmcp provider add --type openai --key - --set-default
.venv/bin/vgmcp provider consent openai
```

**Ollama (로컬, 키 없음, 외부 전송 없음):**

```bash
# 먼저 https://ollama.com 에서 Ollama 설치 후 비전 모델을 받으세요:
ollama pull llava
.venv/bin/vgmcp provider add --type ollama --model "llava" --set-default
# 외부로 나가지 않으므로 동의(consent) 불필요.
```

`consent` 줄은 **"내 스크린샷을 이 클라우드 서비스로 보내도 좋다"**는 1회
동의입니다. (Ollama는 필요 없습니다.)

잘 됐는지 확인:

```bash
.venv/bin/vgmcp provider list
```

`"has_key": true`, `"consented": true`로 표시되면 됩니다.

---

## 3단계 — 화면 기록 권한 부여

macOS가 VGMCP의 화면 보기를 허용해야 합니다.

1. **시스템 설정 → 개인정보 보호 및 보안 → 화면 기록**을 엽니다.
2. **터미널**(나중에는 VGMCP 앱)의 스위치를 켭니다.
3. macOS가 앱을 종료 후 다시 열라고 하면 그렇게 하세요.

한 번만 하면 됩니다. (macOS에서는 VGMCP를 *실행시키는* 앱이 권한을 받습니다 —
설치 중에는 보통 터미널입니다.)

준비 상태 확인:

```bash
.venv/bin/vgmcp check
```

"missing(누락)" 항목이 나오면 각 항목의 `guide`/`install_command`를 따르세요.
모두 갖춰지면 환경이 정상이라고 표시됩니다.

---

## 4단계 — 앱 실행

프로젝트 폴더에서 **`start.command`를 더블클릭**하세요 — 앱이 백그라운드로
실행되며 터미널 창은 닫아도 됩니다. (또는 `.venv/bin/vgmcp` 실행)

- 화면 오른쪽 위 **메뉴바에 작은 아이콘**이 나타납니다.
- 🟢 초록 = 정상 · 🟡 노랑 = 동작하지만 일부 선택 항목 누락 ·
  🔴 빨강 = 조치 필요(클릭하면 안내).
- 첫 실행 시 짧은 환영 안내가 뜹니다 — 읽고 확인을 누르세요.

실행 상태로 두세요. 종료하려면 아이콘 클릭 → **종료**.

**로그인할 때마다 자동으로 켜지게 하려면:**

```bash
.venv/bin/vgmcp autostart enable
```

(또는 메뉴에서 **설정 → 로그인 시 자동 시작** 토글.)

---

## 5단계 — AI 도구에 연결 (MCP)

AI 도구는 **어댑터(adapter)**라는 작은 도우미를 통해 VGMCP와 통신합니다.
도구의 MCP 설정에 한 번만 등록하면 됩니다. 어댑터의 **전체 경로**를 사용하세요
(아래 경로는 실제 프로젝트 위치로 바꾸세요):

```json
{
  "mcpServers": {
    "vgmcp": {
      "command": "/Users/yourname/Projects/vision-graft-mcp/.venv/bin/vgmcp-adapter"
    }
  }
}
```

정확한 경로는 아래로 확인:

```bash
echo "$(pwd)/.venv/bin/vgmcp-adapter"
```

이 JSON을 넣는 위치는 도구마다 다릅니다.

- **Cursor:** `~/.cursor/mcp.json`(전역) 또는 프로젝트의 `.cursor/mcp.json`.
- **Claude Desktop:** `~/Library/Application Support/Claude/claude_desktop_config.json`.
- **oh-my-pi / 기타:** 해당 도구의 "MCP 서버" 설정 위치.

수정 후 AI 도구를 재시작하세요. 이제 VGMCP의 도구(`take_screenshot`,
`analyze_vision` 등)가 보일 겁니다.

> **중요:** 4단계의 메뉴바 앱이 실행 중이어야 합니다. 꺼져 있으면 어댑터가
> "앱이 꺼져 있으니 실행하라"고 정중히 안내합니다.

---

## 일상적인 사용법

**AI에게 맡기기.** 코딩 모델에게 이렇게 요청하세요:

> "앱 실행하고 스크린샷 찍어서 레이아웃 깨진 데 없는지 확인해줘."

그러면 모델이 `take_screenshot` → `analyze_vision`을 호출하고, 글로 된 리포트를
바탕으로 CSS를 고칩니다 — 자신은 이미지를 못 보더라도요.

**또는 메뉴바에서 직접:**

- **캡처** → 모니터 전체, 특정 창, **영역 드래그 선택**, 또는 기존 이미지
  파일 열기.
- **마지막 이미지 분석** → 가장 최근 캡처를 비전 모델에 보내 요약을 보여줍니다.
- **최근 이미지** → 항목을 클릭하면 (이미지 경로가 포함된) 붙여넣기용 프롬프트가
  클립보드에 복사됩니다. AI 도구에 붙여넣으세요.

**터미널에서 빠른 테스트** (AI 도구 없이):

```bash
.venv/bin/vgmcp capture-analyze --target region --x 0 --y 0 --w 800 --h 500
```

화면 일부를 캡처해 비전 모델의 리포트를 출력합니다.

---

## 명령어 모음

```bash
# 앱 / 호스트
vgmcp                      # 메뉴바 앱 + 백그라운드 호스트 실행
vgmcp --no-tray            # 호스트만 포그라운드로 실행 (고급)
vgmcp check                # 환경 점검 및 누락 항목 출력

# 비전 백엔드
vgmcp provider add --type <anthropic|openai|openrouter|custom|ollama> [--model M] [--key -] [--set-default]
vgmcp provider list                         # 등록 목록 (키/동의 상태)
vgmcp provider update <id> [--model M] [--key -] [--set-default]
vgmcp provider remove <id>                  # 저장된 키도 함께 삭제
vgmcp provider consent <id> [--revoke]      # 클라우드 전송 허용/철회

# 실제 비전 루프 실행
vgmcp capture-analyze --target monitor                          # 화면 캡처 + 분석
vgmcp capture-analyze --target window --app-name "Safari"       # 특정 앱 창
vgmcp capture-analyze --target region --x 100 --y 100 --w 600 --h 400
vgmcp analyze /경로/이미지.png                                  # 기존 이미지 분석

# 로그인 시 자동 시작
vgmcp autostart enable | disable | status
```

`custom`(자체 호스팅/게이트웨이) 제공자는 `--base-url "https://엔드포인트/v1"`도
함께 넘기세요. `--key -`는 항상 "가려진 입력으로 키를 물어보라"는 뜻입니다.

---

## 문제 해결

**메뉴바 아이콘이 없어요.**
앱이 실행 중이 아닙니다. `.venv/bin/vgmcp`를 실행하세요. (터미널 창을 닫으면
멈출 수 있으니, 자동 시작을 켜거나 창을 열어 두세요.)

**캡처가 검게 나오거나 실패해요.**
화면 기록 권한이 없거나 만료됐습니다.
[3단계](#3단계--화면-기록-권한-부여)를 다시 한 뒤 앱을 종료 후 재실행하세요.
`.venv/bin/vgmcp check`로 확인하세요.

**AI 도구가 "호스트에 연결할 수 없다"고 해요.**
메뉴바 앱(`.venv/bin/vgmcp`)을 실행하세요 — 어댑터는 앱이 켜져 있어야 합니다.

**비전 모델에서 `AUTH_FAILED` / 401이 나요.**
API 키가 틀렸거나 만료됐습니다. 다시 저장하세요:
`.venv/bin/vgmcp provider update <id> --key -`

**`consent_required`가 나와요.**
아직 해당 클라우드 제공자로 스크린샷 전송에 동의하지 않았습니다:
`.venv/bin/vgmcp provider consent <id>` (또는 메뉴 토글). 로컬 Ollama는 필요
없습니다.

**`OLLAMA_UNAVAILABLE`이 나요.**
Ollama를 실행(`ollama serve`)하고 모델을 받았는지 확인하세요
(`ollama pull llava`).

**`command not found: python3`.**
[python.org/downloads](https://www.python.org/downloads/)에서 Python을
설치하세요.

---

## 프라이버시 & 저장 위치

- **API 키**는 **macOS 키체인**에 저장되며, 평문 파일에 절대 저장되지 않습니다.
- **설정**은 `~/.config/vgmcp/config.json`에 있습니다 (provider, 타겟 폴더, 환경
  설정 — *키는 제외*).
- **스크린샷**은 기본적으로 `~/Pictures/vgmcp/`에 저장됩니다 (설정 → 타겟
  폴더에서 변경).
- **클라우드 제공자**는 제공자별 **동의** 후에만 스크린샷을 받습니다. 큰 이미지는
  전송 전 축소되고, 작은 이미지는 원본 그대로 전송됩니다. 아무것도 Mac 밖으로
  내보내고 싶지 않다면 **Ollama**를 쓰세요.

---

## 개발자용

```bash
.venv/bin/pip install -e ".[macos,dev]"
.venv/bin/python -m pytest -q      # 테스트 실행
.venv/bin/ruff check src/ tests/   # 린트
```

- **언어:** 앱·설치 스크립트·실행 스크립트는 **OS 기본 언어가 한국어면 한국어,
  그 외에는 영어**로 표시됩니다. `VGMCP_LANG=ko` 또는 `VGMCP_LANG=en`으로 강제할
  수 있습니다.
- **트레이 아이콘 교체:** 메뉴바 아이콘은 `src/vgmcp/assets/aperture.svg` 하나의
  SVG에서 생성됩니다. 이 파일을 원하는 라인아트 SVG로 바꾸면 됩니다
  (`stroke="#000000"`를 유지해야 재색칠이 동작). VGMCP는 여기서 3개 상태를
  렌더링합니다 — 정상은 검정 **템플릿** 이미지(라이트/다크에 따라 자동 흑/백),
  경고/오류는 **호박색/빨강** 버전. 렌더 해상도는
  `~/.config/vgmcp/config.json`의 `icon_size`로 조절합니다. 생성된 PNG는
  `~/.config/vgmcp/icons/`에 캐시됩니다(삭제하면 다시 생성).
- 아키텍처·마일스톤·전체 명세: [`docs/plan.md`](docs/plan.md);
  최초 아이디어: [`docs/idea.md`](docs/idea.md).
- 트레이 앱은 루프백 MCP 호스트(`127.0.0.1:8765`)를 띄우며 공유 코어(캡처/
  비전/클립보드/환경 검증)를 보유합니다. MCP 클라이언트는 얇은 `vgmcp-adapter`로
  연결되어 이 호스트로 프록시되므로, 사용자(트레이)와 AI(MCP)가 같은 코어·타겟
  폴더·설정을 공유합니다.
- 호스트를 기본값이 아닌 곳에서 실행한다면 `VGMCP_SERVER_URL`(또는
  `VGMCP_HOST` / `VGMCP_PORT`)로 어댑터 접속 대상을 바꿀 수 있습니다.

Python ≥ 3.11 필요, macOS 타겟은 14(Sonoma)+ (ScreenCaptureKit).
