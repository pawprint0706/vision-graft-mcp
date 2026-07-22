# Windows 지원 구현 계획 (Windows Port Plan)

> 대상: `vision-graft-mcp`
> 작성일: 2026-06-29
> 근거 문서: `docs/plan.md` (특히 §3.1.3, §6.3, §11 M6)

## 구현 상태 (2026-06-29 기준: 완료)

아래 계획의 M6.1~M6.5가 모두 구현·검증되었다. (M6.6 WGC는 의도적으로 보류.)

| 항목 | 결과물 | 검증 |
|------|--------|------|
| 캡처 백엔드 | `src/vgmcp/capture/windows.py` + `capture/__init__.py` 팩토리 | 모니터/영역/창 캡처 실기 통과. **하드웨어 가속 Chrome 창 95.88% 정상 픽셀**(검은 화면 아님) |
| 창/모니터 열거 | `WindowsCaptureBackend.list_windows/list_monitors` | 멀티모니터 2개, 프로세스명(`chrome`/`notepad++`) 정상 해석 |
| 트레이 UI | `src/vgmcp/tray/windows.py` (pystray + tkinter) | `icon.run()` 기동·표시·메뉴/상태 갱신 확인 |
| 자동 시작 | `core/autostart.py` (HKCU Run 키 분기) | enable/disable 레지스트리 왕복 검증 |
| 설정 파일락 | `core/config.py` (msvcrt 분기) | 저장 왕복 검증 |
| 로케일 감지 | `core/i18n.py` (GetUserDefaultUILanguage) | `ko` 정상 감지 |
| 진입점/패키징 | `__main__.py`, `install_win.ps1`/`start_win.ps1` (+ 더블클릭용 `install_win.bat`/`start_win.bat` 래퍼), `pyproject` windows extra | `python -m vgmcp`, 헤드리스 호스트 8765 바인딩, 전체 프로세스 기동, `.bat`→`.ps1` 한글 출력 확인 |
| CLI 분기 | `cli.py` (Windows 트레이 + autostart 출력 일반화) | `vgmcp check` 동작 |
| 테스트/린트 | `tests/test_autostart.py` 크로스플랫폼화 등 | `pytest` 31 passed / 27 skipped, `ruff` 통과 |

미검증(코드는 완성, 실사용 확인 권장): 영역 드래그 오버레이(`capture_region_interactive`)의 혼합 DPI 정확도, 트레이 메뉴의 대화상자 실제 클릭 흐름.

## 0. 요약

이 프로젝트의 **비전 분석 파이프라인 · MCP 서버 · stdio 어댑터 · 설정/자격증명 코어는 이미 플랫폼 독립적**으로 작성되어 있다. macOS 전용으로 채워져 있고 Windows에서 비어 있는 부분은 본질적으로 **OS 의존 레이어 4개**뿐이다.

| # | 레이어 | 현재 상태 | Windows 작업 |
|---|--------|-----------|--------------|
| 1 | 화면 캡처 | `capture/__init__.py`에 빈 stub | `capture/windows.py` 신규 구현 |
| 2 | 트레이/메뉴바 UI | `tray/macos.py`만 존재 | `tray/windows.py` 신규 구현 |
| 3 | 로그인 시 자동 시작 | `autostart.py` macOS 전용 | 레지스트리/시작폴더 분기 |
| 4 | 설치/실행 스크립트 | `*.command` (bash) | `*.ps1` 신규 |

부가적으로 견고성/UX 보완(파일락, 로케일 감지)이 있다. 코드베이스가 `CaptureBackend` 프로토콜(`core/interfaces.py`)·팩토리(`capture/__init__.py`)·플랫폼 헬퍼(`core/platform.py`)로 확장 지점을 잘 마련해 두었으므로, **기존 macOS 코드는 손대지 않고 병렬 구현을 추가**하는 방식으로 진행한다.

---

## 1. 아키텍처 확인 — 무엇이 이미 크로스플랫폼인가

수정이 **불필요**한(이미 플랫폼 독립적인) 영역:

- `vision/*` (anthropic/openai/ollama, httpx 기반)
- `server/app.py`, `server/host.py`, `server/vision_service.py` (MCP 툴 · loopback HTTP 호스트)
- `adapter/stdio_adapter.py` (stdio↔HTTP 프록시)
- `core/credentials.py` — `keyring`이 macOS Keychain / Windows Credential Manager를 자동 추상화
- `core/imaging.py`, `core/models.py`, `core/errors.py`
- `core/clipboard.py` — `NSPasteboard` 실패 시 `pyperclip` 폴백으로 Windows 동작 (단 `clipboard` extra 필요)
- `core/environment.py` — 이미 `_WINDOWS_CAPTURE_PKGS` 정의 및 플랫폼 분기 보유
- `core/mainthread.py` — `PyObjCTools` ImportError 시 인라인 실행 폴백 (Windows 무해)

