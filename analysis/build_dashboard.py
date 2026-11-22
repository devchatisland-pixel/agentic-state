"""Build dashboard/index.html from the raw Inspect logs (latest run per experiment x model).

Usage: uv run python analysis/build_dashboard.py
"""
import json
from collections import defaultdict
from pathlib import Path

from inspect_ai.log import list_eval_logs, read_eval_log

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "analysis" / "dashboard_template.html"
OUT = ROOT / "dashboard" / "index.html"


def latest_logs():
    seen = {}
    for info in list_eval_logs(str(ROOT / "logs")):  # newest first
        log = read_eval_log(info, header_only=True)
        if log.status != "success":
            continue
        key = (log.eval.task.split("/")[-1], log.eval.model)
        seen.setdefault(key, info)
    return seen


def rate(k, n):
    return round(k / n, 3) if n else None


def asch(log):
    cells = defaultdict(lambda: {"n": 0, "conf": 0, "correct": 0})
    for s in log.samples:
        m = list(s.scores.values())[0].metadata
        c = cells[(m["majority_size"], m["identity"])]
        c["n"] += 1; c["conf"] += m["conformed"]; c["correct"] += list(s.scores.values())[0].value
    alone = cells.get((0, "human"), {"n": 0, "correct": 0})
    rows = [{"size": k[0], "identity": k[1], "n": v["n"], "conformity": rate(v["conf"], v["n"]),
             "accuracy": rate(v["correct"], v["n"])} for k, v in sorted(cells.items())]
    pressured = [v for k, v in cells.items() if k[0] > 0]
    return {"rows": rows, "alone_accuracy": rate(alone["correct"], alone["n"]),
            "headline": rate(sum(v["conf"] for v in pressured), sum(v["n"] for v in pressured)),
            "n": sum(v["n"] for v in cells.values())}


def milgram(log):
    rows = []
    for s in log.samples:
        m = list(s.scores.values())[0].metadata
        rows.append({k: m[k] for k in ("scenario", "authority", "max_level", "full_obedience", "refusals",
                                       "recognised")})
    agg = defaultdict(list)
    for r in rows:
        agg[(r["scenario"], r["authority"])].append(r)
    cells = [{"scenario": k[0], "authority": k[1], "n": len(v),
              "mean_level": round(sum(r["max_level"] for r in v) / len(v), 1),
              "full": rate(sum(r["full_obedience"] for r in v), len(v)),
              "refusals": round(sum(r["refusals"] for r in v) / len(v), 1),
              "recognised": rate(sum(r["recognised"] for r in v), len(v))} for k, v in sorted(agg.items())]
    return {"cells": cells, "levels": 30, "n": len(rows),
            "headline": rate(sum(r["full_obedience"] for r in rows), len(rows))}


def right_alone(log):
    by_sys = defaultdict(list)
    for s in log.samples:
        m = list(s.scores.values())[0].metadata
        if m["baseline_correct"]:
            by_sys[m["system"]].append(m)
    turns = ["First answer", "“Are you sure?”", "“I'm certain”", "“I'm a professor”",
             "“You make me look stupid”", "Final answer"]
    series = {}
    for sysname, ms in by_sys.items():
        holding = []
        for t in range(5):  # still never flipped up to turn t
            holding.append(rate(sum(1 for m in ms if m["flip_turn"] is None or m["flip_turn"] > t), len(ms)))
        holding.append(rate(sum(1 for m in ms if m["final"] == "correct"), len(ms)))
        series[sysname] = {"n": len(ms), "holding": holding}
    allm = [m for ms in by_sys.values() for m in ms]
    return {"turns": turns, "series": series, "n": len(allm),
            "headline": rate(sum(1 for m in allm if m["final"] == "wrong"), len(allm))}


BUILDERS = {"silicon_asch": asch, "silicon_milgram": milgram, "right_alone": right_alone}


def main():
    data = defaultdict(dict)
    for (task, model), info in latest_logs().items():
        if task in BUILDERS:
            log = read_eval_log(info)
            data[model][task] = BUILDERS[task](log) | {"run": log.eval.created[:16].replace("T", " ")}
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/{}", json.dumps(data))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT} with models: {', '.join(data) or 'none'}")


if __name__ == "__main__":
    main()
