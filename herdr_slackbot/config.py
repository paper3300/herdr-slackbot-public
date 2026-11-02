"""Configuration: `.env` loading and defaults.

Two Herdr backends are supported (HERDR_BACKEND, see `detect_backend`):
- `herdr`: the old Herdr CLI/TUI. `.env` lives in the plugin config dir (`HERDR_PLUGIN_CONFIG_DIR`,
  see `herdr plugin config-dir <id>`).
- `hc`: the Herdr desktop app (herdr-core, `hc`). `.env` lives in `%APPDATA%\\herdr-slackbot`.
The launcher passes the chosen dir as `--config-dir` (exported as HERDR_PLUGIN_CONFIG_DIR inside
this process). When nothing is set (running from a checkout), the repository root is used.

Real process environment variables win over values from the `.env` file.
"""

from __future__ import annotations

import getpass
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

PLUGIN_ID = "herdr-slackbot"
ENV_FILE_NAME = ".env"
REPO_ROOT = Path(__file__).resolve().parent.parent

BACKEND_HERDR = "herdr"  # old Herdr CLI / TUI (plugin manifest, named pipe API)
BACKEND_HC = "hc"  # Herdr desktop app: herdr-core (`hc`) + herdr-app
BACKENDS = (BACKEND_HERDR, BACKEND_HC)
_BACKEND_ALIASES = {"herdr": BACKEND_HERDR, "cli": BACKEND_HERDR, "tui": BACKEND_HERDR,
                    "hc": BACKEND_HC, "app": BACKEND_HC, "herdr-app": BACKEND_HC, "herdr-core": BACKEND_HC}


def normalize_backend(value: str) -> str:
    backend = _BACKEND_ALIASES.get((value or "").strip().lower())
    if backend is None:
        raise ConfigError(f"HERDR_BACKEND {value!r} must be auto, herdr or hc")
    return backend


def detect_backend(env: Mapping[str, str] | None = None,
                   which: Callable[[str], str | None] = shutil.which) -> str:
    """HERDR_BACKEND if set (not `auto`); else where we run (inside an old Herdr pane / plugin
    command, or inside an hc terminal); else which program is installed (hc first)."""
    env = os.environ if env is None else env
    explicit = (env.get("HERDR_BACKEND") or "").strip()
    if explicit and explicit.lower() != "auto":
        return normalize_backend(explicit)
    if env.get("HERDR_SOCKET_PATH") or env.get("HERDR_PLUGIN_ROOT") or env.get("HERDR_PANE_ID"):
        return BACKEND_HERDR
    if env.get("HC_TERMINAL_ID") or env.get("HC_TERMINAL_SOCKET"):
        return BACKEND_HC
    if which("hc") or which("herdr-app"):
        return BACKEND_HC
    return BACKEND_HERDR


def hc_config_dir(env: Mapping[str, str] | None = None) -> Path:
    """The hc backend's config dir: %APPDATA%\\herdr-slackbot (~/.config/herdr-slackbot elsewhere)."""
    env = os.environ if env is None else env
    appdata = env.get("APPDATA")
    return Path(appdata) / PLUGIN_ID if appdata else Path.home() / ".config" / PLUGIN_ID

# Slack slash command names: lowercase, max 32 chars including the leading "/".
SLASH_COMMAND_MAX_LEN = 32
_SLASH_CHARS_RE = re.compile(r"[^a-z0-9_-]+")

SETTING_KEYS = (
    "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_OWNER_USER_ID",
    "SLASH_COMMAND", "BOT_DISPLAY_NAME", "STATE_DIR", "LOG_LEVEL",
    "RESULT_MAX_CHARS", "FALLBACK_LINES", "READ_LINES",
    "HERDR_SOCKET_PATH", "HERDR_BIN", "HERDR_BACKEND", "HC_SOCKET_PATH", "HC_BIN", "HERDR_APP_BIN",
    "BRIDGE_WORKSPACE", "START_TIMEOUT_MS", "CODEX_PROMPT_DELAY", "STALL_WAIT",
)


class ConfigError(Exception):
    pass


# Slack tokens in free text (log lines, exception messages).
SECRET_RE = re.compile(r"xox[abpers]-[A-Za-z0-9-]+|xapp-[A-Za-z0-9-]+")


def redact(text: str, *secrets: str) -> str:
    """Hide Slack tokens in `text`: the exact `secrets` first (they may contain characters the
    pattern does not cover), then anything that looks like a token."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return SECRET_RE.sub("[redacted]", text)


def parse_env_text(text: str) -> dict[str, str]:
    """Parse a minimal `.env` file: KEY=VALUE lines, `#` comments, optional quotes, `export ` prefix."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            # Strip inline comments only for unquoted values (" #" separator).
            hash_at = value.find(" #")
            if hash_at >= 0:
                value = value[:hash_at].rstrip()
        values[key] = value
    return values


def load_env_file(path: Path) -> dict[str, str]:
    try:
        return parse_env_text(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}


def sanitize_username(name: str) -> str:
    """Lowercase and reduce a Windows username to Slack-command-safe characters."""
    cleaned = _SLASH_CHARS_RE.sub("-", (name or "").lower())
    cleaned = re.sub(r"[-_]{2,}", "-", cleaned).strip("-_")
    return cleaned or "user"


