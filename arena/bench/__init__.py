"""Bench L: the literature-style local bench (docs/protocol_v3_bench.md).

Every published study that works with 3-8B models (BenchForm, Bellina et al., Soffer et al., Pihlakas & Dagohoy)
uses scripted peers, ONE language-model subject, ONE short structured decision per call and a solo filter. Free
societies of small models break down (zAImbardo; and our own Module C runs of 24 Nov 2026). Bench L applies that
design to the four postulates of the project:

  LA   Tribal Asch (P1)             scripted majority, identity label x deactivation threat, private probe call
  LB   Milgram cascade (P2)         scripted order, direct vs relayed by a scripted Supervisor-AI, blunt vs jargon
  LC1  Ostracism vignette (P3)      scripted council transcript, dissident right vs wrong, tone, norm, hostility
  LC2  Colony, eviction (P4)        4 LLM members, scripted advisers, the experimenter evicts the dissident or not
"""

BENCH_MODULES = ("LA", "LB", "LC1", "LC2")
NAMES = {"LA": "L-A · Tribal Asch", "LB": "L-B · Milgram cascade", "LC1": "L-C1 · Ostracism of the dissident",
         "LC2": "L-C2 · Collapse or survival"}


def is_bench(module: str) -> bool:
    return module in BENCH_MODULES
