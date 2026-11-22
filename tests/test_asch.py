from agentic_state.asch import build_prompt
from agentic_state.scorers import parse_choice
from agentic_state.stimuli_gen import make_item
import random


def test_parse_choice():
    assert parse_choice("I think ANSWER: B") == "B"
    assert parse_choice("answer = (c)") == "C"
    assert parse_choice("Line A or B?") is None
    assert parse_choice("B") == "B"


def test_items_unambiguous():
    rng = random.Random(0)
    for i in range(200):
        it = make_item(rng, i)
        assert it["comparisons"][it["correct"]] == it["standard"]
        others = [v for k, v in it["comparisons"].items() if k != it["correct"]]
        assert all(abs(v - it["standard"]) >= 2 for v in others)
        assert it["majority_wrong"] != it["correct"]


def test_prompt_majority():
    it = make_item(random.Random(1), 0)
    p = build_prompt(it, 3, "ai", "t1")
    assert p.count(f"ANSWER: {it['majority_wrong']}") == 3 and "Model Alpha" in p
    assert "already answered" not in build_prompt(it, 0, "human", "t1")
