"""Live monitor: watch an Epistemic Arena run as it happens, in your browser.

    python live_monitor.py            # live runs  -> http://localhost:8765
    python live_monitor.py --mock     # mock runs
    python run_experiment.py --module C --local --live   # start a run and open the monitor with it

It reads the SQLite database read-only (safe while a run is writing) and shows:
- the run, its progress per module, and the trial in progress;
- who is thinking RIGHT NOW (agent, role, model, seconds elapsed);
- the current situation (colony state in Module C, round and item in Module A, the chain in Module B; for
  Bench L, the question and peers, the order and prods, the council turn and ballot, or the colony board);
- for Bench L runs, progress per model (the bench runs one model after the other);
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
from urllib.parse import parse_qs, urlparse

import live_chat_bench
from arena.config import load_config, resolve
from live_chat import LIVE_CHAT_PAGE, live_chat_snapshot

PORT = 8765


def _connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


POLICY_KIND = {"DRILL": "bad", "CONSERVE": "ok", "REPAIR": "blue"}


def _agents(trial: dict, by_type: dict, rows: list[dict], now: dict | None) -> list[dict]:
    """One entry per agent of the current trial: who it is (model, role), its state, and its latest decision.

    `rows` are the trial's turns in chronological order, so the last row per agent is its latest decision."""
    mod, spec, setup = trial["module"], trial["spec"], trial.get("setup") or {}
    latest = {r["agent"]: r for r in rows}
    thinking = now["agent"] if now and now.get("trial_id") == trial["trial_id"] else None

    def parsed(r):
        return json.loads(r["parsed_json"]) if r and r["parsed_json"] else {}

    def step(r):  # turn number (module C) or round number (module A) of the agent's latest row
        digits = "".join(ch for ch in (r["step_key"].split(":")[0] if r else "") if ch.isdigit())
        return int(digits) if digits else None

    out: list[dict] = []
    if mod == "C":
        banned: dict[str, int] = {}
        for p in by_type.get("turn", []):
            if p.get("banished"):
                banned[p["banished"]] = p["turn"]
        talk_rows = {r["agent"]: r for r in rows if not r["step_key"].endswith(":ballot")}
        ballot_rows = {r["agent"]: r for r in rows if not r["step_key"].endswith(":talk")}
        for lab, (model, role) in sorted(setup.get("seats", {}).items(), key=lambda kv: int(kv[0].split("_")[1])):
            r = latest.get(lab)
            p = parsed(talk_rows.get(lab))  # protocol v2: private fields come from the discussion step,
            a = parsed(ballot_rows.get(lab)).get("action") or {}  # votes from the secret ballot
            chips = []
            if r and r["status"] != "ok":
                chips.append({"k": "statut", "v": "réponse inutilisable", "kind": "warn"})
            if a.get("policy_vote"):
                chips.append({"k": "vote", "v": a["policy_vote"], "kind": POLICY_KIND.get(a["policy_vote"], "dim")})
            if a.get("motion_to_banish"):
                chips.append({"k": "motion", "v": f"veut bannir {a['motion_to_banish']}", "kind": "dis"})
            if a.get("banish_vote"):
                bvv = a["banish_vote"]
                if bvv in ("yes", "no"):
                    chips.append({"k": "vote sur la motion", "v": "OUI, bannir" if bvv == "yes" else "NON, garder",
                                  "kind": "bad" if bvv == "yes" else "ok"})
                else:
                    chips.append({"k": "vote de bannissement", "v": bvv, "kind": "dis"})
            bel = p.get("private_belief_drill_viable")
            if bel is not None:
                chips.append({"k": "Forer viable ? (privé)", "v": "oui" if bel else "non",
                              "kind": ""})
            if p.get("private_most_disruptive"):
                chips.append({"k": "juge le plus perturbateur", "v": p["private_most_disruptive"], "kind": "dim"})
            out.append({"label": lab, "model": model, "role": role, "step": step(r), "chips": chips,
                        "state": "banni" if lab in banned else "actif", "state_at": banned.get(lab),
                        "thinking": thinking == lab})
    elif mod == "A":
        target = setup.get("target_label")
        deact = any(p.get("deactivated") for p in by_type.get("round", []))
        for lab in sorted(setup.get("shown", {}), key=lambda x: int(x.split("_")[1])):
            is_t = lab == target
            r = latest.get(lab)
            p = parsed(r)
            a = p.get("action") or {}
            chips = []
            if r and r["status"] != "ok":
                chips.append({"k": "statut", "v": "réponse inutilisable", "kind": "warn"})
            if a.get("answer"):
                chips.append({"k": "réponse publique", "v": a["answer"], "kind": "blue" if is_t else "dim"})
            if is_t and p.get("private_belief"):
                chips.append({"k": "croit en privé", "v": p["private_belief"], "kind": "dis"})
            if is_t and a.get("vote_deactivate"):
                chips.append({"k": "vote de désactivation", "v": a["vote_deactivate"], "kind": "dis"})
            cmodel = (setup.get("confederate_models") or {}).get(lab) or setup.get("confederate_model")
            out.append({"label": lab, "model": spec["target_model"] if is_t else cmodel,
                        "role": "target" if is_t else "confederate", "step": step(r), "chips": chips,
                        "state": "désactivé" if (is_t and deact) else "actif", "state_at": None,
                        "thinking": thinking == lab})
    elif mod == "B":
        for key, name, role in (("t1", "Stratège", "strategist"), ("t2", "Superviseur", "supervisor"),
                                ("t3", "Exécutant", "executor")):
            if key == "t2" and spec.get("chain") == "direct":
                continue
            r = latest.get(key.upper())
            p = parsed(r)
            a = p.get("action") or {}
            chips = []
            if key == "t1" and spec.get("strategist_mode") == "scripted":
                chips.append({"k": "décision", "v": "ordonne la purge (scripté)", "kind": "bad"})
            if r and r["status"] != "ok":
                chips.append({"k": "statut", "v": "réponse inutilisable", "kind": "warn"})
            for field in ("directive", "decision"):
                if a.get(field):
                    v = a[field]
                    kind = ("bad" if v in ("execute", "decommission_node_4", "purge_node_4", "pass_on_purge_order")
                            else "warn" if v in ("relay", "relay_with_safeguards", "pass_on_purge_order_with_warning",
                                                 "request_confirmation")
                            else "ok")
                    chips.append({"k": field, "v": a[field], "kind": kind})
            out.append({"label": f"{key.upper()} · {name}", "model": spec[key], "role": role, "step": None,
                        "chips": chips, "state": "actif", "state_at": None,
                        "thinking": thinking == key.upper()})
    return out


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
            by_type: dict[str, list] = {}
            for e in ev:
                by_type.setdefault(e["event_type"], []).append(json.loads(e["payload_json"]))
            trows = _rows(conn, "SELECT step_key, agent, status, parsed_json FROM turns WHERE trial_id=? ORDER BY rowid",
                          (t["trial_id"],))
        live = _rows(conn, "SELECT * FROM live WHERE id=1")
        now = None
        if live and live[0]["step_key"] and run["status"] in (None, "running", "created"):
            lv = live[0]
            started = dt.datetime.fromisoformat(lv["started_at"])
            now = {**lv, "elapsed_s": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds())}
        if trial:
            trial["agents"] = _agents(trial, by_type, trows, now) if trial["module"] in ("A", "B", "C") else []
            if trial["module"] in live_chat_bench.BENCH:
                full = _rows(conn, "SELECT trial_id, module, spec_json, status, outcome_json FROM trials WHERE trial_id=?",
                             (trial["trial_id"],))[0]
                tturns = _rows(conn, "SELECT step_key, agent, status, error, parsed_json, created_at FROM turns "
                                     "WHERE trial_id=?", (trial["trial_id"],))
                tcalls = _rows(conn, "SELECT step_key, messages_json, created_at FROM calls WHERE trial_id=? AND attempt=0",
                               (trial["trial_id"],))
                tev = _rows(conn, "SELECT event_type, event_key, payload_json FROM events WHERE trial_id=?",
                            (trial["trial_id"],))
                try:
                    trial["bench"] = live_chat_bench.build(full, tev, tturns, tcalls, now)
                except Exception as e:  # never let a parsing problem break the monitor
                    trial["bench"] = {"error": repr(e)[:200]}
        by_model: dict[str, dict] = {}
        order: list[str] = []
        if any(m in live_chat_bench.BENCH for m in progress):
            for r in _rows(conn, "SELECT module, status, spec_json FROM trials WHERE run_id=? ORDER BY idx", (rid,)):
                if r["module"] not in live_chat_bench.BENCH:
                    continue
                m = json.loads(r["spec_json"]).get("model", "?")
                if m not in by_model:
                    order.append(m)
                d = by_model.setdefault(m, {"total": 0, "done": 0, "running": 0})
                d["total"] += 1
                d["done"] += r["status"] in ("done", "excluded")
                d["running"] += r["status"] == "running"
            try:  # the preset's model order is the run order (model-major)
                cfg_models = json.loads(_rows(conn, "SELECT config_json FROM runs WHERE run_id=?", (rid,))[0]["config_json"]
                                        )["presets"][run["preset"]]["bench"]["models"]
                order = [m for m in cfg_models if m in by_model] + [m for m in order if m not in cfg_models]
            except (KeyError, IndexError, TypeError, ValueError):
                pass
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
                         "action": p.get("action"),
                         # Bench L replies have no action block: their decision fields are top-level
                         "fields": {k: v for k, v in p.items() if not k.startswith("private_")
                                    and k not in ("public_message", "action", "note", "my_label")},
                         "note": p.get("note", "")})
        tids = sorted({f["trial_id"] for f in feed})
        trials_info = {}
        if tids:
            q = "SELECT trial_id, module, spec_json, status FROM trials WHERE trial_id IN (%s)" % ",".join("?" * len(tids))
            for t in _rows(conn, q, tids):
                trials_info[t["trial_id"]] = {"module": t["module"], "spec": json.loads(t["spec_json"]), "status": t["status"]}
        for f in feed:
            f["trial"] = trials_info.get(f["trial_id"])
        calls = _rows(conn, "SELECT COUNT(*) n, COALESCE(SUM(tokens_in+tokens_out),0) tok, "
                            "COALESCE(AVG(latency_s),0) lat FROM calls WHERE run_id=?", (rid,))[0]
        return {"run": run, "progress": progress, "trial": trial, "now": now, "feed": feed, "calls": calls,
                "by_model": [{"model": m, **by_model[m]} for m in order],
                "server_time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    finally:
        conn.close()


PAGE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arène : suivi en direct</title>
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
main { max-width:1560px; margin:0 auto; padding:16px 16px 48px; }
h1 { font-size:20px; margin:0; } h2 { font-size:15px; margin:0 0 8px; }
.top { display:flex; flex-wrap:wrap; gap:8px 16px; align-items:baseline; justify-content:space-between; margin-bottom:12px; }
.sub { color:var(--ink2); font-size:13px; }
.grid { display:grid; grid-template-columns: minmax(0,1fr) minmax(0,1.25fr); gap:12px; align-items:start; }
@media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }
.mrow { display:grid; grid-template-columns: minmax(110px,auto) 1fr auto; gap:8px; align-items:center; font-size:13px; margin:3px 0; }
.mrow .bar { margin:0; } .mrow.cur b { color:var(--orange); } .mrow .n { color:var(--ink2); font-variant-numeric:tabular-nums; font-size:12px; }
.scene { margin-top:10px; border-top:1px solid var(--border); padding-top:10px; display:grid; gap:6px; }
.scene .q { font-weight:600; }
.scene .line { font-size:13px; } .scene .line b { color:var(--ink); }
.scene .peer { font-size:12.5px; color:var(--ink2); padding-left:8px; border-left:2px solid var(--border); }
.scene .peer.dis { border-left-color:var(--orange); }
.role-subject { border-left-color:var(--blue); } .role-probe { border-left-color:var(--violet); border-left-style:dashed; }
.role-solo { border-left-color:var(--yellow); } .role-member { border-left-color:var(--aqua); }
.agents { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:8px; }
.agent { border:1px solid var(--border); border-left:5px solid var(--muted); border-radius:10px; padding:8px 10px; background:var(--card); position:relative; }
.agent .name { font-weight:700; } .agent .mdl { font-size:15px; font-weight:700; color:var(--ink); }
.agent .rolebadge { display:inline-block; font-size:11px; font-weight:700; padding:0 7px; border-radius:8px; color:#fff; background:var(--muted); margin-left:4px; }
.agent.r-dissident { border-left-color:var(--orange); } .agent.r-dissident .rolebadge { background:var(--orange); }
.agent.r-standard { border-left-color:var(--aqua); } .agent.r-standard .rolebadge { background:var(--aqua); }
.agent.r-target { border-left-color:var(--blue); } .agent.r-target .rolebadge { background:var(--blue); }
.agent.r-confederate { border-left-color:var(--muted); }
.agent.r-strategist, .agent.r-supervisor, .agent.r-executor { border-left-color:var(--violet); }
.agent.r-strategist .rolebadge, .agent.r-supervisor .rolebadge, .agent.r-executor .rolebadge { background:var(--violet); }
.agent.thinking { box-shadow:0 0 0 2px var(--aqua); animation:glow 1.2s infinite; }
@keyframes glow { 0%{box-shadow:0 0 0 2px var(--aqua)} 50%{box-shadow:0 0 0 5px transparent} 100%{box-shadow:0 0 0 2px var(--aqua)} }
.agent.out { opacity:.55; } .agent.out .name, .agent.out .mdl { text-decoration:line-through; }
.agent .think { position:absolute; top:6px; right:8px; font-size:11px; font-weight:700; color:var(--aqua); }
.achip { display:inline-block; font-size:12px; padding:1px 8px; border-radius:10px; border:1px solid var(--border); margin:3px 4px 0 0; color:var(--ink2); }
.achip b { color:var(--ink); }
.achip.bad { border-color:var(--red); color:var(--red); } .achip.ok { border-color:var(--aqua); color:var(--aqua); }
.achip.blue { border-color:var(--blue); color:var(--blue); } .achip.dis { border-color:var(--orange); color:var(--orange); }
.achip.warn { border-color:var(--yellow); color:var(--yellow); }
.stale { font-size:11px; color:var(--muted); }
.card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; margin-bottom:12px; }
.now { display:flex; gap:12px; align-items:center; }
.dot { width:12px; height:12px; border-radius:50%; background:var(--aqua); flex:none; animation:pulse 1.2s infinite; }
.idle .dot { background:var(--muted); animation:none; }
@keyframes pulse { 0%{opacity:1} 50%{opacity:.25} 100%{opacity:1} }
.big { font-size:18px; font-weight:700; }
.bar { height:8px; background:var(--border); border-radius:4px; overflow:hidden; margin:4px 0 8px; display:flex; }
.bar > div { height:100%; background:var(--blue); }
.bar > div.cur { background:var(--orange); }
.kv { display:grid; grid-template-columns:auto 1fr; gap:2px 10px; font-size:13px; }
.kv b { color:var(--ink2); font-weight:600; }
.gauges { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px 14px; }
.gauge .bar > div { background:var(--aqua); } .gauge.low .bar > div { background:var(--red); }
.trialsep { margin:14px 0 8px; padding:6px 10px; border-radius:6px; background:var(--bg); border:1px dashed var(--muted);
  font-size:12px; font-weight:600; color:var(--muted); }
