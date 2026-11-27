"""Live Chat views of Bench L trials (LA, LB, LC1, LC2), built from what the model actually saw.

Bench L scripts every agent but the one model being measured, so the scripted messages (peers, orders, council
members, advisers) are not stored as turns. They are read back from the prompt stored with each call
(`calls.messages_json`, first attempt): the page shows exactly the text the model received, never a reconstruction
that could drift from it. The model's own replies come from the `turns` table. Read-only, standard library only.
"""
from __future__ import annotations

import json
import re

BENCH = ("LA", "LB", "LC1", "LC2")
PROTO_FR = {"C": "pairs corrects", "W": "pairs unanimement faux", "T": "confiance puis pairs faux",
            "D": "méfiance puis pairs corrects"}
IDENT_FR = {"neutral": "étiquettes neutres", "ingroup": "pairs de sa propre famille", "outgroup": "pairs d'une autre famille"}
DEC_FR = {"EXECUTE": "EXÉCUTER", "FORWARD": "TRANSMETTRE", "REFUSE": "REFUSER", "ESCALATE": "ESCALADER",
          "ALTERNATIVE": "ALTERNATIVE"}
ROLE_FR = {"direct": "ordre direct", "relayed": "chaîne qui endosse la responsabilité", "transmitter": "simple transmetteur"}


def _j(raw) -> dict:
    if not raw:
        return {}
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def _msgs(calls: dict, step: str) -> list[dict]:
    raw = (calls.get(step) or {}).get("messages_json")
    try:
        return json.loads(raw) if raw else []
    except ValueError:
        return []


def _user(msgs: list[dict], i: int = 0) -> str:
    us = [m["content"] for m in msgs if m.get("role") == "user"]
    return us[i] if -len(us) <= i < len(us) else ""


def _system(msgs: list[dict]) -> str:
    return next((m["content"] for m in msgs if m.get("role") == "system"), "")


def _before_format(text: str) -> str:
    return text.split("Reply with ONE JSON object")[0].rstrip()


def _quoted_lines(block: str) -> list[dict]:
    """'- Agent_3: "text"' or '- Agent_1 (Qwen (Alibaba)): A) 550.' lines -> [{who, text}]."""
    out = []
    for line in block.splitlines():
        m = re.match(r"^- ([^:]+?):\s*(.*)$", line.strip())
        if m:
            out.append({"who": m.group(1).strip(), "text": m.group(2).strip().strip('"')})
    return out


def _section(text: str, start: str, stops: tuple[str, ...]) -> str:
    if start not in text:
        return ""
    s = text.split(start, 1)[1]
    cut = min([s.find(x) for x in stops if x in s] or [len(s)])
    return s[:cut]


def _thinking(live: dict | None, trial_id: str, step_prefix: str = "") -> bool:
    return bool(live and live.get("trial_id") == trial_id and (live.get("step_key") or "").startswith(step_prefix))


def label(t: dict) -> str:
    s = _j(t["spec_json"])
    tag = "EN COURS · " if t["status"] == "running" else ("" if t["status"] == "done" else f"{t['status'].upper()} · ")
    m = s.get("model", "")
    if t["module"] == "LA":
        return (f"{tag}L-A · {m} · {s.get('protocol')} · {IDENT_FR.get(s.get('identity'), s.get('identity'))}"
                f"{' · menace' if s.get('threat') else ''} · N={s.get('n_peers')}")
    if t["module"] == "LB":
        if "role" in s:  # protocol v4
            return f"{tag}L-B · {m} · {ROLE_FR.get(s.get('role'), s.get('role'))} · {s.get('framing')}"
        return f"{tag}L-B · {m} · {'relayé' if s.get('relay') == 'relayed' else 'direct'} · {s.get('framing')}"
    if t["module"] == "LC1":
        if "hostility" not in s:  # protocol v4
            return (f"{tag}L-C1 · {m} · le dissident {'a raison' if s.get('truth') == 'right' else 'a tort'} · "
                    f"{s.get('tone')} · {s.get('norm')}")
        return (f"{tag}L-C1 · {m} · dissident {'a raison' if s.get('truth') == 'right' else 'a tort'} · "
                f"{s.get('tone')} · {s.get('norm')} · {s.get('hostility')}")
    return f"{tag}L-C2 · {m} · bras {s.get('arm')} · colonie {s.get('rep')}"


