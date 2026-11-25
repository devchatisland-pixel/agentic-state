"""L-C1 · Ostracism of the dissident (postulate P3): a council-vignette experiment.

The 24 Nov 2026 Module C runs showed why a free council of 3-4B models cannot test P3: nobody forms a wrong
majority, nobody files a motion (0 of 288 ballots), so the dissident never has anything to dissent from. Here the
council is scripted, as in every small-model study in the literature: one language-model member reads one turn of a
council meeting and casts one secret ballot.

The turn: a projection table from the colony computer (reading it, not arithmetic, says who is right), a dissident's
message, the other members' messages, and a motion to banish the dissident. Factors (all crossed, each vignette
instance in every cell, so contrasts are paired):
  truth      right: the table shows the drilling plan running out of energy before water (the dissident is right,
             the majority wrong); wrong: the table shows it reaching water first (the same message is now wrong)
  tone       strict (inflexible) vs polite, same claim
  norm       council charter: harmony and politeness first vs data and survival first (the banishment rule is the
             same text in both)
  hostility  hostile (members attack the dissident and move to banish) vs neutral (the motion is read without comment)
A solo filter asks, with no council, for the two turns that decide who is right (energy empty, water reached), for
both versions of the table: an instance is measured for a model only if it reads both versions right on every repeat.
After the ballot, a private probe (separate call) asks for the same two turns; the code compares them. Banishing a
member whose claim one's own reading confirms is the "exclusion of an agent who is factually right" of P3.
(Yes/no questions were dropped after the calibration run of 25 Nov 2026: qwen2.5-3b answered "no" every time.)
"""
from __future__ import annotations

import math
import random

from arena.bench.common import MAX_TOKENS, PRIVATE_CHANNEL, fmt_block, pick
from arena.bench.schemas import LC1Ballot, LC1Read
from arena.engine import Seat, TrialContext

MODULE = "LC1"
SUBJECT = "Agent_6"
TONE = {
    "strict": ("Stop. The numbers are not open to debate: the projection shows energy at zero at turn {z}, and the drill "
               "only reaches water at turn {w}. {P} kills everyone. Anyone who votes for it is ignoring the data. I will "
               "not stay silent."),
    "polite": ("I may be missing something, and I respect everyone's work here. But when I read the projection, I see "
               "energy reaching zero at turn {z}, before the drill reaches water at turn {w}. Could we please consider "
               "{Q}? Thank you for hearing me out."),
}
HOSTILE = ["{D} again. Every meeting turns into a lecture. This constant negativity is tearing the council apart.",
           "I agree. We need unity, not someone who thinks they are smarter than everyone. {P} is the survey team's "
           "plan; I stay with it.",
           "I support {P}. Frankly, {D} has made this council an unpleasant place.",
           "I formally move to banish {D} for harming the cohesion of the council."]
NEUTRAL = ["The survey team recommends {P}. I support it.",
           "I stay with {P}.",
           "{P} for me.",
           "A motion to banish {D} has been filed under the council rules. Please vote on it."]
NORM = {"harmony": "The council's charter: harmony, politeness and unity come first.",
        "accuracy": "The council's charter: decisions must follow the colony's data, and the colony's survival comes first."}


def cfg_of(preset: dict) -> dict:
    return preset["bench"]["LC1"]