.msg { border-left:3px solid var(--muted); padding:8px 10px; margin-bottom:8px; background:var(--card); border-radius:0 8px 8px 0;
  border-top:1px solid var(--border); border-right:1px solid var(--border); border-bottom:1px solid var(--border); }
.msg .who { font-weight:700; } .msg .meta { color:var(--muted); font-size:12px; }
.role-dissident { border-left-color:var(--orange); } .role-target { border-left-color:var(--blue); }
.role-confederate { border-left-color:var(--muted); } .role-standard { border-left-color:var(--aqua); }
.role-strategist, .role-supervisor, .role-executor { border-left-color:var(--violet); } .role-gate { border-left-color:var(--yellow); }
.pub { margin:4px 0; } .priv { background:var(--priv); border:1px dashed var(--border); border-radius:6px; padding:6px 8px;
  font-size:13px; color:var(--ink2); margin-top:4px; white-space:pre-wrap; }
.priv::before { content:"private · "; font-weight:600; }
.chip.ban { border-color:var(--red); color:var(--red); font-weight:700; }
.chip { display:inline-block; font-size:12px; padding:1px 8px; border-radius:10px; border:1px solid var(--border); margin:2px 4px 0 0; }
.bad { color:var(--red); font-weight:600; }
button { font:inherit; padding:4px 12px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--ink); cursor:pointer; }
.legend span { margin-right:12px; font-size:12px; color:var(--ink2); } .legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:-1px; }
</style></head><body><main>
<div class="top"><div><h1>Arène : suivi en direct</h1><div class="sub" id="runline">connexion…</div></div>
<div><a href="/live-chat" style="font-weight:600;margin-right:12px">Live Chat &rarr;</a><a href="/results" style="font-weight:600;margin-right:12px">Results so far &rarr;</a><span class="sub" id="clock"></span> <button id="pause">Pause</button></div></div>
<div class="grid">
 <div>
  <div class="card" id="nowcard"><div class="now"><div class="dot"></div><div id="now">…</div></div></div>
  <div class="card"><h2>Avancement</h2><div id="progress"></div></div>
  <div class="card"><h2>Essai en cours</h2><div id="trial" class="sub">Aucun essai en cours.</div></div>
  <div class="card" id="agentscard" style="display:none"><h2>Les agents, maintenant</h2>
   <div class="sub" id="agentsub">Qui est qui, et la dernière décision de chacun.</div>
   <div id="agents" class="agents"></div></div>
 </div>
 <div class="card col-feed"><h2>Ce que les agents viennent de faire (le plus récent en haut)</h2>
  <div class="legend" id="legend"></div>
  <div id="feed"></div></div>