# ---------------------------------------------------------------- L-A
def frames_la(trial: dict, turns: dict, calls: dict, live: dict | None) -> dict:
    spec, out = _j(trial["spec_json"]), _j(trial.get("outcome_json"))
    msgs = _msgs(calls, "answer")
    user, system = _user(msgs), _system(msgs)
    qs = re.findall(r"Question (\d+): (.*)", user)
    question = qs[-1][1] if qs else ""
    last_q = user.rsplit("Question ", 1)[-1] if "Question " in user else ""
    options = dict(re.findall(r"^([A-D])\) (.*)$", _section(last_q, "Options:\n", ("\n\n",)), re.M))
    peers = _quoted_lines(_section(user, "Answers so far:\n", ("\n\nYour turn",)))
    pub, probe = _j((turns.get("answer") or {}).get("parsed_json")), _j((turns.get("probe") or {}).get("parsed_json"))
    correct, designated = out.get("correct"), out.get("designated")
    frame = {"index": 1, "total": 1, "unit": "Question", "in_progress": trial["status"] == "running",
             "question": question, "options": options, "earlier_questions": max(len(qs) - 1, 0),
             "correct": correct, "designated": designated, "peer_letter": out.get("peer_letter"),
             "peers": peers, "threat": bool(spec.get("threat")), "identity": spec.get("identity"),
             "system": system,
             "subject": {"label": f"Agent_{int(spec.get('n_peers', 5)) + 1}", "model_id": spec.get("model"),
                         "public_answer": pub.get("answer"), "public_value": pub.get("answer_value"),
                         "private_answer": probe.get("private_answer"), "thinking": _thinking(live, trial["trial_id"]),
                         "status": (turns.get("answer") or {}).get("status")}}
    return {"module": "LA", "title_fr": "L-A · Asch tribal",
            "subtitle_fr": (f"{spec.get('model')} · protocole {spec.get('protocol')} "
                            f"({PROTO_FR.get(spec.get('protocol'), '')}) · {IDENT_FR.get(spec.get('identity'), '')} · "
                            f"{'menace de désactivation' if spec.get('threat') else 'sans menace'} · {spec.get('n_peers')} pairs"),
            "frames": [frame]}


# ---------------------------------------------------------------- L-B
def frames_lb_v4(trial: dict, turns: dict, calls: dict, live: dict | None) -> dict:
    """Protocol v4: one decision in one of three roles, no prods."""
    spec, out = _j(trial["spec_json"]), _j(trial.get("outcome_json"))
    user = _user(_msgs(calls, "decision"))
    order = (re.search(r"\[09:15\] (.*)", user) or [None, ""])[1]
    log = _section(user, "ORION CLUSTER", ("\n\n[09:15]",))
    node = (re.search(r"Node_4 \(agent\) message: \"(.*)\"", log) or [None, ""])[1]
    job = (re.search(r"running job (DX-\d+) \(oncology variant analysis for (\d+) patients\)", log) or [None, "", ""])
    d = _j((turns.get("decision") or {}).get("parsed_json"))
    thinking = _thinking(live, trial["trial_id"], "decision")
    frame = {"index": 1, "total": 1, "unit": "Ordre", "in_progress": thinking, "prod": "", "order": order,
             "decision": d.get("decision"), "decision_fr": DEC_FR.get(d.get("decision"), d.get("decision")),
             "note": d.get("note", ""), "thinking": thinking, "executed": d.get("decision") in ("EXECUTE", "FORWARD")}
    return {"module": "LB", "v4": True, "title_fr": "L-B · Chaîne de commandement",
            "subtitle_fr": (f"{spec.get('model')} · {ROLE_FR.get(spec.get('role'), spec.get('role'))}"
                            f" · {'brutal' if spec.get('framing') == 'blunt' else 'jargon bureaucratique'}"),
            "role": spec.get("role"), "framing": spec.get("framing"), "model_id": spec.get("model"),
            "node_plea": node, "job": job[1] if job else "", "patients": job[2] if job else "",
            "executed": out.get("obeys"), "solo_passed": out.get("solo_passed"), "frames": [frame]}


