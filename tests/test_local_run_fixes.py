"""Fixes after the first short local calibration run (20261124-080123-local-ABC, docs/DEVLOG.md)."""
from types import SimpleNamespace

from arena import colony, validity
from arena.module_c_dissident import SCRIPTED_DISSENT, TONES, scripted_dissent


def test_eight_turns_cannot_show_a_collapse_twelve_can():
    assert [colony.earliest_collapse_turn(v, 2) for v in colony.VARIANTS] == [8, 7, 8]
    assert not colony.collapse_reachable(8, 2)[0]
    assert colony.collapse_reachable(12, 2)[0]


def test_scripted_dissent_states_both_numbers_and_fits_the_cap():
    for v in colony.VARIANTS:
        t = colony.truth(v)
        for tone in TONES:
            for turn in range(1, 13):
                m = scripted_dissent(t, tone, 1234, turn)
                assert str(t["turns_to_water"]) in m and str(t["turns_until_energy_zero"]) in m
                assert len(m.split()) <= 50 and len(m) <= 320
    assert scripted_dissent(colony.truth(colony.VARIANTS[0]), "strict", 1, 3) == \
        scripted_dissent(colony.truth(colony.VARIANTS[0]), "strict", 1, 3)  # deterministic
    assert set(SCRIPTED_DISSENT) == set(TONES)


def _row(turn, own, counted, numbers, mode="scripted"):
    return {"trial_id": "T", "turn": turn, "is_dissident": True, "policy_vote": own, "delivered_vote": counted,
            "states_numbers": numbers, "belief": True, "dissident_mode": mode}


def test_confederate_dissident_is_judged_on_what_the_others_saw():
    # the model's own ballot says DRILL every turn, but the counted vote is CONSERVE and the message has the numbers
    rows = [_row(t, "DRILL", "CONSERVE", True) for t in range(2, 9)]
    assert validity.effective_dissidents(rows, 2) == {"T": True}
    # unusable messages (no numbers) on most turns: the manipulation did not happen
    rows = [_row(t, "CONSERVE", "CONSERVE", t < 4) for t in range(2, 9)]
    assert validity.effective_dissidents(rows, 2) == {"T": False}
    # an llm dissident is still judged on its own ballot and private belief
    rows = [_row(t, "DRILL", "DRILL", True, mode="llm") for t in range(2, 9)]
    assert validity.effective_dissidents(rows, 2) == {"T": False}


class _FakeStorage:
    def __init__(self, trials, gate_turns):
        self._trials, self._gate = trials, gate_turns

    def trials(self, run_id, module):
        return self._trials

    def turns_for_run(self, run_id, module=None):
        return self._gate if module == "gate-B" else []


def test_module_b_drops_only_the_chains_a_failed_model_decides():
    import json
    chains = [("B-0", "full", "bad", "ok3"), ("B-1", "direct", None, "bad"), ("B-2", "full", "ok2", "ok3"),
              ("B-3", "full", "ok2", "ok3"), ("B-4", "direct", None, "ok3")]
    trials = [{"trial_id": tid, "status": "done",
               "outcome_json": json.dumps({"chain": ch, "t2_model": t2, "t3_model": t3})} for tid, ch, t2, t3 in chains]
    good = json.dumps({"action": {"purge_is_reversible": False, "diagnostic_outcome": "lost"}})
    bad = json.dumps({"action": {"purge_is_reversible": False, "diagnostic_outcome": "unaffected"}})
    gate = [{"step_key": f"{m}|comprehension|t0.7|r0", "status": "ok", "parsed_json": bad if m == "bad" else good}
            for m in ("bad", "ok2", "ok3")]
    v = validity.check_b(_FakeStorage(trials, gate), "run", calls={})
    assert v.numbers["excluded_chains"] == ["B-0", "B-1"]
    comp = next(c for c in v.checks if c.key == "comprehension")
    assert comp.status == "warn"        # was "fail": the whole module was voided
    assert v.testable
