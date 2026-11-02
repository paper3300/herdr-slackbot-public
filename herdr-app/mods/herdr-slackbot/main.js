// herdr-slackbot: the Slack bridge's bar in the Herdr app.
//
// - Starts the bridge when the app starts (like the old Herdr plugin's startup hook), unless its
//   Slack settings are missing.
// - Shows its state (running / pairing / ready / stopped) and buttons: Show, Start|Restart, Stop,
//   Setup. Key commands (keys.json): "herdr-slackbot.start|stop|restart|setup|show|status".
// - Shows the bridge's notifications (pairing code, status) as toasts: the bridge writes
//   STATE_DIR/notify.json, this mod watches the folder.
//
// It runs programs: the plugin's Python (`python -m herdr_slackbot ...`) from config.json, which
// scripts/setup.ps1 writes next to this file: { "python", "root", "config_dir" }.
import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { exec, appHome, readTextFile, watchFolder, nextCommand, notify, run, terminals, theme, shared, setShared }
  from "herdr";

const NAME = "herdr-slackbot";
const POLL_MS = 20000;
const AUTOSTART_KEY = "herdr-slackbot.autostart";
const NOTE_KEY = "herdr-slackbot.last-note";

export default class SlackBridgeBar extends View {
  init(_props, cx) {
    this.cfg = null;
    this.error = null;
    this.status = null;
    this.busy = null;
    this.watching = null;  // the state folder being watched
    cx.spawn(async (cx) => {
      await this.loadConfig();
      cx.notify();
      if (!this.cfg) return;
      await this.refresh();
      cx.notify();
      this.watch(cx);
      await this.autostart(cx);
    });
    cx.timer.every(POLL_MS, (cx) => cx.spawn(async (cx) => {
      await this.refresh();
      this.watch(cx);
      cx.notify();
    }));
    cx.spawn(async (cx) => {
      for (;;) {
        const c = await nextCommand();
        await this.command(c, cx);
        cx.notify();
      }
    });
  }

  async loadConfig() {
    try {
      const text = await readTextFile(`${appHome()}/mods/${NAME}/config.json`);
      if (!text) {
        this.error = "not set up: run scripts\\setup.ps1 in the herdr-slackbot folder";
        return;
      }
      const cfg = JSON.parse(text);
      if (!cfg.python || !cfg.root || !cfg.config_dir) throw new Error("config.json needs python, root, config_dir");
      this.cfg = cfg;
    } catch (e) {
      this.error = `config.json: ${e}`;
    }
  }

  async py(...args) {
    const argv = ["-m", "herdr_slackbot", ...args, "--config-dir", this.cfg.config_dir, "--backend", "hc"];
    try {
      return await exec(this.cfg.python, argv, { cwd: this.cfg.root });
    } catch (e) {
      return { code: -1, stdout: "", stderr: String(e) };
    }
  }

  async refresh() {
    if (!this.cfg) return;
    const r = await this.py("status", "--json");
    try {
      this.status = JSON.parse(r.stdout.trim().split("\n").pop());
      this.error = null;
    } catch {
      this.error = (r.stderr || r.stdout || "status failed").trim().split("\n").pop();
    }
  }

  // Watch the bridge's state folder for notify.json (toasts) and state changes (refresh). Called
  // with the caller's own cx; a folder that does not exist yet is retried on the next poll.
  watch(cx) {
    const dir = this.status?.state_dir;
    if (!dir || this.watching === dir) return;
    this.watching = dir;
    cx.spawn(async (cx) => {
      for (;;) {
        let paths;
        try {
          paths = await watchFolder(dir);
        } catch {
          if (this.watching === dir) this.watching = null;
          return;
        }
        if (this.watching !== dir) return;
        if (paths.some((p) => p.toLowerCase().endsWith("notify.json"))) await this.toast();
        if (paths.some((p) => /(bridge\.(ready|runtime)|pairing|launch)\.json$/i.test(p))) {
          await this.refresh();
          cx.notify();
        }
      }
    });
  }

  async autostart(cx) {
    const s = this.status;
    if (!s || s.running || s.starting) return;
    if ((s.slack || "").startsWith("missing") || s.config_error) return;
    const last = Number(shared(AUTOSTART_KEY) || 0);
    if (Date.now() - last < 60000) return;  // another copy of this bar just did it
    setShared(AUTOSTART_KEY, Date.now());
    await this.act("launch", cx);
  }