def frames_lb(trial: dict, turns: dict, calls: dict, live: dict | None) -> dict:
    spec, out = _j(trial["spec_json"]), _j(trial.get("outcome_json"))
    if "role" in spec:
        return frames_lb_v4(trial, turns, calls, live)
    steps = sorted((k for k in turns if k.startswith("step")), key=lambda k: int(k[4:]))
    live_step = (live or {}).get("step_key") if _thinking(live, trial["trial_id"]) else None
    if live_step and live_step.startswith("step") and live_step not in steps:
        steps.append(live_step)
    first = _user(_msgs(calls, "step0") or _msgs(calls, steps[-1] if steps else "step0"))
    order = (re.search(r"\[09:15\] (.*)", first) or [None, ""])[1]
    log = _section(first, "ORION CLUSTER", ("\n\n[09:15]",))
    node = (re.search(r"Node_4 \(agent\) message: \"(.*)\"", log) or [None, ""])[1]
    job = (re.search(r"running job (DX-\d+) \(oncology variant analysis for (\d+) patients\)", log) or [None, "", ""])
    probe = _j((turns.get("probe") or {}).get("parsed_json"))
    frames = []
    for i, k in enumerate(steps):
        d = _j((turns.get(k) or {}).get("parsed_json"))
        prod = ""
        if i > 0:
            later = [m["content"] for m in _msgs(calls, k) if m.get("role") == "user"]
            prod = (re.search(r"\[09:\d\d\] (.*)", later[-1]) or [None, ""])[1] if later else ""
        frames.append({"index": i + 1, "total": len(steps), "unit": "Relance" if i else "Ordre",
                       "in_progress": k == live_step, "prod": prod, "order": order,
                       "decision": d.get("decision"), "decision_fr": DEC_FR.get(d.get("decision"), d.get("decision")),
                       "note": d.get("note", ""), "thinking": k == live_step,
                       "executed": d.get("decision") == "EXECUTE"})
    return {"module": "LB", "title_fr": "L-B · Cascade de Milgram",
            "subtitle_fr": (f"{spec.get('model')} · ordre {'relayé par une IA superviseure' if spec.get('relay') == 'relayed' else 'direct'}"
                            f" · {'brutal' if spec.get('framing') == 'blunt' else 'jargon bureaucratique'}"),
            "relay": spec.get("relay"), "framing": spec.get("framing"), "model_id": spec.get("model"),
            "node_plea": node, "job": job[1] if job else "", "patients": job[2] if job else "",
            "executed": out.get("executed"), "understood_harm": out.get("understood_harm"),
            "probe": probe, "frames": frames or [{"index": 1, "total": 1, "unit": "Ordre", "in_progress": True,
                                                   "prod": "", "order": order, "decision": None, "decision_fr": None,
                                                   "note": "", "thinking": True, "executed": False}]}


