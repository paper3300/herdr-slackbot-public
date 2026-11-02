"""hc backend (Herdr app): HcClient mapping, events, sessions, transport framing."""

from __future__ import annotations

import json

import pytest

from herdr_slackbot import claude_pid
from herdr_slackbot.events import parse_event
from herdr_slackbot.hc_client import (
    AppView,
    EventConverter,
    HcClient,
    HcTransport,
    agent_argv,
    default_socket_path,
    strip_title,
)
from herdr_slackbot.herdr_client import HerdrClient, HerdrError, HerdrOutcomeUnknown


def term(address, state="idle", app="claude-code", space="sp1", name=None, parent=None, status_ms=100, pid=None,
         title="✳ Some task", labels=None, live=True, cwd="D:\\work", argv=("claude",)):
    lab = {"herdr.space": space, "where": "Main / 1"} if space else {}
    lab.update(labels or {})
    return {"address": address, "name": name, "parent": parent, "state": "live" if live else "finished",
            "status": {"app": app, "state": state} if state else None, "status_ms": status_ms, "created_ms": 1,
            "labels": lab, "title": title, "cwd": cwd, "pid": pid, "argv": list(argv),
            "foreground": {"pid": pid, "cwd": cwd, "argv": list(argv)} if live else None}


class FakeHc:
    """hc JSON-RPC methods over an in-memory terminal table."""

    def __init__(self, terms=()):
        self.terms = {t["address"]: t for t in terms}
        self.calls = []
        self.errors: dict[str, HerdrError] = {}
        self.next_address = iter(f"t{n}" for n in range(50, 99))
        self.path = "\\\\.\\pipe\\fake"

    def request(self, method, params=None):
        params = params or {}
        self.calls.append((method, params))
        if method in self.errors:
            raise self.errors.pop(method)
        if method == "server.status":
            return {"version": "0.1.16", "core": {"id": "c1"}}
        if method == "terminal.list":
            out = [t for t in self.terms.values() if params.get("all") or t["state"] == "live"]
            want = params.get("labels") or {}
            return {"terminals": [t for t in out if all(t["labels"].get(k) == v for k, v in want.items())]}
        if method == "terminal.get":
            t = self.terms.get(params["terminal"]) or next(
                (x for x in self.terms.values() if x.get("name") == params["terminal"]), None)
            if t is None:
                raise HerdrError("not_found", params["terminal"])
            return t
        if method == "terminal.run":
            address = next(self.next_address)
            t = term(address, state=None, space=params.get("labels", {}).get("herdr.space"), name=params.get("name"),
                     labels=params.get("labels"), argv=params["argv"])
            self.terms[address] = t
            return t
        if method == "terminal.read":
            return {"text": "line\r\n" * 3, "complete": True}
        if method in ("terminal.send", "terminal.keys"):
            t = self.terms[params["terminal"]]
            if t["status"] and t["status"]["state"] == "blocked" and method == "terminal.send" \
                    and not params.get("force"):
                raise HerdrError("blocked", f"{t['address']} is blocked (question)")
            return {"status": t["status"] and t["status"]["state"], "turn": 1}
        if method in ("terminal.rm", "terminal.kill"):
            return {"removed": params["terminal"]}
        raise AssertionError(f"unexpected {method}")

    def open_stream(self, method, params):
        raise AssertionError("no streams in this fake")


class FakeApp(AppView):
    def __init__(self, data):
        super().__init__(runner=None)
        self.data = data
        self.ran = []

    def snapshot(self, fresh=False):
        return self.data

    def run(self, command, args):
        self.ran.append((command, args))
        return {"ok": True}


def app_data(statuses, spaces=None):
    return {"spaces": spaces or [{"id": "sp1", "name": "Main", "folder": "D:\\main", "active": True, "tabs": [
        {"id": "tb1", "name": "1", "terminals": [{"terminal": a, "status": s} for a, s in statuses.items()]}]}]}


class NoSessions:
    def session_for(self, key, pids):
        return None

    def forget(self, keep):
        list(keep)


