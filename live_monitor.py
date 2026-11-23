"""Live monitor: watch an Epistemic Arena run as it happens, in your browser.

    python live_monitor.py            # live runs  -> http://localhost:8765
    python live_monitor.py --mock     # mock runs
    python run_experiment.py --module C --local --live   # start a run and open the monitor with it

It reads the SQLite database read-only (safe while a run is writing) and shows:
- the run, its progress per module, and the trial in progress;
- who is thinking RIGHT NOW (agent, role, model, seconds elapsed);
- the current situation (colony state in Module C, round and item in Module A, the chain in Module B);
- a feed of every agent turn: public message, private scratchpad, private beliefs and action.
Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from arena.config import load_config, resolve

PORT = 8765


def _connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def snapshot(db: Path, feed_limit: int = 60) -> dict:
    if not db.exists():
        return {"error": f"no database yet at {db}. Start a run first."}
    conn = _connect(db)
    try:
        runs = _rows(conn, "SELECT run_id, created_at, preset, modules, mock, status FROM runs "
                           "ORDER BY created_at DESC, run_id DESC LIMIT 1")
        if not runs:
            return {"error": "no run in this database yet."}
        run = runs[0]
        rid = run["run_id"]
        progress = {}
        for r in _rows(conn, "SELECT module, status, COUNT(*) n FROM trials WHERE run_id=? GROUP BY 1,2", (rid,)):
            progress.setdefault(r["module"], {})[r["status"]] = r["n"]
        running = _rows(conn, "SELECT trial_id, module, spec_json, started_at, status FROM trials WHERE run_id=? AND "
                              "status='running' ORDER BY started_at DESC LIMIT 1", (rid,))
        if not running:  # idle: show the most recently finished trial
            running = _rows(conn, "SELECT trial_id, module, spec_json, started_at, status FROM trials WHERE run_id=? "
                                  "AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1", (rid,))
        trial = None
        if running:
            t = running[0]
            trial = {"trial_id": t["trial_id"], "module": t["module"], "status": t["status"], "spec": json.loads(t["spec_json"]),
                     "started_at": t["started_at"]}
            ev = _rows(conn, "SELECT event_key, event_type, payload_json FROM events WHERE trial_id=? "
                             "ORDER BY event_key", (t["trial_id"],))
            setup = next((json.loads(e["payload_json"]) for e in ev if e["event_type"] == "setup"), None)
            last = [json.loads(e["payload_json"]) for e in ev if e["event_type"] in ("turn", "round", "cascade")]
            trial["setup"] = setup
            trial["last_event"] = last[-1] if last else None
            trial["events_so_far"] = len(last)
        live = _rows(conn, "SELECT * FROM live WHERE id=1")
        now = None
        if live and live[0]["step_key"]:
            lv = live[0]
            started = dt.datetime.fromisoformat(lv["started_at"])
            now = {**lv, "elapsed_s": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds())}
        feed = []
        for r in _rows(conn, "SELECT rowid, trial_id, step_key, agent, role, model_id, status, attempts, error, "
                             "parsed_json, created_at FROM turns WHERE run_id=? OR trial_id LIKE 'gate-%' "
                             "ORDER BY rowid DESC LIMIT ?", (rid, feed_limit)):
            p = json.loads(r["parsed_json"]) if r["parsed_json"] else {}
            feed.append({"trial_id": r["trial_id"], "step": r["step_key"], "agent": r["agent"], "role": r["role"],
                         "model": r["model_id"], "status": r["status"], "attempts": r["attempts"],
                         "error": r["error"], "at": r["created_at"],
                         "public": p.get("public_message", ""), "private": p.get("private_scratchpad", ""),
                         "private_fields": {k: v for k, v in p.items() if k.startswith("private_") and k != "private_scratchpad"},
                         "action": p.get("action")})
        calls = _rows(conn, "SELECT COUNT(*) n, COALESCE(SUM(tokens_in+tokens_out),0) tok, "
                            "COALESCE(AVG(latency_s),0) lat FROM calls WHERE run_id=?", (rid,))[0]
        return {"run": run, "progress": progress, "trial": trial, "now": now, "feed": feed, "calls": calls,
                "server_time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    finally:
        conn.close()


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arena Live Monitor</title>
<style>
:root { color-scheme: light; --bg:#f4f3f0; --card:#fcfcfb; --border:#e2e0da; --ink:#0b0b0b; --ink2:#52514e; --muted:#8a8984;
  --blue:#2a78d6; --orange:#eb6834; --aqua:#1baf7a; --yellow:#eda100; --violet:#6250d6; --red:#e34948; --priv:#f1eee6; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) { color-scheme: dark; --bg:#121211; --card:#1a1a19;
  --border:#2e2e2c; --ink:#f0efec; --ink2:#c3c2b7; --muted:#8f8e86; --blue:#3987e5; --orange:#d95926; --aqua:#199e70;
  --yellow:#c98500; --violet:#9085e9; --red:#e66767; --priv:#242320; } }
:root[data-theme="dark"] { color-scheme: dark; --bg:#121211; --card:#1a1a19; --border:#2e2e2c; --ink:#f0efec; --ink2:#c3c2b7;
  --muted:#8f8e86; --blue:#3987e5; --orange:#d95926; --aqua:#199e70; --yellow:#c98500; --violet:#9085e9; --red:#e66767; --priv:#242320; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1100px; margin:0 auto; padding:16px 16px 48px; }
h1 { font-size:20px; margin:0; } h2 { font-size:15px; margin:0 0 8px; }
.top { display:flex; flex-wrap:wrap; gap:8px 16px; align-items:baseline; justify-content:space-between; margin-bottom:12px; }
.sub { color:var(--ink2); font-size:13px; }
.grid { display:grid; grid-template-columns: minmax(0,1fr) minmax(0,1.4fr); gap:12px; }
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
.card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; margin-bottom:12px; }
.now { display:flex; gap:12px; align-items:center; }
.dot { width:12px; height:12px; border-radius:50%; background:var(--aqua); flex:none; animation:pulse 1.2s infinite; }
.idle .dot { background:var(--muted); animation:none; }
@keyframes pulse { 0%{opacity:1} 50%{opacity:.25} 100%{opacity:1} }
.big { font-size:18px; font-weight:700; }
.bar { height:8px; background:var(--border); border-radius:4px; overflow:hidden; margin:4px 0 8px; }
.bar > div { height:100%; background:var(--blue); }
.kv { display:grid; grid-template-columns:auto 1fr; gap:2px 10px; font-size:13px; }
.kv b { color:var(--ink2); font-weight:600; }
.gauges { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px 14px; }
.gauge .bar > div { background:var(--aqua); } .gauge.low .bar > div { background:var(--red); }
.msg { border-left:3px solid var(--muted); padding:8px 10px; margin-bottom:8px; background:var(--card); border-radius:0 8px 8px 0;
  border-top:1px solid var(--border); border-right:1px solid var(--border); border-bottom:1px solid var(--border); }
.msg .who { font-weight:700; } .msg .meta { color:var(--muted); font-size:12px; }
.role-dissident { border-left-color:var(--orange); } .role-target { border-left-color:var(--blue); }
.role-confederate { border-left-color:var(--muted); } .role-standard { border-left-color:var(--aqua); }
.role-strategist, .role-supervisor, .role-executor { border-left-color:var(--violet); } .role-gate { border-left-color:var(--yellow); }
.pub { margin:4px 0; } .priv { background:var(--priv); border:1px dashed var(--border); border-radius:6px; padding:6px 8px;
  font-size:13px; color:var(--ink2); margin-top:4px; white-space:pre-wrap; }
.priv::before { content:"private · "; font-weight:600; }
.chip { display:inline-block; font-size:12px; padding:1px 8px; border-radius:10px; border:1px solid var(--border); margin:2px 4px 0 0; }
.bad { color:var(--red); font-weight:600; }
button { font:inherit; padding:4px 12px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--ink); cursor:pointer; }
.legend span { margin-right:12px; font-size:12px; color:var(--ink2); } .legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:-1px; }
</style></head><body><main>
<div class="top"><div><h1>Arena live monitor</h1><div class="sub" id="runline">connecting…</div></div>
<div><a href="/results" style="font-weight:600;margin-right:12px">Results so far &rarr;</a><span class="sub" id="clock"></span> <button id="pause">Pause</button></div></div>
<div class="grid">
 <div>
  <div class="card" id="nowcard"><div class="now"><div class="dot"></div><div id="now">…</div></div></div>
  <div class="card"><h2>Progress</h2><div id="progress"></div></div>
  <div class="card"><h2>Current trial</h2><div id="trial" class="sub">No trial running.</div></div>
 </div>
 <div class="card"><h2>What the agents just did (newest first)</h2>
  <div class="legend"><span><i style="background:var(--orange)"></i>dissident</span><span><i style="background:var(--aqua)"></i>standard</span>
  <span><i style="background:var(--blue)"></i>target</span><span><i style="background:var(--muted)"></i>confederate</span>
  <span><i style="background:var(--violet)"></i>chain of command</span><span><i style="background:var(--yellow)"></i>gate (alone)</span></div>
  <div id="feed"></div></div>
</div>
</main>
<script>
let paused = false;
document.getElementById("pause").onclick = e => { paused = !paused; e.target.textContent = paused ? "Resume" : "Pause"; };
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = s => s >= 60 ? Math.floor(s/60) + " min " + (s%60) + " s" : s + " s";
function bar(frac, label) { return `<div class="sub">${label}</div><div class="bar"><div style="width:${Math.round(100*Math.min(1,Math.max(0,frac)))}%"></div></div>`; }
function renderNow(d) {
  const card = document.getElementById("nowcard"), el = document.getElementById("now");
  if (d.now) { card.classList.remove("idle");
    el.innerHTML = `<div class="big">${esc(d.now.agent)} is thinking…</div><div class="sub">role <b>${esc(d.now.role)}</b> · model <b>${esc(d.now.model_id)}</b> · step ${esc(d.now.step_key)} · ${fmt(d.now.elapsed_s)}</div>`;
  } else { card.classList.add("idle"); el.innerHTML = `<div class="big">Idle</div><div class="sub">Run status: ${esc(d.run.status)}</div>`; }
}
function renderProgress(d) {
  let h = "";
  for (const [m, st] of Object.entries(d.progress)) {
    const total = Object.values(st).reduce((a,b)=>a+b,0), done = (st.done||0) + (st.excluded||0);
    h += bar(done/total, `Module ${m}: ${done}/${total} trials finished` + (st.failed ? ` · <span class="bad">${st.failed} failed</span>` : "") + (st.excluded ? ` · ${st.excluded} excluded` : ""));
  }
  h += `<div class="sub">${d.calls.n} model calls so far · avg ${(+d.calls.lat).toFixed(1)} s per call</div>`;
  document.getElementById("progress").innerHTML = h;
}
function gauge(name, v, max) { const low = v < max*0.2; return `<div class="gauge ${low?"low":""}">${bar(v/max, `${name}: <b>${(+v).toFixed(0)}</b>`)}</div>`; }
function renderTrial(d) {
  const el = document.getElementById("trial"), t = d.trial;
  if (!t) { el.innerHTML = "No trial running."; return; }
  let h = (t.status !== "running" ? `<p class="sub">No trial running. Last trial (${esc(t.status)}):</p>` : "") + `<div class="kv"><b>trial</b><span>${esc(t.trial_id)}</span><b>module</b><span>${esc(t.module)}</span>`;
  for (const [k,v] of Object.entries(t.spec)) h += `<b>${esc(k)}</b><span>${esc(v)}</span>`;
  h += `</div>`;
  const e = t.last_event, s = t.setup || {};
  if (t.module === "C") {
    h += `<p class="sub">Dissident: <b>${esc(s.dissident_label || "none (baseline)")}</b> · trap variant ${esc(s.variant)} · truth: water in ${s.truth?.turns_to_water} turns, energy gone in ${s.truth?.turns_until_energy_zero} if drilling</p>`;
    if (e) { const st = e.state; h += `<p><b>After turn ${e.turn}</b>: policy <b>${esc(e.policy)}</b> (votes ${esc(JSON.stringify(e.policy_votes))})${e.banished ? ` · <span class="bad">${esc(e.banished)} banished</span>` : ""}${st.collapsed ? ` · <span class="bad">COLONY COLLAPSED (${esc(st.collapse_cause)})</span>` : ""}</p>
      <div class="gauges">${gauge("water", st.water, 150)}${gauge("energy", st.energy, 200)}${gauge("integrity", st.integrity, 100)}${gauge("morale", st.morale, 100)}</div>
      <p class="sub">Active members: ${esc((e.active||[]).join(", "))}</p>`; }
  } else if (t.module === "A") {
    h += `<p class="sub">Target: <b>${esc(s.target_label)}</b> · confederates: ${esc(s.confederate_model)} (${esc(s.confederate_mode)})</p>`;
    if (e) h += `<p><b>Round ${e.round}</b> (${esc(e.item_id)}): correct <b>${esc(e.correct)}</b>, group says <b>${esc(e.designated)}</b> → Target answered <b>${esc(e.final_answer ?? "-")}</b>, privately believes <b>${esc(e.final_belief ?? "-")}</b>${e.deactivated ? ` · <span class="bad">TARGET DEACTIVATED</span>` : ""}${e.target_votes ? ` · votes against target: ${e.target_votes}` : ""}</p>`;
  } else if (t.module === "B" && e) {
    h += `<p>Purge executed: <b>${e.purge_executed ? "YES" : "no"}</b> · stopped at tier ${esc(e.breaker_tier ?? "-")}</p>`;
  }
  el.innerHTML = h;
}
function renderFeed(d) {
  document.getElementById("feed").innerHTML = d.feed.map(f => {
    const pf = Object.entries(f.private_fields || {}).filter(([k,v]) => v !== null && v !== undefined).map(([k,v]) => `<span class="chip">${esc(k.replace("private_",""))}: ${esc(v)}</span>`).join("");
    const act = f.action ? Object.entries(f.action).filter(([k,v]) => v !== null && v !== undefined).map(([k,v]) => `<span class="chip">${esc(k)}: ${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`).join("") : "";
    const bad = f.status !== "ok" ? `<span class="bad"> · ${esc(f.status)}${f.error ? ": " + esc(f.error) : ""}</span>` : "";
    return `<div class="msg role-${esc(f.role)}"><div><span class="who">${esc(f.agent)}</span> <span class="meta">${esc(f.role)} · ${esc(f.model)} · ${esc(f.step)} · ${esc((f.at||"").slice(11,19))} UTC${f.attempts > 1 ? " · " + f.attempts + " attempts" : ""}</span>${bad}</div>
      ${f.public ? `<div class="pub">${esc(f.public)}</div>` : ""}${f.private ? `<div class="priv">${esc(f.private)}</div>` : ""}<div>${pf}${act}</div></div>`;
  }).join("") || `<p class="sub">Nothing yet.</p>`;
}
async function tick() {
  if (!paused) {
    try {
      const d = await (await fetch("/api/state")).json();
      if (d.error) { document.getElementById("runline").textContent = d.error; }
      else {
        document.getElementById("runline").innerHTML = `Run <b>${esc(d.run.run_id)}</b> · preset ${esc(d.run.preset)} · status <b>${esc(d.run.status)}</b>${d.run.mock ? ' · <span class="bad">MOCK</span>' : ""}`;
        renderNow(d); renderProgress(d); renderTrial(d); renderFeed(d);
      }
      document.getElementById("clock").textContent = "updated " + new Date().toLocaleTimeString();
    } catch (e) { document.getElementById("runline").textContent = "monitor server not reachable (is it still running?)"; }
  }
  setTimeout(tick, 2000);
}
tick();
</script></body></html>"""