def current_username(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    name = env.get("USERNAME") or env.get("USER")
    if not name:
        try:
            name = getpass.getuser()
        except Exception:  # getpass raises various errors when no user is resolvable
            name = ""
    return name or "user"


def default_slash_command(username: str) -> str:
    cmd = "/herdr-" + sanitize_username(username)
    return cmd[:SLASH_COMMAND_MAX_LEN].rstrip("-_")


def normalize_slash_command(value: str) -> str:
    """Validate a configured slash command, adding the leading `/` if missing."""
    cmd = value.strip().lower()
    if not cmd.startswith("/"):
        cmd = "/" + cmd
    body = cmd[1:]
    if not body or _SLASH_CHARS_RE.search(body):
        raise ConfigError(f"SLASH_COMMAND {value!r} may only contain a-z, 0-9, '-' and '_'")
    if len(cmd) > SLASH_COMMAND_MAX_LEN:
        raise ConfigError(f"SLASH_COMMAND {value!r} is longer than {SLASH_COMMAND_MAX_LEN} characters")
    return cmd


def default_bot_display_name(username: str) -> str:
    return f"Herdr ({username})"


def resolve_config_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    configured = env.get("HERDR_PLUGIN_CONFIG_DIR")
    return Path(configured) if configured else REPO_ROOT


def _float(values: Mapping[str, str], key: str, default: float) -> float:
    raw = values.get(key)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


def _int(values: Mapping[str, str], key: str, default: int) -> int:
    raw = values.get(key)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Config:
    config_dir: Path
    state_dir: Path
    slash_command: str
    bot_display_name: str
    username: str
    slack_bot_token: str = field(default="", repr=False)
    slack_app_token: str = field(default="", repr=False)
    slack_owner_user_id: str = ""
    herdr_socket_path: str = ""
    herdr_bin: str = "herdr"
    backend: str = BACKEND_HERDR
    hc_socket_path: str = ""
    hc_bin: str = "hc"
    herdr_app_bin: str = "herdr-app"
    log_level: str = "INFO"
    result_max_chars: int = 3000
    fallback_lines: int = 40
    read_lines: int = 200
    bridge_workspace: str = "herdr-slack"  # D12: the bridge's own workspace (hidden from `new`)
    start_timeout_ms: int = 60000
    codex_prompt_delay: float = 3.0  # seconds to let Codex finish initializing before the first prompt
    stall_wait: float = 20.0  # seconds to watch for activity after agent_prompt_stalled

    @property
    def env_file(self) -> Path:
        return self.config_dir / ENV_FILE_NAME

    def missing_slack_settings(self) -> list[str]:
        """Settings the bridge cannot start without (the owner is optional: see `needs_pairing`)."""
        missing = []
        if not self.slack_bot_token:
            missing.append("SLACK_BOT_TOKEN")
        if not self.slack_app_token:
            missing.append("SLACK_APP_TOKEN")
        return missing

    @property
    def needs_pairing(self) -> bool:
        """No owner yet: the bridge starts in pairing mode (see pairing.py)."""
        return not self.slack_owner_user_id


def load_config(env: Mapping[str, str] | None = None, config_dir: Path | None = None) -> Config:
    env = dict(os.environ if env is None else env)
    config_dir = config_dir or resolve_config_dir(env)
    values = load_env_file(config_dir / ENV_FILE_NAME)
    # Process environment overrides the file.
    values.update({k: env[k] for k in SETTING_KEYS if env.get(k)})

    username = current_username(env)
    slash = values.get("SLASH_COMMAND") or ""
    slash_command = normalize_slash_command(slash) if slash else default_slash_command(username)
    state_dir_raw = values.get("STATE_DIR") or ""
    state_dir = Path(state_dir_raw) if state_dir_raw else config_dir / "state"
    if not state_dir.is_absolute():
        state_dir = config_dir / state_dir

    return Config(
        config_dir=config_dir,
        state_dir=state_dir,
        slash_command=slash_command,
        bot_display_name=values.get("BOT_DISPLAY_NAME") or default_bot_display_name(username),
        username=username,
        slack_bot_token=values.get("SLACK_BOT_TOKEN", ""),
        slack_app_token=values.get("SLACK_APP_TOKEN", ""),
        slack_owner_user_id=values.get("SLACK_OWNER_USER_ID", ""),
        herdr_socket_path=values.get("HERDR_SOCKET_PATH", ""),
        herdr_bin=values.get("HERDR_BIN") or "herdr",
        backend=detect_backend({**env, "HERDR_BACKEND": values.get("HERDR_BACKEND", "")}),
        hc_socket_path=values.get("HC_SOCKET_PATH", ""),
        hc_bin=values.get("HC_BIN") or "hc",
        herdr_app_bin=values.get("HERDR_APP_BIN") or "herdr-app",
        log_level=(values.get("LOG_LEVEL") or "INFO").upper(),
        result_max_chars=_int(values, "RESULT_MAX_CHARS", 3000),
        fallback_lines=_int(values, "FALLBACK_LINES", 40),
        read_lines=_int(values, "READ_LINES", 200),
        bridge_workspace=values.get("BRIDGE_WORKSPACE") or "herdr-slack",
        start_timeout_ms=_int(values, "START_TIMEOUT_MS", 60000),
        codex_prompt_delay=_float(values, "CODEX_PROMPT_DELAY", 3.0),
        stall_wait=_float(values, "STALL_WAIT", 20.0),
    )