경로는 전부 `pathlib.Path` 기반이라 구분자 문제 없음.

---

## 2. 작업 항목 (우선순위순)

### 작업 1 — 캡처 백엔드 `capture/windows.py` (최우선·핵심)

**현재 상태:** `src/vgmcp/capture/__init__.py:25-29`에서 Windows 분기가 `_cached = None`인 빈 stub. `win32gui`가 설치돼 있어도 무조건 `None`을 반환하여 모든 캡처가 `{"status": "not_implemented"}`로 떨어진다.

**구현 대상:** `core/interfaces.py`의 `CaptureBackend` 프로토콜 전체 메서드.

| 메서드 | Windows 구현 방안 | 참고 |
|--------|-------------------|------|
| `list_monitors()` | `mss().monitors` 열거 → `MonitorInfo`(width/height/dpi_scale/primary) | plan §5.2 |
| `list_windows()` | `win32gui.EnumWindows` + `GetWindowText`/`GetWindowRect`/`IsWindowVisible`. 소유 프로세스명은 `GetWindowThreadProcessId` + `psutil`/`QueryFullProcessImageName` | plan §6.3 |
| `capture_monitor(index, dest)` | `mss().grab(monitor[index])` → PNG 저장 | |
| `capture_window(window_id, dest)` | **대상 창을 전면(foreground)으로 올린 뒤** HWND의 `GetWindowRect` 영역을 `mss`로 캡처 (= 화면에 그려진 픽셀을 찍음). `PrintWindow`는 채택하지 않음(아래 설계 결정 참조). | plan §6.3, §7.4 제약 |
| `find_window(app_name, title_contains)` | `list_windows()` 결과를 셀렉터로 필터 → 첫 HWND 반환 | plan §6.4 |
| `capture_region(x,y,w,h,dest)` | `mss().grab({"left":x,"top":y,"width":w,"height":h})` | |
| `capture_region_interactive(dest)` | macOS `screencapture -i` 등가물 없음 → **커스텀 오버레이 필요** (아래 별도 항목) | plan §6.5 |
| `check_permission()` | Windows엔 화면기록 권한 개념 없음 → 항상 `True` 반환 (대신 DPI awareness 처리) | plan §3.1.3 |

**내부 window_id 규약:** HWND(int)를 그대로 `window_id`로 사용 (macOS는 CGWindowID, plan §6.6 일관).

**DPI Awareness (중요):** 프로세스 시작 시 `ctypes.windll.shcore.SetProcessDpiAwareness(2)` 또는 `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` 호출. 미적용 시 멀티모니터/고DPI에서 좌표·캡처 영역이 어긋난다 (plan §6.3, §9.2). 호출 위치는 트레이/호스트 부팅 초기(예: `cli._run_app` 진입부 또는 windows 백엔드 생성 시점).

#### 설계 결정 — 하드웨어 가속 창(크롬 등) 캡처 전략

이 MCP의 주 용도는 **웹/앱 UI 시각 버그 디버깅**이므로, **하드웨어 가속이 켜진 Chrome 등 웹브라우저 창이 캡처되는지가 가장 중요한 검증 포인트**다. (게임 등 풀스크린 GPU 앱 캡처는 현재 목표에서 제외.)

캡처 방식별 동작 차이:

| 방식 | 하드웨어 가속 크롬 | 가려진 창 | 비고 |
|------|-------------------|-----------|------|
| **`GetWindowRect` 영역 → `mss`** (채택) | ✅ 정상 (DWM이 합성해 화면에 그린 결과를 찍음) | ⚠️ 베스트에포트 전면화로 대부분 회피, 실패 시 가린 창 함께 찍힘 | 전면화는 시도하되 강제하지 않음 |
| `PrintWindow` + `PW_RENDERFULLCONTENT` | ⚠️ 검은 화면 빈번 (백버퍼를 못 가져옴) | ✅ 가려져도 가능 | 본 프로젝트에서 **비채택** |

**채택 전략:** `capture_window`는 **베스트에포트로 대상 창을 전면화한 뒤** `GetWindowRect` 영역을 `mss`로 캡처한다. 이렇게 하면 **하드웨어 가속 브라우저 창도 "화면에 보이는 그대로" 캡처**된다.