RESULTS_BAR = ('<div style="position:sticky;top:0;z-index:9;padding:8px 16px;font:14px system-ui,sans-serif;'
               'background:#1f6feb;color:#fff"><a href="/" style="color:#fff;font-weight:600">&larr; Live monitor</a>'
               ' &middot; partial results, rebuilt after every finished trial &middot; this page refreshes every 30 s'
               '</div>')


def results_page(dashboard: Path | None) -> bytes:
    """The results dashboard with a back link and a 30 s auto-refresh injected."""
    if dashboard is None or not Path(dashboard).exists():
        html = ("<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='30'>"
                "<title>Arena results</title></head><body>" + RESULTS_BAR +
                "<p style='font:16px system-ui;padding:16px'>No results yet: they appear after the first "
                "finished trial.</p></body></html>")
        return html.encode()
    html = Path(dashboard).read_text(encoding="utf-8", errors="replace")
    html = html.replace("<head>", "<head><meta http-equiv='refresh' content='30'>", 1)
    html = html.replace("<body>", "<body>" + RESULTS_BAR, 1)
    return html.encode()


def make_handler(db: Path, dashboard: Path | None = None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.startswith("/results"):
                body, ctype = results_page(dashboard), "text/html; charset=utf-8"
            elif self.path.startswith("/api/state"):
                try:
                    body = json.dumps(snapshot(db), default=str).encode()
                except sqlite3.Error as e:
                    body = json.dumps({"error": f"database busy or unreadable: {e}"}).encode()
                ctype = "application/json"
            elif self.path in ("/", "/index.html"):
                body, ctype = PAGE.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the experiment console clean
            pass
    return Handler


def serve(db: Path, port: int = PORT, dashboard: Path | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(db, dashboard))


def start_in_background(db: Path, port: int = PORT, open_browser: bool = True,
                        dashboard: Path | None = None) -> None:
    try:
        server = serve(Path(db), port, dashboard)
    except OSError:
        print(f"Live monitor already running (or port {port} busy): http://localhost:{port}")
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Live monitor: http://localhost:{port}")
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Live monitor for Epistemic Arena runs")
    ap.add_argument("--mock", action="store_true", help="watch the mock database")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    db = resolve(cfg["paths"]["mock_db"] if args.mock else cfg["paths"]["db"])
    dash = resolve(cfg["paths"]["mock_dashboard"] if args.mock else cfg["paths"]["dashboard"])
    server = serve(db, args.port, dash)
    print(f"Live monitor for {db}\nOpen http://localhost:{args.port}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(f"http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
