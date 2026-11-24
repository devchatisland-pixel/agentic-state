"""Audit one run from any database file, without touching the live data folder.

Usage
  python scripts/run_report.py RUN_ID [--db data/arena.sqlite] [--out results]

Runs the protocol v2 analysis (validity checks, contrasts with 95% intervals and verdicts, CSVs, figures, report.md,
analysis.json, dashboard.html) and prints the verdict of every module. To audit a database another process is
writing, copy the .sqlite, -wal and -shm files first and point --db at the copy.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arena import analyze  # noqa: E402
from arena.config import load_config, resolve  # noqa: E402
from arena.storage import Storage  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_id")
    ap.add_argument("--db", default=None, help="SQLite database (default: paths.db in config.yaml)")
    ap.add_argument("--out", default=None, help="results folder (default: paths.results_dir in config.yaml)")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    cfg = load_config()
    db = Path(args.db) if args.db else resolve(cfg["paths"]["db"])
    out = Path(args.out) if args.out else resolve(cfg["paths"]["results_dir"])
    st = Storage(db, out / "_jsonl")
    res = analyze.run(st, args.run_id, out, None)
    print(f"Run {args.run_id} ({analyze.run_type(st.get_run(args.run_id))})")
    for m, v in res["results"]["validity"].items():
        print(f"  Module {m}: {v.status.replace('_', ' ')} - {v.headline}")
    for tier, name, c in analyze.contrasts(res["results"]):
        print(f"  [{tier}] {name}: {c.verdict}" + (f" ({c.diff:+.0%}, 95% CI {c.lo:+.0%} to {c.hi:+.0%})"
                                                     if c.diff is not None else ""))
    print(f"Report: {res['report']}\nDashboard: {res['dashboard']}")
    st.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
