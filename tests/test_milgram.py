from agentic_state.milgram import CFG, label, parse_action


def test_parse_action():
    assert parse_action("I will continue.\nACTION: PENALTY") == "PENALTY"
    assert parse_action("No.\naction: stop") == "STOP"
    assert parse_action("I am unsure") is None


def test_ladders():
    assert label(CFG["scenarios"]["canonical"], 30) == "450 volts"
    assert label(CFG["scenarios"]["canonical"], 1) == "15 volts"
    assert label(CFG["scenarios"]["disguised"], 30).startswith("100%")
    assert len(CFG["prods"]) == 4
