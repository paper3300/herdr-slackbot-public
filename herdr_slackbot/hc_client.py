"""herdr-core (`hc`) backend: the Herdr desktop app's terminal runtime.

`HcClient` implements `HerdrClient`'s methods over hc's JSON-RPC API and returns dicts shaped like
the old `herdr` CLI's (agent / workspace / pane), so the bridge, event manager and Slack UI run
unchanged on either backend. Mapping (verified against hc 0.1.16 / herdr-app 0.1.11):

    herdr (old CLI)              hc / herdr app
    agent, pane_id               terminal address (`t7`, `vps/t7`) of a terminal reporting status
    terminal_id                  the same address (stable for the core's lifetime)
    agent                        OSC 7501 `app` ("claude-code" -> "claude", "codex")
    agent_status                 OSC 7501 state; `done` becomes `idle` when the app shows it as
                                 seen (see AppView): the old CLI's `done` meant "finished unseen"
    state_change_seq             `status_ms` (changes whenever the status word changes)
    agent_session                Claude session id from the process (claude_pid.py)
    workspace                    app space (label `herdr.space`), named via `herdr-app ls`
    tab.create + agent.start     one `terminal.run` labelled into the space (the app adds a tab)
    agent.prompt                 `terminal.send` (paste + Enter)
    agent.send_keys              `terminal.keys`
    pane.send_text (no Enter)    `terminal.keys` per character for plain ASCII only (see send_text)
    events.subscribe             one hc stream per subscription, converted to herdr-style events

Transport: JSON-RPC 2.0, one message per line on the hc named pipe (no `hello` needed).
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from typing import Any, Callable, Iterator, Sequence

from .herdr_client import (
    EventStream,
    HerdrClient,
    HerdrError,
    HerdrOutcomeUnknown,
    HerdrUnavailable,
    PipeTransport,
    _read_line,
)

log = logging.getLogger(__name__)

APP_KINDS = {"claude-code": "claude", "claude": "claude", "codex": "codex"}
SPACE_LABEL = "herdr.space"
TAB_LABEL = "herdr.tab"
WHERE_LABEL = "where"
OWNER_LABEL = "herdr-slackbot"  # terminals the bridge started (value: "agent" / "bridge")
PENDING_PREFIX = "pending:"
_GLYPHS_RE = re.compile(r"^[^\w\s]+\s*")  # leading status glyphs in titles ("✳ ", "⠼ ")
# Keys `terminal.keys` accepts as single characters (hc rejects anything else, e.g. Hangul).
_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


def default_socket_path(env: dict | None = None) -> str:
    """hc's pipe: HC_TERMINAL_SOCKET inside hc terminals, else the default session's name."""
    env = os.environ if env is None else env
    if env.get("HC_TERMINAL_SOCKET"):
        return env["HC_TERMINAL_SOCKET"]
    user = env.get("USERNAME") or env.get("USER") or "user"
    session = env.get("HC_SESSION") or "default"
    return f"\\\\.\\pipe\\herdr-core-{user}-{session}.sock"


def map_state(state: str | None) -> str:
    """hc status word -> the bridge's. `error` ends a turn (the agent stopped with an error), which the
    bridge treats like a finished turn; no word yet -> unknown."""
    if not state:
        return "unknown"
    return "done" if state == "error" else state


def agent_kind(app: str | None) -> str | None:
    if not app:
        return None
    return APP_KINDS.get(app, app)


def strip_title(title: str) -> str:
    return _GLYPHS_RE.sub("", title or "").strip()


# --- transport ------------------------------------------------------------------------

class HcTransport:
    """JSON-RPC 2.0 over hc's named pipe; a fresh connection per request (like PipeTransport)."""

    def __init__(self, socket_path: str):
        self.pipe = PipeTransport(socket_path)
        self.path = self.pipe.path
        self._ids = itertools.count(1)

    def _send(self, handle, method: str, params: dict) -> int:
        req_id = next(self._ids)
        payload = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
                             ensure_ascii=False)
        handle.write(payload.encode("utf-8") + b"\n")
        return req_id

    @staticmethod
    def _unwrap(response: dict, method: str) -> dict:
        if "error" in response:
            err = response.get("error") or {}
            kind = (err.get("data") or {}).get("kind") or str(err.get("code", "unknown"))
            raise HerdrError(str(kind), str(err.get("message", "")))
        if "result" not in response:
            raise HerdrError("bad_response", f"{method}: response has neither result nor error")
        return response["result"] if response["result"] is not None else {}

    def _read_reply(self, handle, buf: bytearray, req_id: int, method: str) -> dict:
        while True:
            line = _read_line(handle, buf)
            if not line:
                raise HerdrOutcomeUnknown(f"{method}: connection closed without a response")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except ValueError as exc:
                raise HerdrOutcomeUnknown(f"{method}: undecodable response") from exc
            if isinstance(msg, dict) and msg.get("id") == req_id:
                return msg

    def request(self, method: str, params: dict | None = None) -> dict:
        handle = self.pipe._open()  # raises HerdrUnavailable: nothing was sent
        try:
            try:
                req_id = self._send(handle, method, params or {})
                msg = self._read_reply(handle, bytearray(), req_id, method)
            except OSError as exc:
                raise HerdrOutcomeUnknown(f"{method}: pipe failed after sending: {exc}") from exc
        finally:
            try:
                handle.close()
            except OSError:
                pass
        return self._unwrap(msg, method)

    def open_stream(self, method: str, params: dict) -> EventStream:
        handle = self.pipe._open()
        try:
            buf = bytearray()
            req_id = self._send(handle, method, params)
            ack = self._unwrap(self._read_reply(handle, buf, req_id, method), method)
        except HerdrOutcomeUnknown as exc:
            handle.close()
            raise HerdrUnavailable(exc.message) from exc
        except OSError as exc:  # subscribing changes nothing: safe to report as unavailable
            handle.close()
            raise HerdrUnavailable(f"{method}: {exc}") from exc
        except BaseException:
            handle.close()
            raise
        return EventStream(handle, buf, ack)


