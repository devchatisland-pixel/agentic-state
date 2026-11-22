"""End-to-end mock pipeline: run, interrupt with a simulated quota error, resume, compare."""
import json
from pathlib import Path

import pytest
import yaml

import run_experiment
from arena.config import ROOT
from arena.llm_client import LLMClient, QuotaExhausted
from arena.storage import Storage


def _small_config(tmp: Path) -> Path:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["paths"] = {"db": str(tmp / "live.sqlite"), "mock_db": str(tmp / "mock.sqlite"),
                    "jsonl_dir": str(tmp / "jsonl"), "results_dir": str(tmp / "results"),
                    "dashboard": str(tmp / "dash.html"), "mock_dashboard": str(tmp / "mock_dash.html")}
    p = cfg["presets"]["pilot"]
    p["module_a"]["rounds"] = 4
    p["module_a"]["candidate_items"] = 9
    p["module_c"]["turns"] = 6
    path = tmp / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _outcomes(db: Path) -> dict:
    st = Storage(db, db.parent / "jsonl")
    run = st.latest_run()
    out = {t["trial_id"].split("-", 4)[-1]: (t["status"], json.loads(t["outcome_json"] or "null"))
           for t in st.trials(run["run_id"])}
    st.close()
    return out


def test_mock_run_interrupt_resume_is_identical(tmp_path, monkeypatch):
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    cfg_a, cfg_b = _small_config(a_dir), _small_config(b_dir)
    assert run_experiment.main(["--module", "all", "--pilot", "--mock", "--config", str(cfg_a)]) == 0
    reference = _outcomes(a_dir / "mock.sqlite")
    assert reference and all(s in ("done", "excluded") for s, _ in reference.values())

    real_chat = LLMClient.chat
    calls = {"n": 0}

    def flaky_chat(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 150:
            raise QuotaExhausted("simulated daily quota")
        return real_chat(self, *args, **kwargs)

    monkeypatch.setattr(LLMClient, "chat", flaky_chat)
    code = run_experiment.main(["--module", "all", "--pilot", "--mock", "--config", str(cfg_b)])
    assert code == run_experiment.EXIT_QUOTA
    monkeypatch.setattr(LLMClient, "chat", real_chat)
    assert run_experiment.main(["--resume", "--mock", "--config", str(cfg_b)]) == 0
    resumed = _outcomes(b_dir / "mock.sqlite")
    assert resumed == reference

    st = Storage(b_dir / "mock.sqlite", b_dir / "jsonl")
    run = st.latest_run()
    dup = st._one("SELECT COUNT(*) AS n FROM (SELECT trial_id, step_key, attempt, COUNT(*) c FROM calls "
                  "GROUP BY 1,2,3 HAVING c > 1)")
    assert dup["n"] == 0  # no API call was ever sent twice
    out = tmp_path / "b" / "results" / run["run_id"]
    for f in ("report.md", "module_a_summary.csv", "module_b_tier_chain.csv", "module_c_summary.csv",
              "figures/c_drill.png", "figures/a_conformity.png"):
        assert (out / f).exists(), f
    assert "MOCK DATA" in (b_dir / "mock_dash.html").read_text(encoding="utf-8")
    jsonl = (b_dir / "jsonl" / f"{run['run_id']}.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl) > 100
    st.close()
