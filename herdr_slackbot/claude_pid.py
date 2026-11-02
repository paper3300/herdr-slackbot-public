"""Claude Code session id from a process id (both backends).

Claude Code writes `~/.claude/sessions/<pid>.json` (`{"pid", "sessionId", "cwd", ...}`) for each
running interactive session and updates `sessionId` when the session changes (`/clear`). Herdr's
old CLI reported the session only with its Claude integration (hooks in ~/.claude), and herdr-core
(`hc`) does not report it at all, so the bridge finds it from the agent's process instead:

    pane / terminal -> foreground pid -> (that pid or a descendant) -> sessions/<pid>.json

The pid found for a terminal is cached by the caller; the json file is re-read on every lookup
(cheap) so a `/clear` shows up as a new session id.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterable

from . import procinfo

MAX_DEPTH = 3  # shell -> (cmd shim) -> claude.exe


def sessions_dir(env: dict | None = None) -> Path:
    env = os.environ if env is None else env
    base = env.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "sessions"


def read_session_file(pid: int, directory: Path | None = None) -> dict | None:
    path = (directory or sessions_dir()) / f"{int(pid)}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("sessionId"):
        return None
    return data


def find_session_pid(pids: Iterable[int], directory: Path | None = None,
                     children: Callable[[int], list | None] = procinfo.child_processes,
                     max_depth: int = MAX_DEPTH) -> int | None:
    """The first of `pids` (or of their descendants, breadth first) that has a sessions file."""
    directory = directory or sessions_dir()
    frontier = [int(p) for p in pids if p]
    seen: set[int] = set()
    for _ in range(max_depth + 1):
        nxt: list[int] = []
        for pid in frontier:
            if pid in seen:
                continue
            seen.add(pid)
            if read_session_file(pid, directory) is not None:
                return pid
            for child_pid, _name in children(pid) or []:
                nxt.append(int(child_pid))
        if not nxt:
            break
        frontier = nxt
    return None


class SessionLocator:
    """Caches the Claude pid per terminal identity; reads the session id fresh each time."""

    def __init__(self, directory: Path | None = None,
                 children: Callable[[int], list | None] = procinfo.child_processes):
        self.directory = directory
        self.children = children
        self._pids: dict[str, int] = {}

    def session_for(self, key: str, pids: Callable[[], Iterable[int]]) -> str | None:
        """Session id for the terminal `key` (e.g. its terminal id). `pids` is called only when the
        Claude pid of `key` is not cached yet (or its sessions file disappeared)."""
        directory = self.directory or sessions_dir()
        pid = self._pids.get(key)
        if pid is not None:
            data = read_session_file(pid, directory)
            if data is not None:
                return str(data["sessionId"])
            self._pids.pop(key, None)
        try:
            candidates = list(pids())
        except Exception:  # a failed lookup just means "unknown for now"
            return None
        pid = find_session_pid(candidates, directory, self.children)
        if pid is None:
            return None
        self._pids[key] = pid
        data = read_session_file(pid, directory)
        return str(data["sessionId"]) if data else None

    def forget(self, keep: Iterable[str]) -> None:
        """Drop cached pids of terminals that are gone."""
        keep = set(keep)
        for key in list(self._pids):
            if key not in keep:
                self._pids.pop(key, None)  # another thread may have dropped it meanwhile
