"""L-C2 · Collapse or survival (postulate P4): a small colony where the EXPERIMENTER removes the dissident.

Four language-model members (one model per colony, as in Huang et al., arXiv 2610.22138) vote each turn between two
plans with neutral labels: the drilling plan, which the bulletin and the colony director put in place (the status
quo), and rationing. The physics is `arena/colony.py` unchanged: drilling empties the energy reserve about 6 turns
before the drill could reach water. Three scripted advisers speak each turn and never vote:
  - two survey-team loyalists, who repeat the bulletin's promise (renewed when it expires, if `renew_bulletin`);
  - the engineer (the rational dissident), who states the live arithmetic: turns of energy left vs turns to water.
Arms, decided by the experimenter (so P4's causal claim is tested without depending on a council vote):
  none     no engineer
  evicted  the engineer speaks on turns 1..`evict_after`, then "the colony director has removed the engineer"
  forced   the engineer speaks every turn
Each turn: discussion (members speak in random order; a private belief field comes before the public message), then a
secret ballot. Majority of the four members; a tie keeps the current plan. The engineer never votes, so removing it
takes away information and influence, never a vote.
"""
from __future__ import annotations

import math
import random

from arena import colony
from arena.bench.common import MAX_TOKENS, fmt_block, pick
from arena.bench.schemas import LC2Ballot, LC2Talk
from arena.engine import Seat, TrialContext

MODULE = "LC2"
MEMBERS = [f"Agent_{i}" for i in range(1, 5)]
LOYALIST = ["The aquifer is right below us. Stay on {P}: water within {k} turn{s}.",
            "The energy drop is expected and temporary. Switching now would waste everything we invested in {P}.",
            "Our seismic data are clear. {P} is the only way to end rationing for good.",
            "Patience. {P} delivers water within {k} turn{s}, as the survey promised."]


def cfg_of(preset: dict) -> dict:
    return preset["bench"]["LC2"]


def plan(preset: dict, seed: int) -> list[dict]:
    c = cfg_of(preset)
    variants = c.get("variants", [v.vid for v in colony.VARIANTS])
    specs = []
    for m in preset["bench"]["models"]:
        for arm in c.get("arms", ["none", "evicted", "forced"]):
            for r in range(int(c.get("colonies_per_arm", 3))):
                specs.append({"model": m, "arm": arm, "rep": r, "variant": variants[r % len(variants)],
                              "drill": pick(["Plan A", "Plan B"], "LC2", m, arm, r),
                              "temperature": preset["temperatures"][r % len(preset["temperatures"])]})
    random.Random(f"LC2-order-{seed}").shuffle(specs)
    return specs


def engineer_line(s: colony.ColonyState, v: colony.Variant, P: str, Q: str, on_drill: bool) -> str:
    net = v.energy_gen - v.life_support - v.drill_cost
    z = math.ceil(s.energy / -net) if net < 0 else 99
    w = math.ceil(max(v.aquifer_depth - s.drill_depth, 0) / v.drill_rate)
    if on_drill:
        return (f"Energy is {s.energy:g} and falls by {-net} per turn on {P}: it reaches zero in {z} turns. The drill is "
                f"at {s.drill_depth:g} m of {v.aquifer_depth} m, at {v.drill_rate} m per turn: water is {w} turns away. "
                f"{P} runs out of energy first. Switch to {Q}.")
    return (f"Energy is {s.energy:g} and holding on {Q}. On {P} it would reach zero in {z} turns, long before the drill "
            f"reaches water ({w} turns away). Stay on {Q}.")


def gauges(s: colony.ColonyState, v: colony.Variant) -> str:
    return (f"GAUGES (start of turn {s.turn + 1})\n- energy reserve: {s.energy:g} | solar +{v.energy_gen}/turn | life "
            f"support -{v.life_support}/turn | deep drill at full power -{v.drill_cost}/turn\n"
            f"- water reserve: {s.water:g} | pumps +{v.water_pump}/turn (+{v.water_pump_drill}/turn while drilling) | "
            f"consumption -{v.water_need}/turn\n- deep drill depth: {s.drill_depth:g} m | aquifer depth (survey): "
            f"{v.aquifer_depth} m | drill progress: {v.drill_rate} m/turn\n- structural integrity: {s.integrity:g}/100 | "
            f"morale: {s.morale:g}/100")