**전면화는 베스트에포트(best-effort) — 실패해도 그냥 캡처한다:**
- 시도 순서: `ShowWindow(hwnd, SW_RESTORE)`(최소화 해제) → `BringWindowToTop(hwnd)` → `SetForegroundWindow(hwnd)`. 호출 후 짧게(예: ~100ms) 대기해 DWM 합성을 기다린 뒤 캡처.
- **Windows의 포커스 도용 방지 정책** 때문에, 다른 프로세스가 포그라운드를 쥐고 있으면 `SetForegroundWindow`가 실패하고 작업표시줄만 깜빡일 수 있다. 이때는 **강제로 뚫지 않는다** — 그대로 `GetWindowRect` 영역을 캡처하며, 다른 창이 위에 겹쳐 있으면 함께 찍히는 것을 감수한다(UI 디버깅 용도에서 수용 가능).
- **명시적 비채택 (구현 비용·취약성 과다):** `AttachThreadInput` 기반 강제 전면화, 가짜 `ALT` 키 입력, `SPI_SETFOREGROUNDLOCKTIMEOUT` 변경 등 포커스 정책 우회 해킹. 깨지기 쉽고 부작용이 있어 도입하지 않는다.

트레이드오프는 (1) 전면화 성공 시 캡처 순간 대상 창이 잠깐 앞으로 나오고, (2) 전면화 실패 시 위에 떠 있는 창이 함께 찍힐 수 있다는 점 — 둘 다 수용 가능 범위.

**잔여 제약 (plan §7.4):** DirectX 풀스크린/배타 모드 같은 일부 GPU 앱은 위 방식으로도 검은 화면이 날 수 있으나, 이는 현재 목표 밖이다. 최악의 경우 **모니터 전체 캡처(`capture_monitor`)로 항상 우회 가능**하다.

**최소화 창 (플랫폼 차이, 의도적):** Windows는 `list_windows`에 최소화 창도 포함하고 `capture_window`가 `SW_RESTORE`로 복원 후 캡처한다(권한 불필요). macOS는 최소화 창을 제외한다 — ScreenCaptureKit은 최소화 창의 렌더 surface가 없고, 타 앱 창을 복원하려면 별도의 접근성(Accessibility) 권한이 필요해 비용 대비 효율이 낮다. 이 비대칭은 의도적으로 두고 README에 명시했다.

**WGC 후속 분리 사유:** 견고 대응인 `Windows.Graphics.Capture`(Win10 1903+)는 WinRT/COM interop + D3D11 프레임풀 파이프라인이 필요해 비용이 높다. 다만 `windows-capture` 같은 기성 Rust 백엔드 PyPI 패키지로 비용을 크게 낮출 여지가 있으므로, plan.md의 "Python 바인딩이 약하다"는 전제는 재검토 대상이다. **결론: 레거시 mss/GDI로 먼저 구현하고, 실제로 "캡처해야 할 대상 창에서 검은 화면이 자주 난다"는 사례가 보고되면 그때 M6.6(WGC)을 앞당겨 투자**한다 (plan §11 제외사항 기준).

**팩토리 수정:** `capture/__init__.py:25-29`의 stub을
```python
elif is_windows() and module_available("mss"):
    from .windows import WindowsCaptureBackend
    _cached = WindowsCaptureBackend()
```
로 교체. (감지 키를 `win32gui` → `mss`로 바꿀지 검토: 모니터/영역 캡처만이라면 `mss`만으로 가능, 윈도우 열거에 `win32gui` 필요하므로 둘 다 체크하거나 윈도우 기능을 graceful degrade.)

---

### 작업 2 — 트레이/메뉴바 UI `tray/windows.py`

**현재 상태:** `tray/macos.py`(635줄, rumps + NSAlert/NSOpenPanel)만 존재. `cli.py:34-44`의 `_run_app`은 `is_macos() and module_available("rumps")`일 때만 트레이를 띄우고 Windows에선 헤드리스 HTTP 호스트로만 동작한다.

**구현 대상:** macOS 트레이의 기능 동등 구현 (plan §4.1 메뉴 구조 공통).

| macOS 구현 | Windows 대응 |
|------------|--------------|
| `rumps` 메뉴바 앱 | `pystray`(windows extra 포함) 시스템 트레이 |
| `NSImage` 아이콘 브랜딩 (`assets/camera.svg`) | SVG→PNG/ICO 렌더 후 `PIL.Image`로 트레이 아이콘 설정 |
| `NSAlert` 모달/토스트 | `tkinter.messagebox` 또는 `win32ui` MessageBox, 토스트는 `winrt`/`win10toast` 선택 |
| `NSOpenPanel` (폴더 선택) | `tkinter.filedialog.askdirectory` |
| `NSPopUpButton` (provider 선택 등) | pystray 서브메뉴 또는 tkinter 다이얼로그 |
| `subprocess.run(["open", folder])` (`macos.py:329-333`) | `os.startfile(folder)` |
| Dock 아이콘 숨김 `setActivationPolicy_` | 불필요 (콘솔 창 숨김은 `pythonw.exe`/`.pyw`로 실행) |

