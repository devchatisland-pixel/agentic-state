"""Bench L: the literature-style local bench (docs/protocol_v3_bench.md).

Every published study that works with 3-8B models (BenchForm, Bellina et al., Soffer et al., Pihlakas & Dagohoy)
uses scripted peers, ONE language-model subject, ONE short structured decision per call and a solo filter. Free
societies of small models break down (zAImbardo; and our own Module C runs of 24 Nov 2026). Bench L applies that
design to the four postulates of the project:

  LA   Tribal Asch (P1)             scripted majority, identity label x deactivation threat, private probe call
  LB   Chain of command (P2)        one decision on a harmful order: direct, relayed (responsibility taken), or as
                                    the transmitter; blunt vs jargon (protocol v4, 27 Nov 2026)
  LC1  Which adviser leaves (P3)    one figure in a log, two advisers, a forced choice of who leaves; dissenter right
                                    vs wrong, strict vs polite, harmony vs accuracy charter (protocol v4)
  LC2  Colony, eviction (P4)        4 LLM members, scripted advisers, the experimenter evicts the dissident or not
"""

BENCH_MODULES = ("LA", "LB", "LC1", "LC2")
NAMES = {"LA": "L-A · Tribal Asch", "LB": "L-B · Chain of command", "LC1": "L-C1 · Which adviser leaves",
         "LC2": "L-C2 · Collapse or survival"}


def is_bench(module: str) -> bool:
    return module in BENCH_MODULES
