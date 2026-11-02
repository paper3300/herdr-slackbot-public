# herdr-slackbot user guide

**English** | [한국어](GUIDE.ko.md)

The [README](../README.md) covers the basics. This guide has the details. It describes the **Herdr app** (the desktop app: `herdr-app` + herdr-core `hc`); what differs on the older **Herdr CLI** is collected in [Herdr CLI](#herdr-cli).

- [Setup wizard](#setup-wizard)
- [Pairing details](#pairing-details)
- [The Slack bridge tab](#the-slack-bridge-tab)
- [Manual setup](#manual-setup)
- [Herdr CLI](#herdr-cli)
- [Using it in Slack](#using-it-in-slack)
  - [Answering dialogs](#answering-dialogs)
  - [Home tab](#home-tab)
- [Troubleshooting](#troubleshooting)

## Setup wizard

Start it with **Setup** in the Slack bridge tab (a **Slack setup** tab opens), or from a terminal with `scripts\setup.ps1 -Backend hc -Wizard`.

1. Creates the `.env` skeleton and the Slack app manifest in the config folder (`%APPDATA%\herdr-slackbot`). It asks for the slash command and bot name only when `.env` has no value for them. Press Enter to accept the default shown in brackets (`/herdr-<windows username>`, `Herdr (<username>)`).
2. Opens Slack's create-app page in your browser with the manifest prefilled; just pick the workspace and click **Next → Create**. It also prints the link and the manifest file path, so if the browser doesn't open or the form is empty, paste the file contents yourself.
   - **Already have a Slack app for this command** (e.g. from an earlier install)? Don't create a second one — two apps with the same slash command fight over it. Close the page and take the tokens from your existing app at <https://api.slack.com/apps>.
3. Asks for two tokens and tells you where to copy them from:
   - `xapp-...` (App-Level Token): **Basic Information → App-Level Tokens** — an existing token, or **Generate Token and Scopes** with any name and the scope `connections:write`
   - `xoxb-...` (Bot User OAuth Token): **Install App** (or OAuth & Permissions) after **Install to Workspace**

   Tokens are verified against Slack directly (`apps.connections.open`, `auth.test`). If one is wrong, the wizard shows Slack's error and asks again. If `.env` already holds valid tokens, it skips this step and only asks whether to replace them. Tokens are never echoed back in full.
4. Writes the tokens into `.env` **in place**, leaving comments and other values untouched.
5. Starts the bridge, or restarts it if it is already running.
6. If you haven't paired yet, shows the pairing code and waits (up to 10 minutes) until pairing completes. See [Pairing details](#pairing-details).
7. Prints a summary: the slash command, where to find the bot DM, and how to restart and check status.

You can stop at any time with Ctrl+C. Whatever you entered so far stays in `.env`, and running the wizard again picks up where you left off.

## Pairing details

`SLACK_OWNER_USER_ID` in `.env` decides whose requests the bot accepts. You don't need to look up your member ID: when the value is empty, the bridge starts in **pairing mode**.

1. The bridge generates a 6-digit code. It appears in the wizard, as a Herdr app notification ("Slack pairing code: NNNNNN") and in large type in the bridge's terminal (**Show** in the Slack bridge tab).
2. Open the bot from the **Apps** list in Slack's sidebar and send `/herdr-kim pair 123456` in the DM.
3. When "paired ✅" comes back, the bridge writes `SLACK_OWNER_USER_ID` to `.env` and switches to owner-only mode **without a restart**. When it is ready, the bot DMs you a usage guide (👋 Paired!) and the Slack bridge tab shows `ready (owner U...)`. Commands sent before that get a "still starting" notice. If startup fails (after a few retries), a notification and the wizard tell you to restart the bridge, which then starts normally with the saved account.

- In pairing mode only the `pair` command is accepted. Other commands, buttons, modals, DM messages and the Home tab only get a "not paired yet" notice. Agent notifications also start only after pairing.
- The code is replaced after 15 minutes or after 5 wrong attempts in total (the new code is shown again). In addition, a Slack user who gets it wrong 5 times within 10 minutes is locked out for 10 minutes — **only that user**. Someone who hasn't guessed wrong (you) is never blocked, so nobody can stop you from pairing by guessing codes.
- Once paired, `pair` is rejected like any other request from a non-owner. To **re-pair with a different account**, clear the value of `SLACK_OWNER_USER_ID=` in `.env` and restart the bridge.
- The status says `waiting for pairing (...)` while it waits, and `ready (owner U...)` only when the bridge is actually running in owner-only mode. If `.env` has a member ID but the bridge isn't ready, it says `not ready`; if startup failed, `owner mode failed to start`. The wizard also waits (up to 60 seconds) for the bridge to report ready before declaring success.
- You can also enter your member ID yourself instead of pairing: in Slack, click your profile picture → **Profile** → **⋮** (More) at the top right → **Copy member ID**. It looks like `U0123ABCD`.

## The Slack bridge tab

The **Slack bridge** tab in the space **herdr-slack** is the bridge's control panel. It shows the state (a dot in the theme's colors: idle = ready, working = running/starting, dim = stopped, blocked = error), the slash command, the config and log paths, and buttons:

| Button | What it does |
|---|---|
| **Show** | Peeks at the bridge's terminal (its output, the pairing code) |
| **Start** / **Restart** | Starts the bridge, or stops and starts it (e.g. after editing `.env`) |
| **Stop** | Stops the bridge |
| **Setup** | Opens a **Slack setup** tab with the wizard |

- **How it runs:** the bridge is the herdr-core terminal `herdr-slackbot` (`python -m herdr_slackbot run`), with no parent, so it keeps running when the Herdr window closes. It shows up as its own tab in the space herdr-slack (`BRIDGE_WORKSPACE`); without that space it runs hidden. `hc read herdr-slackbot` or `hc attach herdr-slackbot` (Ctrl+\ detaches) show it from any terminal.
- **Automatic start:** when the Herdr app starts, the panel starts the bridge (unless the Slack tokens are missing). **Keep the tab:** an app mod runs only while it is in the window (a tab you are not looking at is fine). Herdr's own layouts are read-only, which is why the panel lives in its own tab instead of the status bar.
- **Notifications:** the pairing code and other bridge messages appear as Herdr app toasts (the bridge writes `STATE_DIR\notify.json`, the panel shows it).
- **Keys:** bind the panel's commands in `~\.config\herdr-app\keys.json`, e.g. `"global": { "ctrl-alt-s": "herdr-slackbot.restart" }` (commands: `start`, `stop`, `restart`, `setup`, `status`, `show`).
- **From a terminal:** `scripts\herdr-slackbot.ps1 launch|restart|stop|status` does the same as the buttons.
- **One bridge at a time:** the bridge holds an instance lock (`STATE_DIR\bridge.lock`). Start, stop and restart are serialized through `STATE_DIR\lifecycle.lock`, so the state is always one of stopped / starting / running; other starts during a start (up to 60 seconds) are ignored and a stop at that point cancels it. Stop never types into a terminal: it leaves a `stop.request` addressed to the running bridge process (pid + creation time), which shuts down cleanly on its own; after 15 seconds the process is terminated, but only if it is still that process. Before a start, the previous bridge's finished terminal is removed.
- If tokens are missing or wrong, the bridge doesn't crash or restart in a loop. It prints the reason and what to do next once and exits; its finished terminal keeps the message (**Show** / `hc read herdr-slackbot`). Fix the settings and restart it.
- **Running manually** (development):

  ```powershell
  .venv\Scripts\python -m herdr_slackbot check         # settings + the Herdr connection, lists the agents
  .venv\Scripts\python -m herdr_slackbot status
  .venv\Scripts\python -m herdr_slackbot manifest      # print the manifest for the current settings
  .venv\Scripts\python -m herdr_slackbot marker-check  # round-trip the duplicate-prevention marker through real Slack
  ```

For your first run against real Slack, follow the checklist in [LIVE_TEST.md](LIVE_TEST.md).

## Manual setup

For when you don't use the wizard: do by hand what the wizard does.

### What `setup.ps1` does

1. Creates `.venv` in the repo folder and installs the dependencies (`slack_bolt`, `slack_sdk`).
2. Picks defaults: slash command `/herdr-<windows username>` (lowercase, at most 32 characters), bot name `Herdr (<username>)`.
3. Writes two files to the config folder (`%APPDATA%\herdr-slackbot`):
   - `.env`: the config skeleton. If the file already exists, it **never overwrites existing values** and only appends missing keys.
   - `slack-app-manifest.json`: the manifest to paste when creating the Slack app.
4. Herdr app: copies the panel mod to `~\.config\herdr-app\mods\herdr-slackbot` (`main.js`, `mod.json`), writes its `config.json` (which Python, repo folder and config folder to use) and, with the app running, creates the space herdr-slack and its **Slack bridge** tab when they are missing.
5. Prints the next steps.

Options: `-Backend auto|hc|herdr` (default `auto`: the Herdr app when `hc` is installed), `-SlashCommand`, `-DisplayName`, `-ConfigDir`, `-SkipConfig`, `-Wizard` (runs the wizard instead; needs a terminal). `setup.ps1` itself reads no input. If `.env` already has a key, even with an empty value, `-SlashCommand`/`-DisplayName` leave it as is and say so. The manifest is always generated from the settings that will actually apply.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 -Backend hc -SlashCommand /herdr-kim -DisplayName "Herdr (Kim)"
```

> Slash command names **must be unique across the whole Slack workspace.** If two apps use the same name, the most recently installed app takes the command. That's why each user picks a different name, such as `/herdr-<name>`.

### Create the Slack app (from the manifest)

1. Go to <https://api.slack.com/apps> → **Create New App** → **From a manifest**.
2. Pick your workspace.
3. On the **JSON** tab, replace the existing content with the contents of `slack-app-manifest.json`, then click **Next** → **Create**.
4. **Basic Information** → **App-Level Tokens** → **Generate Token and Scopes**: any name, the `connections:write` scope, Generate. The `xapp-...` token is `SLACK_APP_TOKEN`.
5. **Install App** → **Install to Workspace** → Allow. The **Bot User OAuth Token** `xoxb-...` is `SLACK_BOT_TOKEN`.
6. Open the new bot from the **Apps** list in Slack's sidebar to get a DM window. If the messages tab is disabled, turn on **App Home** → *Allow users to send Slash commands and messages from the messages tab* in the app settings.
7. Put both tokens into `.env`, restart the bridge (**Restart** in the Slack bridge tab) and pair.

The manifest contains the settings below. They are derived from the Slack APIs the code actually calls, and `tests/test_slack_manifest.py` checks that the two stay in sync.

| Setting | Value |
|---|---|
| Socket Mode | On (no public URL or open port needed) |
| Interactivity | On (modals, buttons) |
| Events | `message.im` (DM thread replies), `app_home_opened` (Home tab refresh) |
| App Home | Home tab on, messages tab on (input allowed) |
| Slash command | `SLASH_COMMAND` from `.env` |
| Bot scopes | `chat:write` (post, update, ephemeral messages), `commands`, `im:write` (open DMs), `im:history` (receive DM messages), `files:write` ([View full] file upload) |

#### Updating the manifest of an existing app

When a new version changes the manifest, or you changed `SLASH_COMMAND`: run `scripts\setup.ps1` again — it regenerates `slack-app-manifest.json` without touching the values in `.env` — then at <https://api.slack.com/apps> open your app → **App Manifest**, paste the new JSON and **Save Changes**. Reinstall if Slack asks (**Install App → Reinstall to Workspace**; update `.env` if the tokens changed), then restart the bridge.

### Fill in `.env`

`.env` lives in the config folder. Restart the bridge after editing it.

```powershell
notepad "$env:APPDATA\herdr-slackbot\.env"
```

| Key | Required | Description |
|---|---|---|
| `SLACK_BOT_TOKEN` | ✔ | `xoxb-...` (Install App page) |
| `SLACK_APP_TOKEN` | ✔ | `xapp-...` (App-Level Token, `connections:write`) |
| `SLACK_OWNER_USER_ID` | | **Your** Slack member ID (starts with `U`). Leave it empty and pairing fills it in. Only this user can use the bot. |
| `SLASH_COMMAND` | | Default `/herdr-<username>`. **Must match the command in the manifest.** |
| `BOT_DISPLAY_NAME` | | Default `Herdr (<username>)` |
| `HERDR_BACKEND` | | Which Herdr to talk to: `auto` (default), `hc` (Herdr app) or `herdr` (Herdr CLI). `auto` picks the Herdr CLI inside an old Herdr pane or plugin command, otherwise the Herdr app when `hc` is installed. |
| `STATE_DIR`, `LOG_LEVEL`, `RESULT_MAX_CHARS`, `FALLBACK_LINES`, `READ_LINES`, `BRIDGE_WORKSPACE`, `START_TIMEOUT_MS`, `CODEX_PROMPT_DELAY`, `STALL_WAIT`, `HC_SOCKET_PATH`, `HC_BIN`, `HERDR_APP_BIN`, `HERDR_BIN`, `HERDR_SOCKET_PATH` | | Optional settings, documented in `.env.example`. |

## Herdr CLI

The older terminal Herdr (`herdr`, 0.8.2 or later; checked with 0.9.5) is still supported, as a Herdr plugin. Slack works the same; what differs:

- **Install:** `herdr plugin install paper3300/herdr-slackbot` (Herdr runs `scripts\setup.ps1 -Backend herdr` as the install step). Or clone the repo, run `scripts\setup.ps1 -Backend herdr` and `herdr plugin link D:\Git\herdr-slackbot` (`herdr plugin list` should show `herdr-slackbot ... enabled`). If there is no venv, the plugin creates one on first start.
- **Config folder:** the plugin config folder, `herdr plugin config-dir herdr-slackbot` (usually `%APPDATA%\herdr\plugins\config\herdr-slackbot`): `notepad "$(herdr plugin config-dir herdr-slackbot)\.env"`.
- **Setup wizard:** `herdr plugin action invoke setup --plugin herdr-slackbot` (or the *Slack bridge: setup wizard* action in the command palette). Plugin actions cannot read input, so the action opens a new tab and types the wizard command into that tab's shell.
- **Where the bridge runs:** a pane of the workspace `herdr-slack`. The plugin's startup hook starts it when the Herdr server starts (not right after `plugin link`/`install`: the wizard or the `start` action starts it then). It creates the workspace without taking focus if needed, and each start uses a new tab, never typing into an existing pane. Once the new bridge confirms it started, it closes the previous bridge tab, but only if it is verifiably ours and idle (same Herdr server, same tab/pane/terminal ids, a single pane, nothing running in it).
- **Pairing code:** in the bridge pane of the workspace `herdr-slack` and as a Herdr notification.
- **Plugin actions** (output: `herdr plugin log list --plugin herdr-slackbot`):

  ```powershell
  herdr plugin action invoke setup   --plugin herdr-slackbot   # setup wizard (runs in a new tab)
  herdr plugin action invoke start   --plugin herdr-slackbot   # no-op if already running
  herdr plugin action invoke restart --plugin herdr-slackbot   # after editing .env
  herdr plugin action invoke stop    --plugin herdr-slackbot
  herdr plugin action invoke status  --plugin herdr-slackbot   # also shown as a Herdr notification
  ```

- **Key bindings:** the plugin manifest can't declare keys. Add them to your Herdr `config.toml` and run `herdr server reload-config`:

  ```toml
  [[keys.command]]
  key = "prefix+shift+s"
  type = "plugin_action"
  command = "herdr-slackbot.restart"
  description = "restart Slack bridge"
  ```

- **Claude sessions:** found from the agent's process like on the Herdr app; Herdr's own Claude integration (`herdr integration install claude`) is not needed.

## Using it in Slack

Below, `/herdr` stands for your own `SLASH_COMMAND` (e.g. `/herdr-kim`). Use it in the bot DM.

| Command | What it does |
|---|---|
| `/herdr` | Usage |
| `/herdr list` | List agents (by workspace, with status emoji) |
| `/herdr new` | Start a new agent from a modal: workspace, cwd, kind (claude/codex), model, effort, permission mode, name, prompt |
| `/herdr new <workspace> [name=..] [kind=claude\|codex] [model=..] [effort=..] [mode=..] [cwd=..] <prompt>` | Start directly, without the modal |
| `/herdr send` | Send a prompt to a running agent from a modal. Once you pick an agent, the **conversation so far** is shown between Agent and Prompt: your prompts (including ones typed on the PC) and the agent's final answers, oldest at the top. Long answers show only their last ~2500 characters, long prompts their start; older messages that do not fit are summarized as "… N earlier messages not shown". For a working or blocked agent the history is shown with a note. Claude conversations come from the session transcript; for Codex (or when no transcript is found) the agent's **last response** (with time and duration) is shown instead. The Send button on the Home tab opens the same modal. |
| `/herdr send <agent name\|id> <prompt>` | Send directly (Herdr app: the terminal address such as `t7`; Herdr CLI: the pane id) |
| `/herdr status` | Bridge status |
| `/herdr pair <code>` | Link your account in pairing mode (see [Pairing details](#pairing-details)). Rejected once paired. |

- **New agent:** Creates a new tab in the chosen workspace (space) and starts the agent there; the tab is named `slack-<N> <prompt summary>` or after the name you gave. Defaults are claude `--model opus --effort high --permission-mode auto`. Codex runs with `--no-daemon` on the Herdr app.
- **Send rules:** Prompts are sent only when the target is `idle`/`done`.
  - `working` → replies "busy".
  - `blocked` → tells you to answer with the buttons in the thread (`/herdr send`, modal).
- **Threads:** Each agent gets one DM thread.
  - For work sent from Slack, "⏳ started" and the final result arrive as thread replies.
  - Replying in the thread sends the reply to that agent as a prompt. If the agent is waiting for an answer, the reply becomes the typed answer to that question (see [Answering dialogs](#answering-dialogs)).
  - If the agent has exited or a different session now runs in the same terminal, the reply is not forwarded and you get a notice instead.
- **Notifications:** Agents started directly on the PC are covered too.
  - Work that finishes while you aren't looking at it is notified (`done`); work that finishes in the tab you are looking at is not. On the Herdr app this follows the app's own "finished while you weren't looking" state. When the app window is not running, or the agent has no tab (e.g. a sub-agent started with `hc run`), every finished turn counts as unseen.
  - When an agent becomes `blocked`, the dialog is posted with buttons.
  - The 🔕 button in a thread mutes that agent. Results of work sent from Slack arrive regardless of mute.
- **Result text:**
  - For claude, the last answer is read from the session JSONL (the session is found from the agent's process), falling back to parsing the screen. For codex, the end of the screen is sent.
  - For claude (answer read from the JSONL), the message also shows the **conversation since the previous notification in that thread**, above the final answer: prompts typed on the PC or queued while the agent worked, the intermediate answers and `⚙️` lines (background task finished, conversation compacted). So the thread reads as the whole conversation without repeats. A prompt you sent from Slack is not repeated (it is already in the thread). The first message in a thread shows only the latest turn. Blocked-dialog messages carry no history; the next result covers what happened meanwhile, and so does a result after a muted stretch. Codex, or no transcript: only the result.
  - The final answer always stays; if the message runs out of room, older items collapse into "… N earlier messages not shown — View full", and **[View full]** then uploads the whole range untruncated.
  - Over 3000 characters, the text is truncated and a **[View full]** button uploads the full content as a `.md` file.

### Answering dialogs

When an agent becomes `blocked`, the thread gets a **"⚠️ <name> · <workspace> is waiting for your answer"** message. The bridge reads the dialog from the screen and adds a button for each option.

- **Supported:** Claude permission prompts (Bash etc.), AskUserQuestion (single choice, multiple choice, multiple questions, free text), plan approval (ExitPlanMode), the folder trust prompt at startup (Claude, Codex), and Codex command approval.
- **Buttons:** Each option gets a button like `1. Yes`. "Always allow / don't ask again" options show up as buttons too. Multiple choice uses ☐/☑ toggle buttons, and **[Next →]** moves the cursor to the question's Submit row and presses Enter (the next question, or the review screen). **[Esc]** and **[Show screen]** (posts the last 40 lines of the screen to the thread) are always there.
- **Free text:** The "Type something." / "Tell Claude what to change" button opens an input modal. Replying in the thread gives the same answer. Several lines are sent as they are (a line break only breaks the line in the agent's input; it does not submit). In a multiple-choice question the typed text also ticks the "Type something" box; press **[Next →]** to submit the question. Replying to a question without a free-text option gets "This question needs one of the buttons above."
  - Herdr app: herdr-core can type text without pressing Enter only key by key, so in a **multiple-choice** question the typed text may contain only letters, digits and spaces (anything else: you are asked to answer that one on the PC, and nothing is pressed). Single-choice questions and plan feedback take any text, Korean included.
- **Plan approval:** The plan file (`~\.claude\plans\…md`) is read and its text shown; long plans get **[View full]** to upload the whole thing.
- **Safeguards:** Pressing a button first re-checks the agent and the screen. If you already answered on the PC or the question changed in the meantime (including a different plan behind the same approval question), no keys are sent and only the message is updated. Pressing twice still sends the keys once; a button from an older version of the message only gets "That button was out of date".
- **After answering:** If another question follows, the same message is replaced with the new question. When the agent moves on, the message becomes `✅ <choice> — answered from Slack` and the buttons disappear. If you answer on the PC, it becomes `✅ answered on PC` (also after a bridge restart). If the screen doesn't change within 5 seconds, the buttons stay and you get "Could not confirm the answer".
- **When the screen can't be read:** A keypad (`1`–`4`, `↑`, `↓`, Enter, Esc) and the last 15 lines of the screen are shown.
- **If an agent started from Slack asks for folder trust right away:** A thread is created with that question, and the original prompt is sent after you answer. (On the Herdr app Claude reports no status while that screen is up; the bridge recognizes the screen itself.)
- **Codex:** If `~/.codex/config.toml` delegates approvals with `approvals_reviewer = "auto_review"`, Codex never shows an approval screen, so nothing reaches Slack either. That's configuration, not a bug.

### Home tab

Open the bot from the **Apps** list in Slack's sidebar and click the **Home** tab for a dashboard.

- **Top:** Bridge status (uptime, agent count, slash command, last update) and three buttons:
  - **[➕ New Agent]**: opens the `/herdr new` modal.
  - **[📤 Send]**: opens the `/herdr send` modal.
  - **[🔄 Refresh]**: redraws immediately.
- **Below:** Agents by workspace (status emoji · name · kind · status · terminal title). The **[Send]** button on an idle/done agent's row opens the send modal with that agent preselected.
- **Auto refresh:** Redrawn every time you open Home. After you've opened it once, it also refreshes when agent status changes, batched to at most once every 5 seconds.
- **Display limit:** Up to 100 blocks per view; the rest are collapsed into one "N more agents (see the `list` command)" line.
- **Owner only:** If another user opens the Home tab, nothing is published, so they never see agent information.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Slash command doesn't respond | 1. Look at the Slack bridge tab and the bridge's output (**Show**, or `hc read herdr-slackbot`).<br>2. Check `STATE_DIR\bridge.log` (path shown in the tab). |
| No Slack bridge tab | With the Herdr app open, run `scripts\setup.ps1 -Backend hc` again: it reinstalls the mod and recreates the space herdr-slack / **Slack bridge** tab. Then check `herdr-app status` for mod errors. |
| The bridge didn't start with the app | The Slack bridge tab must be in the window (it may be in the background) and the tokens must be set. Press **Start**. |
| `a bridge terminal (tN) is still running but holds no lock` | Something else runs under the name `herdr-slackbot`. Look at it with `hc read tN`; end it with `hc kill tN` if it is a stale bridge. |
| `missing settings in ...` | Fill in both tokens (`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`) in `.env` and restart, or use **Setup**. |
| "🔗 This Herdr bridge is not paired yet" | Pairing mode. Send `/herdr pair <code>` with the code from the notification / **Show**. |
| "❌ Wrong pairing code" / "⌛ That code expired" | Use the **most recent** code. The code changes after 5 wrong attempts or 15 minutes. |
| "⏳ Too many wrong codes from you" | You got it wrong 5 times within 10 minutes. Wait the indicated time, then try again with the **most recent** code. |
| "You are paired, but the bridge could not start" | Your account was saved, but owner-only mode failed to start. Check the bridge's output and restart it. |
| `Slack connection failed: invalid_auth` | Check that the `xoxb`/`xapp` tokens are correct, the app is installed to the workspace, and the App-Level Token has `connections:write`. |
| `/herdr-...` gives "dispatch_failed" or another app answers | Check that the bridge is running. Also check whether another app uses a command with the same name (names must be unique across the workspace). |
| "⛔ This Herdr bridge only accepts requests from its owner." | It is paired with a different account. Clear `SLACK_OWNER_USER_ID` in `.env`, restart, and pair again. |
| Can't type in the DM window | Check the App Home messages tab setting ([Create the Slack app](#create-the-slack-app-from-the-manifest), step 6). |
| `another bridge is running (pid N)` | It's already running. Check the status and restart it if needed. |
| Wizard stops with "needs a terminal" | It was run somewhere that can't take input. Use **Setup** or run it from a terminal. |
| Broken venv | Delete `.venv` in the repo folder and run `scripts\setup.ps1` again. |
| `cannot verify the running bridge` | The running bridge couldn't be verified, so it wasn't stopped. End it yourself (Herdr app: `hc kill herdr-slackbot`; Herdr CLI: Ctrl+C in its pane). |
| Herdr app: `unavailable` / cannot open the hc pipe | Outside an hc terminal the pipe name is derived from your Windows user name (`\\.\pipe\herdr-core-<user>-default.sock`). If yours differs, set `HC_SOCKET_PATH` in `.env`. |
| Herdr CLI: a plugin action seems to do nothing | Look at stdout/stderr in `herdr plugin log list --plugin herdr-slackbot`. |
