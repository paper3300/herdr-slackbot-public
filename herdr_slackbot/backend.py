"""Backend selection: the Herdr client and desktop notifications for the configured backend.

- `herdr` (old CLI/TUI): `HerdrClient` over Herdr's named pipe; notifications via
  `herdr notification show`.
- `hc` (Herdr desktop app): `HcClient` over herdr-core's pipe; hc has no notification API, so
  notifications are written to `STATE_DIR/notify.json`, which the herdr-slackbot app mod
  (herdr-app/mods/herdr-slackbot) watches and shows as a toast.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from .config import BACKEND_HC, PLUGIN_ID, Config

log = logging.getLogger(__name__)

NOTIFY_FILE = "notify.json"

# What to tell people, per backend (wizard, setup, error messages).
HINTS = {
    "herdr": {
        "restart": f"herdr plugin action invoke restart --plugin {PLUGIN_ID}",
        "status": f"herdr plugin action invoke status --plugin {PLUGIN_ID}",
        "setup": f"herdr plugin action invoke setup --plugin {PLUGIN_ID}     (opens a new Herdr tab with the wizard)",
        "code_where": "the herdr-slack pane",
        "bridge_where": "the bridge pane in workspace herdr-slack",
        "starting": "starting the bridge in Herdr workspace herdr-slack ...",
        "restart_or": "(or restart Herdr)",
    },
    "hc": {
        "restart": "Restart in the Herdr app's Slack bridge tab, or: scripts\\herdr-slackbot.ps1 restart",
        "status": "the Herdr app's Slack bridge tab, or: scripts\\herdr-slackbot.ps1 status",
        "setup": "Setup in the Herdr app's Slack bridge tab (opens a new tab with the wizard)",
        "code_where": "a Herdr app notification",
        "bridge_where": "the bridge terminal (Show in the Slack bridge tab, or: hc read herdr-slackbot)",
        "starting": "starting the bridge as the Herdr app terminal herdr-slackbot ...",
        "restart_or": "(or restart the Herdr app)",
    },
}


def hints(backend: str) -> dict[str, str]:
    return HINTS.get(backend, HINTS["herdr"])


def make_client(cfg: Config):
    if cfg.backend == BACKEND_HC:
        from .hc_client import HcClient

        return HcClient.from_env(cfg.hc_socket_path or None, cfg.herdr_app_bin)
    from .herdr_client import HerdrClient

    return HerdrClient.from_env(cfg.herdr_socket_path or None, cfg.herdr_bin)


def write_notification(state_dir: Path, title: str, body: str, level: str = "info") -> dict:
    """For the app mod: the latest notification (it shows each new `id` once)."""
    from .state import atomic_write_text

    note = {"id": uuid.uuid4().hex, "title": title, "body": body, "level": level, "at": time.time()}
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(state_dir / NOTIFY_FILE, json.dumps(note, ensure_ascii=False, indent=1))
    return note


def notify(backend: str, state_dir: Path, body: str, title: str = "herdr-slackbot",
           herdr_bin: str | None = None, sound: str | None = None, level: str = "info") -> None:
    """Best effort desktop notification on the active backend. Never raises."""
    try:
        if backend == BACKEND_HC:
            write_notification(state_dir, title, body, level)
            return
        from .plugin import HerdrCli

        args = ["notification", "show", title, "--body", body]
        if sound:
            args += ["--sound", sound]
        HerdrCli(herdr_bin, timeout=10).run(*args)
    except Exception as exc:  # notifications are a convenience
        log.warning("notification failed: %s", exc)