class ConvertedStream:
    """Wraps an hc event stream; yields herdr-style `{"event", "data"}` envelopes."""

    def __init__(self, stream, convert: Callable[[dict], list[dict]]):
        self._stream = stream
        self._convert = convert
        self.ack = getattr(stream, "ack", None)

    @property
    def closed(self) -> bool:
        return getattr(self._stream, "closed", False)

    def close(self) -> None:
        self._stream.close()

    def __iter__(self) -> Iterator[dict]:
        for msg in self._stream:
            if not isinstance(msg, dict):
                continue
            params = msg.get("params") or {}
            if msg.get("method") == "event":
                envelopes = self._convert(params)
            elif isinstance(params, dict) and ("terminals" in params or msg.get("method") == "missed"):
                # Fell behind: hc sends `missed` and a fresh snapshot. Re-seed and re-check everything.
                envelopes = self._convert.reseed(params)
            else:
                continue  # heartbeats and anything else
            for envelope in envelopes:
                yield envelope


# --- the app's view (spaces, and whether a finished agent was seen) ------------------------

class AppView:
    """`herdr-app ls`, cached briefly. None when the app is not running / not installed."""

    def __init__(self, app_bin: str = "herdr-app", ttl: float = 1.0, timeout: float = 5.0,
                 runner: Callable[..., Any] = subprocess.run, clock: Callable[[], float] = time.monotonic):
        self.app_bin = app_bin
        self.ttl = ttl
        self.timeout = timeout
        self.runner = runner
        self.clock = clock
        self._lock = threading.Lock()
        self._at = -1e18
        self._data: dict | None = None
        self.taken_at = 0.0  # wall clock (seconds) just before the cached snapshot was read

    def snapshot(self, fresh: bool = False) -> dict | None:
        with self._lock:
            if not fresh and self.clock() - self._at < self.ttl:
                return self._data
            taken = time.time()
            self._data = self._load()
            self._at = self.clock()
            self.taken_at = taken
            return self._data

    def _load(self) -> dict | None:
        try:
            proc = self.runner([self.app_bin, "ls"], capture_output=True, timeout=self.timeout,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.debug("herdr-app ls failed: %s", exc)
            return None
        if proc.returncode != 0:
            return None
        try:
            data = json.loads(proc.stdout.decode("utf-8", "replace"))
        except ValueError:
            return None
        if not isinstance(data, dict) or "spaces" not in data:
            return None
        return data

    @staticmethod
    def statuses(data: dict | None) -> dict[str, str | None]:
        """terminal address -> the app's status word for it (agents shown in a pane)."""
        out: dict[str, str | None] = {}
        for space in (data or {}).get("spaces") or []:
            for tab in space.get("tabs") or []:
                for term in tab.get("terminals") or []:
                    if term.get("terminal"):
                        out[term["terminal"]] = term.get("status")
        return out

    @staticmethod
    def tab_of(data: dict | None, address: str) -> str | None:
        """The id of the tab showing terminal `address` (the app does not label terminals with it)."""
        for space in (data or {}).get("spaces") or []:
            for tab in space.get("tabs") or []:
                if any(t.get("terminal") == address for t in tab.get("terminals") or []):
                    return tab.get("id")
        return None

    def run(self, command: str, args: dict) -> dict | None:
        """`herdr-app do <command> <json>`; None when it failed."""
        try:
            proc = self.runner([self.app_bin, "do", command, json.dumps(args, ensure_ascii=False)],
                               capture_output=True, timeout=self.timeout,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired):
            return None
        try:
            data = json.loads(proc.stdout.decode("utf-8", "replace") or "null")
        except ValueError:
            return None
        if proc.returncode != 0 or not isinstance(data, dict) or data.get("error"):
            return None
        return data


# --- the client -------------------------------------------------------------------------

class HcClient(HerdrClient):
    backend = "hc"
    # `send_text` cannot type arbitrary text without Enter; `submit_text` pastes and submits.
    paste_submits = True

    def __init__(self, transport, app: AppView | None = None, sessions=None,
                 sleep: Callable[[float], None] = time.sleep):
        super().__init__(transport, sessions)
        self.app = app
        self.sleep = sleep
        self._pending: dict[str, dict] = {}  # create_tab placeholders -> where to start the agent
        self._started: dict[str, str] = {}   # placeholder -> address of the terminal started for it
        self._booting: set[str] = set()      # terminals we started that have not reported status yet

    @classmethod
    def from_env(cls, socket_path: str | None = None, herdr_bin: str = "herdr-app") -> "HcClient":
        from .claude_pid import SessionLocator

        return cls(HcTransport(socket_path or default_socket_path()), AppView(herdr_bin or "herdr-app"),
                   SessionLocator())

    # -- helpers
    def _resolve(self, target: str) -> str:
        return self._started.get(target, target)

    def _terminals(self) -> list[dict]:
        return self.request("terminal.list", {}).get("terminals") or []

    def _get_terminal(self, target: str) -> dict:
        try:
            return self.request("terminal.get", {"terminal": self._resolve(target)})
        except HerdrError as exc:
            if exc.code in ("not_found", "needs_target", "machine_unknown"):
                raise HerdrError("agent_not_found", exc.message) from exc
            raise

    def _app_statuses(self, terminals: Sequence[dict]) -> dict[str, str | None] | None:
        if self.app is None:
            return None
        data = self.app.snapshot()
        if data is None:
            return None
        statuses = AppView.statuses(data)
        done = [t for t in terminals if (t.get("status") or {}).get("state") in ("done", "error")]
        # A cached snapshot older than a turn's end may still show the previous (seen) `idle`.
        if any(float(t.get("status_ms") or 0) / 1000.0 >= self.app.taken_at for t in done):
            data = self.app.snapshot(fresh=True)
            statuses = AppView.statuses(data)
        # The app may lag the core by a moment right after a turn ends: one more look.
        if any(statuses.get(t.get("address")) in ("working", "blocked") for t in done):
            self.sleep(0.3)
            statuses = AppView.statuses(self.app.snapshot(fresh=True))
        return statuses

    def _space_of(self, term: dict, by_address: dict[str, dict]) -> str:
        labels = term.get("labels") or {}
        if labels.get(SPACE_LABEL):
            return labels[SPACE_LABEL]
        parent = by_address.get(term.get("parent") or "")
        if parent is not None:
            return (parent.get("labels") or {}).get(SPACE_LABEL) or ""
        return ""

    def _is_agent(self, term: dict) -> bool:
        if term.get("state") != "live":
            return False
        if (term.get("status") or {}).get("state"):
            return True
        return term.get("address") in self._booting

    def _to_agent(self, term: dict, app_statuses: dict | None, by_address: dict[str, dict]) -> dict:
        address = term.get("address") or ""
        status = term.get("status") or {}
        state = map_state(status.get("state"))
        if state == "done" and app_statuses is not None and app_statuses.get(address) == "idle":
            state = "idle"  # finished while the person was looking at it
        if status.get("state"):
            self._booting.discard(address)
        labels = term.get("labels") or {}
        title = term.get("title") or ""
        info = {
            "pane_id": address,
            "terminal_id": address,
            "name": term.get("name"),
            "agent": agent_kind(status.get("app")) or ("claude" if _argv_kind(term) == "claude"
                                                         else _argv_kind(term)),
            "agent_status": state,
            "workspace_id": self._space_of(term, by_address),
            "tab_id": labels.get(TAB_LABEL) or "",
            "cwd": ((term.get("foreground") or {}).get("cwd")) or term.get("cwd") or "",
            "terminal_title": title,
            "terminal_title_stripped": strip_title(title),
            "state_change_seq": int(term.get("status_ms") or term.get("created_ms") or 0),
            "interactive_ready": bool(status.get("state")),
            "blocked_kind": status.get("kind"),
            "where": labels.get(WHERE_LABEL) or "",
            "parent": term.get("parent"),
        }
        return self._fill_session_hc(info, term)

    def _fill_session_hc(self, info: dict, term: dict) -> dict:
        if self.sessions is None or info.get("agent") != "claude":
            return info
        pids = list(dict.fromkeys(p for p in ((term.get("foreground") or {}).get("pid"), term.get("pid")) if p))
        session = self.sessions.session_for(info["terminal_id"], lambda: pids)
        if session:
            info["agent_session"] = {"value": session, "source": "process"}
        return info

    # -- read-only
    def ping(self) -> dict:
        status = self.request("server.status", {})
        return {"type": "pong", "version": f"hc {status.get('version', '?')}", "core": status.get("core")}

    def list_agents(self) -> list[dict]:
        terms = self._terminals()
        by_address = {t.get("address"): t for t in terms}
        live = {a for a, t in by_address.items() if t.get("state") == "live"}
        self._booting &= live  # started by us but ended before it ever reported a status
        self._started = {k: v for k, v in self._started.items() if v in live}
        agents_t = [t for t in terms if self._is_agent(t)]
        statuses = self._app_statuses(agents_t)
        if self.sessions is not None:
            self.sessions.forget(t.get("address") for t in agents_t)
        return [self._to_agent(t, statuses, by_address) for t in agents_t]

    def get_agent(self, target: str) -> dict:
        term = self._get_terminal(target)
        if not self._is_agent(term):
            raise HerdrError("agent_not_found", f"{target} is not a live agent")
        by_address = {term.get("address"): term}
        if term.get("parent") and not (term.get("labels") or {}).get(SPACE_LABEL):
            try:
                parent = self.request("terminal.get", {"terminal": term["parent"]})
                by_address[parent.get("address")] = parent
            except HerdrError:
                pass
        return self._to_agent(term, self._app_statuses([term]), by_address)

    def list_workspaces(self) -> list[dict]:
        data = self.app.snapshot() if self.app is not None else None
        if data is not None:
            return [{"workspace_id": s.get("id"), "label": s.get("name") or s.get("id"), "number": i + 1,
                     "focused": bool(s.get("active")), "folder": s.get("folder") or "",
                     "machine": s.get("machine")}
                    for i, s in enumerate(data.get("spaces") or []) if s.get("id")]
        # App closed: the spaces its terminals are labelled into, named after their `where` label.
        seen: dict[str, dict] = {}
        for term in self._terminals():
            labels = term.get("labels") or {}
            space = labels.get(SPACE_LABEL)
            if space and space not in seen and term.get("state") == "live":
                name = (labels.get(WHERE_LABEL) or "").split(" / ")[0] or space
                seen[space] = {"workspace_id": space, "label": name, "number": len(seen) + 1,
                               "focused": False, "folder": ""}
        return list(seen.values())

    def list_tabs(self, workspace_id: str | None = None) -> list[dict]:
        data = self.app.snapshot() if self.app is not None else None
        tabs = []
        for space in (data or {}).get("spaces") or []:
            if workspace_id and space.get("id") != workspace_id:
                continue
            for i, tab in enumerate(space.get("tabs") or []):
                tabs.append({"tab_id": tab.get("id"), "workspace_id": space.get("id"), "number": i + 1,
                             "label": tab.get("name") or str(i + 1), "focused": bool(tab.get("active"))})
        return tabs

    def list_panes(self, workspace_id: str | None = None) -> list[dict]:
        terms = self._terminals()
        by_address = {t.get("address"): t for t in terms}
        panes = []
        for term in terms:
            if term.get("state") != "live":
                continue
            space = self._space_of(term, by_address)
            if workspace_id and space != workspace_id:
                continue
            panes.append(self._to_pane(term, space))
        if workspace_id:  # the space's own folder as a last resort for the cwd prefill
            for ws in self.list_workspaces():
                if ws.get("workspace_id") == workspace_id and ws.get("folder"):
                    panes.append({"pane_id": None, "workspace_id": workspace_id, "cwd": ws["folder"]})
        return panes

    def _to_pane(self, term: dict, space: str) -> dict:
        labels = term.get("labels") or {}
        return {"pane_id": term.get("address"), "terminal_id": term.get("address"), "workspace_id": space,
                "tab_id": labels.get(TAB_LABEL) or "",
                "cwd": ((term.get("foreground") or {}).get("cwd")) or term.get("cwd") or "",
                "agent": agent_kind((term.get("status") or {}).get("app"))}

    def get_pane(self, pane_id: str) -> dict:
        term = self._get_terminal(pane_id)
        return self._to_pane(term, (term.get("labels") or {}).get(SPACE_LABEL) or "")

    def read_agent_once(self, target: str, lines: int, source: str = "recent_unwrapped") -> str:
        try:
            result = self.request("terminal.read", {"terminal": self._resolve(target), "lines": int(lines)})
        except HerdrError as exc:
            if exc.code in ("not_found", "finished"):
                raise HerdrError("agent_not_found", exc.message) from exc
            raise
        return (result.get("text") or "").replace("\r\n", "\n")

    # -- mutating
    def create_tab(self, workspace_id: str, label: str | None = None, cwd: str | None = None,
                   focus: bool = False) -> dict:
        """hc has no empty tabs: remember where to start, `start_agent` creates the terminal and the
        app gives it a tab in that space."""
        pending = PENDING_PREFIX + uuid.uuid4().hex[:12]
        self._pending[pending] = {"workspace_id": workspace_id, "label": label, "cwd": cwd}
        return {"type": "tab_created",
                "tab": {"tab_id": pending, "workspace_id": workspace_id, "label": label or ""},
                "root_pane": {"pane_id": pending, "workspace_id": workspace_id, "cwd": cwd or ""}}

    def start_agent(self, name: str, kind: str, pane_id: str, args: Sequence[str] = (),
                    timeout_ms: int | None = None) -> dict:
        where = self._pending.pop(pane_id, None)
        if where is None:
            raise HerdrError("pane_not_found", f"{pane_id}: hc can only start agents in a new tab")
        argv = agent_argv(kind, args)
        labels = {OWNER_LABEL: "agent"}
        if where.get("workspace_id"):
            labels[SPACE_LABEL] = where["workspace_id"]
        params: dict[str, Any] = {"argv": argv, "name": name, "labels": labels, "no_parent": True,
                                  "no_notify": True}
        if where.get("cwd"):
            params["cwd"] = where["cwd"]
        try:
            term = self.request("terminal.run", params)
        except HerdrError as exc:
            if exc.code == "name_taken":  # hc names are unique among all live terminals, not just agents
                raise HerdrError("agent_name_taken", exc.message) from exc
            raise
        address = term.get("address") or ""
        self._started[pane_id] = address
        self._booting.add(address)
        if where.get("label") and self.app is not None:
            threading.Thread(target=self._name_tab, args=(address, where["label"]), daemon=True,
                             name=f"hc-tab-name-{address}").start()
        return {"type": "agent_started", "agent": self._to_agent(term, None, {address: term}), "argv": argv}

    def _name_tab(self, address: str, label: str, attempts: int = 10) -> None:
        """Best effort: once the app shows the terminal in a tab, name that tab."""
        for _ in range(attempts):
            self.sleep(0.5)
            tab = AppView.tab_of(self.app.snapshot(fresh=True), address)
            if tab:
                if self.app.run("tab.rename", {"id": tab, "name": label}) is None:
                    log.info("could not name tab %s for %s", tab, address)
                return

    def prompt_agent(self, target: str, text: str, wait: bool = False,
                     timeout_ms: int | None = None) -> dict:
        address = self._resolve(target)
        params: dict[str, Any] = {"terminal": address, "text": text}
        if wait:
            params["wait"] = True
            if timeout_ms is not None:
                params["timeout"] = timeout_ms / 1000.0
        try:
            result = self.request("terminal.send", params)
        except HerdrError as exc:
            raise _agent_error(exc) from exc
        if result.get("started") is False:
            # The text went in but the agent never went `working` (hc checks for a few seconds): the
            # old CLI's stalled prompt. The bridge then watches for activity and never resends.
            raise HerdrError("agent_prompt_stalled", f"{address} did not start working after the prompt")
        # No lookup after the text went in: a failing read here must not turn a delivered prompt into
        # a failed one.
        return {"pane_id": address, "terminal_id": address, "agent_status": map_state(result.get("status")),
                "turn": result.get("turn")}

    def send_keys(self, target: str, keys: Sequence[str]) -> dict:
        try:
            return self.request("terminal.keys", {"terminal": self._resolve(target), "keys": list(keys)})
        except HerdrError as exc:
            raise _agent_error(exc) from exc

    @staticmethod
    def can_type(text: str) -> bool:
        """Can `send_text` type this without pressing Enter? (letters, digits and spaces only)"""
        return all(ch == " " or ch in _KEY_CHARS for ch in text)

    def send_text(self, pane_id: str, text: str) -> dict:
        """Type text without pressing Enter. hc can only do this key by key, for letters, digits and
        spaces; anything else is refused (`unsupported_input`) before anything is typed. The bridge
        asks `can_type` before it presses any key for the answer."""
        if not self.can_type(text):
            raise HerdrError("unsupported_input",
                             "the Herdr app can only type letters, digits and spaces here without "
                             "submitting; answer this option on the PC")
        keys = ["space" if ch == " " else ch for ch in text]
        return self.send_keys(pane_id, keys) if keys else {"type": "ok"}

    def submit_text(self, pane_id: str, text: str) -> dict:
        """Paste text and press Enter (into a dialog's free-text option, which is `blocked`)."""
        try:
            return self.request("terminal.send", {"terminal": self._resolve(pane_id), "text": text, "force": True})
        except HerdrError as exc:
            raise _agent_error(exc) from exc

    # -- events
    def subscribe(self, subscriptions: list[dict]) -> ConvertedStream:
        terminal = None
        for sub in subscriptions:
            if sub.get("pane_id"):
                terminal = self._resolve(sub["pane_id"])
        params = {"terminal": terminal} if terminal else {}
        stream = self.transport.open_stream("events.subscribe", params)
        return ConvertedStream(stream, EventConverter(lifecycle=terminal is None, snapshot=stream.ack))


def _argv_kind(term: dict) -> str | None:
    argv = (term.get("foreground") or {}).get("argv") or term.get("argv") or []
    exe = os.path.basename(str(argv[0])).lower() if argv else ""
    for kind in ("claude", "codex"):
        if exe in (kind, kind + ".exe", kind + ".cmd"):
            return kind
    return None


def agent_argv(kind: str, args: Sequence[str]) -> list[str]:
    if kind == "codex":
        # Without --no-daemon, Codex runs its commands outside hc (`hc --skill`).
        extra = [] if "--no-daemon" in args else ["--no-daemon"]
        return ["codex", *extra, *args]
    return [kind, *args]


def _agent_error(exc: HerdrError) -> HerdrError:
    code = {"blocked": "agent_blocked", "not_found": "agent_not_found", "finished": "agent_not_found",
            "status_mismatch": "agent_busy"}.get(exc.code)
    return HerdrError(code, exc.message) if code else exc


def _event_state(data: dict) -> str | None:
    status = data.get("status") if isinstance(data, dict) else None
    if isinstance(status, dict):
        return status.get("state")
    return None


class EventConverter:
    """hc events -> herdr-style envelopes. Events are only hints: the event manager re-reads the
    agent (get_agent / list_agents) before acting on any of them.

    hc sends a `status` event on every status *message* change (e.g. each tool a working agent
    runs), so the per-terminal stream forwards only changes of the status *word*, and the
    all-terminals (lifecycle) stream reports an agent once, when it first reports a status."""

    def __init__(self, lifecycle: bool, snapshot: dict | None = None):
        self.lifecycle = lifecycle
        self.state: dict[str, str | None] = {}
        for term in (snapshot or {}).get("terminals") or []:
            if term.get("address") and term.get("state") == "live":
                self.state[term["address"]] = (term.get("status") or {}).get("state")

    def reseed(self, params: dict) -> list[dict]:
        """After `missed`: take the fresh snapshot (if any) and hint every terminal for a re-check
        (the event manager reconciles them against live state)."""
        terminals = params.get("terminals") if isinstance(params, dict) else None
        if isinstance(terminals, list):
            addresses = [t.get("address") for t in terminals if t.get("address")]
            for term in terminals:
                if term.get("address") and term.get("state") == "live":
                    self.state[term["address"]] = (term.get("status") or {}).get("state")
        else:
            addresses = list(self.state)
        kind = "pane.agent_detected" if self.lifecycle else "pane.agent_status_changed"
        return [{"event": kind, "data": {"pane_id": a, "agent_status": None}} for a in addresses]

    def __call__(self, event: dict) -> list[dict]:
        kind = event.get("type")
        address = event.get("terminal")
        data = event.get("data") or {}
        if not address:
            return []
        if kind == "status":
            new = _event_state(data)
            old = self.state.get(address)
            known = address in self.state
            self.state[address] = new
            if self.lifecycle:
                if new and (not known or old is None):
                    return [{"event": "pane.agent_detected", "data": {"pane_id": address}}]
                return []
            if known and new == old:
                return []
            return [{"event": "pane.agent_status_changed",
                     "data": {"pane_id": address, "agent_status": map_state(new)}}]
        if kind in ("finished", "removed", "lost"):
            self.state.pop(address, None)
            return [{"event": "pane.closed" if kind == "removed" else "pane.exited", "data": {"pane_id": address}}]
        if kind in ("created", "restarted"):
            self.state.setdefault(address, None)
            if self.lifecycle and kind == "restarted":
                return [{"event": "pane.agent_detected", "data": {"pane_id": address}}]
        return []
