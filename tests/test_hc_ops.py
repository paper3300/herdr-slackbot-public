"""Bridge lifecycle on the Herdr app backend (HcOps) and the app mod install."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from herdr_slackbot import plugin as P
from herdr_slackbot.herdr_client import HerdrError, HerdrOutcomeUnknown
from herdr_slackbot.setup_cmd import MOD_FILES, install_app_mod
from test_hc_client import FakeApp, FakeHc, app_data, term


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HERDR_BACKEND", "hc")
    d = tmp_path / "cfg"
    d.mkdir()
    (d / ".env").write_text("SLACK_BOT_TOKEN=xoxb-1\nSLACK_APP_TOKEN=xapp-1\n", encoding="utf-8")
    return d


def ops_for(cfg_dir, hc, app=None, out=None):
    return P.HcOps(hc, cfg_dir, plugin_root=Path(r"D:\Plug Root"), app=app,
                   python_exe=r"D:\Plug Root\.venv\python.exe", out=(out if out is not None else []).append,
                   env={})


def bridge_term(address, live=True):
    return term(address, state=None, space=None, name="herdr-slackbot", labels={"herdr-slackbot": "bridge"},
                live=live)


def test_launch_runs_the_bridge_as_its_own_hc_terminal(cfg_dir):
    hc = FakeHc([bridge_term("t5", live=False)])
    out = []
    ops = ops_for(cfg_dir, hc, FakeApp(app_data({})), out)
    assert ops.launch() == 0
    methods = [m for m, _ in hc.calls]
    assert ("terminal.rm", {"terminal": "t5"}) in hc.calls  # the previous bridge's finished terminal
    method, params = hc.calls[-1]
    assert method == "terminal.run"
    launch = json.loads((ops.state_dir / P.LAUNCH_FILE).read_text(encoding="utf-8"))
    assert params["argv"] == [r"D:\Plug Root\.venv\python.exe", "-m", "herdr_slackbot", "run", "--config-dir",
                              str(cfg_dir), "--backend", "hc", "--launch-id", launch["launch_id"]]
    assert params["name"] == "herdr-slackbot" and params["no_parent"] is True
    assert params["cwd"] == r"D:\Plug Root" and params["env"]["HERDR_BACKEND"] == "hc"
    assert params["labels"] == {"herdr-slackbot": "bridge"}  # no herdr-slack space: hidden
    assert launch["active"] is True
    assert "hidden" in out[-1] and methods.count("terminal.run") == 1


def test_launch_shows_the_bridge_in_the_bridge_space_when_it_exists(cfg_dir):
    spaces = [{"id": "spB", "name": "herdr-slack", "tabs": []}]
    hc = FakeHc()
    ops_for(cfg_dir, hc, FakeApp(app_data({}, spaces=spaces))).launch()
    assert hc.calls[-1][1]["labels"] == {"herdr-slackbot": "bridge", "herdr.space": "spB"}


def test_launch_refuses_next_to_a_live_bridge_terminal_without_the_lock(cfg_dir):
    hc = FakeHc([bridge_term("t5")])
    out = []
    t = [0.0]
    ops = P.HcOps(hc, cfg_dir, plugin_root=Path(r"D:\Plug Root"), python_exe="py", out=out.append, env={},
                  clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
    assert ops.launch() == 1 and t[0] >= P.BRIDGE_EXIT_WAIT
    assert "terminal.run" not in [m for m, _ in hc.calls] and "t5" in out[-1]


def test_launch_refused_by_hc_releases_the_reservation(cfg_dir):
    hc = FakeHc()
    hc.errors["terminal.run"] = HerdrError("invalid_params", "bad")
    ops = ops_for(cfg_dir, hc)
    with pytest.raises(P.PluginError):
        ops.launch()
    assert ops.reservation() is None


def test_launch_with_unknown_outcome_keeps_the_reservation(cfg_dir):
    hc = FakeHc()
    hc.errors["terminal.run"] = HerdrOutcomeUnknown("lost")
    ops = ops_for(cfg_dir, hc)
    with pytest.raises(P.PluginUncertain):
        ops.launch()
    assert ops.reservation() is not None
    hc2 = FakeHc()
    out = []
    assert ops_for(cfg_dir, hc2, None, out).launch() == 0 and "already in progress" in out[-1]


def test_status_json_and_notification_file(cfg_dir):
    out = []
    ops = ops_for(cfg_dir, FakeHc(), None, out)
    assert ops.status(notify=True, as_json=True) == 0
    data = json.loads(out[-1])
    assert data["backend"] == "hc" and data["running"] is False and data["bridge"] == "stopped"
    assert data["state_dir"] == str(ops.state_dir) and data["slack"].startswith("tokens set")
    note = json.loads((ops.state_dir / "notify.json").read_text(encoding="utf-8"))
    assert note["title"] == "herdr-slackbot" and "bridge: stopped" in note["body"] and note["id"]


def test_open_wizard_opens_an_app_tab(cfg_dir):
    app = FakeApp(app_data({}))
    ops = ops_for(cfg_dir, FakeHc(), app)
    assert ops.open_wizard() == 0
    command, args = app.ran[-1]
    assert command == "tab.new" and args["name"] == "Slack setup"
    assert args["argv"][-5:] == ["wizard", "--config-dir", str(cfg_dir), "--backend", "hc"]
    with pytest.raises(P.PluginError) as exc:
        ops_for(cfg_dir, FakeHc(), None).open_wizard()
    assert "wizard" in str(exc.value)


def test_make_ops_follows_the_backend(cfg_dir, monkeypatch):
    assert isinstance(P.make_ops(cfg_dir, env={"HERDR_BACKEND": "hc", "USERNAME": "me"}), P.HcOps)
    (cfg_dir / ".env").write_text("HERDR_BACKEND=herdr\n", encoding="utf-8")
    ops = P.make_ops(cfg_dir, env={"USERNAME": "me"})
    assert type(ops) is P.PluginOps


def test_install_app_mod(tmp_path):
    target = install_app_mod(tmp_path / "cfg", python_exe=r"C:\py.exe", app_home=tmp_path / "app")
    assert target == tmp_path / "app" / "mods" / "herdr-slackbot"
    assert sorted(p.name for p in target.iterdir()) == sorted([*MOD_FILES, "config.json"])
    cfg = json.loads((target / "config.json").read_text(encoding="utf-8"))
    assert cfg["python"] == r"C:\py.exe" and cfg["config_dir"] == str(tmp_path / "cfg")
    assert Path(cfg["root"], "herdr_slackbot").is_dir()


def test_detect_backend():
    from herdr_slackbot.config import detect_backend

    none = lambda name: None  # noqa: E731
    assert detect_backend({"HERDR_BACKEND": "app"}, none) == "hc"
    assert detect_backend({"HERDR_BACKEND": "auto", "HERDR_SOCKET_PATH": "x"}, none) == "herdr"
    assert detect_backend({"HC_TERMINAL_ID": "t1"}, none) == "hc"
    assert detect_backend({}, lambda name: "C:\\hc.exe" if name == "hc" else None) == "hc"
    assert detect_backend({}, none) == "herdr"
    with pytest.raises(Exception):
        detect_backend({"HERDR_BACKEND": "nope"}, none)


def test_launch_waits_for_a_stopping_bridge_terminal_to_end(cfg_dir):
    hc = FakeHc([bridge_term("t5")])
    t = [0.0]

    def sleep(s):
        t[0] += s
        hc.terms["t5"]["state"] = "finished"  # the stopped bridge's process ends

    ops = P.HcOps(hc, cfg_dir, plugin_root=Path(r"D:\Plug Root"), python_exe="py", out=[].append, env={},
                  clock=lambda: t[0], sleep=sleep)
    assert ops.launch() == 0
    assert ("terminal.rm", {"terminal": "t5"}) in hc.calls and hc.calls[-1][0] == "terminal.run"


def test_finished_bridge_does_not_wait_for_the_lifecycle_lock_once_acknowledged(cfg_dir, monkeypatch):
    from herdr_slackbot import __main__ as main_mod

    state = P.state_dir_for(cfg_dir)
    P._write_json(state / P.LAUNCH_FILE, {"launch_id": "L1", "active": False, "at": 0})
    monkeypatch.setenv("HERDR_PLUGIN_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setattr(P, "lifecycle_lock", lambda *a, **k: pytest.fail("must not wait for the lock"))
    main_mod._release_launch("L1")  # returns at once (a restart may hold the lock)
    assert main_mod._launch_active(state, "L1") is False
    P._write_json(state / P.LAUNCH_FILE, {"launch_id": "L2", "active": True, "at": 0})
    assert main_mod._launch_active(state, "L2") is True


def test_ensure_app_tab_creates_the_space_and_the_bar_tab_once():
    from herdr_slackbot.setup_cmd import ensure_app_tab
    from test_hc_client import FakeApp

    class App(FakeApp):
        def run(self, command, args):
            self.ran.append((command, args))
            if command == "space.new":
                self.data["spaces"].append({"id": "spN", "name": args["name"], "tabs": [{"id": "tb1", "name": "1"}]})
                return {"space": "spN", "tab": "tb1", "terminal": "t9"}
            if command == "tab.new":
                self.data["spaces"][-1]["tabs"].append({"id": "tb2", "name": args["name"]})
            return {"ok": True}

    app = App({"spaces": []})
    assert "added" in ensure_app_tab("herdr-slack", Path("D:/x"), app)
    assert [c for c, _ in app.ran] == ["space.new", "tab.new", "tab.close"]
    assert app.ran[1][1] == {"space": "spN", "name": "Slack bridge", "mod": "herdr-slackbot"}
    assert app.ran[2][1] == {"id": "tb1", "confirmed": True}  # only the shell tab it just made
    assert "already" in ensure_app_tab("herdr-slack", Path("D:/x"), app) and len(app.ran) == 3
    assert "not running" in ensure_app_tab("herdr-slack", Path("D:/x"), FakeApp(None))