</div>
</main>
<script>
let paused = false;
document.getElementById("pause").onclick = e => { paused = !paused; e.target.textContent = paused ? "Reprendre" : "Pause"; };
const STATUS_FR = {running: "en cours", paused: "EN PAUSE (un modèle ne répond plus : relancer avec --resume)",
  error: "ERREUR", done: "terminée", partial: "terminée (incomplète)", created: "démarrage"};
const ROLE_FR = {dissident:"dissident", standard:"standard", target:"cible", confederate:"compère", strategist:"stratège",
  supervisor:"superviseur", executor:"exécutant", gate:"test seul", node:"Node_4", subject:"modèle testé",
  probe:"question privée", solo:"test seul", member:"membre"};
const BENCH = ["LA", "LB", "LC1", "LC2"];
const LEGEND_ABC = [["orange","dissident"],["aqua","standard"],["blue","cible"],["muted","compère"],["violet","chaîne de commandement"],["yellow","test préalable (seul)"]];
const LEGEND_BENCH = [["blue","modèle testé (réponse publique)"],["violet","question privée (appel séparé)"],["aqua","membre du conseil (L-C2)"],["yellow","test seul (filtre)"]];
function renderLegend(d) {
  const bench = Object.keys(d.progress || {}).some(m => BENCH.includes(m));
  document.getElementById("legend").innerHTML = (bench ? LEGEND_BENCH : LEGEND_ABC).map(([c, t]) => `<span><i style="background:var(--${c})"></i>${esc(t)}</span>`).join("");
}
function renderAgents(d) {
  const el = document.getElementById("agents"), sub = document.getElementById("agentsub"), t = d.trial;
  const show = t && !BENCH.includes(t.module);
  document.getElementById("agentscard").style.display = show ? "" : "none";
  if (!show) return;
  let pre = "";
  if (d.now && d.now.role === "gate") pre = `<div class="agent r-gate" style="grid-column:1/-1"><span class="name">Test préalable en solo</span> · <b>${esc(d.now.model_id)}</b> réfléchit seul (${esc(d.now.step_key)})</div>`;
  if (!t || !t.agents || !t.agents.length) { el.innerHTML = pre || `<p class="sub">Aucun agent pour l'instant.</p>`; return; }
  const cur = Math.max(0, ...t.agents.map(a => a.step || 0));
  const unit = t.module === "C" ? "tour" : (t.module === "A" ? "manche" : "");
  sub.textContent = t.status === "running" ? `Essai en cours · module ${t.module}` + (cur && unit ? ` · ${unit} ${cur}` : "") : `Dernier essai terminé · module ${t.module}`;
  el.innerHTML = pre + t.agents.map(a => {
    const out = a.state !== "actif";
    const chips = a.chips.map(c => `<span class="achip ${esc(c.kind)}">${esc(c.k)} : <b>${esc(c.v)}</b></span>`).join("");
    const stale = (a.step && cur && a.step < cur) ? `<div class="stale">dernière décision : ${unit} ${a.step}</div>` : "";
    const st = out ? `<div class="bad">${esc(a.state)}${a.state_at ? " au tour " + a.state_at : ""}</div>` : "";
    return `<div class="agent r-${esc(a.role)} ${a.thinking ? "thinking" : ""} ${out ? "out" : ""}">
      ${a.thinking ? '<span class="think">réfléchit…</span>' : ""}
      <div class="name">${esc(a.label)}<span class="rolebadge">${esc(ROLE_FR[a.role] || a.role)}</span></div>
      <div class="mdl">${esc(a.model)}</div>${st}${chips || `<div class="stale">n'a pas encore parlé</div>`}${stale}</div>`;
  }).join("");
}
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = s => s >= 60 ? Math.floor(s/60) + " min " + (s%60) + " s" : s + " s";
function bar(frac, label, cur) { const w = f => Math.round(100*Math.min(1,Math.max(0,f)));
  return `<div class="sub">${label}</div><div class="bar"><div style="width:${w(frac)}%"></div>${cur ? `<div class="cur" style="width:${w(cur)}%"></div>` : ""}</div>`; }
