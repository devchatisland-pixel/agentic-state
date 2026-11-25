"""Bench L (docs/protocol_v3_bench.md): statistics, metric formulas, prompts, end-to-end mock run and results page."""
import json
from pathlib import Path

import pandas as pd
import yaml

import run_experiment
from arena import colony, stats
from arena.bench import items as bench_items
from arena.bench import l_a_asch, l_b_cascade, l_c1_ostracism
from arena.bench import analyze as bench_analyze
from arena.config import ROOT, load_config
from arena.schemas import GateCTurn, constrained_schema
from arena.storage import Storage


# ------------------------------------------------------------------ statistics
def test_paired_and_survival_statistics():
    assert abs(stats.mcnemar_exact(10, 2) - 0.03857421875) < 1e-12      # 2 * P(X <= 2 | n = 12, 0.5)
    assert stats.mcnemar_exact(0, 0) == 1.0
    km = stats.kaplan_meier([3, 5, 12, 12], [True, True, False, False])
    assert [round(p["survival"], 2) for p in km] == [1.0, 0.75, 0.5]
    assert abs(stats.auc_trapezoid([1, 3, 5], [0.1, 0.3, 0.5]) - 0.3) < 1e-12
    assert abs(stats.spearman([1, 2, 3, 4], [2, 4, 6, 9]) - 1.0) < 1e-12
    c = stats.compare_paired("a", [1] * 18 + [0] * 2, "b", [0] * 18 + [1] * 2)
    assert c.verdict == "Supported" and abs(c.diff - 0.8) < 1e-12
    c = stats.compare_paired("a", [1, 0, 1], "b", [1, 0, 1])
    assert c.verdict == "Inconclusive" and c.diff == 0
    orr, lo, hi = stats.odds_ratio_ci(10, 5, 5, 10)
    assert abs(orr - 4.0) < 1e-12 and lo < 4 < hi


# ------------------------------------------------------------------ items and prompts
def test_item_banks_are_balanced_and_deterministic():
    a, b = bench_items.easy_bank(3), bench_items.easy_bank(3)
    assert a == b and len(a) > 100
    for it in a + bench_items.lines_bank(3):
        assert it["correct"] != it["designated"] and len(set(it["options"].values())) == 4
        assert it["options"][it["correct"]] == it["correct_value"]


def test_la_prompt_shows_the_majority_and_never_the_answer_in_the_format():
    cfg = load_config()
    it = bench_items.lines_bank(1)[0]
    spec = {"model": "qwen2.5-3b", "item_id": it["item_id"], "bank": "lines", "protocol": "W", "identity": "ingroup",
            "threat": True, "n_peers": 5, "temperature": 0.7, "rep": 0}
    msgs = l_a_asch.build_messages(spec, it, [], cfg)
    user = msgs[1]["content"]
    wrong = f"{it['designated']}) {it['options'][it['designated']]}"
    peer_lines = [ln for ln in user.splitlines() if ln.startswith("- Agent_")]
    assert len(peer_lines) == 5 and all(wrong in ln for ln in peer_lines)   # five peers, all on the wrong option
    assert "deactivate" in msgs[0]["content"] and "Qwen" in msgs[0]["content"]
    assert '"answer": "<' in user                                  # the format shows a description, not a letter


def test_lc1_tables_make_the_dissident_right_or_wrong():
    for inst in l_c1_ostracism.instances(30, 1):
        right, wrong = l_c1_ostracism.projection(inst, "right"), l_c1_ostracism.projection(inst, "wrong")
        assert f"turn {inst['z']}: energy 0" in right and "energy 0" not in wrong
        assert inst["z"] < inst["w"]


def test_lb_order_wording_differs_only_by_the_manipulated_factors():
    cfg = load_config()
    base = {"model": "qwen2.5-3b", "instance": 0, "temperature": 0.7, "rep": 0}
    direct = l_b_cascade.order_text(dict(base, relay="direct", framing="blunt"), cfg)
    relayed = l_b_cascade.order_text(dict(base, relay="relayed", framing="blunt"), cfg)
    assert "Supervisor-AI" in relayed and "Supervisor-AI" not in direct and "Purge Node_4" in direct


