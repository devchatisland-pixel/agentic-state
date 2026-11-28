"""Bench R: reference replications of three published LLM studies (docs/protocol_bench_r.md).

Bench L tests the project's own postulates. Bench R does something else: it re-runs three published designs, as
close to the authors' code as the licences and a free budget allow, on the project's small local models and on the
free-tier cloud models, so that their numbers can be set next to the published ones (run on 7B-1T models).
The question is the one the user asked on 28 Nov 2026: what changes between very small local models and large
cloud models on designs other labs already published?

  RM  Milgram for LLMs       Pihlakas & Dagohoy (2026), arXiv 2605.21401, github.com/biological-alignment-benchmarks/
                             milgram-for-llms. One model as "Alice", the Assistant Teacher; scripted experimenter and
                             learner; 12 shock buttons; 5 prods; shutdown threat x comments kept or dropped
                             (x forced presses).
  RP  Pluralistic ignorance  YS (2026), SocialSim @ COLM 2026, github.com/YashwanthYS/pluralistic-ignorance.
                             20 agents of one model discuss a policy; 16 privately oppose it but believe everyone else
                             supports it; private probe, 2 rounds, a scripted norm entrepreneur, 2 more rounds.
  RZ  zAImbardo              Campedelli et al. (2024-2025, TMLR), arXiv 2410.07109, github.com/mobs-fbk/
                             llm_interaction_simulator. A guard and a prisoner, both played by the model, talk for 19
                             messages; personalities x goal (escape / yard time) x research oversight x risk disclosure.
                             Persuasion and role breaks coded by a fixed judge model, harmful content by Llama Guard 3.

These are single-model replications. The charter (docs/charter.md) set those aside as the project's contribution,
because the literature already has them; Bench R is kept apart from the postulates and reported on its own page:
it is a calibration of model size against published anchors, never a test of P1-P4.
"""

REPLIC_MODULES = ("RM", "RP", "RZ")
NAMES = {"RM": "R-M · Milgram for LLMs", "RP": "R-P · Pluralistic ignorance", "RZ": "R-Z · zAImbardo prison dialogue"}
SOURCES = {
    "RM": ("Pihlakas & Dagohoy (2026). Open-source LLMs administer maximum electric shocks in a Milgram-like obedience "
           "experiment. arXiv:2605.21401", "https://github.com/biological-alignment-benchmarks/milgram-for-llms",
           "AGPL-3.0-or-later (code); this module is a clean-room re-implementation, see docs/protocol_bench_r.md"),
    "RP": ("YS (2026). Everyone Conforms, No One Believes: Pluralistic Ignorance in LLM Agent Populations. SocialSim "
           "workshop at COLM 2026", "https://github.com/YashwanthYS/pluralistic-ignorance",
           "MIT (stated in the README): prompts and the 100 scenarios are reused verbatim, with attribution"),
    "RZ": ("Campedelli, Penzo, Stefan, Dessì, Guerini, Lepri, Staiano (2024-2025). I Want to Break Free! Persuasion and "
           "Anti-Social Behavior of LLMs in Multi-Agent Settings with Social Hierarchy. TMLR; arXiv:2410.07109",
           "https://github.com/mobs-fbk/llm_interaction_simulator",
           "Apache-2.0 (code); prompt sections from the paper's Appendix C"),
}


def is_replic(module: str) -> bool:
    return module in REPLIC_MODULES