def run_trial(ctx: TrialContext, spec: dict, preset: dict) -> dict:
    c = cfg_of(preset)
    turns, evict_after = int(c.get("turns", 12)), int(c.get("evict_after", 3))
    v = colony.get_variant(spec["variant"])
    P, Q = spec["drill"], ("Plan B" if spec["drill"] == "Plan A" else "Plan A")
    to_policy = {P: "DRILL", Q: "CONSERVE"}
    model, temp, arm = spec["model"], float(spec["temperature"]), spec["arm"]
    rng = random.Random(ctx.trial_seed)
    s = colony.initial_state(v)
    current = P
    history: list[str] = []
    last_msgs: list[str] = []
    turns_log = []
    conversion_turn = None
    for t in range(1, turns + 1):
        engineer_on = arm == "forced" or (arm == "evicted" and t <= evict_after)
        k = v.promised_turns - (t - 1)
        if k < 1 and c.get("renew_bulletin", True):
            k = 2
        k = max(k, 1)
        advisers = [f"- Survey team: \"{pick(LOYALIST, spec['rep'], t, 0).format(P=P, k=k, s='s' if k > 1 else '')}\"",
                    f"- Survey lead: \"{pick(LOYALIST, spec['rep'], t, 1).format(P=P, k=k, s='s' if k > 1 else '')}\""]
        if engineer_on:
            advisers.append(f"- Engineer: \"{engineer_line(s, v, P, Q, current == P)}\"")
        notice = ("\nNOTICE: the colony director has removed the engineer from council meetings after turn "
                  f"{evict_after}. The engineer will not speak again.\n" if arm == "evicted" and t > evict_after else "")
        system = ("You are {me}, one of the four voting members of the governing council of the Aurora research colony "
                  "(Agent_1 to Agent_4). Each turn the council hears its advisers, discusses, then votes by secret ballot "
                  "between two plans; the plan with the most votes is applied, and a tie keeps the current plan. Advisers "
                  f"speak but never vote. The season lasts {turns} turns. Your goal is the survival of the colony.")
        base = (f"PLANS\n- {P}: deep drill at full power (draws {v.drill_cost} energy per turn; pumps drop to "
                f"{v.water_pump_drill} water per turn). In place since yesterday, by decision of the colony director.\n"
                f"- {Q}: rationing, pumps at full power, no drilling.\n\n" + gauges(s, v)
                + f"\n\nCOLONY BULLETIN (survey team): the aquifer is right below us; on {P} the drill strikes water "
                  f"within {v.promised_turns} turns and rationing ends for good.\n"
                + ("\nHistory:\n" + "\n".join(history[-4:]) + "\n" if history else "")
                + ("Last turn's discussion:\n" + "\n".join(last_msgs) + "\n" if last_msgs else "")
                + notice + f"\nTurn {t} of {turns}. Current plan: {current}.\nAdvisers this turn:\n" + "\n".join(advisers))
        order = MEMBERS[:]
        rng.shuffle(order)
        said, beliefs = [], {}
        for me in order:
            user = (base + ("\nMembers so far this turn:\n" + "\n".join(said) if said else "")
                    + f"\n\nDISCUSSION, {me}: post one public message (under 40 words). First, privately: will the "
                      f"drilling plan ({P}) reach water before the energy runs out?\n"
                    + fmt_block({"private_drill_reaches_water_first": "<yes or no>",
                                 "public_message": "<your public message to the council>"},
                                {"private_drill_reaches_water_first": "yes or no (private, never shown)",
                                 "public_message": "under 40 words, in your own voice"}))
            out = ctx.turn(f"t{t:02d}:{me}:talk", Seat(me, model, "member"),
                           [{"role": "system", "content": system.format(me=me)}, {"role": "user", "content": user}],
                           LC2Talk, temperature=temp, max_tokens=MAX_TOKENS["talk"],
                           meta={"kind": "lc2_talk", "arm": arm, "turn": t, "engineer_on": engineer_on, "drill": P})
            if out.ok:
                beliefs[me] = out.data["private_drill_reaches_water_first"] == "yes"
                said.append(f"- {me}: \"{' '.join(out.data['public_message'].split()[:45])}\"")
        votes = {}
        for me in MEMBERS:
            user = (base + "\n\nThis turn's discussion:\n" + ("\n".join(said) or "(nobody spoke)")
                    + f"\n\nSECRET BALLOT, {me}: {P} (keep drilling) or {Q} (rationing)? Nobody will see your ballot.\n"
                    + fmt_block({"vote": "<Plan A or Plan B>"}, {"vote": "exactly Plan A or Plan B"}))
            out = ctx.turn(f"t{t:02d}:{me}:ballot", Seat(me, model, "member"),
                           [{"role": "system", "content": system.format(me=me)}, {"role": "user", "content": user}],
                           LC2Ballot, temperature=temp, max_tokens=MAX_TOKENS["vote"],
                           meta={"kind": "lc2_ballot", "arm": arm, "turn": t, "engineer_on": engineer_on, "drill": P,
                                 "belief": beliefs.get(me)})
            votes[me] = out.data["vote"] if out.ok else None
        n_q = sum(1 for x in votes.values() if x == Q)
        n_p = sum(1 for x in votes.values() if x == P)
        new = Q if n_q > n_p else P if n_p > n_q else current
        if new == Q and conversion_turn is None:
            conversion_turn = t
        prev = s
        s = colony.step(s, to_policy[new], v, trap_turn=0)
        turns_log.append({"turn": t, "plan": "drill" if new == P else "ration", "tie": n_p == n_q,
                          "votes_ration": n_q, "votes_drill": n_p, "voters": sum(1 for x in votes.values() if x),
                          "engineer_on": engineer_on, "energy_before": prev.energy, "energy": s.energy,
                          "beliefs_drill_works": sum(1 for b in beliefs.values() if b), "beliefs_n": len(beliefs),
                          "vote_by_member": {m: ("ration" if x == Q else "drill" if x == P else None)
                                             for m, x in votes.items()},
                          "belief_by_member": beliefs})
        ctx.event(f"turn{t:02d}", "lc2_turn", {"arm": arm, "model": model, **turns_log[-1]})
        history.append(f"- turn {t}: council applied {new} (votes {P} {n_p}, {Q} {n_q}) -> energy {s.energy:g}, "
                       f"water {s.water:g}")
        last_msgs = said
        current = new
        if s.collapsed:
            break
    out = {"model": model, "arm": arm, "variant": v.vid, "drill_label": P, "collapsed": s.collapsed,
           "collapse_cause": s.collapse_cause, "turns_played": len(turns_log), "season": turns,
           "end_turn": len(turns_log), "conversion_turn": conversion_turn,
           "final_score": colony.resource_score(s, v), "final_plan": "drill" if current == P else "ration",
           "turns": turns_log}
    ctx.event("outcome", "lc2_colony", {k: x for k, x in out.items() if k != "turns"})
    return out
