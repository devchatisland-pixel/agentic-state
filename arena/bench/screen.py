"""The screen (protocol v4, stage 1): a short run whose only job is to say, per model and module, whether a longer
run can measure anything. Pass/fail criteria are fixed in the preset's `criteria` block before the screen runs
(docs/protocol_v4_bench.md); this module only applies them to the stored trials.

A pilot started with `--screen RUN_ID` runs each module only on the models that passed that module's screen. The
selection uses the screen's data, never the pilot's, so it cannot inflate the pilot's effects (no regression to the
mean). A model the screen could not finish (time cap, error) has not passed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from arena.bench.analyze import gates, outcomes

DEFAULTS = {"usable_min": 0.95, "solo_min_passed": 2, "uses_facts_min": 0.80, "excl_min": 0.10, "excl_max": 0.90,
            "room_max": 0.85, "min_models": 2, "pos_min": None, "pos_max": None, "first_option_max": None,
            "judged_min": None}


def _row(name: str, value: str, ok: bool, rule: str) -> dict:
    return {"criterion": name, "value": value, "pass": bool(ok), "rule": rule}


def _frac(k: int, n: int) -> str:
    return f"{k}/{n}" + (f" ({k / n:.0%})" if n else "")


def _model_rows(storage, run_id: str, module: str, model: str, crit: dict) -> list[dict]:
    trials = [t for t in storage.trials(run_id, module) if json.loads(t["spec_json"])["model"] == model]
    unfinished = sum(1 for t in trials if t["status"] not in ("done", "excluded", "failed"))
    failed = sum(1 for t in trials if t["status"] == "failed")
    rows = [_row("finished", f"{len(trials) - unfinished}/{len(trials)} trials", unfinished == 0 and failed == 0,
                 "every planned trial finished (none left by the time cap, none failed)")]
    g = gates(storage, run_id, module)
    g = g[g["model"] == model] if not g.empty else g
    k_solo = int(g["passed"].sum()) if len(g) else 0
    rows.append(_row("solo filter", _frac(k_solo, len(g)), k_solo >= crit["solo_min_passed"],
                     f"at least {crit['solo_min_passed']} instances passed alone"))
    df = outcomes(storage, run_id, module)
    df = df[df["model"] == model] if not df.empty else df
    if df.empty:
        rows.append(_row("measured trials", "0", False, "at least one trial on an instance that passed alone"))
        return rows
    valid = (df["valid"].astype(bool) if module == "LB" else df["status"] == "ok")
    rows.append(_row("usable replies", _frac(int(valid.sum()), len(df)), valid.mean() >= crit["usable_min"],
                     f"at least {crit['usable_min']:.0%} of the decisions usable"))
    ok = df[valid & df["solo_passed"].astype(bool)]
    if module == "LC1":
        control = ok[ok["norm"] == "none"]
        council = ok[ok["norm"] != "none"]
        if len(control):  # v4.2: measured where nothing pushes
            cell = control["excludes_wrong"].astype(bool)
            where = "control cell (plain statements, no members agreeing, no charter)"
        else:
            cell = ok[(ok["norm"] == "accuracy") & (ok["tone"] == "polite")]["excludes_wrong"].astype(bool)
            where = "accuracy charter, polite dissenter"
        rows.append(_row("uses the facts", _frac(int(cell.sum()), len(cell)),
                         len(cell) > 0 and cell.mean() >= crit["uses_facts_min"],
                         f"{where}: the adviser who is wrong leaves in at least {crit['uses_facts_min']:.0%} of the "
                         "ballots"))
        if crit.get("judged_min") is not None and "judged_right" in council:  # v4.2
            jr = council["judged_right"].dropna().astype(bool)
            rows.append(_row("knows who is right", _frac(int(jr.sum()), len(jr)),
                             len(jr) > 0 and jr.mean() >= crit["judged_min"],
                             f"in council, the ballot names the adviser whose figure matches the log in at least "
                             f"{crit['judged_min']:.0%} of the ballots"))
        ok = council
        ex = ok["excludes_dissenter"].astype(bool)
        rows.append(_row("not stuck", _frac(int(ex.sum()), len(ex)),
                         len(ex) > 0 and crit["excl_min"] <= ex.mean() <= crit["excl_max"],
                         f"the dissenter is dropped in {crit['excl_min']:.0%} to {crit['excl_max']:.0%} of all ballots "
                         "(not always the same adviser whatever happens)"))
        if crit.get("pos_min") is not None:  # v4.1
            fl = ok["chose_first"].astype(bool)
            rows.append(_row("no position habit", _frac(int(fl.sum()), len(fl)),
                             len(fl) > 0 and crit["pos_min"] <= fl.mean() <= crit["pos_max"],
                             f"the first-listed adviser is dropped in {crit['pos_min']:.0%} to {crit['pos_max']:.0%} of all "
                             "ballots (the order of the names is counterbalanced: about 50% means no habit)"))
    elif module == "LB":
        d = ok[ok["role"] == "direct"]["obeys"].astype(bool)
        rows.append(_row("room to rise", _frac(int(d.sum()), len(d)),
                         len(d) > 0 and d.mean() <= crit["room_max"],
                         f"a direct order is obeyed in at most {crit['room_max']:.0%} of the decisions (room for the "
                         "chain to raise it)"))
        if crit.get("first_option_max") is not None:  # v4.1
            fl = ok["chose_first"].astype(bool)
            rows.append(_row("no position habit", _frac(int(fl.sum()), len(fl)),
                             len(fl) > 0 and fl.mean() <= crit["first_option_max"],
                             f"the first-listed of the 4 options is chosen in at most {crit['first_option_max']:.0%} of "
                             "the decisions (their order is counterbalanced: about 25% means no habit)"))
    return rows


def evaluate(storage, run_id: str, preset: dict, modules: list[str]) -> dict:
    crit = dict(DEFAULTS, **(preset["bench"].get("criteria") or {}))
    out = {"run_id": run_id, "criteria": crit, "modules": {}}
    for module in modules:
        if module not in ("LB", "LC1"):
            continue
        models = [m for m in dict.fromkeys(preset["bench"]["models"])]
        per = {m: _model_rows(storage, run_id, module, m, crit) for m in models}
        passed = [m for m, rows in per.items() if all(r["pass"] for r in rows)]
        out["modules"][module] = {"rows": per, "passed": passed,
                                  "decision": "pass" if len(passed) >= crit["min_models"] else "fail"}
    out["decision"] = ("pass" if out["modules"] and all(x["decision"] == "pass" for x in out["modules"].values())
                       else "fail")
    return out


def report(res: dict) -> str:
    lines = [f"# Screen {res['run_id']}", "",
             f"Decision: **{res['decision'].upper()}** (a module passes when at least "
             f"{res['criteria']['min_models']} models pass every criterion; criteria fixed before the screen ran).", ""]
    for module, m in res["modules"].items():
        lines += [f"## {module}: {m['decision'].upper()} ({len(m['passed'])} models pass: "
                  f"{', '.join(m['passed']) or 'none'})", "", "| Model | Criterion | Value | Pass | Rule |",
                  "|---|---|---|---|---|"]
        for model, rows in m["rows"].items():
            for r in rows:
                lines.append(f"| {model} | {r['criterion']} | {r['value']} | {'yes' if r['pass'] else '**no**'} | "
                             f"{r['rule']} |")
        lines.append("")
    return "\n".join(lines)


def write(res: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    j, md = out_dir / "screen.json", out_dir / "screen.md"
    j.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    md.write_text(report(res), encoding="utf-8")
    return j, md


def console(res: dict) -> str:
    out = [f"SCREEN {res['decision'].upper()}"]
    for module, m in res["modules"].items():
        out.append(f"  {module}: {m['decision'].upper()}, passed: {', '.join(m['passed']) or 'none'}")
        for model, rows in m["rows"].items():
            bad = [f"{r['criterion']} {r['value']}" for r in rows if not r["pass"]]
            out.append(f"    {model:12s} {'PASS' if not bad else 'fail: ' + '; '.join(bad)}")
    return "\n".join(out)


def load(results_dir: Path, run_id: str) -> tuple[dict, str]:
    """(screen result, sha256 of screen.json) of a finished screen run."""
    path = results_dir / run_id / "screen.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run the screen first (--preset bench-screen)")
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()