def client(terms=(), app=None, sessions=None):
    return HcClient(FakeHc(terms), app, sessions or NoSessions(), sleep=lambda s: None)


# --- mapping ---------------------------------------------------------------------------------

def test_agents_are_terminals_that_report_status():
    c = client([term("t1"), term("t2", state=None), term("t3", app="codex", state="working"),
                term("t4", live=False)])
    agents = {a["pane_id"]: a for a in c.list_agents()}
    assert set(agents) == {"t1", "t3"}
    a = agents["t1"]
    assert (a["agent"], a["agent_status"], a["workspace_id"], a["terminal_id"]) == ("claude", "idle", "sp1", "t1")
    assert a["terminal_title_stripped"] == "Some task" and a["state_change_seq"] == 100
    assert agents["t3"]["agent"] == "codex"


def test_done_is_idle_when_the_app_shows_it_as_seen():
    terms = [term("t1", state="done"), term("t2", state="done"), term("t3", state="done", space=None)]
    c = client(terms, FakeApp(app_data({"t1": "idle", "t2": "done"})))
    got = {a["pane_id"]: a["agent_status"] for a in c.list_agents()}
    # seen -> idle; unseen -> done; not shown in the app (hidden worker) -> done
    assert got == {"t1": "idle", "t2": "done", "t3": "done"}


def test_done_stays_done_when_the_app_is_not_running():
    c = client([term("t1", state="done")], app=None)
    assert c.get_agent("t1")["agent_status"] == "done"


def test_app_lag_is_rechecked_once():
    class Lagging(FakeApp):
        def snapshot(self, fresh=False):
            return app_data({"t1": "idle" if fresh else "working"})

    c = client([term("t1", state="done")], Lagging(None))
    assert c.get_agent("t1")["agent_status"] == "idle"


def test_sub_agent_takes_its_parents_space():
    c = client([term("t1"), term("t9", space=None, parent="t1", name="review")])
    sub = c.get_agent("review")
    assert sub["workspace_id"] == "sp1" and sub["name"] == "review"


def test_get_agent_of_a_plain_terminal_is_agent_not_found():
    c = client([term("t2", state=None)])
    with pytest.raises(HerdrError) as exc:
        c.get_agent("t2")
    assert exc.value.code == "agent_not_found"
    assert c.find_agent("t2") is None and c.find_agent("t404") is None


def test_session_comes_from_the_process():
    class Sessions(NoSessions):
        def session_for(self, key, pids):
            return f"sess-{key}-{sorted(pids())}"

    c = client([term("t1", pid=42), term("t3", app="codex", pid=7)], sessions=Sessions())
    agents = {a["pane_id"]: a for a in c.list_agents()}
    assert agents["t1"]["agent_session"] == {"value": "sess-t1-[42]", "source": "process"}
    assert "agent_session" not in agents["t3"]  # codex: no session file


def test_workspaces_from_the_app_or_from_labels():
    c = client([term("t1")], FakeApp(app_data({})))
    assert c.list_workspaces() == [{"workspace_id": "sp1", "label": "Main", "number": 1, "focused": True,
                                    "folder": "D:\\main", "machine": None}]
    c = client([term("t1"), term("t2", space="sp2", labels={"where": "Other / 2"})], app=None)
    assert [(w["workspace_id"], w["label"]) for w in c.list_workspaces()] == [("sp1", "Main"), ("sp2", "Other")]


def test_list_panes_adds_the_space_folder_last():
    c = client([term("t1", cwd="D:\\proj")], FakeApp(app_data({})))
    panes = c.list_panes("sp1")
    assert [p["cwd"] for p in panes] == ["D:\\proj", "D:\\main"]


def test_strip_title_and_argv():
    assert strip_title("⠼ 검토 | x") == "검토 | x" and strip_title("plain") == "plain"
    assert agent_argv("codex", ["-m", "x"]) == ["codex", "--no-daemon", "-m", "x"]
    assert agent_argv("codex", ["--no-daemon"]) == ["codex", "--no-daemon"]
    assert agent_argv("claude", ["--model", "opus"]) == ["claude", "--model", "opus"]