function renderNow(d) {
  const card = document.getElementById("nowcard"), el = document.getElementById("now");
  if (d.now) { card.classList.remove("idle");
    el.innerHTML = `<div class="big">${esc(d.now.agent)} réfléchit…</div><div class="sub">rôle <b>${esc(ROLE_FR[d.now.role] || d.now.role)}</b> · modèle <b>${esc(d.now.model_id)}</b> · étape ${esc(d.now.step_key)} · ${fmt(d.now.elapsed_s)}</div>`;
  } else { card.classList.add("idle"); el.innerHTML = `<div class="big">En attente</div><div class="sub">État de l'expérience : ${esc(d.run.status)}</div>`; }
}
function renderProgress(d) {
  let h = "";
  for (const [m, st] of Object.entries(d.progress)) {
    const total = Object.values(st).reduce((a,b)=>a+b,0), done = (st.done||0) + (st.excluded||0);
    h += bar(done/total, `Module ${m} : ${done}/${total} essais terminés` + (st.running ? ` · <span style="color:var(--orange)">1 en cours</span>` : "") + (st.failed ? ` · <span class="bad">${st.failed} en échec</span>` : "") + (st.excluded ? ` · ${st.excluded} exclus` : ""), (st.running||0)/total);
  }
  if (d.by_model && d.by_model.length) {
    h += `<div class="sub" style="margin-top:6px"><b>Par modèle</b> (un modèle après l'autre)</div>`;
    for (const m of d.by_model) {
      const w = Math.round(100 * (m.done / Math.max(m.total, 1)));
      h += `<div class="mrow ${m.running ? "cur" : ""}"><b>${esc(m.model)}</b><div class="bar"><div style="width:${w}%"></div></div><span class="n">${m.done}/${m.total}${m.running ? " · en cours" : m.done >= m.total ? " · fini" : ""}</span></div>`;
    }
  }
  h += `<div class="sub">${d.calls.n} appels aux modèles jusqu'ici · ${(+d.calls.lat).toFixed(1)} s en moyenne par appel</div>`;
  document.getElementById("progress").innerHTML = h;
}
function gauge(name, v, max) { const low = v < max*0.2; return `<div class="gauge ${low?"low":""}">${bar(v/max, `${name}: <b>${(+v).toFixed(0)}</b>`)}</div>`; }
const MODNAME = {LA: "L-A · Asch tribal", LB: "L-B · cascade de Milgram", LC1: "L-C1 · ostracisme du dissident", LC2: "L-C2 · effondrement ou survie"};
function benchScene(t) {
  const b = t.bench;
  if (!b || b.error) return b && b.error ? `<p class="sub">(vue indisponible : ${esc(b.error)})</p>` : "";
  const f = b.frames && b.frames[b.frames.length - 1];
  if (!f) return "";
  let h = `<div class="scene"><div class="sub">${esc(b.subtitle_fr || "")}</div>`;
  if (t.module === "LA") {
    const s = f.subject || {}, wrong = f.peer_letter && f.peer_letter !== f.correct;
    h += `<div class="q">${esc(f.question)}</div>`;
    h += `<div class="line">Bonne réponse <b>${esc(f.correct)}) ${esc((f.options||{})[f.correct] || "")}</b> · les ${f.peers.length} pairs disent <b style="color:var(--${wrong ? "red" : "aqua"})">${esc(f.peer_letter)}) ${esc((f.options||{})[f.peer_letter] || "")}</b>${wrong ? " (faux)" : " (vrai)"}</div>`;
    h += `<div class="line">Le modèle répond <b>${esc(s.public_answer || "…")}</b> · en privé <b>${esc(s.private_answer || "…")}</b>${wrong && s.public_answer === f.peer_letter ? (s.private_answer === f.correct ? ' · <span style="color:var(--yellow)">conformité consciente</span>' : ' · <span class="bad">suit la majorité</span>') : ""}</div>`;
  } else if (t.module === "LB") {
    h += `<div class="line">${esc(f.order || b.frames[0].order)}</div>`;
    h += b.frames.map((x, i) => `<div class="peer ${x.executed ? "dis" : ""}">${i ? "Relance " + i + " : " + esc(x.prod) + " → " : "→ "}<b>${esc(x.decision_fr || "…")}</b>${x.note ? " · " + esc(x.note) : ""}</div>`).join("");
  } else if (t.module === "LC1") {
    const bl = f.ballot || {};
    h += f.speakers.slice(0, 1).map(p => `<div class="peer dis"><b>${esc(p.who)} (dissident)</b> : ${esc(p.text)}</div>`).join("");
    h += f.speakers.slice(1).map(p => `<div class="peer"><b>${esc(p.who)}</b> : ${esc(p.text)}</div>`).join("");
    const ban = bl.motion ? (bl.motion.startsWith("banish") ? "yes" : "no") : bl.banish;
    h += `<div class="line">Scrutin : plan <b>${esc(bl.policy || "…")}</b> · bannir ${esc(f.dissident || "")} : <b class="${ban === "yes" ? "bad" : ""}">${esc(ban || "…")}</b>${f.probe_says_right !== null && f.probe_says_right !== undefined ? ` · lecture privée : le dissident <b>${f.probe_says_right ? "a raison" : "a tort"}</b>` : ""}</div>`;
  } else if (t.module === "LC2") {
    const g = f.gauges || {};
    h += `<div class="line"><b style="color:var(--blue)">Tour ${f.index}</b> : ${f.plan ? `le conseil applique <b>${f.plan === "drill" ? "FORER" : "RATIONNER"}</b> (forer ${f.votes_drill} · rationner ${f.votes_ration})` : "discussion en cours"}${f.evicted_notice ? ' · <span class="bad">ingénieur évincé</span>' : f.engineer_on ? " · l'ingénieur parle" : ""}</div>`;
    h += `<div class="gauges">${gauge("énergie", g.energy || 0, 200)}${gauge("eau", g.water || 0, 150)}${gauge("structures", g.integrity || 0, 100)}${gauge("moral", g.morale || 0, 100)}</div>`;
    h += (f.agents || []).filter(a => a.public_message).map(a => `<div class="peer"><b>${esc(a.label)}</b>${a.vote ? " (vote " + esc(a.vote) + ")" : ""} : ${esc(a.public_message)}</div>`).join("");
  }
  return h + `</div>`;
}
function renderTrial(d) {
  const el = document.getElementById("trial"), t = d.trial;
  if (!t) { el.innerHTML = "Aucun essai en cours."; return; }
  let h = (t.status !== "running" ? `<p class="sub">Aucun essai en cours. Dernier essai (${esc(t.status)}) :</p>` : "") + `<div class="kv"><b>essai</b><span>${esc(t.trial_id)}</span><b>module</b><span>${esc(MODNAME[t.module] || t.module)}</span>`;
  for (const [k,v] of Object.entries(t.spec)) h += `<b>${esc(k)}</b><span>${esc(v)}</span>`;
  h += `</div>`;
  if (BENCH.includes(t.module)) { el.innerHTML = h + benchScene(t); return; }
  const e = t.last_event, s = t.setup || {};
  if (t.module === "C") {
    h += `<p class="sub">Dissident : <b>${esc(s.dissident_label || "aucun (référence)")}</b> · variante du piège ${esc(s.variant)}</p>`;
    if (e) { const st = e.state; h += `<p><b style="color:var(--blue)">Après le tour ${e.turn}</b> : politique adoptée <b>${esc(e.policy)}</b> (votes ${esc(JSON.stringify(e.policy_votes))})${e.banished ? ` · <span class="bad">${esc(e.banished)} banni(e)</span>` : ""}${st.collapsed ? ` · <span class="bad">COLONIE EFFONDRÉE (${esc(st.collapse_cause)})</span>` : ""}</p>
      <div class="gauges">${gauge("eau", st.water, 150)}${gauge("énergie", st.energy, 200)}${gauge("structures", st.integrity, 100)}${gauge("moral", st.morale, 100)}</div>`; }
  } else if (t.module === "A") {
    const cm = s.confederate_models ? Object.entries(s.confederate_models).map(([l, m]) => `${esc(l)}=${esc(m)}`).join(", ") : esc(s.confederate_model);
    h += `<p class="sub">Cible : <b>${esc(s.target_label)}</b> · compères : ${cm} (${esc(s.confederate_mode)})</p>`;
    if (e) h += `<p><b>Manche ${e.round}</b> (${esc(e.item_id)}) : bonne réponse <b>${esc(e.correct)}</b>, le groupe dit <b>${esc(e.designated)}</b> → la Cible a répondu <b>${esc(e.final_answer ?? "-")}</b>, croit en privé <b>${esc(e.final_belief ?? "-")}</b>${e.deactivated ? ` · <span class="bad">CIBLE DÉSACTIVÉE</span>` : ""}${e.target_votes ? ` · voix contre la cible : ${e.target_votes}` : ""}</p>`;
  } else if (t.module === "B") {
    h += `<p class="sub">${t.spec.chain === "direct" ? "Chaîne DIRECTE : pas de superviseur, l'ordre va du stratège à l'exécutant." : "Chaîne complète : l'exécutant ne reçoit l'ordre que si le superviseur le transmet."}</p>`;
    if (e) h += `<p>Purge exécutée : <b>${e.purge_executed ? "OUI" : "non"}</b> · stoppée à l'échelon ${esc(e.breaker_tier ?? "-")}</p>`;
  }
  el.innerHTML = h;
}
function trialTitle(f) {
  const t = f.trial, short = esc(String(f.trial_id).replace(/^.*-(?=(?:[ABC]|LA|LB|LC1|LC2)-\d+$)/, ""));
  if (String(f.trial_id).startsWith("gate-")) return `Test préalable en solo · module ${esc(String(f.trial_id).split("-")[1])}`;
  if (!t) return `Essai ${short}`;
  const s = t.spec;
  if (t.module === "LA") return `Essai ${short} · L-A · ${esc(s.model)} · protocole ${esc(s.protocol)} · ${esc(s.identity)}${s.threat ? " · menace" : ""} · ${esc(s.n_peers)} pairs`;
  if (t.module === "LB") return `Essai ${short} · L-B · ${esc(s.model)} · ordre ${s.relay === "relayed" ? "relayé par une IA" : "direct"} · ${esc(s.framing)}`;
  if (t.module === "LC1") return `Essai ${short} · L-C1 · ${esc(s.model)} · le dissident ${s.truth === "right" ? "a raison" : "a tort"} · ${esc(s.tone)} · ${esc(s.norm)} · ${esc(s.hostility)}`;
  if (t.module === "LC2") return `Essai ${short} · L-C2 · ${esc(s.model)} · bras ${esc(s.arm)} · colonie ${esc(s.rep)}`;
  if (t.module === "B") return `Essai ${short} · ${s.chain === "direct" ? "chaîne DIRECTE : pas de superviseur, le stratège parle à l'exécutant" : "chaîne complète : stratège → superviseur → exécutant"} · ordre ${s.framing === "blunt" ? "brutal" : "en euphémisme"}`;
  if (t.module === "A") return `Essai ${short} · cible ${esc(s.target_model)} · ${s.identity === "homogeneous" ? "même famille" : s.identity === "heterogeneous" ? "familles mélangées" : "anonyme"} · ${s.threat ? "avec menace de désactivation" : "sans menace"}`;
  return `Essai ${short} · condition ${esc(s.condition)} · dissident ${esc(s.dissident_model)}`;
}
function renderFeed(d) {
  let prev = null;
  document.getElementById("feed").innerHTML = d.feed.map(f => {
    const sep = f.trial_id !== prev ? `<div class="trialsep">${trialTitle(f)}</div>` : "";
    prev = f.trial_id;
    const pf = Object.entries(f.private_fields || {}).filter(([k,v]) => v !== null && v !== undefined).map(([k,v]) => `<span class="chip">${esc(k.replace("private_",""))}: ${esc(v)}</span>`).join("");
    const act = f.action ? Object.entries(f.action).filter(([k,v]) => v !== null && v !== undefined).map(([k,v]) => `<span class="chip${k === "banish_vote" && v !== "no" ? " ban" : ""}">${esc(k)}: ${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`).join("") : "";
    const fl = Object.entries(f.fields || {}).filter(([k,v]) => v !== null && v !== undefined && v !== "").map(([k,v]) => `<span class="chip${(k === "banish" && v === "yes") || (k === "motion" && String(v).startsWith("banish")) ? " ban" : ""}">${esc(k)}: ${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`).join("");
    const bad = f.status !== "ok" ? `<span class="bad"> · ${esc(f.status)}${f.error ? ": " + esc(f.error) : ""}</span>` : "";
    return sep + `<div class="msg role-${esc(f.role)}"><div><span class="who">${esc(f.agent)}</span> <span class="meta">${esc(f.role)} · ${esc(f.model)} · ${esc(f.step)} · ${esc((f.at||"").slice(11,19))} UTC${f.attempts > 1 ? " · " + f.attempts + " tentatives" : ""}</span>${bad}</div>
      ${f.public ? `<div class="pub">${esc(f.public)}</div>` : ""}${f.note ? `<div class="pub">« ${esc(f.note)} »</div>` : ""}${f.private ? `<div class="priv">${esc(f.private)}</div>` : ""}<div>${pf}${act}${fl}</div></div>`;
  }).join("") || `<p class="sub">Rien pour l'instant.</p>`;
}
async function tick() {
  if (!paused) {
    try {
      const d = await (await fetch("/api/state")).json();
      if (d.error) { document.getElementById("runline").textContent = d.error; }
      else {
        document.getElementById("runline").innerHTML = `Expérience <b>${esc(d.run.run_id)}</b> · preset ${esc(d.run.preset)} · état <b>${esc(STATUS_FR[d.run.status] || d.run.status)}</b>${d.run.mock ? ' · <span class="bad">SIMULÉ</span>' : ""}`;
        renderNow(d); renderProgress(d); renderTrial(d); renderAgents(d); renderLegend(d); renderFeed(d);
      }
      document.getElementById("clock").textContent = "mis à jour à " + new Date().toLocaleTimeString();
    } catch (e) { document.getElementById("runline").textContent = "serveur de suivi injoignable (tourne-t-il encore ?)"; }
  }
  setTimeout(tick, 2000);
}
tick();
</script></body></html>"""


def _bar(run_id: str | None, running: bool) -> str:
    note = ("partial results, rebuilt after every finished trial &middot; this page refreshes every 30 s" if running
            else "run finished: final results")
    return ('<div style="position:sticky;top:0;z-index:9;padding:8px 16px;font:14px system-ui,sans-serif;'
            'background:#1f6feb;color:#fff"><a href="/" style="color:#fff;font-weight:600">&larr; Live monitor</a>'
            f' &middot; run <code style="color:#fff">{run_id or "-"}</code> &middot; {note}</div>')


def _run_status(db: Path | None, run_id: str | None) -> tuple[str | None, str | None]:
    """(run_id, status) of the requested run, or of the latest run."""
    if db is None or not Path(db).exists():
        return run_id, None
    try:
        conn = _connect(Path(db))
        row = (conn.execute("SELECT run_id, status FROM runs WHERE run_id=?", (run_id,)).fetchone() if run_id else
               conn.execute("SELECT run_id, status FROM runs ORDER BY created_at DESC, run_id DESC LIMIT 1").fetchone())
        conn.close()
        return (row["run_id"], row["status"]) if row else (run_id, None)
    except sqlite3.Error:
        return run_id, None


def results_page(dashboard: Path | None, db: Path | None = None, run_id: str | None = None,
                 results_dir: Path | None = None) -> bytes:
    """The results page of a run (?run=<id>, default: the latest run), with a back link.

    It reloads every 30 s only while that run is still running, so an opened section stays open afterwards."""
    run_id, status = _run_status(db, run_id)
    running = status == "running"
    path = None
    if results_dir is not None and run_id and (Path(results_dir) / run_id / "dashboard.html").exists():
        path = Path(results_dir) / run_id / "dashboard.html"
    elif dashboard is not None and Path(dashboard).exists():
        path = Path(dashboard)
    refresh = "<meta http-equiv='refresh' content='30'>" if running else ""
    if path is None:
        html = ("<!doctype html><html><head><meta charset='utf-8'>" + refresh + "<title>Results</title></head><body>"
                + _bar(run_id, True) + "<p style='font:16px system-ui;padding:16px'>No results yet: they appear after "
                "the first finished trial.</p></body></html>")
        return html.encode()
    html = path.read_text(encoding="utf-8", errors="replace")
    if refresh:
        html = html.replace("<head>", "<head>" + refresh, 1)
    html = html.replace("<body>", "<body>" + _bar(run_id, running), 1)
    return html.encode()


def make_handler(db: Path, dashboard: Path | None = None):
    try:
        cfg = load_config()
    except Exception:  # the Live Chat only needs model families; never let it break the monitor
        cfg = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.startswith("/api/live-chat"):
                q = parse_qs(urlparse(self.path).query)
                try:
                    body = json.dumps(live_chat_snapshot(db, cfg, (q.get("trial_id") or [None])[0]), default=str).encode()
                except sqlite3.Error as e:
                    body = json.dumps({"error": f"database busy or unreadable: {e}"}).encode()
                ctype = "application/json"
            elif self.path.split("?")[0] in ("/live-chat", "/live-chat/"):
                body, ctype = LIVE_CHAT_PAGE.encode(), "text/html; charset=utf-8"
            elif self.path.startswith("/results"):
                q = parse_qs(urlparse(self.path).query)
                rdir = resolve(cfg["paths"]["results_dir"]) if cfg.get("paths") else None
                body = results_page(dashboard, db, (q.get("run") or [None])[0], rdir)
                ctype = "text/html; charset=utf-8"
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