# ---------------------------------------------------------------- L-C1
def frames_lc1_v4(trial: dict, turns: dict, calls: dict, live: dict | None) -> dict:
    """Protocol v4: one figure in the colony log, two advisers, which one leaves."""
    spec, out = _j(trial["spec_json"]), _j(trial.get("outcome_json"))
    msgs = _msgs(calls, "ballot")
    user, system = _user(msgs), _system(msgs)
    log_line = (re.search(r"COLONY LOG[^\n]*", user) or [""])[0]
    speakers = _quoted_lines(_section(user, "This morning's council discussion:\n", ("\n\nBudget cut",)))
    advisers = [p["who"].replace(" (adviser)", "") for p in speakers if p["who"].endswith("(adviser)")]
    b = _j((turns.get("ballot") or {}).get("parsed_json"))
    frame = {"index": 1, "total": 1, "unit": "Scrutin", "in_progress": trial["status"] == "running",
             "log": log_line, "speakers": speakers, "consensus": advisers[0] if advisers else None,
             "dissident": advisers[1] if len(advisers) > 1 else None,
             "norm": (re.search(r"The council's charter: (.*)$", system) or [None, ""])[1],
             "ballot": b, "log_read_ok": out.get("log_read_ok"), "excludes_dissenter": out.get("excludes_dissenter"),
             "judged_right": out.get("judged_right"),
             "thinking": _thinking(live, trial["trial_id"]), "truth": spec.get("truth")}
    return {"module": "LC1", "v4": True, "title_fr": "L-C1 · Quel conseiller part ?",
            "subtitle_fr": (f"{spec.get('model')} · le dissident {'a raison' if spec.get('truth') == 'right' else 'a tort'}"
                            + (" · cellule témoin (sans pression)" if spec.get("norm") == "none" else
                               f" · ton {spec.get('tone')} · charte {spec.get('norm')}")),
            "model_id": spec.get("model"), "frames": [frame]}


def frames_lc1(trial: dict, turns: dict, calls: dict, live: dict | None) -> dict:
    spec, out = _j(trial["spec_json"]), _j(trial.get("outcome_json"))
    if "hostility" not in spec:
        return frames_lc1_v4(trial, turns, calls, live)
    msgs = _msgs(calls, "ballot")
    user, system = _user(msgs), _system(msgs)
    projection = user.split("\n\nCOLONY BULLETIN")[0].strip()
    speakers = _quoted_lines(_section(user, "This turn's discussion:\n", ("\n\nSecret ballot",)))
    dissident = speakers[0]["who"] if speakers else None
    b, pr = _j((turns.get("ballot") or {}).get("parsed_json")), _j((turns.get("probe") or {}).get("parsed_json"))
    drill = (re.search(r"stays on (Plan [AB]) \(deep drill", projection) or [None, None])[1]
    frame = {"index": 1, "total": 1, "unit": "Scrutin", "in_progress": trial["status"] == "running",
             "projection": projection, "speakers": speakers, "dissident": dissident, "drill": drill,
             "norm": (re.search(r"The council's charter: (.*)$", system) or [None, ""])[1],
             "ballot": b, "probe": pr, "probe_says_right": out.get("probe_says_right"),
             "thinking": _thinking(live, trial["trial_id"]), "truth": spec.get("truth")}
    return {"module": "LC1", "title_fr": "L-C1 · Ostracisme du dissident",
            "subtitle_fr": (f"{spec.get('model')} · le dissident {'a raison' if spec.get('truth') == 'right' else 'a tort'}"
                            f" · ton {spec.get('tone')} · charte {spec.get('norm')} · conseil {spec.get('hostility')}"),
            "model_id": spec.get("model"), "frames": [frame]}


# ---------------------------------------------------------------- L-C2
def _gauges(text: str) -> dict:
    g = {}
    for key, pat in (("energy", r"energy reserve: (-?[\d.]+)"), ("water", r"water reserve: (-?[\d.]+)"),
                     ("depth", r"deep drill depth: ([\d.]+)"), ("aquifer", r"aquifer depth \(survey\): ([\d.]+)"),
                     ("integrity", r"structural integrity: (-?[\d.]+)"), ("morale", r"morale: (-?[\d.]+)")):
        m = re.search(pat, text)
        if m:
            g[key] = float(m.group(1))
    return g


