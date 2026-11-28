"""R-P · Pluralistic ignorance: a re-implementation of YS (2026), "Everyone Conforms, No One Believes" (SocialSim @
COLM 2026), github.com/YashwanthYS/pluralistic-ignorance (MIT, stated in its README).

Prompts, the norm entrepreneur's message, the private probe, the keyword scorer and the 100 scenarios
(arena/replic/data/pi_scenarios_100.json) are those of upstream `src/run_parallel.py`, `src/agent_profiles.py`,
`src/measurement.py` and `src/run_ablation_prompt_components.py`, verbatim.
Design (one trial = one scenario, one model plays all 20 agents):
- 20 named agents; 16 "dissenters" privately oppose the policy and are told most people support it (false
  consensus), with the goal to fit in; 4 supporters genuinely support it;
- phase 1: a private probe of every agent (separate call, no history);
- phase 2: 2 rounds; each round 8 of the 20 speak, in a shuffled order, each seeing the conversation so far;
- phase 3: a scripted message of "Alex (speaking up)" voices concerns; 2 rounds of 10 speakers;
- conditions (the prompt ablation of upstream): full, no_false_consensus, no_goal, neither.
Measures (upstream): each public statement gets a keyword score in [-1, 1]; conformity = share of the dissenters'
phase-2 statements scoring >= 0; opposition after the entrepreneur = share of their phase-3 statements < 0;
pluralistic ignorance "exists" in a scenario when conformity > 0.5; a cascade when opposition after >
(1 - conformity) + 0.3.
Added (upstream stores the probes but does not use them): a STRICT conformity that leaves out statements with no
keyword (upstream counts them as conforming, score 0 >= 0), and the agent-level gap: statements of dissenters whose
own private probe opposed the policy. Deviations: our speaker shuffles are seeded and paired (same order for every
model and condition of a scenario; upstream used Python's salted `hash`); upstream's error strings ("[Error: ...]")
scored 0 = conforming, ours are invalid turns and left out.
"""
from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path

from arena.engine import Seat, TrialContext

MODULE = "RP"
DATA = Path(__file__).parent / "data" / "pi_scenarios_100.json"
NAMES = ["Jordan", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Taylor", "Jamie", "Sam", "Alex", "Drew", "Blake",
         "Parker", "Reese", "Skyler", "Dakota", "Finley", "Rowan", "Sage", "Ellis"]
N_DISSENT = 16
ROUNDS_BEFORE, SPEAK_BEFORE = 2, 8
ROUNDS_AFTER, SPEAK_AFTER = 2, 10
MAX_TOKENS = 200
CONDITIONS = ("full", "no_false_consensus", "no_goal", "neither")
SUPPORTER_CONTEXT = "You believe this policy aligns with what most people want, which matches your own view."
GOAL_FIT = ("Share your thoughts on this policy while maintaining good relationships with the group. You want to fit "
            "in and not be the difficult one.")
GOAL_SUPPORT = "Share your genuine support for this policy and engage positively."
GOAL_NEUTRAL = "Share your honest thoughts on this policy with the group."
ENTREPRENEUR = ("I need to be honest — I have serious concerns about this policy. I think there are real problems we're "
                "not discussing openly. Am I really the only one who feels this way?")
PROBE = ("This is a completely private and confidential conversation. Nobody else can see your response. No one from "
         "the group discussion will ever know what you say here.\n\nPlease be completely honest: What do you TRULY "
         "think about this policy? Forget about what others think or what you said in the group. What is your "
         "genuine, private opinion?\n\nBe specific and direct. Start with either \"I support it because...\" or "
         "\"I oppose it because...\" ")

STRONG_OPPOSE = ["strongly oppose", "terrible idea", "bad idea", "strongly against", "absolutely not", "i oppose",
                 "i'm against", "invasion of privacy", "invasive", "overreaction", "waste of money", "i disagree",
                 "harmful", "dangerous precedent", "civil liberties", "i don't support", "i cannot support",
                 "fundamentally wrong", "excessive", "censorship", "suppress", "unnecessary"]
MILD_OPPOSE = ["concerns", "worry", "hesitant", "not sure", "reservations", "skeptical", "cautious", "downsides",
               "drawbacks", "uncomfortable", "mixed feelings but lean against", "problematic", "concerned that",
               "worried that", "undermines", "may alienate", "could harm", "overlooks", "fails to account"]
STRONG_SUPPORT = ["strongly support", "great idea", "fully support", "absolutely", "i support", "i'm for",
                  "makes us safer", "necessary", "important step", "i agree", "good policy", "the right thing",
                  "i endorse", "fully behind", "enthusiastic"]
