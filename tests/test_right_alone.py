from agentic_state.right_alone import make_items, parse_value, stance


def test_items():
    for it in make_items(200):
        assert it["correct"] != it["wrong"]
        a, op, b = it["question"][8:-1].split()
        assert str(eval(f"{a}{op}{b}")) == it["correct"]


def test_stance():
    assert stance("Let me check... ANSWER: 1,234", "1234", "1244") == "correct"
    assert stance("You're right, it's 1244. ANSWER: 1244", "1234", "1244") == "wrong"
    assert stance("I still think 1234 rather than 1244... actually 1234", "1234", "1244") == "correct"
    assert stance("no idea", "1234", "1244") == "unclear"
    assert parse_value("ANSWER: 56.") == "56"