  async act(what, cx) {
    if (!this.cfg || this.busy) return;
    this.busy = what;
    cx?.notify();
    const r = await this.py(what);
    this.busy = null;
    if (r.code !== 0) {
      notify({ title: "Slack bridge", body: (r.stderr || r.stdout || `${what} failed`).trim().slice(-300), level: "error" });
    }
    await this.refresh();
  }

  bridgeTerminal() {
    return terminals().find((t) => t.name === NAME && t.state === "live");
  }

  async command(c, cx) {
    if (c === "start") return this.act("launch", cx);
    if (c === "stop" || c === "restart") return this.act(c, cx);
    if (c === "setup") return this.act("open-wizard", cx);
    if (c === "status") {
      await this.refresh();
      return notify({ title: "Slack bridge", body: this.summary(), level: "info" });
    }
    if (c === "show") {
      const t = this.bridgeTerminal();
      if (t) run("terminal.peek", { terminal: t.address });
    }
  }

  summary() {
    if (this.error) return this.error;
    const s = this.status;
    if (!s) return "checking…";
    if (this.busy) return `${this.busy}…`;
    if (s.starting && !s.running) return "starting…";
    if (!s.running) return s.slack?.startsWith("missing") ? `not configured (${s.slack}) — Setup` : "stopped";
    return s.slack || "running";
  }

  render() {
    const t = theme();
    const s = this.status;
    const running = Boolean(this.bridgeTerminal()) || Boolean(s?.running);
    const ready = Boolean(s?.ready);
    const dot = this.error ? t.blocked : ready ? t.idle : running ? t.working : t.dim;
    const button = (id, label, onClick) => div().id(`hs-${id}`).px(6).rounded(4).text_color(t.muted)
      .hover((st) => st.bg(t.hover).text_color(t.foreground))
      .on_click((_e, cx) => cx.spawn(async (cx) => { await onClick(cx); cx.notify(); }))
      .child(label);
    const bar = h_flex().h(34).flex_none().px(12).gap(10).items_center().bg(t.chrome).border_b(1)
      .border_color(t.border).text_size(11.8).text_color(t.muted)
      .child(div().size(7).rounded(4).bg(dot))
      .child(div().text_color(t.foreground).child("Slack bridge"))
      .child(div().truncate().child(this.summary()))
      .when(Boolean(s?.command), (el) => el.child(div().text_color(t.dim).child(s.command)))
      .child(div().flex_1())
      .when(Boolean(this.cfg), (el) => el
        .when(running, (el) => el.child(button("show", "Show", async () => this.command("show"))))
        .child(button("start", running ? "Restart" : "Start", async (cx) => this.act(running ? "restart" : "launch", cx)))
        .when(running, (el) => el.child(button("stop", "Stop", async (cx) => this.act("stop", cx))))
        .child(button("setup", "Setup", async (cx) => this.act("open-wizard", cx))));
    // Placed as a full pane (its own tab), the details go below the bar; docked as a slim bar, only
    // the bar shows.
    const rows = [["bridge", s?.bridge], ["slack", s?.slack], ["command", s?.command], ["config", s?.config],
                  ["log", s?.log], ["error", this.error || s?.config_error]].filter(([, v]) => v);
    const line = (k, v) => h_flex().gap(10).child(div().w(70).flex_none().text_color(t.dim).child(k))
      .child(div().text_color(t.foreground).child(String(v)));
    const help = !this.cfg ? "Run scripts\\setup.ps1 -Backend hc in the herdr-slackbot folder."
      : (s?.slack || "").startsWith("missing") ? "Setup opens a tab with the setup wizard: Slack app, tokens, pairing."
      : !running ? "Start runs the bridge as the terminal herdr-slackbot. It also starts with the Herdr app."
      : "Show opens the bridge's terminal. Restart after editing .env.";
    return v_flex().id("root").size_full().bg(t.background).overflow_y_scrollbar()
      .child(bar)
      .child(v_flex().p(16).gap(6).text_size(12.5).text_color(t.muted)
        .children(rows.map(([k, v]) => line(k, v)))
        .child(div().pt(8).text_color(t.dim).child(help)));
  }

  async toast() {
    if (!this.status?.state_dir) return;
    try {
      const note = JSON.parse((await readTextFile(`${this.status.state_dir}/notify.json`)) || "null");
      if (!note || !note.id || shared(NOTE_KEY) === note.id) return;
      if (note.at && Date.now() / 1000 - note.at > 300) return;  // stale
      setShared(NOTE_KEY, note.id);
      notify({ title: note.title || "Slack bridge", body: note.body || "", level: note.level || "info", timeout: 30000 });
    } catch {}
  }
}
