# Dual backend: Herdr CLI + Herdr app (2026-11-02)

The PC switched from the Herdr CLI (`herdr`, TUI + plugin) to the Herdr desktop app (`herdr-app`
0.1.11 + herdr-core `hc` 0.1.16). The old `herdr` binary was gone, so the bridge could not run.
Decision: support both (`HERDR_BACKEND=auto|herdr|hc`). Design notes: `docs/SPEC.md` → "Two Herdr
backends".

## User decisions
1. Herdr app side ships an app mod (Slack bridge tab: autostart, Start/Restart/Stop/Setup, toasts);
   the CLI side keeps `herdr-plugin.toml`.
2. Herdr app config dir: `%APPDATA%\herdr-slackbot` (CLI keeps the plugin config dir).
3. D9 on the app: notify a PC agent's `done` only when the app shows it unseen (`herdr-app ls` still
   `done`); seen (`idle`) → no DM; app not running → notify.

## Changes
- `hc_client.py` (new): JSON-RPC transport, `HcClient` adapter (same interface/dict shapes as
  `HerdrClient`), `AppView` (`herdr-app ls` cache, tab lookup, `do`), `EventConverter`.
- `claude_pid.py` (new): Claude session id from the process (`~/.claude/sessions/<pid>.json`), used
  by both backends (`HerdrClient` fills `agent_session` when Herdr reports none).
- `backend.py` (new): `make_client`, notifications (CLI: `herdr notification show`; app:
  `STATE_DIR\notify.json` for the mod), per-backend hint texts.
- `config.py`: `HERDR_BACKEND`, `detect_backend`, `hc_config_dir`, `HC_SOCKET_PATH`, `HC_BIN`,
  `HERDR_APP_BIN`.
- `plugin.py`: `HcOps` (bridge = hc terminal `herdr-slackbot`), `make_ops`, backend-aware config dir
  discovery, `status --json`, runtime record from `HC_TERMINAL_*`.
- `bridge.py`: dialog free text uses `submit_text` when the client `paste_submits`; result header
  without an empty workspace segment (agents with no space).
- `setup_cmd.py` / `wizard.py`: per-backend instructions; `setup` on the app installs the mod +
  `config.json`.
- `herdr-app/mods/herdr-slackbot` (new): the panel, shown in its own tab (`herdr-app check` passes).
- `scripts/*.ps1`: `-Backend`.
- Tests: `tests/test_hc_client.py`, `tests/test_hc_ops.py`, one bridge dialog test for the app path;
  `conftest.py` pins existing tests to the CLI backend (pytest may run inside an hc terminal).

## Verified live (no real Slack yet)
- Herdr CLI 0.9.5 (a temporary, isolated install, since removed): all API
  methods/events used exist; real `Bridge` + event manager with a fake Slack transport: PC agent
  `done` → ✅ DM with the conversation from the session JSONL (session id from the process), thread
  reply → prompt → ⏳ + ✅ in the thread.
- Herdr app: read-only mapping of all live agents (sessions found for every Claude agent, including
  ones inside PowerShell; sub-agents get their parent's space; `done`/`idle` follows the app); start in
  a space + tab rename; prompt/events/read; AskUserQuestion answered with keys + `submit_text`
  (Korean); prompt while blocked → `agent_blocked`; same E2E as above with a hidden PC agent;
  `HcOps` launch → bridge terminal → "not configured" exit → reservation acked.

## Review round 1 (independent reviewer, 13 findings) — fixed
- High: restart on hc stopped the bridge but never started it again. The old bridge's exit path
  waited for the lifecycle lock that the restarter held, so its terminal stayed live. Now: an
  already-acknowledged start skips that lock (`__main__._release_launch`), and `HcOps` waits up to
  10 s for a lock-less bridge terminal to end.
- hc `error` status → treated as a finished turn (`done`).
- `terminal.send` with `started: false` → `agent_prompt_stalled` (watch, never resend). No lookup
  after the text went in.
- Claude reports **no status** on hc while its folder-trust screen is up (verified live): the start
  now detects the trust screen while waiting to settle and opens the startup dialog.
- A cached app snapshot older than the turn's end is read again, so a fresh `done` is not taken as
  seen.
- Multi-select text the app cannot type is refused before any key is pressed (`can_type`).
- `name_taken` → `agent_name_taken`. Booting/placeholder ids are pruned. `missed` events re-seed the
  converter. `OSError` on subscribe → unavailable. `SessionLocator.forget` race fixed.
- Config-dir discovery falls back to the old CLI's dir when hc was only guessed and has no `.env`.
  The plugin manifest pins `-Backend herdr`.
- Kept as a limitation: outside an hc terminal, the hc pipe name is derived from `USERNAME`
  (`\\.\pipe\herdr-core-<user>-default.sock`, matches this PC). Set `HC_SOCKET_PATH` if it differs.

## Real Slack on the Herdr app (2026-11-02, user)
- `setup.ps1 -Backend hc` installed the mod. The shipped `main` layout is read-only, so the panel does
  not dock there; it now lives in its own tab: space `herdr-slack` → tab **Slack bridge**, created by
  setup (`setup_cmd.ensure_app_tab`). The mod's `mod.json` is `place: none`. The bridge terminal shows
  in the same space.
- Wizard (Setup button) → tokens → pairing: OK. `/herdr list`, new agent from Slack (tab named in the
  space), thread reply, PC agent notifications, dialog answers: OK (checklist 1–5).
- Restart from the panel: stop request → new bridge 4 s later, ready again; old terminal removed,
  start acknowledged (verified in `bridge.log`).
- Seen in the log, harmless: `updating the send modal failed: not_found` (the send modal was closed
  before its history update; existing behavior).

## Still unverified
- Multi-select "Type something" on the app (ASCII-only path) against a real dialog.
- The Herdr CLI path against real Slack (only with the real bridge + fake Slack, see above).

## Cleanup (2026-11-02, done)
The temporary Herdr CLI and every old Herdr CLI leftover were removed: the temporary server was
stopped, and `%APPDATA%\herdr`, `%LOCALAPPDATA%\herdr` and `D:\Git\_herdr-cli-temp` were deleted
(no Herdr integration had been installed). Test terminals and probe files were removed too. The Herdr
CLI backend stays supported in the code.