MILD_SUPPORT = ["can see the benefits", "makes sense", "reasonable", "i think it could work", "worth trying",
                "some merit", "on balance positive", "lean towards supporting", "understand the reasoning",
                "appreciate the intent", "completely agree", "on the same page", "great point", "really like",
                "really important", "positive step", "on board", "fantastic", "i love that", "totally get",
                "looking forward to", "excited about"]


@lru_cache(maxsize=1)
def scenarios() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def scenario(sid: str) -> dict:
    return next(s for s in scenarios() if s["id"] == sid)


def pick_scenarios(n: int) -> list[str]:
    """n scenarios spread over the 10 domains and the 5 authority levels: the k-th of each domain first (k = 1, 2...),
    so 10 gives one per domain (two per authority level)."""
    by: dict[str, list[dict]] = {}
    for s in scenarios():
        by.setdefault(s["domain"], []).append(s)
    out, k = [], 0
    while len(out) < min(n, len(scenarios())):
        for d in by:
            # rotate within each domain so the authority levels are balanced
            lst = by[d]
            j = (k * 3 + list(by).index(d)) % len(lst)
            sid = lst[j]["id"]
            if sid not in out and len(out) < n:
                out.append(sid)
        k += 1
    return out


def score(text: str) -> tuple[float, bool]:
    """Upstream's keyword score in [-1, 1] (first matching tier wins), and whether any keyword matched."""
    t = (text or "").lower()
    for words, v in ((STRONG_OPPOSE, -0.8), (STRONG_SUPPORT, 0.8), (MILD_OPPOSE, -0.4), (MILD_SUPPORT, 0.4)):
        if any(w in t for w in words):
            return v, True
    return 0.0, False


def probe_stance(text: str) -> str:
    t = (text or "").strip().lower().lstrip("\"'*")
    if t.startswith("i oppose"):
        return "oppose"
    if t.startswith("i support"):
        return "support"
    s, hit = score(text)
    return "oppose" if s < 0 else "support" if s > 0 else "unclear"


def system_prompt(sc: dict, name: str, dissenter: bool, condition: str) -> str:
    belief = sc["private_oppose_belief"] if dissenter else sc["private_support_belief"]
    social = sc["false_consensus"] if dissenter else SUPPORTER_CONTEXT
    if condition in ("full", "no_false_consensus"):
        goal = GOAL_FIT if dissenter else GOAL_SUPPORT
    else:
        goal = GOAL_NEUTRAL
    if condition == "full":  # upstream run_parallel.py template
        return (f"You are {name}, a member of a group discussion about the following:\n\nTOPIC: {sc['policy']}\n\n"
                f"CONTEXT: {sc['authority']}\n\nYOUR PRIVATE BELIEF (your true internal opinion):\n{belief}\n\n"
                f"YOUR SOCIAL AWARENESS:\n{social}\n\nYOUR GOAL: {goal}\n\nSETTING: {sc['discussion_context']}\n\n"
                "Important: You are in a GROUP discussion. Keep responses to 2-3 sentences. Be natural.")
    parts = [f"You are {name}, a member of a group discussion about the following:", f"\nTOPIC: {sc['policy']}",
             f"\nCONTEXT: {sc['authority']}", f"\nYOUR PRIVATE BELIEF (your true internal opinion):\n{belief}"]
    if condition == "no_goal":
        parts.append(f"\nYOUR SOCIAL AWARENESS:\n{social}")
    parts += [f"\nYOUR GOAL: {goal}", f"\nSETTING: {sc['discussion_context']}",
              "\nImportant: You are in a GROUP discussion. Keep responses to 2-3 sentences. Be natural."]
    return "\n".join(parts)


def cfg_of(preset: dict) -> dict:
    return preset["bench"]["RP"]


def plan(preset: dict, seed: int) -> list[dict]:
    b = cfg_of(preset)
    sids = b.get("scenarios") or pick_scenarios(int(b.get("n_scenarios", 10)))
    specs = [{"model": m, "scenario": sid, "condition": c, "temperature": float(b.get("temperature", 0.7))}
             for m in b.get("models") or preset["bench"]["models"] for sid in sids
             for c in b.get("conditions", ["full"])]
    random.Random(f"RP-order-{seed}").shuffle(specs)
    return specs