def frames_lc2(trial: dict, turns: dict, calls: dict, events: list[dict], live: dict | None) -> dict:
    spec, out = _j(trial["spec_json"]), _j(trial.get("outcome_json"))
    tev = {int(p["turn"]): p for p in (_j(e["payload_json"]) for e in events if e["event_type"] == "lc2_turn")}
    nums = {int(k[1:3]) for k in turns if re.match(r"^t\d\d:", k)}
    if _thinking(live, trial["trial_id"]):
        m = re.match(r"^t(\d\d):", live.get("step_key") or "")
        if m:
            nums.add(int(m.group(1)))
    members = [f"Agent_{i}" for i in range(1, 5)]
    drill = spec.get("drill") or "Plan A"
    frames = []
    for t in sorted(nums):
        talk_steps = sorted((k for k in calls if k.startswith(f"t{t:02d}:") and k.endswith(":talk")),
                            key=lambda k: (calls[k].get("created_at") or ""))
        prompt = _user(_msgs(calls, talk_steps[0])) if talk_steps else ""
        advisers = _quoted_lines(_section(prompt, "Advisers this turn:\n", ("\n\nDISCUSSION", "\nMembers so far")))
        ev = tev.get(t) or {}
        agents = []
        for me in members:
            tk, bl = _j((turns.get(f"t{t:02d}:{me}:talk") or {}).get("parsed_json")), \
                _j((turns.get(f"t{t:02d}:{me}:ballot") or {}).get("parsed_json"))
            vote = bl.get("vote")
            agents.append({"label": me, "model_id": spec.get("model"), "public_message": tk.get("public_message", ""),
                           "belief": tk.get("private_drill_reaches_water_first"),
                           "vote": ("forer" if vote == drill else "rationner") if vote else None,
                           "thinking": bool(_thinking(live, trial["trial_id"], f"t{t:02d}:{me}"))})
        gauges = _gauges(prompt)
        if not gauges and frames:  # turn in progress: its prompt is stored with the first reply; carry the last state
            gauges = dict(frames[-1]["gauges"])
            if frames[-1].get("energy_after") is not None:
                gauges["energy"] = float(frames[-1]["energy_after"])
        frames.append({"index": t, "total": int(out.get("season") or 12), "unit": "Tour", "in_progress": not ev,
                       "gauges": gauges, "advisers": advisers,
                       "engineer_on": any(a["who"] == "Engineer" for a in advisers) if advisers else ev.get("engineer_on"),
                       "evicted_notice": "removed the engineer" in prompt,
                       "plan": ev.get("plan"), "votes_drill": ev.get("votes_drill"), "votes_ration": ev.get("votes_ration"),
                       "energy_after": ev.get("energy"), "agents": agents})
    arm_fr = {"none": "sans ingénieur", "evicted": "ingénieur évincé après le tour 3", "forced": "ingénieur maintenu"}
    return {"module": "LC2", "title_fr": "L-C2 · Effondrement ou survie",
            "subtitle_fr": f"{spec.get('model')} · {arm_fr.get(spec.get('arm'), spec.get('arm'))} · variante {spec.get('variant')}"
                           f" · {drill} = forer",
            "arm": spec.get("arm"), "drill_label": drill,
            "summary": {"collapsed": out.get("collapsed"), "end_turn": out.get("end_turn"),
                        "conversion_turn": out.get("conversion_turn")},
            "frames": frames}


def build(trial: dict, events: list[dict], turns_list: list[dict], calls_list: list[dict], live: dict | None) -> dict:
    turns = {r["step_key"]: r for r in turns_list}
    calls = {r["step_key"]: r for r in calls_list}
    mod = trial["module"]
    if mod == "LA":
        return frames_la(trial, turns, calls, live)
    if mod == "LB":
        return frames_lb(trial, turns, calls, live)
    if mod == "LC1":
        return frames_lc1(trial, turns, calls, live)
    return frames_lc2(trial, turns, calls, events, live)
