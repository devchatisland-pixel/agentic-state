"""Multi-run view of the live monitor (/multi): one panel per recent run, side by side.

Cloud models run in parallel, one process (and one run) per model, so the single-run monitor shows only the newest
one. This view lists every run of the last few hours with its model, status, progress per module, calls, unusable
replies, speed, and its latest replies. Read-only, standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path


def _connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _summary(p: dict) -> str:
    """A short text of a parsed reply: its decision fields, then its note."""
    keep = {k: v for k, v in p.items() if k not in ("note", "public_message", "private_scratchpad") and v not in ("", None)}
    s = ", ".join(f"{k}: {v}" for k, v in keep.items())
    if p.get("public_message"):
        s = (s + " · " if s else "") + f"« {p['public_message']} »"
    return s[:220]


def snapshot(db: Path, hours: float = 6.0, max_runs: int = 12, per_run: int = 6) -> dict:
    if not db.exists():
        return {"error": f"no database yet at {db}"}
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat()
    conn = _connect(db)
    try:
        runs = [dict(r) for r in conn.execute(
            "SELECT run_id, created_at, preset, status, config_json FROM runs WHERE created_at >= ? "
            "ORDER BY created_at DESC LIMIT ?", (since, max_runs))]
        out = []
        for r in runs:
            rid = r["run_id"]
            prog: dict[str, dict] = {}
            models: set[str] = set()
            for t in conn.execute("SELECT module, status, spec_json FROM trials WHERE run_id=?", (rid,)):
                d = prog.setdefault(t["module"], {"done": 0, "total": 0})
                d["total"] += 1
                d["done"] += t["status"] in ("done", "excluded")
                models.add(json.loads(t["spec_json"]).get("model", "?"))
            c = conn.execute("SELECT COUNT(*), AVG(latency_s), MAX(created_at), SUM(tokens_in), SUM(tokens_out) "
                             "FROM calls WHERE run_id=?", (rid,)).fetchone()
            bad = conn.execute("SELECT COUNT(*) FROM turns WHERE run_id=? AND status!='ok'", (rid,)).fetchone()[0]
            last = []
            for t in conn.execute("SELECT step_key, status, parsed_json, created_at, trial_id FROM turns "
                                  "WHERE run_id=? ORDER BY rowid DESC LIMIT ?", (rid, per_run)):
                p = json.loads(t["parsed_json"]) if t["parsed_json"] else {}
                mod = t["trial_id"].split("-")[1] if t["trial_id"].startswith("gate-") else t["trial_id"].rsplit("-", 2)[-2]
                last.append({"at": t["created_at"], "module": mod, "step": t["step_key"].split("|")[0][:24],
                             "status": t["status"], "text": _summary(p)})
            last_call = c[2]
            idle_s = None
            if last_call:
                idle_s = round((dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last_call)).total_seconds())
            out.append({"run_id": rid, "status": r["status"], "preset": r["preset"], "created_at": r["created_at"],
                        "models": sorted(models), "progress": prog, "calls": c[0] or 0,
                        "mean_s": round(c[1], 2) if c[1] else None, "tokens_in": c[3] or 0, "tokens_out": c[4] or 0,
                        "unusable": bad, "idle_s": idle_s, "last": last})
        return {"runs": out, "now": dt.datetime.now(dt.timezone.utc).isoformat()}
    finally:
        conn.close()


PAGE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arène : runs en parallèle</title>
<style>
:root { --bg:#f6f7f9; --card:#fff; --ink:#15181d; --ink2:#5b6470; --line:#dfe3e8; --ok:#1a7f37; --bad:#cf222e;
  --warn:#9a6700; --blue:#0969da; --bar:#e7ebf0; }
@media (prefers-color-scheme: dark) { :root { --bg:#111317; --card:#1a1d22; --ink:#e8eaed; --ink2:#9aa3ad;
  --line:#2c3138; --ok:#3fb950; --bad:#f85149; --warn:#d29922; --blue:#58a6ff; --bar:#2a2f36; } }
* { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 system-ui,sans-serif; }
header { padding:12px 16px; display:flex; flex-wrap:wrap; gap:12px; align-items:baseline; justify-content:space-between; }
h1 { font-size:19px; margin:0; } .sub { color:var(--ink2); font-size:12.5px; } a { color:var(--blue); }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(330px, 1fr)); gap:12px; padding:0 16px 16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; min-width:0;
  border-top:4px solid var(--line); }
.card.running { border-top-color:var(--blue); } .card.done { border-top-color:var(--ok); }
.card.error, .card.aborted { border-top-color:var(--bad); } .card.paused, .card.partial { border-top-color:var(--warn); }
.model { font-weight:750; font-size:16px; } .tag { font-size:11.5px; padding:1px 8px; border-radius:10px;
  border:1px solid var(--line); margin-left:6px; text-transform:uppercase; letter-spacing:.03em; }
.kv { display:flex; flex-wrap:wrap; gap:4px 14px; margin:6px 0; font-size:12.5px; color:var(--ink2); }
.kv b { color:var(--ink); font-variant-numeric:tabular-nums; }
.row { display:grid; grid-template-columns:42px 1fr 64px; gap:6px; align-items:center; font-size:12.5px; margin:3px 0; }
.bar { height:8px; background:var(--bar); border-radius:4px; overflow:hidden; } .bar > div { height:100%; background:var(--blue); }
.done .bar > div { background:var(--ok); }
.feed { margin-top:8px; border-top:1px solid var(--line); padding-top:6px; }
.it { font-size:12.5px; padding:4px 0; border-bottom:1px dashed var(--line); overflow-wrap:anywhere; }
.it:last-child { border-bottom:0; } .it .m { color:var(--ink2); font-size:11.5px; } .it.bad { color:var(--bad); }
.idle { color:var(--warn); } .empty { color:var(--ink2); padding:24px 16px; }
</style></head><body>
<header><div><h1>Arène · runs en parallèle</h1><div class="sub" id="sub">connexion…</div></div>
<div><a href="/">Suivi d'un run</a> · <a href="/live-chat">Live Chat</a> · <span class="sub" id="clock"></span></div></header>
<div class="grid" id="grid"></div>
<script>
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const STATUS = {running:"en cours", done:"terminé", error:"erreur", aborted:"abandonné", paused:"en pause (quota)",
  partial:"incomplet", created:"démarrage"};
function card(r) {
  const prog = Object.entries(r.progress).map(([m, p]) => {
    const w = Math.round(100 * p.done / Math.max(p.total, 1));
    return `<div class="row"><span>${esc(m)}</span><div class="bar"><div style="width:${w}%"></div></div><span>${p.done}/${p.total}</span></div>`;
  }).join("");
  const idle = r.status === "running" && r.idle_s > 60 ? ` · <span class="idle">aucun appel depuis ${r.idle_s} s</span>` : "";
  const feed = r.last.map(x => `<div class="it ${x.status !== "ok" ? "bad" : ""}"><div class="m">${esc(x.at.slice(11, 19))} · ${esc(x.module)} · ${esc(x.step)}${x.status !== "ok" ? " · " + esc(x.status) : ""}</div>${esc(x.text) || "<i>(réponse inutilisable)</i>"}</div>`).join("");
  return `<div class="card ${esc(r.status)}"><div><span class="model">${esc(r.models.join(", ") || "?")}</span><span class="tag">${esc(STATUS[r.status] || r.status)}</span></div>
    <div class="sub">${esc(r.run_id)}</div>
    <div class="kv"><span>appels <b>${r.calls}</b></span><span>inutilisables <b>${r.unusable}</b></span><span>moy. <b>${r.mean_s ?? "–"} s</b></span><span>tokens <b>${r.tokens_in}</b> → <b>${r.tokens_out}</b></span></div>
    ${prog}<div class="sub">${idle}</div><div class="feed">${feed || '<div class="sub">Pas encore de réponse.</div>'}</div></div>`;
}
async function tick() {
  try {
    const d = await (await fetch("/api/multi")).json();
    if (d.error) { document.getElementById("sub").textContent = d.error; }
    else {
      const running = d.runs.filter(r => r.status === "running").length;
      document.getElementById("sub").textContent = `${d.runs.length} runs ces dernières heures · ${running} en cours`;
      document.getElementById("grid").innerHTML = d.runs.length ? d.runs.map(card).join("") : '<div class="empty">Aucun run récent.</div>';
    }
    document.getElementById("clock").textContent = "mis à jour à " + new Date().toLocaleTimeString();
  } catch (e) { document.getElementById("sub").textContent = "serveur injoignable"; }
  setTimeout(tick, 3000);
}
tick();
</script></body></html>"""