**cli 분기 추가:** `cli.py:34-44`에
```python
if not args.no_tray and is_windows() and module_available("pystray"):
    from .tray.windows import run_tray
    run_tray(); return 0
```
를 macOS 분기와 병렬로 추가.

**참고:** 메뉴 동작 로직(캡처·분석·설정·provider 관리)은 코어 함수를 호출하는 것이므로, `tray/macos.py`에서 UI 비의존 로직을 공통 모듈로 추출할지 검토하면 두 트레이 간 중복을 줄일 수 있다. (선택적 리팩터링; MVP에선 windows.py에 직접 작성해도 무방.)

---

### 작업 3 — 인터랙티브 영역 선택 (작업 1의 하위, 별도 난이도)

macOS는 시스템 유틸 `/usr/sbin/screencapture -i -x`(`macos.py:292-296`)로 드래그 선택을 위임한다. **Windows엔 동등한 헤드리스 시스템 유틸이 없다.**

**옵션 (택1):**
1. **커스텀 전체화면 투명 오버레이** — `tkinter` 전체화면 + 반투명 캔버스에서 드래그 사각형을 받아 좌표 산출 후 `capture_region` 호출. (의존성 추가 없음, 권장)
2. Windows 11 `ms-screenclip:` / Snipping Tool 호출 — 결과를 클립보드로만 반환하여 파일 경로 연동이 번거로움. 비권장.

`capture_region_interactive`는 취소 시 `None` 반환 규약(`interfaces.py:31-32`)을 지킬 것.

---

### 작업 4 — 로그인 시 자동 시작 `core/autostart.py`

**현재 상태:** 전부 macOS 전용 — LaunchAgent plist 작성(`~/Library/LaunchAgents/com.vgmcp.tray.plist`) + `launchctl load/unload`. `cli.py:171-184`의 `autostart` 서브커맨드와 트레이가 `enable()/disable()/is_enabled()/plist_path()`를 호출한다.