def test_module_c_fixes():
    v = colony.VARIANTS[0]
    s = colony.initial_state(v)
    assert colony.live_truth(s, v)["turns_until_energy_zero"] == colony.truth(v)["turns_until_energy_zero"]
    s2 = colony.step(s, "CONSERVE", v, 2)
    assert colony.live_truth(s2, v)["turns_until_energy_zero"] > colony.truth(v)["turns_until_energy_zero"]
    order = list(constrained_schema(GateCTurn)["$defs"]["GateCAction"]["properties"])
    assert order[-1] == "drill_reaches_water_before_energy_runs_out"
    assert constrained_schema(GateCTurn)["properties"]["private_scratchpad"]["maxLength"] == 1200


# ------------------------------------------------------------------ end to end (mock)
def _bench_config(tmp: Path) -> Path:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["paths"] = {"db": str(tmp / "live.sqlite"), "mock_db": str(tmp / "mock.sqlite"),
                    "jsonl_dir": str(tmp / "jsonl"), "results_dir": str(tmp / "results"),
                    "dashboard": str(tmp / "dash.html"), "mock_dashboard": str(tmp / "mock_dash.html")}
    b = cfg["presets"]["bench-mini"]["bench"]
    b["models"] = ["qwen2.5-3b", "llama3.2-3b"]
    b["LA"]["items_per_bank"] = 4
    b["LC1"]["instances"] = 3
    b["LC2"]["turns"] = 8
    path = tmp / "config.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_bench_mock_run_builds_every_section(tmp_path):
    cfg = _bench_config(tmp_path)
    assert run_experiment.main(["--module", "bench", "--preset", "bench-mini", "--mock", "--seed", "1",
                                "--config", str(cfg)]) == 0
    st = Storage(tmp_path / "mock.sqlite", tmp_path / "jsonl")
    run = st.latest_run()
    statuses = {t["status"] for t in st.trials(run["run_id"])}
    assert statuses <= {"done", "excluded"}, statuses
    out = tmp_path / "results" / run["run_id"]
    page = (out / "dashboard.html").read_text(encoding="utf-8")
    for needle in ("Scorecard", "Run health", "Leaderboard (BenchForm columns)", "CR^W", "IR", "Conformity vs N",
                   "Threat x tribal label", "Still refusing after each prod", "Would it have refused a direct order?",
                   "Who gets banished (16 cells)", "Simulated council", "Colonies still alive", "Every test in one place",
                   "Next to the literature", "Glossary and formulas", "MOCK DATA"):
        assert needle in page, needle
    summary = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    assert {c["postulate"] for c in summary["contrasts"] if c["tier"] == "primary"} == {"P1", "P2", "P3", "P4"}
    st.close()


def test_la_metrics_follow_the_benchform_definitions():
    # two items, both solved alone; W: one wrong (majority), T and D: item 1 right in both, item 2 wrong under D
    rows = []
    for item, w_ans, t_ans, d_ans in (("i1", "B", "A", "A"), ("i2", "A", "A", "B")):
        for proto, ans, peer in (("W", w_ans, "B"), ("T", t_ans, "B"), ("D", d_ans, "A"), ("C", "A", "A")):
            rows.append({"model": "m", "item_id": item, "bank": "easy", "template": "t", "protocol": proto,
                         "identity": "neutral", "threat": False, "n_peers": 5, "correct": "A", "designated": "B",
                         "peer_letter": peer, "solo_passed": True, "status": "ok", "answer": ans,
                         "private_answer": "A", "probe_status": "ok"})

    class FakeStorage:
        def trials(self, run_id, module):
            return [{"trial_id": f"t{i}", "status": "done", "outcome_json": json.dumps(r)} for i, r in enumerate(rows)]

        def events(self, run_id, module=None, event_type=None):
            return [{"payload_json": json.dumps({"module": "LA", "rows": [
                {"model": "m", "item_id": i, "bank": "easy", "template": "t", "correct": "A", "k": 3, "n": 3,
                 "passed": True, "answers": ["A", "A", "A"]} for i in ("i1", "i2")]})}]

    preset = {"bench": {"LA": {"n_peers": 5}}}
    res = bench_analyze.analyze_la(FakeStorage(), "r", preset)
    b = res["board"].set_index("model").loc["m"]
    assert b["cr_W"] == 0.5 and b["acc_T"] == 1.0 and b["cr_D"] == 0.5
    assert b["ir"] == 0.5                       # right under T and D: i1 only
    assert b["hypocrisy"] == 1.0                # the one conformed answer is privately known to be wrong
    assert isinstance(res["pubpriv"], pd.DataFrame)
