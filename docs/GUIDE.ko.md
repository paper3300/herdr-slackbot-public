# herdr-slackbot 사용 가이드

[English](GUIDE.md) | **한국어**

기본 내용은 [README](../README.ko.md)에 있습니다. 이 문서에는 자세한 내용을 담았습니다. **Herdr 앱**(데스크톱 앱: `herdr-app` + herdr-core `hc`)을 기준으로 설명하고, 예전 **Herdr CLI**에서 다른 점은 [Herdr CLI](#herdr-cli)에 모았습니다.

- [설정 마법사](#설정-마법사)
- [페어링 자세히](#페어링-자세히)
- [Slack bridge 탭](#slack-bridge-탭)
- [수동 설정](#수동-설정)
- [Herdr CLI](#herdr-cli)
- [Slack에서 쓰기](#slack에서-쓰기)
  - [대화 상자에 답하기](#대화-상자에-답하기)
  - [Home 탭](#home-탭)
- [문제 해결](#문제-해결)

## 설정 마법사

Slack bridge 탭에서 **Setup**을 눌러 시작하거나(**Slack setup** 탭이 열림), 터미널에서 `scripts\setup.ps1 -Backend hc -Wizard`로 실행합니다.

1. 설정 폴더(`%APPDATA%\herdr-slackbot`)에 `.env` 뼈대와 Slack 앱 manifest를 만듭니다. 슬래시 명령과 봇 이름은 `.env`에 값이 없을 때만 묻습니다. Enter를 누르면 괄호 안의 기본값(`/herdr-<windows username>`, `Herdr (<username>)`)을 씁니다.
2. 브라우저로 Slack의 앱 만들기 화면을 엽니다. manifest가 미리 채워져 있으니 워크스페이스를 고르고 **Next → Create**만 누르면 됩니다. 링크와 manifest 파일 경로도 출력하므로, 브라우저가 안 열리거나 양식이 비어 있으면 파일 내용을 직접 붙여 넣습니다.
   - **이 명령을 쓰는 Slack 앱이 이미 있다면**(예: 이전에 설치한 것) 두 번째 앱을 만들지 마세요. 슬래시 명령이 같은 앱 두 개는 명령을 서로 가져가려고 다툽니다. 화면을 닫고 <https://api.slack.com/apps>에서 기존 앱의 토큰을 가져옵니다.
3. 어느 페이지에서 무엇을 복사할지 알려 주고 토큰 두 개를 받습니다.
   - `xapp-...` (App-Level Token): **Basic Information → App-Level Tokens** — 기존 토큰을 쓰거나, **Generate Token and Scopes**에서 이름은 아무거나, scope는 `connections:write`로 만듭니다
   - `xoxb-...` (Bot User OAuth Token): **Install to Workspace** 후 **Install App**(또는 OAuth & Permissions) 페이지

   받은 토큰은 Slack에 직접 확인합니다(`apps.connections.open`, `auth.test`). 틀리면 Slack이 돌려준 오류를 보여 주고 다시 묻습니다. `.env`에 이미 유효한 토큰이 있으면 이 단계를 건너뛰고, 바꿀지만 묻습니다. 토큰 전체를 화면에 다시 출력하지 않습니다.
4. 토큰을 `.env`에 **제자리에서** 씁니다. 주석과 다른 값은 그대로 둡니다.
5. 브리지를 시작합니다. 이미 돌고 있으면 재시작합니다.
6. 아직 페어링하지 않았다면 페어링 코드를 보여 주고 페어링될 때까지(최대 10분) 기다립니다. [페어링 자세히](#페어링-자세히)를 보세요.
7. 슬래시 명령, 봇 DM 위치, 재시작·상태 확인 방법을 요약해 줍니다.

Ctrl+C로 언제든 멈출 수 있습니다. 그때까지 입력한 값은 `.env`에 남아 있고, 다시 실행하면 이어서 진행합니다.

## 페어링 자세히

봇이 누구의 요청을 받을지는 `.env`의 `SLACK_OWNER_USER_ID`로 정합니다. 멤버 ID를 직접 찾을 필요는 없습니다. 값이 비어 있으면 브리지가 **페어링 모드**로 시작합니다.

1. 브리지가 6자리 코드를 만듭니다. 코드는 마법사 화면, Herdr 앱 알림("Slack pairing code: NNNNNN"), 브리지 터미널(Slack bridge 탭의 **Show**)에 크게 표시됩니다.
2. Slack 왼쪽 **앱** 목록에서 봇을 열고, DM 창에서 `/herdr-kim pair 123456`을 보냅니다.
3. "paired ✅"가 오면 브리지가 `.env`에 `SLACK_OWNER_USER_ID`를 써 넣고, **재시작 없이** 본인 전용 모드로 바뀝니다. 준비가 끝나면 봇 DM으로 사용법 안내(👋 Paired!)가 오고, Slack bridge 탭에 `ready (owner U...)`가 표시됩니다. 그 전에 명령을 보내면 "still starting" 안내가 나옵니다. 시작에 실패하면(몇 번 다시 시도한 뒤) 알림과 마법사가 브리지를 재시작하라고 알려 줍니다. 재시작하면 저장된 계정으로 정상 시작합니다.

- 페어링 모드에서는 `pair` 명령만 받습니다. 다른 명령, 버튼, 모달, DM 메시지, Home 탭에는 "not paired yet" 안내만 보냅니다. 에이전트 알림도 페어링 후에 시작합니다.
- 코드는 15분이 지나거나 틀린 코드가 모두 5번 들어오면 새 코드로 바뀝니다(새 코드를 다시 표시). 또 Slack 사용자 한 명이 10분 안에 5번 틀리면 **그 사람만** 10분 동안 시도할 수 없습니다. 틀린 적이 없는 사람(본인)은 막히지 않으므로, 누가 코드를 찍어 보더라도 본인의 페어링을 막을 수 없습니다.
- 한 번 페어링하면 `pair`도 다른 사람의 요청처럼 거절합니다. **다른 계정으로 다시 페어링**하려면 `.env`에서 `SLACK_OWNER_USER_ID=` 값을 지우고 브리지를 재시작합니다.
- 페어링을 기다리는 동안 상태는 `waiting for pairing (...)`으로 표시되고, 브리지가 실제로 본인 전용 모드로 돌고 있을 때만 `ready (owner U...)`가 나옵니다. `.env`에 멤버 ID가 있는데 브리지가 준비되지 않았으면 `not ready`, 시작에 실패했으면 `owner mode failed to start`로 표시합니다. 마법사도 브리지가 준비됐다고 알릴 때까지(최대 60초) 기다린 뒤에만 성공이라고 말합니다.
- 페어링 대신 멤버 ID를 직접 적어도 됩니다: Slack에서 내 프로필 사진 → **프로필** → 오른쪽 위 **⋮**(더보기) → **멤버 ID 복사**. `U0123ABCD` 같은 형태입니다.

## Slack bridge 탭

space **herdr-slack**의 **Slack bridge** 탭이 브리지의 제어판입니다. 상태(테마 색 점: idle = 준비됨, working = 실행 중/시작 중, dim = 멈춤, blocked = 오류), 슬래시 명령, 설정·로그 경로, 버튼이 표시됩니다.

| 버튼 | 동작 |
|---|---|
| **Show** | 브리지 터미널(출력, 페어링 코드)을 잠깐 봅니다 |
| **Start** / **Restart** | 브리지를 시작하거나, 멈췄다가 다시 시작합니다(예: `.env` 수정 후) |
| **Stop** | 브리지를 멈춥니다 |
| **Setup** | **Slack setup** 탭을 열고 마법사를 실행합니다 |

- **실행 방식:** 브리지는 부모 없는 herdr-core 터미널 `herdr-slackbot`(`python -m herdr_slackbot run`)으로 돌기 때문에 Herdr 창을 닫아도 계속 돕니다. space herdr-slack(`BRIDGE_WORKSPACE`)에 자기 탭으로 보이고, 그 space가 없으면 숨은 채로 돕니다. 어느 터미널에서든 `hc read herdr-slackbot`이나 `hc attach herdr-slackbot`(Ctrl+\로 분리)으로 볼 수 있습니다.
- **자동 시작:** Herdr 앱이 시작되면 패널이 브리지를 시작합니다(Slack 토큰이 없으면 시작하지 않음). **탭을 닫지 마세요:** 앱 mod는 창 안에 있을 때만 돕니다(보고 있지 않은 탭이어도 됩니다). Herdr 기본 레이아웃은 읽기 전용이라 패널은 상태 표시줄 대신 자기 탭에 둡니다.
- **알림:** 페어링 코드와 그 밖의 브리지 메시지는 Herdr 앱 토스트로 뜹니다(브리지가 `STATE_DIR\notify.json`을 쓰고 패널이 보여 줌).
- **단축키:** `~\.config\herdr-app\keys.json`에서 패널의 명령에 키를 지정합니다. 예: `"global": { "ctrl-alt-s": "herdr-slackbot.restart" }` (명령: `start`, `stop`, `restart`, `setup`, `status`, `show`).
- **터미널에서:** `scripts\herdr-slackbot.ps1 launch|restart|stop|status`로 버튼과 같은 일을 할 수 있습니다.
- **브리지는 한 번에 하나만:** 브리지는 인스턴스 잠금(`STATE_DIR\bridge.lock`)을 잡습니다. 시작·중지·재시작은 `STATE_DIR\lifecycle.lock`으로 한 번에 하나씩만 진행되므로, 상태는 항상 멈춤 / 시작 중 / 실행 중 셋 중 하나입니다. 시작 중(최대 60초)에 들어온 다른 시작 요청은 무시되고, 이때 중지하면 그 시작이 취소됩니다. 중지는 터미널에 아무것도 입력하지 않습니다. 실행 중인 브리지 프로세스(pid + 생성 시각) 앞으로 `stop.request`를 남기면 브리지가 스스로 정상 종료합니다. 15초가 지나면 프로세스를 종료하는데, 여전히 그 프로세스일 때만 종료합니다. 시작하기 전에 이전 브리지의 끝난 터미널을 지웁니다.
- 토큰이 없거나 틀려도 브리지는 죽거나 재시작을 반복하지 않습니다. 이유와 다음 할 일을 한 번 출력하고 종료하며, 끝난 터미널에 그 메시지가 남습니다(**Show** / `hc read herdr-slackbot`). 설정을 고친 뒤 재시작하면 됩니다.
- **수동 실행**(개발): 개발할 때는 아래처럼 직접 실행합니다.

  ```powershell
  .venv\Scripts\python -m herdr_slackbot check         # settings + the Herdr connection, lists the agents
  .venv\Scripts\python -m herdr_slackbot status
  .venv\Scripts\python -m herdr_slackbot manifest      # print the manifest for the current settings
  .venv\Scripts\python -m herdr_slackbot marker-check  # round-trip the duplicate-prevention marker through real Slack
  ```

처음 실제 Slack으로 돌려 볼 때는 [LIVE_TEST.md](LIVE_TEST.md)의 체크리스트를 따라 하세요.

## 수동 설정

마법사를 쓰지 않을 때의 방법입니다. 마법사가 하는 일을 손으로 합니다.

### `setup.ps1`이 하는 일

1. 저장소 폴더에 `.venv`를 만들고 의존성(`slack_bolt`, `slack_sdk`)을 설치합니다.
2. 기본값을 정합니다: 슬래시 명령 `/herdr-<windows username>` (소문자, 32자 이내), 봇 이름 `Herdr (<username>)`.
3. 설정 폴더(`%APPDATA%\herdr-slackbot`)에 파일 두 개를 씁니다.
   - `.env`: 설정 뼈대입니다. 파일이 이미 있으면 **기존 값은 절대 덮어쓰지 않고** 빠진 키만 덧붙입니다.
   - `slack-app-manifest.json`: Slack 앱을 만들 때 붙여 넣을 manifest입니다.
4. Herdr 앱: 패널 mod를 `~\.config\herdr-app\mods\herdr-slackbot`에 복사하고(`main.js`, `mod.json`), 그 `config.json`(어느 Python, 저장소 폴더, 설정 폴더를 쓸지)을 씁니다. 앱이 켜져 있으면 space herdr-slack과 그 안의 **Slack bridge** 탭이 없을 때 만듭니다.
5. 다음에 할 일을 출력합니다.

옵션: `-Backend auto|hc|herdr`(기본값 `auto`: `hc`가 설치되어 있으면 Herdr 앱), `-SlashCommand`, `-DisplayName`, `-ConfigDir`, `-SkipConfig`, `-Wizard`(설정 단계 대신 마법사를 실행하며, 터미널이 필요함). `setup.ps1` 자체는 입력을 받지 않습니다. `.env`에 이미 키가 있으면 빈 값이라도 `-SlashCommand`/`-DisplayName`은 그 값을 그대로 두고, 그렇다고 알려 줍니다. manifest는 항상 실제로 적용될 설정으로 만들어집니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 -Backend hc -SlashCommand /herdr-kim -DisplayName "Herdr (Kim)"
```

> 슬래시 명령 이름은 **Slack 워크스페이스 전체에서 겹치면 안 됩니다.** 같은 이름이면 가장 나중에 설치한 앱이 명령을 가져갑니다. 그래서 사용자마다 `/herdr-<name>`처럼 다르게 정합니다.

### Slack 앱 만들기 (manifest 사용)

1. <https://api.slack.com/apps> → **Create New App** → **From a manifest**를 누릅니다.
2. 사용할 워크스페이스를 고릅니다.
3. **JSON** 탭에서 기존 내용을 지우고 `slack-app-manifest.json`의 내용을 붙여 넣은 뒤 **Next** → **Create**를 누릅니다.
4. **Basic Information** → **App-Level Tokens** → **Generate Token and Scopes**: 이름은 아무거나 넣고, scope는 `connections:write`를 추가한 뒤 Generate를 누릅니다. 나온 `xapp-...` 토큰이 `SLACK_APP_TOKEN`입니다.
5. **Install App** → **Install to Workspace** → 허용을 누릅니다. **Bot User OAuth Token** `xoxb-...`이 `SLACK_BOT_TOKEN`입니다.
6. Slack 왼쪽 **앱** 목록에서 방금 만든 봇을 열면 DM 창이 생깁니다. 메시지 탭이 막혀 있으면 앱 설정의 **App Home** → *Allow users to send Slash commands and messages from the messages tab*을 켭니다.
7. 토큰 두 개를 `.env`에 넣고, 브리지를 재시작한 뒤(Slack bridge 탭의 **Restart**) 페어링합니다.

manifest에는 아래 설정이 들어 있습니다. 코드에서 실제로 호출하는 Slack API를 기준으로 뽑았고, `tests/test_slack_manifest.py`가 둘이 어긋나지 않는지 검사합니다.

| 항목 | 값 |
|---|---|
| Socket Mode | 켜짐 (공개 URL이나 포트 개방이 필요 없음) |
| Interactivity | 켜짐 (모달, 버튼) |
| 이벤트 | `message.im` (DM 스레드 답장), `app_home_opened` (Home 탭 새로고침) |
| App Home | Home 탭 켜짐, 메시지 탭 켜짐(입력 가능) |
| 슬래시 명령 | `.env`의 `SLASH_COMMAND` |
| Bot scopes | `chat:write` (메시지 전송·수정·ephemeral), `commands`, `im:write` (DM 열기), `im:history` (DM 메시지 수신), `files:write` ([View full] 파일 업로드) |

#### 이미 만든 앱의 manifest 갱신하기

새 버전에서 manifest가 바뀌었거나 `SLASH_COMMAND`를 바꿨다면: `scripts\setup.ps1`을 다시 실행합니다. `.env` 값은 건드리지 않고 `slack-app-manifest.json`을 새로 만듭니다. 그다음 <https://api.slack.com/apps>에서 앱 → **App Manifest**를 열고, 새 JSON을 붙여 넣은 뒤 **Save Changes**를 누릅니다. Slack이 재설치를 요구하면 재설치하고(**Install App → Reinstall to Workspace**, 토큰이 바뀌었다면 `.env`도 고침), 브리지를 재시작합니다.

### `.env` 채우기

`.env`는 설정 폴더에 있습니다. 고친 뒤에는 브리지를 재시작합니다.

```powershell
notepad "$env:APPDATA\herdr-slackbot\.env"
```

| 키 | 필수 | 설명 |
|---|---|---|
| `SLACK_BOT_TOKEN` | ✔ | `xoxb-...` (Install App 페이지) |
| `SLACK_APP_TOKEN` | ✔ | `xapp-...` (App-Level Token, `connections:write`) |
| `SLACK_OWNER_USER_ID` | | **본인** Slack 멤버 ID (`U`로 시작). 비워 두면 페어링으로 채워집니다. 이 사용자만 봇을 쓸 수 있습니다. |
| `SLASH_COMMAND` | | 기본 `/herdr-<username>`. **manifest의 명령과 같아야 합니다.** |
| `BOT_DISPLAY_NAME` | | 기본 `Herdr (<username>)` |
| `HERDR_BACKEND` | | 통신할 Herdr: `auto`(기본값), `hc`(Herdr 앱) 또는 `herdr`(Herdr CLI). `auto`는 예전 Herdr pane이나 플러그인 명령 안이면 Herdr CLI, 그 밖에는 `hc`가 설치되어 있으면 Herdr 앱을 고릅니다. |
| `STATE_DIR`, `LOG_LEVEL`, `RESULT_MAX_CHARS`, `FALLBACK_LINES`, `READ_LINES`, `BRIDGE_WORKSPACE`, `START_TIMEOUT_MS`, `CODEX_PROMPT_DELAY`, `STALL_WAIT`, `HC_SOCKET_PATH`, `HC_BIN`, `HERDR_APP_BIN`, `HERDR_BIN`, `HERDR_SOCKET_PATH` | | 선택 설정. 설명은 `.env.example`에 있습니다. |

## Herdr CLI

예전 터미널 Herdr(`herdr`, 0.8.2 이상, 0.9.5로 확인)도 Herdr 플러그인으로 계속 지원합니다. Slack에서 쓰는 방법은 같고, 다른 점은 다음과 같습니다.

- **설치:** `herdr plugin install paper3300/herdr-slackbot` (Herdr가 설치 단계에서 `scripts\setup.ps1 -Backend herdr`를 실행합니다). 또는 저장소를 받아 `scripts\setup.ps1 -Backend herdr`를 실행하고 `herdr plugin link D:\Git\herdr-slackbot`을 실행합니다(`herdr plugin list`에 `herdr-slackbot ... enabled`가 보여야 합니다). venv가 없으면 첫 시작 때 플러그인이 만듭니다.
- **설정 폴더:** 플러그인 설정 폴더 `herdr plugin config-dir herdr-slackbot` (보통 `%APPDATA%\herdr\plugins\config\herdr-slackbot`): `notepad "$(herdr plugin config-dir herdr-slackbot)\.env"`.
- **설정 마법사:** `herdr plugin action invoke setup --plugin herdr-slackbot` (또는 명령 팔레트의 *Slack bridge: setup wizard* 액션). 플러그인 액션은 입력을 받을 수 없어서, 액션은 새 탭을 열고 그 탭의 셸에 마법사 명령을 입력합니다.
- **브리지가 도는 곳:** 워크스페이스 `herdr-slack`의 pane. Herdr 서버가 시작될 때 플러그인 startup hook이 브리지를 시작합니다(`plugin link`/`install` 직후에는 돌지 않으므로, 그때는 마법사나 `start` 액션이 시작합니다). 필요하면 포커스를 가져가지 않고 워크스페이스를 만들고, 시작할 때마다 새 탭을 쓰며 기존 pane에는 절대 입력하지 않습니다. 새 브리지가 시작을 확인하면 이전 브리지 탭을 닫는데, 확실히 우리 것이고 비어 있을 때만 닫습니다(같은 Herdr 서버, 같은 탭/pane/터미널 ID, pane 하나, 실행 중인 것 없음).
- **페어링 코드:** 워크스페이스 `herdr-slack`의 브리지 pane과 Herdr 알림에 표시됩니다.
- **플러그인 액션** (출력: `herdr plugin log list --plugin herdr-slackbot`):

  ```powershell
  herdr plugin action invoke setup   --plugin herdr-slackbot   # setup wizard (runs in a new tab)
  herdr plugin action invoke start   --plugin herdr-slackbot   # no-op if already running
  herdr plugin action invoke restart --plugin herdr-slackbot   # after editing .env
  herdr plugin action invoke stop    --plugin herdr-slackbot
  herdr plugin action invoke status  --plugin herdr-slackbot   # also shown as a Herdr notification
  ```

- **단축키:** 플러그인 manifest로는 키를 지정할 수 없습니다. Herdr `config.toml`에 직접 추가하고 `herdr server reload-config`를 실행합니다.

  ```toml
  [[keys.command]]
  key = "prefix+shift+s"
  type = "plugin_action"
  command = "herdr-slackbot.restart"
  description = "restart Slack bridge"
  ```

- **Claude 세션:** Herdr 앱과 마찬가지로 에이전트 프로세스로 찾습니다. Herdr 자체의 Claude 연동(`herdr integration install claude`)은 필요 없습니다.

## Slack에서 쓰기

아래에서 `/herdr`는 본인의 `SLASH_COMMAND`를 뜻합니다(예: `/herdr-kim`). 봇 DM 창에서 사용합니다.

| 명령 | 동작 |
|---|---|
| `/herdr` | 사용법 |
| `/herdr list` | 에이전트 목록 (워크스페이스별, 상태 이모지) |
| `/herdr new` | 모달로 새 에이전트 시작: 워크스페이스, cwd, 종류(claude/codex), 모델, effort, 권한 모드, 이름, 프롬프트 |
| `/herdr new <workspace> [name=..] [kind=claude\|codex] [model=..] [effort=..] [mode=..] [cwd=..] <prompt>` | 모달 없이 바로 시작 |
| `/herdr send` | 모달로 실행 중인 에이전트에 프롬프트 전송. 에이전트를 고르면 Agent와 Prompt 사이에 **지금까지의 대화**가 표시됩니다. 내가 보낸 프롬프트(PC에서 입력한 것 포함)와 에이전트의 최종 답변이 오래된 것부터 차례로 나옵니다. 긴 답변은 끝부분 약 2500자, 긴 프롬프트는 앞부분만 보여 주고, 다 들어가지 않는 오래된 메시지는 "… N earlier messages not shown" 한 줄로 줄입니다. 작업 중이거나 응답을 기다리는(blocked) 에이전트는 대화와 함께 안내 한 줄이 붙습니다. Claude 대화는 세션 기록(transcript)에서 읽고, Codex이거나 기록을 찾지 못하면 대신 에이전트의 **마지막 응답**(시각·소요 시간 포함)을 보여 줍니다. Home 탭의 Send 버튼에서도 같은 모달이 열립니다. |
| `/herdr send <agent name\|id> <prompt>` | 바로 전송 (Herdr 앱: `t7` 같은 터미널 주소, Herdr CLI: pane id) |
| `/herdr status` | 브리지 상태 |
| `/herdr pair <code>` | 페어링 모드에서 본인 계정 연결 ([페어링 자세히](#페어링-자세히) 참고). 페어링 후에는 거절됩니다. |

- **새 에이전트:** 선택한 워크스페이스(space)에 새 탭을 만들고 거기서 에이전트를 시작합니다. 탭 이름은 `slack-<N> <prompt summary>` 또는 지정한 이름입니다. 기본값은 claude `--model opus --effort high --permission-mode auto`입니다. Herdr 앱에서 Codex는 `--no-daemon`으로 실행합니다.
- **전송 규칙:** 대상이 `idle`/`done`일 때만 보냅니다.
  - `working`이면 "busy"라고 답합니다.
  - `blocked`이면 스레드의 버튼으로 답하라고 안내합니다 (`/herdr send`, 모달).
- **스레드:** 에이전트마다 DM 스레드가 하나씩 생깁니다.
  - Slack에서 보낸 작업은 "⏳ started"와 완료 결과가 스레드 답장으로 옵니다.
  - 스레드에 답장하면 그 에이전트에게 프롬프트로 전달됩니다. 에이전트가 답을 기다리는 중이면 답장은 그 질문의 직접 입력 답이 됩니다([대화 상자에 답하기](#대화-상자에-답하기) 참고).
  - 에이전트가 종료되었거나 같은 터미널에 다른 세션이 뜬 경우에는 전달하지 않고 안내만 합니다.
- **알림:** PC에서 직접 시작한 에이전트도 알립니다.
  - 보고 있지 않을 때 끝난 작업은 알리고(`done`), 보고 있는 탭에서 끝난 작업은 알리지 않습니다. Herdr 앱에서는 앱 자체의 "보고 있지 않을 때 끝남" 상태를 따릅니다. 앱 창이 실행 중이 아니거나 에이전트에 탭이 없으면(예: `hc run`으로 띄운 하위 에이전트) 끝난 턴은 모두 안 본 것으로 칩니다.
  - `blocked` 상태가 되면 대화 상자를 버튼과 함께 보냅니다.
  - 스레드의 🔕 버튼으로 해당 에이전트 알림을 끌 수 있습니다. Slack에서 보낸 작업의 결과는 음소거와 상관없이 옵니다.
- **결과 본문:**
  - claude는 세션 JSONL에서 마지막 답변을 읽고(세션은 에이전트 프로세스로 찾음), 읽지 못하면 화면에서 파싱합니다. codex는 화면 끝부분을 보냅니다.
  - claude 답변을 JSONL에서 읽은 경우, 최종 답변 위에 **그 스레드의 이전 알림 이후 대화**도 함께 보여 줍니다. PC에서 입력했거나 작업 중에 큐에 넣은 프롬프트, 중간 답변, `⚙️` 줄(백그라운드 작업 완료, 대화 압축)이 들어갑니다. 그래서 스레드를 따라 읽으면 중복 없이 전체 대화가 됩니다. Slack에서 보낸 프롬프트는 이미 스레드에 있으므로 다시 보여 주지 않습니다. 스레드의 첫 메시지는 마지막 턴만 보여 줍니다. blocked(대화 상자) 메시지에는 기록이 없고, 그동안의 내용은 다음 결과 메시지에 포함됩니다. 음소거했던 동안의 내용도 마찬가지입니다. codex이거나 기록이 없으면 결과만 보냅니다.
  - 최종 답변은 항상 남습니다. 메시지 공간이 모자라면 오래된 항목은 "… N earlier messages not shown — View full" 한 줄로 줄이고, **[View full]**을 누르면 범위 전체를 자르지 않고 올립니다.
  - 3000자가 넘으면 잘라서 보내고, **[View full]** 버튼을 누르면 전체 내용을 `.md` 파일로 올립니다.

### 대화 상자에 답하기

에이전트가 `blocked`가 되면 스레드에 **"⚠️ <name> · <workspace> is waiting for your answer"** 메시지가 옵니다. 브리지가 화면의 대화 상자를 읽어 선택지마다 버튼을 붙입니다.

- **지원:** Claude 권한 확인(Bash 등), AskUserQuestion(단일 선택, 복수 선택, 여러 질문, 직접 입력), 계획 승인(ExitPlanMode), 시작할 때의 폴더 신뢰 확인(Claude, Codex), Codex 명령 승인.
- **버튼:** 선택지마다 `1. Yes` 같은 버튼이 있습니다. "항상 허용 / 다시 묻지 않기" 선택지도 그대로 버튼으로 나옵니다. 복수 선택은 ☐/☑ 버튼으로 켜고 끄고, **[Next →]**는 커서를 그 질문의 Submit 줄로 옮겨 Enter를 누릅니다(다음 질문 또는 검토 화면으로 넘어감). 항상 **[Esc]**와 **[Show screen]**(화면 끝 40줄을 스레드에 올림)이 있습니다.
- **직접 입력:** "Type something." / "Tell Claude what to change" 버튼을 누르면 입력 모달이 열립니다. 스레드에 답장해도 같은 답이 됩니다. 여러 줄은 그대로 보냅니다(줄바꿈은 에이전트 입력란에서 줄만 바꿀 뿐 제출하지 않습니다). 복수 선택 질문에서는 입력한 글이 "Type something" 칸도 체크하므로, **[Next →]**를 눌러 그 질문을 제출합니다. 직접 입력 선택지가 없는 질문에 답장하면 "This question needs one of the buttons above."라고 안내합니다.
  - Herdr 앱: herdr-core는 Enter 없이 글자를 입력할 때 키를 하나씩 보내는 방법밖에 없어서, **복수 선택** 질문의 직접 입력에는 영문자, 숫자, 공백만 쓸 수 있습니다(그 밖의 글자가 있으면 그 질문은 PC에서 답하라고 안내하고, 아무 키도 누르지 않습니다). 단일 선택 질문과 계획 피드백은 한글을 포함해 어떤 글자든 됩니다.
- **계획 승인:** 계획 파일(`~\.claude\plans\…md`)을 읽어 본문을 보여 주고, 길면 **[View full]**로 전체를 올립니다.
- **안전장치:** 버튼을 누르면 먼저 에이전트와 화면을 다시 확인합니다. 그 사이 PC에서 답했거나 질문이 바뀌었으면(같은 승인 질문 뒤의 계획이 바뀐 경우 포함) 키를 보내지 않고 메시지만 갱신합니다. 두 번 눌러도 키는 한 번만 가고, 이전 버전 메시지의 버튼을 누르면 "That button was out of date"만 안내합니다.
- **답한 뒤:** 다음 질문이 나오면 같은 메시지가 새 질문으로 바뀝니다. 에이전트가 계속 진행하면 `✅ <choice> — answered from Slack`으로 바뀌고 버튼이 사라집니다. PC에서 답하면 `✅ answered on PC`가 됩니다(브리지를 재시작한 뒤에도). 5초 안에 화면이 바뀌지 않으면 버튼을 남겨 두고 "Could not confirm the answer"를 알립니다.
- **화면을 읽지 못할 때:** `1`–`4`, `↑`, `↓`, Enter, Esc 키패드와 화면 끝 15줄을 보여 줍니다.
- **Slack에서 띄운 에이전트가 시작하자마자 폴더 신뢰를 물으면:** 스레드를 만들어 그 질문을 보내고, 답하면 원래 프롬프트를 보냅니다. (Herdr 앱에서는 그 화면이 떠 있는 동안 Claude가 상태를 알리지 않으므로, 브리지가 화면을 직접 알아봅니다.)
- **Codex:** `~/.codex/config.toml`에서 승인을 `approvals_reviewer = "auto_review"`로 넘기도록 설정했다면 Codex가 승인 화면을 띄우지 않으므로 Slack에도 오지 않습니다. 버그가 아니라 설정입니다.

### Home 탭

Slack 왼쪽 **앱** 목록에서 봇을 열고 **홈** 탭을 누르면 대시보드가 나옵니다.

- **맨 위:** 브리지 상태(uptime, 에이전트 수, 슬래시 명령, 갱신 시각)와 버튼 3개가 있습니다.
  - **[➕ New Agent]**: `/herdr new` 모달이 열립니다.
  - **[📤 Send]**: `/herdr send` 모달이 열립니다.
  - **[🔄 Refresh]**: 화면을 즉시 다시 그립니다.
- **아래:** 워크스페이스별 에이전트 목록(상태 이모지 · 이름 · 종류 · 상태 · 터미널 제목)이 있습니다. idle/done인 에이전트 줄의 **[Send]**를 누르면, 그 에이전트가 미리 선택된 보내기 모달이 열립니다.
- **자동 갱신:** 홈을 열 때마다 새로 그립니다. 한 번 연 뒤에는 에이전트 상태가 바뀔 때도 자동으로 갱신됩니다. 몰아서 최소 5초 간격으로 갱신합니다.
- **표시 한도:** 한 화면에 블록 100개까지 표시되고, 넘치면 "N more agents (see the `list` command)" 한 줄로 줄입니다.
- **소유자 전용:** 다른 사용자가 홈 탭을 열면 아무것도 게시하지 않습니다. 그 사람에게 에이전트 정보는 보이지 않습니다.

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 슬래시 명령에 반응이 없음 | 1. Slack bridge 탭과 브리지 출력(**Show** 또는 `hc read herdr-slackbot`)을 봅니다.<br>2. `STATE_DIR\bridge.log`를 확인합니다(경로는 탭에 표시됨). |
| Slack bridge 탭이 없음 | Herdr 앱을 켠 채 `scripts\setup.ps1 -Backend hc`를 다시 실행합니다. mod를 다시 설치하고 space herdr-slack / **Slack bridge** 탭을 다시 만듭니다. 그다음 `herdr-app status`에서 mod 오류를 확인합니다. |
| 앱과 함께 브리지가 시작되지 않음 | Slack bridge 탭이 창 안에 있어야 하고(뒤에 있어도 됨), 토큰이 설정되어 있어야 합니다. **Start**를 누릅니다. |
| `a bridge terminal (tN) is still running but holds no lock` | 다른 무언가가 `herdr-slackbot` 이름으로 돌고 있습니다. `hc read tN`으로 확인하고, 오래된 브리지라면 `hc kill tN`으로 끝냅니다. |
| `missing settings in ...` | `.env`에 토큰 두 개(`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`)를 채운 뒤 재시작합니다. **Setup**을 써도 됩니다. |
| "🔗 This Herdr bridge is not paired yet" | 페어링 모드입니다. 알림이나 **Show**에 표시된 코드로 `/herdr pair <code>`를 보냅니다. |
| "❌ Wrong pairing code" / "⌛ That code expired" | **가장 최근** 코드를 씁니다. 5번 틀리거나 15분이 지나면 코드가 바뀝니다. |
| "⏳ Too many wrong codes from you" | 10분 안에 5번 틀렸습니다. 안내된 시간만큼 기다린 뒤 **가장 최근** 코드로 다시 보냅니다. |
| "You are paired, but the bridge could not start" | 계정은 저장되었지만 본인 전용 모드 시작이 실패했습니다. 브리지 출력을 확인하고 재시작합니다. |
| `Slack connection failed: invalid_auth` | `xoxb`/`xapp` 토큰이 맞는지, 앱을 워크스페이스에 설치했는지, App-Level Token에 `connections:write`가 있는지 확인합니다. |
| `/herdr-...`가 "dispatch_failed" 또는 다른 앱이 응답 | 브리지가 떠 있는지 확인합니다. 같은 이름의 명령을 쓰는 다른 앱이 있는지도 확인합니다(이름은 워크스페이스 전체에서 유일해야 함). |
| "⛔ This Herdr bridge only accepts requests from its owner." | 다른 계정으로 페어링되어 있습니다. `.env`의 `SLACK_OWNER_USER_ID`를 비우고 재시작한 뒤 다시 페어링합니다. |
| DM 창에 입력이 안 됨 | App Home의 messages tab 설정을 확인합니다([Slack 앱 만들기](#slack-앱-만들기-manifest-사용) 6번). |
| `another bridge is running (pid N)` | 이미 실행 중입니다. 상태를 확인하고, 필요하면 재시작합니다. |
| 마법사가 "needs a terminal"이라며 멈춤 | 입력을 받을 수 없는 곳에서 실행했습니다. **Setup**을 쓰거나 터미널에서 실행합니다. |
| venv가 깨짐 | 저장소 폴더의 `.venv`를 지우고 `scripts\setup.ps1`을 다시 실행합니다. |
| `cannot verify the running bridge` | 실행 중인 브리지를 확인할 수 없어 멈추지 않은 경우입니다. 직접 끝냅니다(Herdr 앱: `hc kill herdr-slackbot`, Herdr CLI: 그 pane에서 Ctrl+C). |
| Herdr 앱: `unavailable` / hc 파이프를 열 수 없음 | hc 터미널 밖에서는 파이프 이름을 Windows 사용자 이름으로 만듭니다(`\\.\pipe\herdr-core-<user>-default.sock`). 이름이 다르면 `.env`에 `HC_SOCKET_PATH`를 설정합니다. |
| Herdr CLI: 플러그인 액션이 아무것도 안 하는 것 같음 | `herdr plugin log list --plugin herdr-slackbot`에서 stdout/stderr를 봅니다. |