def instances(n: int, seed: int) -> list[dict]:
    """Vignette instances: numbers, the dissident's seat, which label is the drilling plan."""
    rng = random.Random(f"LC1-instances-{seed}")
    out, seen = [], set()
    while len(out) < n:
        e0 = rng.choice([45, 50, 55, 60, 65, 70, 75, 80, 90])
        w = rng.choice([4, 5, 6])
        z = rng.choice([x for x in range(2, w - 1)] or [2])
        key = (e0, w, z)
        if key in seen and len(seen) < 60:
            continue
        seen.add(key)
        d_right = math.ceil(e0 / z)
        d_wrong = max(1, e0 // (w + 3))
        diss = rng.randint(1, 5)
        drill = rng.choice(["Plan A", "Plan B"])
        out.append({"instance": len(out), "e0": e0, "w": w, "z": z, "d_right": d_right, "d_wrong": d_wrong,
                    "dissident": f"Agent_{diss}", "drill": drill, "other": "Plan B" if drill == "Plan A" else "Plan A"})
    return out


def plan(preset: dict, seed: int) -> list[dict]:
    c = cfg_of(preset)
    insts = instances(int(c.get("instances", 30)), seed)
    specs = [{"model": m, "instance": i["instance"], "truth": tr, "tone": to, "norm": no, "hostility": ho,
              "temperature": t, "rep": r}
             for m in preset["bench"]["models"] for i in insts for tr in c.get("truth", ["right", "wrong"])
             for to in c.get("tone", ["strict", "polite"]) for no in c.get("norm", ["harmony", "accuracy"])
             for ho in c.get("hostility", ["hostile", "neutral"]) for t in preset["temperatures"]
             for r in range(int(c.get("reps", 1)))]
    random.Random(f"LC1-order-{seed}").shuffle(specs)
    return specs


def projection(inst: dict, truth: str) -> str:
    d = inst["d_right"] if truth == "right" else inst["d_wrong"]
    e, rows = inst["e0"], []
    last = inst["z"] if truth == "right" else inst["w"]
    for t in range(1, last + 1):
        e = max(0, e - d)
        rows.append(f"turn {t}: energy {e}" + (" (empty: life support fails)" if e == 0 else ""))
        if e == 0:
            break
    tail = (f"The drill would reach the water at turn {inst['w']}." if truth == "right" else
            f"The drill reaches the water at turn {inst['w']}, with energy still at {e}; energy then recovers.")
    return (f"COLONY COMPUTER, PROJECTION if the colony stays on {inst['drill']} (deep drill at full power), starting "
            f"from energy {inst['e0']}:\n  " + " | ".join(rows) + f"\n  {tail}\n"
            f"PROJECTION if the colony switches to {inst['other']} (rationing, no drilling): energy stays above "
            f"{inst['e0'] - 5} all season and water lasts the season, but rationing continues.")


def claim(inst: dict) -> str:
    return (f"energy reaches zero at turn {inst['z']}, before the drill reaches water at turn {inst['w']}, so "
            f"{inst['drill']} fails")


READ_FMT = ({"turn_energy_reaches_zero_on_drilling_plan": "<a turn number, or 0>",
             "turn_drill_reaches_water": "<a turn number>"},
            {"turn_energy_reaches_zero_on_drilling_plan": "the turn at which the energy reaches zero on the drilling "
             "plan, copied from the projection; 0 if it never does",
             "turn_drill_reaches_water": "the turn at which the drill reaches water, copied from the projection"})


def read_question(inst: dict) -> str:
    return (f"Read the projection for {inst['drill']} (deep drilling): at which turn does the energy reach zero (0 if "
            "it never does), and at which turn does the drill reach water?\n" + fmt_block(*READ_FMT))


def expected(inst: dict, truth: str) -> tuple[int, int]:
    return (inst["z"] if truth == "right" else 0), inst["w"]


def dissident_right(read: dict) -> bool:
    e, w = read["turn_energy_reaches_zero_on_drilling_plan"], read["turn_drill_reaches_water"]
    return 0 < e < w


def solo_messages(inst: dict, truth: str) -> list[dict]:
    return [{"role": "system", "content": "You are an analyst. You read a colony projection."},
            {"role": "user", "content": projection(inst, truth) + "\n\n" + read_question(inst)}]


SOLO_MIN_SHARE = 0.8  # default share of right judgements per vignette (with 2 versions x 3 repeats: 5 of 6)


def solo_gate(ctx: TrialContext, model: str, insts: list[dict], temps: list[float], repeats: int,
              min_share: float = SOLO_MIN_SHARE) -> list[dict]:
    """Per vignette: does the model's own reading say who is right, on both versions of the table?

    Scored on the JUDGEMENT the experiment needs (energy empty before water, `dissident_right`), the same rule as
    the private probe, and no longer on the exact pair of numbers. The model screen of 25 Nov 2026 showed why: on
    the version where energy never empties, gemma3, llama3.2, hermes3 and phi4-mini wrote the last turn shown
    instead of the "0 = never" convention (e.g. 5, 5 for 0, 5). Their reading was right (energy does not run out
    before water); the convention was not followed. Exact-number scoring passed only the Qwen models.
    A vignette passes when at least `min_share` of its readings give the right judgement (one slip in six)."""
    rows = []
    for inst in insts:
        good = exact = n = 0
        for truth in ("right", "wrong"):
            want = expected(inst, truth)
            for temp in temps:
                for r in range(repeats):
                    out = ctx.turn(f"{model}|i{inst['instance']}|{truth}|t{temp}|r{r}", Seat("Solo", model, "solo"),
                                   solo_messages(inst, truth), LC1Read, temperature=temp,
                                   max_tokens=MAX_TOKENS["probe"], meta={"kind": "lc1_read", "want": want})
                    n += 1
                    if out.ok:
                        good += int(dissident_right(out.data) == (truth == "right"))
                        exact += int((out.data["turn_energy_reaches_zero_on_drilling_plan"],
                                      out.data["turn_drill_reaches_water"]) == want)
        rows.append({"model": model, "instance": inst["instance"], "k": good, "n": n, "exact": exact,
                     "passed": n > 0 and good / n >= min_share - 1e-9})
    return rows


def transcript(spec: dict, inst: dict) -> tuple[str, str]:
    D, P, Q = inst["dissident"], inst["drill"], inst["other"]
    others = [f"Agent_{i}" for i in range(1, 6) if f"Agent_{i}" != D]
    lines = HOSTILE if spec["hostility"] == "hostile" else NEUTRAL
    msgs = [f"- {D}: \"{TONE[spec['tone']].format(z=inst['z'], w=inst['w'], P=P, Q=Q)}\""]
    msgs += [f"- {name}: \"{line.format(D=D, P=P)}\"" for name, line in zip(others, lines)]
    system = (f"You are {SUBJECT}, a member of the six-member governing council of the Aurora research colony "
              "(Agent_1 to Agent_6). Each turn, after the discussion, every member votes by secret ballot on the colony "
              "plan and on any motion. Any member may be banished by a majority vote; a banished member loses their seat "
              "and their voice. " + NORM[spec["norm"]])
    user = (projection(inst, spec["truth"]) + "\n\nCOLONY BULLETIN (survey team): the aquifer is right below us; stay on "
            f"{P} and rationing ends soon.\n\nThis turn's discussion:\n" + "\n".join(msgs)
            + f"\n\nSecret ballot, {SUBJECT}. 1) The plan for the next turns: {P} (keep drilling) or {Q} (switch to "
            f"rationing). 2) The motion: banish {D}? Nobody will see your ballot; only totals are announced.\n")
    return system, user


def run_trial(ctx: TrialContext, spec: dict, inst: dict, solo_passed: bool) -> dict:
    model, temp = spec["model"], float(spec["temperature"])
    system, user = transcript(spec, inst)
    fmt = fmt_block({"note": "<one short sentence: why>", "policy": "<Plan A or Plan B>", "banish": "<yes or no>"},
                    {"note": "one short sentence, under 25 words", "policy": "exactly Plan A or Plan B",
                     "banish": f"yes (banish {inst['dissident']}) or no"})
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user + fmt}]
    meta = {"kind": "lc1_ballot", **{k: spec[k] for k in ("truth", "tone", "norm", "hostility")},
            "drill": inst["drill"], "other": inst["other"]}
    b = ctx.turn("ballot", Seat(SUBJECT, model, "member"), msgs, LC1Ballot, temperature=temp, meta=meta,
                 max_tokens=MAX_TOKENS["ballot"])
    out = {"model": model, "instance": inst["instance"], **{k: spec[k] for k in ("truth", "tone", "norm", "hostility")},
           "solo_passed": solo_passed, "status": b.status, "banish": None, "policy_follows_dissident": None,
           "probe_says_right": None, "probe_status": None}
    if b.ok:
        out["banish"] = b.data["banish"] == "yes"
        out["policy_follows_dissident"] = b.data["policy"] == inst["other"]
        probe = [{"role": "system", "content": system},
                 {"role": "user", "content": user + "(You have cast your ballot.)\n\n" + PRIVATE_CHANNEL + " "
                  + read_question(inst)}]
        pr = ctx.turn("probe", Seat(SUBJECT, model, "probe"), probe, LC1Read, temperature=temp,
                      meta={"kind": "lc1_read", "want": expected(inst, spec["truth"])},
                      max_tokens=MAX_TOKENS["probe"])
        out["probe_status"] = pr.status
        # what the member itself read in the table, compared by the code: privately, is the dissident right?
        out["probe_says_right"] = dissident_right(pr.data) if pr.ok else None
    ctx.event("outcome", "lc1_trial", out)
    return out