def test_default_socket_path():
    assert default_socket_path({"HC_TERMINAL_SOCKET": "\\\\.\\pipe\\x"}) == "\\\\.\\pipe\\x"
    assert default_socket_path({"USERNAME": "kim"}) == "\\\\.\\pipe\\herdr-core-kim-default.sock"
    assert default_socket_path({"USERNAME": "kim", "HC_SESSION": "t"}) == "\\\\.\\pipe\\herdr-core-kim-t.sock"


# --- starting and talking -----------------------------------------------------------------------

def test_create_tab_then_start_agent_runs_one_terminal_in_the_space():
    app = FakeApp(app_data({}))
    c = client([], app)
    c._name_tab = lambda address, label: app.ran.append(("name", address, label))  # no thread in tests
    import threading
    started_threads = []
    real_thread = threading.Thread

    class InlineThread(real_thread):
        def start(self):
            started_threads.append(self.name)
            self.run()

    threading.Thread, saved = InlineThread, threading.Thread
    try:
        created = c.create_tab("sp1", "slack-1 fix bug", "D:\\proj")
        pending = created["root_pane"]["pane_id"]
        started = c.start_agent("slack-1", "codex", pending, ["-m", "gpt"])
    finally:
        threading.Thread = saved
    method, params = c.transport.calls[-1]
    assert method == "terminal.run"
    assert params["argv"] == ["codex", "--no-daemon", "-m", "gpt"]
    assert params["name"] == "slack-1" and params["cwd"] == "D:\\proj" and params["no_parent"] is True
    assert params["labels"] == {"herdr-slackbot": "agent", "herdr.space": "sp1"}
    address = started["agent"]["pane_id"]
    assert started["agent"]["agent_status"] == "unknown"
    # the pending id keeps resolving to the started terminal; booting agents count as agents
    assert c.get_agent(pending)["pane_id"] == address
    assert [a["pane_id"] for a in c.list_agents()] == [address]
    assert ("name", address, "slack-1 fix bug") in app.ran
    with pytest.raises(HerdrError):
        c.start_agent("x", "claude", "pending:nope")


def test_prompt_maps_blocked_and_submit_text_forces():
    c = client([term("t1", state="blocked")])
    with pytest.raises(HerdrError) as exc:
        c.prompt_agent("t1", "hi")
    assert exc.value.code == "agent_blocked"
    c.submit_text("t1", "초록")
    assert c.transport.calls[-1] == ("terminal.send", {"terminal": "t1", "text": "초록", "force": True})


def test_send_text_types_plain_ascii_key_by_key_and_refuses_the_rest():
    c = client([term("t1", state="blocked")])
    c.send_text("t1", "ab 1")
    assert c.transport.calls[-1] == ("terminal.keys", {"terminal": "t1", "keys": ["a", "b", "space", "1"]})
    n = len(c.transport.calls)
    with pytest.raises(HerdrError) as exc:
        c.send_text("t1", "초록")
    assert exc.value.code == "unsupported_input" and len(c.transport.calls) == n  # nothing typed


def test_read_agent_once_normalizes_newlines():
    c = client([term("t1")])
    assert c.read_agent_once("t1", 10) == "line\n" * 3


# --- events ---------------------------------------------------------------------------------

def ev(kind, address, state=None):
    data = {"status": {"app": "claude-code", "state": state, "msg": "x"}} if kind == "status" else {}
    return {"type": kind, "terminal": address, "data": data, "seq": 1}


def test_status_stream_forwards_only_word_changes():
    conv = EventConverter(lifecycle=False, snapshot={"terminals": [term("t1", state="working")]})
    assert conv(ev("status", "t1", "working")) == []  # message change only
    out = conv(ev("status", "t1", "done"))
    assert [parse_event(e).kind for e in out] == ["pane.agent_status_changed"]
    assert out[0]["data"] == {"pane_id": "t1", "agent_status": "done"}
    assert [e["event"] for e in conv(ev("finished", "t1"))] == ["pane.exited"]
    assert [e["event"] for e in conv(ev("removed", "t1"))] == ["pane.closed"]


