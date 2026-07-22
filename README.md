# Vision-Graft MCP (VGMCP)

**한국어** · [English](docs/README.en.md)

이미지를 보지 못하는 AI 코딩 모델에게 **눈**을 달아 주는 스크린샷·비전 분석 MCP 서버입니다.

빠른 모델이나 로컬 LLM 상당수는 이미지를 읽지 못합니다. 코드만 보고는 버튼이
잘렸는지, 요소가 겹쳤는지 알 수 없습니다. VGMCP는 화면을 캡처해 **이미지를 볼 수
있는 비전 모델**에게 보내고, 결과를 **텍스트 리포트**로 AI에게 돌려줍니다.
AI는 그 리포트를 근거로 시각적 버그를 실제로 고칩니다.

- **AI가 사용** — [MCP](https://modelcontextprotocol.io) 표준으로 Claude Code,
  Cursor, Claude Desktop 등에서 도구를 호출합니다.
- **사용자가 사용** — 메뉴바(macOS) / 시스템 트레이(Windows) 아이콘에서 직접
  캡처하고 분석합니다.

---

## 동작 구조

```
AI 코딩 도구 (Claude Code · Cursor · Claude Desktop 등)
      │  stdio (MCP)
      ▼
vgmcp-adapter ──HTTP──▶ VGMCP 트레이 앱 = 상주 MCP 호스트 (127.0.0.1:8765/mcp)
(얇은 프록시)              ├─ 화면 캡처: 모니터 · 창 · 영역
                          ├─ 비전 백엔드 호출 → 텍스트 리포트 반환
                          │    OpenRouter · Anthropic · OpenAI · custom · Ollama(로컬)
                          └─ 트레이 메뉴: 사용자가 같은 기능을 직접 사용
```

- 사용자(트레이)와 AI(MCP)는 **같은 코어와 설정**(타겟 폴더, 비전 백엔드)을 공유합니다.
- 트레이 앱이 꺼져 있으면 어댑터는 `vgmcp_status` 진단 도구 하나만 노출해
  "앱을 실행하라"고 안내합니다. **트레이 앱이 켜져 있어야 AI 쪽이 동작합니다.**
- 호스트는 루프백(127.0.0.1) 전용이라 외부에서 접근할 수 없습니다.

## 요구 사항

| 항목 | 내용 |
|---|---|
| OS | macOS 14 (Sonoma) 이상 또는 Windows 10/11 |
| Python | 3.11 이상 ([python.org/downloads](https://www.python.org/downloads/), Windows는 "Add Python to PATH" 체크) |
| 비전 백엔드 | 클라우드 API 키 1개 **또는** 로컬 [Ollama](https://ollama.com) (아래 표 참고) |
| AI 도구 | MCP(stdio)를 지원하는 도구 아무거나 |

| 백엔드 종류(`--type`) | 기본 모델 | 키 발급 |
|---|---|---|
| `openrouter` (추천) | `anthropic/claude-sonnet-4.6` | <https://openrouter.ai/keys> |
| `anthropic` | `claude-sonnet-4-6` | <https://console.anthropic.com/> |
| `openai` | `gpt-5.4` | <https://platform.openai.com/api-keys> |
| `custom` | 직접 지정 (`--base-url` 필수) | OpenAI 호환 엔드포인트 |
| `ollama` | `llava:7b` | 키 불필요 — 내 컴퓨터에서 실행 |

모델을 지정하지 않으면 위 기본 모델이 자동으로 쓰입니다.

---

## 빠른 시작

> 🤖 **AI 에이전트를 쓴다면** — 저장소를 클론한 뒤 에이전트에게 이 README를 주고
> "설치하고 MCP 등록해줘"라고 요청하세요. 에이전트는
> [AI 에이전트용 설치 지침](#ai-에이전트용-설치-지침)을 따라 아래 과정을 대신 수행합니다.

### 1. 설치

더블클릭 한 번이면 됩니다. `.venv` 가상환경을 만들고 VGMCP를 설치합니다.
재실행해도 안전합니다(실행 중인 인스턴스를 종료하고 다시 설치).

| OS | 방법 |
|---|---|
| Windows | **`install_win.bat` 더블클릭** |
| macOS | **`install_mac.command` 더블클릭** (막히면 우클릭 → 열기) |

"✅ 설치 완료 / Install complete"가 보이면 성공입니다.

### 2. 앱 실행

| OS | 방법 | 아이콘 위치 |
|---|---|---|
| Windows | **`start_win.bat` 더블클릭** | 트레이(시계 옆, `^` 오버플로 안에 있을 수 있음) |
| macOS | **`start_mac.command` 더블클릭** | 메뉴바 오른쪽 위 |

- 아이콘을 클릭하면 메뉴가 열립니다. 색상: 정상(테마에 맞는 흰/검 또는 초록) ·
  🟡 선택 항목 누락 · 🔴 조치 필요(클릭하면 안내).
- 시작 스크립트는 항상 **완전 재시작**합니다(이미 떠 있으면 종료 후 새로 실행).
- 로그인할 때 자동으로 켜려면: 메뉴 **설정 → 로그인 시 자동 시작**
  (또는 `vgmcp autostart enable`).

### 3. 비전 백엔드 등록

트레이 아이콘 → **설정 → 비전 백엔드 관리 → 추가…** 에서 종류·이름·모델·API 키를
차례로 입력합니다(키 입력 칸은 가려짐). 같은 메뉴에서 **외부 전송 동의**와
**기본값으로 설정**까지 하면 끝입니다. 모델은 나중에 **모델명 변경**으로 바꿀 수
있습니다.

터미널을 선호하면 (명령 접두사: Windows `.\.venv\Scripts\vgmcp.exe`,
macOS `./.venv/bin/vgmcp`):

```bash
# 예: OpenRouter — `--key -` 는 가려진 입력으로 키를 물어봅니다
./.venv/bin/vgmcp provider add --type openrouter --key - --set-default
./.venv/bin/vgmcp provider consent openrouter   # 스크린샷 외부 전송 1회 동의

# 예: Ollama (로컬 · 키/동의 불필요)
ollama pull llava:7b
./.venv/bin/vgmcp provider add --type ollama --set-default
```

> **로컬 모델 팁** — VRAM에 맞는 **비추론(non-reasoning)** 비전 모델을 쓰세요.
> 추론형 VLM(`qwen3-vl` 등)은 토큰을 "생각"에 다 쓰고 빈 응답을 내기 쉽습니다.
> 8GB GPU면 `llava:7b`(~4.7GB)를 권장합니다. 정밀한 분석이 필요하면 클라우드
> 백엔드를 쓰세요.

### 4. 화면 기록 권한 (macOS만)

**시스템 설정 → 개인정보 보호 및 보안 → 화면 기록**에서 VGMCP를 실행하는 앱
(보통 터미널)을 켜고, 앱을 종료 후 다시 실행하세요. **Windows는 권한이 필요
없습니다.** 준비 상태는 언제든 `vgmcp check`로 확인할 수 있습니다.

### 5. AI 도구에 MCP 등록

AI 도구에는 어댑터(`vgmcp-adapter`)를 **절대 경로**로 등록합니다.

- Windows: `<프로젝트 경로>\.venv\Scripts\vgmcp-adapter.exe`
- macOS: `<프로젝트 경로>/.venv/bin/vgmcp-adapter`

**Claude Code:**

```bash
claude mcp add vgmcp -- "C:\path\to\vision-graft-mcp\.venv\Scripts\vgmcp-adapter.exe"  # Windows
claude mcp add vgmcp -- "/path/to/vision-graft-mcp/.venv/bin/vgmcp-adapter"            # macOS
```

**Cursor / Claude Desktop / 기타 (JSON, 경로의 `\`는 `\\`로):**

```json
{ "mcpServers": { "vgmcp": { "command": "<어댑터 절대 경로>" } } }
```

| 도구 | 설정 위치 |
|---|---|
| Cursor | `~/.cursor/mcp.json` (전역) 또는 프로젝트 `.cursor/mcp.json` |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |

등록 후 AI 도구를 재시작하면 `take_screenshot` 등 VGMCP 도구가 보입니다.
이제 AI에게 이렇게 요청해 보세요:

> "앱 실행하고 스크린샷 찍어서 레이아웃 깨진 곳 없는지 확인해줘."

---

## AI 에이전트용 설치 지침

> 이 절은 AI 에이전트가 그대로 실행하도록 작성되었습니다. 사용자가 이 저장소의
> 설치를 요청하면 아래 절차를 순서대로 수행하세요.
> 전제: 현재 작업 디렉터리 = 이 저장소 루트.

**0. Python 확인** — `python --version`(Windows) / `python3 --version`(macOS)이
3.11 이상인지 확인합니다. 미만이거나 없으면 사용자에게
<https://www.python.org/downloads/> 설치를 요청하고 중단하세요.

**1. 설치** — 여러 번 실행해도 안전합니다(실행 중인 VGMCP를 종료 후 재설치하므로,
사용자가 사용 중일 수 있으면 먼저 알리세요). 성공 기준: 출력에 `설치 완료` 또는
`Install complete`.

```powershell
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_win.ps1
```

```bash
# macOS
chmod +x install_mac.command && ./install_mac.command
```

**2. 트레이 앱 실행** — 앱은 분리(detached) 실행되므로 명령은 곧바로 반환됩니다.

```powershell
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_win.ps1
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8765/mcp   # HTTP 상태 코드가 나오면(값 무관) 호스트 실행 중
```

```bash
# macOS
./start_mac.command
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/mcp
```

**3. 비전 백엔드 등록** — 아래 중 한 가지를 선택합니다
(명령 접두사: Windows `.\.venv\Scripts\vgmcp.exe`, macOS `./.venv/bin/vgmcp`).

- **(A) Ollama — 완전 자동, 키·동의 불필요.** Ollama가 설치돼 있거나 사용자가
  로컬 처리를 원할 때:

  ```bash
  ollama pull llava:7b
  ./.venv/bin/vgmcp provider add --type ollama --set-default
  ```

- **(B) 클라우드 — 환경변수 키 사용.** `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` /
  `OPENAI_API_KEY` 중 하나가 **사용자(시스템) 수준 환경변수**로 이미 있으면
  `--key` 없이 등록할 수 있습니다(실행 시 환경변수를 읽음). 셸 세션에만 있는
  변수는 트레이 앱 프로세스에 보이지 않으니 주의하세요.

  ```bash
  ./.venv/bin/vgmcp provider add --type openrouter --set-default
  ```

- **(C) 클라우드 — 키 직접 입력.** API 키는 비밀값입니다. **키를 명령 인자로
  넘기지 마세요**(셸 기록에 남음). 사용자에게 아래 명령을 직접 실행해 달라고
  요청하거나(`--key -` = 가려진 입력), 트레이 메뉴(설정 → 비전 백엔드 관리 →
  추가…)를 안내하세요.

  ```bash
  ./.venv/bin/vgmcp provider add --type openrouter --key - --set-default
  ```

- **클라우드 공통 — 전송 동의.** 스크린샷을 해당 클라우드로 보내는 것에 대한
  1회 동의입니다. **사용자에게 동의 여부를 먼저 확인한 뒤** 실행하세요
  (Ollama는 불필요):

  ```bash
  ./.venv/bin/vgmcp provider consent openrouter
  ```

**4. 점검**

```bash
./.venv/bin/vgmcp check            # exit 0 = 정상
./.venv/bin/vgmcp provider list    # 등록한 백엔드가 "has_key": true, "consented": true 인지 확인
```

`check`가 누락 항목을 반환하면 각 항목의 `guide` / `install_command`를 따르거나
사용자에게 전달하세요. **macOS 화면 기록 권한은 에이전트가 대신 켤 수 없습니다**
— 사용자에게 시스템 설정 → 개인정보 보호 및 보안 → 화면 기록 활성화를 요청하세요.

**5. MCP 등록** — 어댑터의 **절대 경로**를 사용합니다.
Windows: `<저장소 절대경로>\.venv\Scripts\vgmcp-adapter.exe` ·
macOS: `<저장소 절대경로>/.venv/bin/vgmcp-adapter`

- Claude Code: `claude mcp add vgmcp -- <어댑터 절대경로>`
  (모든 프로젝트에서 쓰려면 `--scope user` 추가)
- JSON 설정을 쓰는 도구(Cursor, Claude Desktop 등)는 해당 파일의 `mcpServers`에
  아래 항목을 **병합**하세요. 기존 서버 항목을 지우거나 파일을 통째로 덮어쓰면
  안 됩니다.

  ```json
  { "mcpServers": { "vgmcp": { "command": "<어댑터 절대경로>" } } }
  ```

**6. 최종 확인** — MCP 클라이언트를 재시작(재연결)한 뒤 `check_environment`
도구를 호출해 `"status": "ok"`를 확인하세요. 도구 목록에 `vgmcp_status`만 보이면
트레이 앱이 꺼진 것입니다 → 2단계를 다시 실행하세요.

**에이전트 주의사항**

- 스크린샷이 필요하면 항상 `take_screenshot` 도구를 사용하세요. 자체 캡처
  스크립트(PowerShell, `screencapture`, `PIL.ImageGrab` 등)를 작성하지 마세요.
- `region_interactive` 캡처와 트레이 메뉴 조작은 사용자 상호작용이 필요합니다.

---

## MCP 도구

| 도구 | 하는 일 |
|---|---|
| `take_screenshot` | 화면을 캡처해 타겟 폴더에 저장하고 경로 반환. `target`: `monitor` · `window`(`app_name`/`title_contains`/`window_id`) · `region`(x·y·w·h) · `region_interactive`(사용자 드래그). 분석 없이 단독 사용 가능 |
| `analyze_vision` | 이미지 파일 + 프롬프트를 비전 백엔드로 분석해 텍스트 리포트 반환 |
| `capture_and_analyze` | 캡처 + 분석을 한 번에 |
| `list_monitors` / `list_windows` | 캡처 가능한 모니터/창 목록 |
| `check_environment` | 런타임·패키지·권한·키·설정 점검, 누락 항목별 해결 가이드 반환 |
| `get_config` / `set_target_folder` | 설정 조회(키 제외) / 캡처 저장 폴더 변경 |

**self_analyze** — 호출한 모델이 스스로 이미지를 볼 수 있다면
`analyze_vision` / `capture_and_analyze`에 `self_analyze=true`를 넘겨 외부 백엔드
없이 직접 분석할 수 있습니다. 먼저 검증 코드가 그려진 작은 이미지가 반환되고,
그 코드를 읽어 `vision_check`로 다시 호출해야 스크린샷을 받습니다(비전 능력
검증). 코드를 읽을 수 없으면 `self_analyze=false`로 백엔드에 맡기세요.

**셀프 분석 모드 사용** — 트레이의 설정에서 이 모드를 켜면 사용자 선택이 모든
도구 인자보다 우선합니다. 활성화 후 시작되는 호출과 재시도는 비전 백엔드를 사용하지
않으며, 능력 검증 없이 이미지가 호출한 LLM에 직접 반환됩니다. 활성화 전에 이미 시작된
요청은 완료될 수 있습니다. 비전 기능이 없는 모델은 이미지를 분석할 수 없습니다. 이
모드에서는 비전 백엔드가 없어도 환경 검사를 통과하며 트레이의 **마지막 이미지 분석**
메뉴는 비활성화됩니다.

## 트레이 메뉴 (사용자 직접 사용)

- **캡처** — 모니터 전체 · 앱 창 선택 · 영역 드래그 선택 · 이미지 파일 열기.
- **마지막 이미지 분석** — 가장 최근 캡처를 비전 백엔드로 분석해 결과를 표시.
- **최근 이미지** — 클릭하면 이미지 경로가 담긴 붙여넣기용 프롬프트가 클립보드에
  복사됩니다(템플릿은 설정에서 편집).
- **설정** — 셀프 분석 모드, 비전 백엔드 관리(추가·모델명 변경·외부 전송
  동의·기본값·삭제), 타겟 폴더, 자동 클립보드 복사, 로그인 시 자동 시작.

> **창 캡처의 플랫폼 차이** — Windows는 최소화된 창도 목록에 나오고 캡처 전에
> 자동 복원되며, 캡처를 거부하는 창은 모니터 캡처로 대체됩니다. macOS는 최소화된
> 창이 목록에서 빠지므로(ScreenCaptureKit 제약) 먼저 창을 복원하고 캡처하세요.

## 명령어 요약

접두사 생략: Windows `.\.venv\Scripts\vgmcp.exe …`, macOS `./.venv/bin/vgmcp …`

```bash
vgmcp                       # 트레이 앱 + 상주 호스트 실행
vgmcp --no-tray             # 호스트만 포그라운드로 실행 (고급)
vgmcp check                 # 환경 점검 및 누락 항목 안내

vgmcp provider add --type <anthropic|openai|openrouter|custom|ollama> [--model M] [--key -] [--base-url URL] [--set-default]
vgmcp provider list                        # 등록 목록 (키/동의 상태 포함)
vgmcp provider update <id> [--model M] [--key -] [--set-default]
vgmcp provider remove <id>                 # 저장된 키도 함께 삭제
vgmcp provider consent <id> [--revoke]     # 외부 전송 동의 / 철회

vgmcp analyze <이미지경로> [--prompt P] [--backend ID]
vgmcp capture-analyze --target <monitor|window|region|region_interactive> [--app-name A] [--x --y --w --h] …
vgmcp autostart enable|disable|status      # 로그인 시 자동 시작
```

`custom` 백엔드는 `--base-url "https://엔드포인트/v1"`을 함께 넘기세요.
`--key -`는 항상 "가려진 입력으로 키를 물어보라"는 뜻입니다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| 트레이/메뉴바 아이콘이 없음 | 앱이 꺼져 있음 → `start_win.bat` / `start_mac.command` 실행. Windows는 `^` 오버플로도 확인 |
| AI 도구에 `vgmcp_status`만 보임 / "host unreachable" | 트레이 앱을 실행한 뒤 다시 시도 |
| 캡처가 검거나 실패 (macOS) | 화면 기록 권한 재부여 후 앱 재시작. `vgmcp check`로 확인 |
| 캡처가 검게 나옴 (Windows) | DirectX/배타 전체화면 앱은 지원 밖 → 모니터 전체 캡처 사용 |
| `AUTH_FAILED` / 401 | 키가 틀리거나 만료 → `vgmcp provider update <id> --key -` |
| `consent_required` | `vgmcp provider consent <id>` (또는 트레이 메뉴의 외부 전송 동의) |
| `OLLAMA_UNAVAILABLE` | `ollama serve` 실행 + `ollama pull llava:7b` 확인 |
| `command not found: python3` | [python.org/downloads](https://www.python.org/downloads/)에서 설치 |

## 프라이버시 & 저장 위치

- **API 키** — OS 자격 증명 저장소(macOS 키체인 / Windows 자격 증명 관리자)에만
  저장됩니다. 평문 파일에 남지 않습니다.
- **설정** — `~/.config/vgmcp/config.json` (백엔드 목록·타겟 폴더 등, *키 제외*).
- **스크린샷** — 기본 저장 위치 `~/Pictures/vgmcp/` (트레이 설정 → 타겟 폴더에서 변경).
- **외부 전송** — 클라우드 백엔드는 제공자별 **동의 후에만** 스크린샷을 받습니다.
  큰 이미지는 전송 전 자동 축소됩니다. 아무것도 내보내고 싶지 않다면 Ollama를
  쓰세요. MCP 호스트는 127.0.0.1 전용입니다.

## 개발자

```bash
# macOS (Windows: .\.venv\Scripts\… 접두사 + ".[windows,dev]")
./.venv/bin/pip install -e ".[macos,dev]"
./.venv/bin/python -m pytest -q      # 테스트
./.venv/bin/ruff check src/ tests/   # 린트
```

- 설계·마일스톤: [`docs/plan.md`](docs/plan.md) · 최초 아이디어:
  [`docs/idea.md`](docs/idea.md) · Windows 포팅:
  [`docs/windows-port-plan.md`](docs/windows-port-plan.md) ·
  이전 README: [`docs/archive/`](docs/archive/)
- **환경변수** — `VGMCP_LANG=ko|en`(UI 언어 강제, 기본은 OS 언어 따라감) ·
  `VGMCP_SERVER_URL`(어댑터가 접속할 호스트 URL, 기본
  `http://127.0.0.1:8765/mcp`; `VGMCP_HOST` / `VGMCP_PORT` / `VGMCP_PATH`로 부분
  지정 가능)
- **트레이/모달 아이콘** — 원본은 `src/vgmcp/assets/aperture.svg` 하나. macOS는 PNG로
  래스터화해 `~/.config/vgmcp/icons/`에 캐시하고, Windows는 `resvg-py`로 SVG를 직접
  렌더링합니다. SVG를 바꾸면 양쪽 운영체제에 동일하게 반영됩니다.

라이선스: [MIT](LICENSE)