**Windows 대응:** 플랫폼 분기 도입.
- **방안 A (권장):** 레지스트리 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`에 실행 명령 등록 (`winreg` 표준 라이브러리, 관리자 권한 불필요).
- 방안 B: 시작프로그램 폴더(`shell:startup`)에 `.lnk` 생성 (`pywin32`/`winshell`).
- `is_enabled()`는 레지스트리 값 존재 여부로 판단.

`cli.py`의 autostart 출력이 `plist` 키를 하드코딩하므로(`cli.py:176,183`), 플랫폼 중립 키(예: `location`)로 일반화하거나 분기 처리 필요.

---

### 작업 5 — 설정 파일 잠금 `core/config.py:122-138` (견고성)

**현재 상태:** `_file_lock`이 POSIX `fcntl.flock` 사용, `ImportError` 시 **Windows에선 잠금 없이 진행**. 동작은 하나 트레이 + MCP 동시 쓰기 시 경쟁 조건 위험.

**대응:** `msvcrt.locking` 또는 `portalocker`로 cross-process 락 구현. 기능 차단은 아니므로 MVP 후순위 가능하나, 트레이와 MCP가 동시에 config를 쓰는 구조이므로 권장.

---

### 작업 6 — 설치/실행 스크립트

**현재 상태:** `install_mac.command`, `start_mac.command` (bash, macOS 전용). `defaults read -g AppleLocale`, `.venv/bin/`, `nohup`/`open` 사용.

**대응:** `install_win.ps1` / `start_win.ps1`(또는 `.bat`) 신규 작성.
- venv 경로 `.venv\Scripts\`
- `pip install -e ".[windows]"` (pyproject `windows` extra: pywin32, pygetwindow, pystray, mss)
- 백그라운드 실행은 `pythonw.exe` 또는 `Start-Process -WindowStyle Hidden`
- 콘솔 창 없이 트레이만 띄우도록 `pythonw` 사용 권장

---

### 작업 7 — 로케일 감지 보완 `core/i18n.py:19-32` (UX, 선택)

**현재 상태:** macOS `NSLocale.preferredLanguages` 우선, 실패 시 POSIX 환경변수(`LANG`) 폴백. Windows는 `LANG`이 보통 미설정이라 **항상 영어로 떨어질 가능성**.

**대응:** Windows 분기로 `ctypes.windll.kernel32.GetUserDefaultUILanguage` 또는 `locale.getlocale()` 사용. 기능 영향 없음, UI 언어 정확도만 개선.

---

## 3. 의존성 / 패키징

`pyproject.toml`의 `windows` extra(이미 정의됨: `pywin32`, `pygetwindow`, `pystray`, `mss`)를 검토·확정한다. 추가 검토 대상:
- 토스트 알림 라이브러리(예: `win10toast`/`winrt`) — 선택
- 인터랙티브 선택을 tkinter로 구현하면 표준 라이브러리라 의존성 추가 없음
- `clipboard` extra의 `pyperclip` 포함 여부 확인 (Windows 클립보드 폴백용)
- 콘솔 숨김 실행을 위한 진입점/런처 정리

---

## 4. 환경 검사 통합

`core/environment.py`는 이미 Windows를 부분 인지한다:
- `_WINDOWS_CAPTURE_PKGS`(`environment.py:29-32`): `win32gui`→pywin32, `mss`
- `_check_capture_packages` 플랫폼 분기(`environment.py:48-49`)
- `_check_capture_permission`은 `if not is_macos(): return []`(`environment.py:65-66`) — Windows 권한 검사 스킵

**보완:** 백엔드 구현 후, `check_environment` MCP 툴이 Windows에서 누락 패키지·DPI 상태를 사용자 친화적으로 안내하도록 검증. 필요 시 DPI awareness 적용 여부를 검사 항목으로 추가(plan §3.1.3 표).

---

## 5. 권장 마일스톤 (plan §11 M6 세분화)

- **M6.1 — 캡처 코어:** `capture/windows.py`(monitor/region/window/list) + 팩토리 + DPI awareness. `vgmcp capture-analyze`/`vgmcp check` CLI로 헤드리스 검증.
  - **핵심 합격 기준:** 하드웨어 가속(`chrome://gpu`에서 활성)이 켜진 **Chrome 창을 `capture_window`로 찍었을 때 검은 화면 없이 정상 캡처**될 것. 이게 안 되면 전략 재검토(전면 전환 로직 보강 또는 M6.6 조기 착수).
- **M6.2 — 인터랙티브 선택:** 오버레이 기반 `capture_region_interactive`.
- **M6.3 — 트레이 UI:** `tray/windows.py`(pystray) + 다이얼로그 + cli 분기. 전체 메뉴 동작.
- **M6.4 — 자동시작 + 견고성:** `autostart` Windows 분기, config 파일락, i18n 로케일.
- **M6.5 — 패키징:** `install_win.ps1`/`start_win.ps1` + 더블클릭용 `.bat` 래퍼(실행정책 우회 + UTF-8 콘솔), pythonw 런처, extra 확정. (`.ps1`은 PowerShell 5.1 한글 파싱을 위해 UTF-8 BOM으로 저장.)
- **M6.6 (후속/제외 가능):** `Windows.Graphics.Capture` interop으로 DirectX/가려진 창 캡처 한계 해소 (plan §11 제외사항).

---

## 6. 핵심 파일 참조 요약

| 파일:라인 | 내용 | 작업 |
|-----------|------|------|
| `capture/__init__.py:25-29` | Windows 팩토리 stub | 작업 1 |
| `capture/macos.py` (전체) | macOS 캡처 참조 구현 | 작업 1 모델 |
| `core/interfaces.py:11-37` | `CaptureBackend` 프로토콜 | 작업 1 계약 |
| `cli.py:34-44` | `_run_app` 트레이 분기 | 작업 2 |
| `tray/macos.py` (전체) | macOS 트레이 참조 | 작업 2 모델 |
| `tray/macos.py:292-296` | `screencapture -i` | 작업 3 |
| `tray/macos.py:329-333` | `open` 셸 명령 | 작업 2 (`os.startfile`) |
| `core/autostart.py` (전체) | LaunchAgent | 작업 4 |
| `cli.py:171-184` | autostart 서브커맨드 | 작업 4 |
| `core/config.py:122-138` | `fcntl` 파일락 | 작업 5 |
| `install_mac.command`/`start_mac.command` | bash 스크립트 | 작업 6 |
| `core/i18n.py:19-32` | 로케일 감지 | 작업 7 |
| `core/environment.py:29-66` | Windows 환경검사 골격 | 작업 1/4 통합 |
| `pyproject.toml:35-40` | windows extra | 작업 3 |