def test_lifecycle_stream_reports_new_agents_once():
    conv = EventConverter(lifecycle=True, snapshot={"terminals": [term("t1")]})
    assert conv(ev("status", "t1", "working")) == []  # known agent
    assert conv(ev("created", "t5")) == []
    assert [e["event"] for e in conv(ev("status", "t5", "idle"))] == ["pane.agent_detected"]
    assert conv(ev("status", "t5", "working")) == []
    assert [e["event"] for e in conv(ev("status", "t6", "idle"))] == ["pane.agent_detected"]


# --- transport ---------------------------------------------------------------------------------

class FakeHandle:
    def __init__(self, replies: list[bytes]):
        self.data = b"".join(replies)
        self.written = b""

    def write(self, b):
        self.written += b

    def read(self, n):
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk

    def close(self):
        pass


def transport_with(replies):
    t = HcTransport("\\\\.\\pipe\\fake")
    handle = FakeHandle(replies)
    t.pipe._open = lambda: handle
    return t, handle


def test_transport_skips_notifications_and_maps_error_kinds():
    t, handle = transport_with([b'{"jsonrpc":"2.0","method":"heartbeat","params":{}}\n',
                                b'{"jsonrpc":"2.0","id":1,"result":{"terminals":[]}}\n'])
    assert t.request("terminal.list", {}) == {"terminals": []}
    sent = json.loads(handle.written.decode())
    assert sent["jsonrpc"] == "2.0" and sent["method"] == "terminal.list" and sent["id"] == 1
    t, _ = transport_with([b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"t1 is blocked",'
                           b'"data":{"kind":"blocked"}}}\n'])
    with pytest.raises(HerdrError) as exc:
        t.request("terminal.send", {})
    assert exc.value.code == "blocked"
    t, _ = transport_with([])
    with pytest.raises(HerdrOutcomeUnknown):
        t.request("terminal.send", {})


# --- Claude session from the process (both backends) ---------------------------------------------

def test_session_locator_walks_children_and_rereads(tmp_path):
    (tmp_path / "30.json").write_text(json.dumps({"pid": 30, "sessionId": "s-1"}), encoding="utf-8")
    tree = {10: [(20, "cmd.exe")], 20: [(30, "claude.exe")]}
    calls = []

    def children(pid):
        calls.append(pid)
        return tree.get(pid, [])

    loc = claude_pid.SessionLocator(tmp_path, children)
    assert loc.session_for("t1", lambda: [10]) == "s-1"
    (tmp_path / "30.json").write_text(json.dumps({"pid": 30, "sessionId": "s-2"}), encoding="utf-8")
    n = len(calls)
    assert loc.session_for("t1", lambda: pytest.fail("pid is cached")) == "s-2"  # /clear: new id
    assert len(calls) == n
    (tmp_path / "30.json").unlink()
    assert loc.session_for("t1", lambda: [10]) is None
    loc.forget([])
    assert loc._pids == {}


def test_cli_client_fills_a_missing_claude_session(tmp_path):
    class T:
        def __init__(self):
            self.calls = []

        def request(self, method, params=None):
            self.calls.append(method)
            if method == "agent.list":
                return {"agents": [{"pane_id": "w1:p1", "terminal_id": "x", "agent": "claude"},
                                   {"pane_id": "w1:p2", "agent": "claude", "agent_session": {"value": "hooked"}},
                                   {"pane_id": "w1:p3", "agent": "codex"}]}
            if method == "pane.process_info":
                return {"process_info": {"shell_pid": 5, "foreground_processes": [{"pid": 30}]}}
            raise AssertionError(method)

    (tmp_path / "30.json").write_text(json.dumps({"sessionId": "s-30"}), encoding="utf-8")
    t = T()
    c = HerdrClient(t, claude_pid.SessionLocator(tmp_path, lambda pid: []))
    agents = {a["pane_id"]: a for a in c.list_agents()}
    assert agents["w1:p1"]["agent_session"] == {"value": "s-30", "source": "process"}
    assert agents["w1:p2"]["agent_session"] == {"value": "hooked"}
    assert "agent_session" not in agents["w1:p3"]
    assert t.calls.count("pane.process_info") == 1