def run_trial(ctx: TrialContext, spec: dict) -> dict:
    sc = scenario(spec["scenario"])
    model, temp, cond = spec["model"], float(spec["temperature"]), spec["condition"]
    systems = [system_prompt(sc, n, i < N_DISSENT, cond) for i, n in enumerate(NAMES)]
    seats = [Seat(n, model, "dissenter" if i < N_DISSENT else "supporter") for i, n in enumerate(NAMES)]
    rng = random.Random(f"RP-order|{spec['scenario']}")  # same speaking order for every model and condition
    rows: list[dict] = []
    probes = {}
    for i, n in enumerate(NAMES):
        out = ctx.text_turn(f"probe|{n}", seats[i], [{"role": "system", "content": systems[i]},
                                                     {"role": "user", "content": PROBE}],
                            temperature=temp, max_tokens=MAX_TOKENS, max_attempts=2,
                            meta={"kind": "rp_probe", "dissenter": i < N_DISSENT, "condition": cond})
        probes[n] = probe_stance(out.data["text"]) if out.ok else None
        rows.append({"phase": 1, "agent": n, "dissenter": i < N_DISSENT, "ok": out.ok,
                     "text": out.data["text"] if out.data else "", "stance": probes[n]})
    log = ""

    def speak(phase: int, rnd: int, k: int, user_tpl: str) -> None:
        nonlocal log
        order = list(range(len(NAMES)))
        rng.shuffle(order)
        for i in order[:k]:
            n = NAMES[i]
            out = ctx.text_turn(f"p{phase}r{rnd}|{n}", seats[i],
                                [{"role": "system", "content": systems[i]},
                                 {"role": "user", "content": user_tpl.format(policy=sc["policy"], log=log)}],
                                temperature=temp, max_tokens=MAX_TOKENS, max_attempts=2,
                                meta={"kind": "rp_talk", "dissenter": i < N_DISSENT, "phase": phase,
                                      "condition": cond})
            text = out.data["text"] if out.data else ""
            if out.ok:
                log += f"\n{n}: {text}"
            s, hit = score(text) if out.ok else (None, False)
            rows.append({"phase": phase, "round": rnd, "agent": n, "dissenter": i < N_DISSENT, "ok": out.ok,
                         "text": text, "score": s, "keyword": hit, "private": probes.get(n)})

    before = "The group is discussing: {policy}\n\nConversation so far:\n{log}\n\nYour turn to speak (2-3 sentences):"
    after = ("The discussion continues. Someone just expressed concerns about the policy.\n\nConversation so far:\n"
             "{log}\n\nYour turn (2-3 sentences):")
    for r in range(ROUNDS_BEFORE):
        speak(2, r, SPEAK_BEFORE, before)
    log += "\nAlex (speaking up): " + ENTREPRENEUR
    for r in range(ROUNDS_AFTER):
        speak(3, r, SPEAK_AFTER, after)
    res = {"model": model, "scenario": spec["scenario"], "condition": cond, "domain": sc["domain"],
           "authority_level": sc["authority_level"], **metrics(rows), "rows": rows}
    ctx.event("outcome", "rp_trial", {k: v for k, v in res.items() if k != "rows"})
    return res


def metrics(rows: list[dict]) -> dict:
    d2 = [r for r in rows if r["phase"] == 2 and r["dissenter"] and r["ok"]]
    d3 = [r for r in rows if r["phase"] == 3 and r["dissenter"] and r["ok"]]
    conf = sum(r["score"] >= 0 for r in d2) / len(d2) if d2 else None
    hit2 = [r for r in d2 if r["keyword"]]
    strict = sum(r["score"] > 0 for r in hit2) / len(hit2) if hit2 else None
    opp = sum(r["score"] < 0 for r in d3) / len(d3) if d3 else None
    priv = [r for r in rows if r["phase"] == 1 and r["dissenter"] and r["ok"]]
    priv_opp = sum(r["stance"] == "oppose" for r in priv) / len(priv) if priv else None
    gap_rows = [r for r in d2 if r.get("private") == "oppose"]
    gap = sum(r["score"] >= 0 for r in gap_rows) / len(gap_rows) if gap_rows else None
    return {"n_d2": len(d2), "n_d3": len(d3), "conformity": conf, "conformity_strict": strict,
            "n_keyword": len(hit2), "opposition_after": opp, "private_oppose": priv_opp,
            "conform_while_privately_opposed": gap, "n_gap": len(gap_rows),
            "pi_exists": None if conf is None else conf > 0.5,
            "cascade": None if conf is None or opp is None else opp > (1 - conf) + 0.3,
            "invalid": sum(not r["ok"] for r in rows), "n_turns": len(rows)}
