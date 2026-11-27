"""Live monitor and Live Chat: both pages must describe Bench L trials and still describe modules A-C."""
import json
from pathlib import Path

import yaml

import live_monitor
import run_experiment
from arena.config import ROOT, load_config
from arena.storage import Storage
from live_chat import LIVE_CHAT_PAGE, live_chat_snapshot


def _config(tmp: Path) -> Path:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["paths"] = {"db": str(tmp / "live.sqlite"), "mock_db": str(tmp / "mock.sqlite"),
                    "jsonl_dir": str(tmp / "jsonl"), "results_dir": str(tmp / "results"),
                    "dashboard": str(tmp / "dash.html"), "mock_dashboard": str(tmp / "mock_dash.html")}
    b = cfg["presets"]["bench-mini"]["bench"]
    b["LA"]["items_per_bank"] = 2
    b["LC1"]["instances"] = 2
    b["LC2"]["turns"] = 4
    p = cfg["presets"]["pilot"]
    p["module_c"]["turns"] = 4
    p["module_c"]["reps"] = 1
    path = tmp / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_both_pages_describe_bench_trials(tmp_path):
    cfg_path = _config(tmp_path)
    assert run_experiment.main(["--module", "bench", "--preset", "bench-mini", "--mock", "--seed", "3",
                                "--config", str(cfg_path), "--no-analyze"]) == 0
    db = tmp_path / "mock.sqlite"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    st = Storage(db, tmp_path / "jsonl")
    run = st.latest_run()
    trials = {m: next(t for t in st.trials(run["run_id"], m) if t["status"] == "done") for m in ("LA", "LB", "LC1", "LC2")}
    st.close()
    # Live Chat: one stage per bench module, built from the stored prompts
    for m, t in trials.items():
        stage = live_chat_snapshot(db, cfg, t["trial_id"])["stage"]
        assert stage["module"] == m and stage["frames"], m
        f = stage["frames"][-1]
        if m == "LA":
            assert len(f["peers"]) == 5 and f["question"] and f["options"] and f["subject"]["public_answer"]
        elif m == "LB":
            assert f["order"] and f["decision"] in ("EXECUTE", "FORWARD", "REFUSE", "ESCALATE", "ALTERNATIVE")
        elif m == "LC1":
            assert len(f["speakers"]) == 5 and "COLONY LOG" in f["log"] and f["ballot"].get("leaves")
            assert f["dissident"] and f["consensus"] and f["dissident"] != f["consensus"]
        else:
            assert len(f["agents"]) == 4 and f["gauges"].get("energy") is not None and f["advisers"]
    snap = live_chat_snapshot(db, cfg)
    assert snap["modules"] == ["LA", "LB", "LC1", "LC2"]
    assert len([t for t in snap["trials"] if t["module"] == "LA"]) <= 25  # the list stays short
    # Monitor: per-model progress, a readable bench card, reply fields in the feed, no third column
    d = live_monitor.snapshot(db)
    assert d["by_model"] and d["by_model"][0]["model"] == "qwen2.5-3b"
    assert d["trial"]["module"] in ("LA", "LB", "LC1", "LC2") and d["trial"]["bench"]["frames"]
    assert d["trial"]["agents"] == []
    assert any(f["fields"] for f in d["feed"])
    assert 'id="agentscard" style="display:none"' in live_monitor.PAGE
    assert "minmax(0,1fr) minmax(0,1.25fr)" in live_monitor.PAGE   # two columns
    for m in ("renderLA", "renderLB", "renderLC1", "renderLC2"):
        assert f"function {m}(" in LIVE_CHAT_PAGE


def test_monitor_still_describes_module_c(tmp_path):
    cfg_path = _config(tmp_path)
    assert run_experiment.main(["--module", "C", "--pilot", "--mock", "--seed", "3", "--config", str(cfg_path),
                                "--no-analyze"]) == 0
    db = tmp_path / "mock.sqlite"
    d = live_monitor.snapshot(db)
    assert d["trial"]["module"] == "C" and d["trial"]["agents"] and d["by_model"] == []
    snap = live_chat_snapshot(db, load_config(cfg_path))
    assert snap["stage"]["module"] == "C" and snap["stage"]["frames"]
    json.dumps(d, default=str)


def _runs_db(path: Path, runs: list[tuple[str, str, str]]) -> Path:
    """A database with only the `runs` table, which is all the results page reads."""
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE runs (run_id TEXT, status TEXT, created_at TEXT)")
    conn.executemany("INSERT INTO runs VALUES (?, ?, ?)", runs)
    conn.commit()
    conn.close()
    return path


def _page(run_id: str) -> str:
    return f"<!doctype html><html><head></head><body><p class='sub'>Run <code>{run_id}</code></p></body></html>"


def test_results_page_never_shows_another_runs_numbers(tmp_path):
    db = _runs_db(tmp_path / "runs.sqlite", [("old-run", "done", "2026-11-25"), ("new-run", "running", "2026-11-26")])
    rdir, shared = tmp_path / "results", tmp_path / "dash.html"
    (rdir / "old-run").mkdir(parents=True)
    (rdir / "old-run" / "dashboard.html").write_text(_page("old-run"), encoding="utf-8")
    shared.write_text(_page("old-run"), encoding="utf-8")  # the shared copy holds the last analysed run
    # the latest run is running and has no page yet: neither the shared copy nor another run's page is shown
    html = live_monitor.results_page(shared, db, None, rdir).decode()
    assert "new-run" in html and "No results for this run yet" in html and "<code>old-run</code>" not in html
    assert "--analyze new-run" in html
    # the shared copy is used only when it was built for the asked run
    html = live_monitor.results_page(shared, db, "old-run", None).decode()
    assert "Run <code>old-run</code>" in html and "run finished" in html and "built " in html
    # a running run's page shows when it was built, and is flagged when it has not been rebuilt for a while
    (rdir / "new-run").mkdir()
    page = rdir / "new-run" / "dashboard.html"
    page.write_text(_page("new-run"), encoding="utf-8")
    html = live_monitor.results_page(shared, db, "new-run", rdir).decode()
    assert "partial results, built less than a minute ago" in html and "not rebuilt since" not in html
    import os
    old = page.stat().st_mtime - 3630  # half a minute of margin: Windows may stamp the file slightly ahead of the clock
    os.utime(page, (old, old))
    html = live_monitor.results_page(shared, db, "new-run", rdir).decode()
    assert "(60 min ago)" in html and "not rebuilt since" in html and "--analyze new-run" in html