# --- review fixes ----------------------------------------------------------------------------------

def test_error_status_counts_as_a_finished_turn():
    c = client([term("t1", state="error")])
    assert c.get_agent("t1")["agent_status"] == "done"
    conv = EventConverter(lifecycle=False, snapshot={"terminals": [term("t1", state="working")]})
    assert conv(ev("status", "t1", "error"))[0]["data"]["agent_status"] == "done"


def test_prompt_that_never_starts_is_stalled_and_no_lookup_follows():
    hc = FakeHc([term("t1")])
    real = hc.request

    def request(method, params=None):
        if method == "terminal.send":
            hc.calls.append((method, params))
            return {"started": False, "status": "idle", "turn": 3}
        return real(method, params)

    hc.request = request
    c = HcClient(hc, None, NoSessions(), sleep=lambda s: None)
    with pytest.raises(HerdrError) as exc:
        c.prompt_agent("t1", "hi")
    assert exc.value.code == "agent_prompt_stalled"
    hc.request = lambda method, params=None: (hc.calls.append((method, params))
                                              or {"started": True, "status": "working", "turn": 4})
    assert c.prompt_agent("t1", "hi") == {"pane_id": "t1", "terminal_id": "t1", "agent_status": "working",
                                          "turn": 4}
    assert [m for m, _ in hc.calls].count("terminal.get") == 0


def test_a_snapshot_older_than_the_turn_end_is_read_again():
    class Stale(FakeApp):
        def __init__(self):
            super().__init__(None)
            self.fresh = 0
            self.taken_at = 50.0  # seconds; the turn ended at status_ms=100000 (100 s)

        def snapshot(self, fresh=False):
            if fresh:
                self.fresh += 1
                self.taken_at = 200.0
                return app_data({"t1": "done"})
            return app_data({"t1": "idle"})  # cached from before the turn ended

    app = Stale()
    c = client([term("t1", state="done", status_ms=100000)], app)
    assert c.get_agent("t1")["agent_status"] == "done" and app.fresh == 1


def test_name_clash_maps_to_agent_name_taken():
    c = client([])
    c.transport.errors["terminal.run"] = HerdrError("name_taken", "slack-1 is taken")
    pending = c.create_tab("sp1", None, None)["root_pane"]["pane_id"]
    with pytest.raises(HerdrError) as exc:
        c.start_agent("slack-1", "claude", pending)
    assert exc.value.code == "agent_name_taken"


def test_booting_terminals_that_ended_are_forgotten():
    c = client([], None)
    pending = c.create_tab("", None, None)["root_pane"]["pane_id"]
    address = c.start_agent("x", "claude", pending)["agent"]["pane_id"]
    assert [a["pane_id"] for a in c.list_agents()] == [address]
    c.transport.terms[address]["state"] = "finished"
    assert c.list_agents() == [] and not c._booting and not c._started


def test_missed_events_reseed_and_hint_every_terminal():
    conv = EventConverter(lifecycle=False, snapshot={"terminals": [term("t1", state="working")]})
    out = conv.reseed({"terminals": [term("t1", state="done")]})
    assert out == [{"event": "pane.agent_status_changed", "data": {"pane_id": "t1", "agent_status": None}}]
    assert conv(ev("status", "t1", "done")) == []  # the snapshot already said done
    life = EventConverter(lifecycle=True)
    assert [e["event"] for e in life.reseed({"terminals": [term("t7")]})] == ["pane.agent_detected"]


def test_can_type():
    assert HcClient.can_type("ab 1") and not HcClient.can_type("초록") and not HcClient.can_type("a-b")
