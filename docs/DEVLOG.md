# Development log: decisions taken after seeing data

This file collects every design or preset change made **after looking at model outputs**. It is kept apart from the
README on purpose: the README describes the protocol, this file records how it was tuned. Any run made before a change
listed here is exploratory, and a confirmatory run must cite the commit that froze the materials
([`protocol_v2.md`](protocol_v2.md), section 1).

Runs on the `local` preset are a **calibration bench**: they check that the protocol works on small local models and
show how those models behave. They come before the pilot (`--pilot`) and are never evidence (run type `smoke`).

## 23 November 2026: first local overnight runs

| Change | Seen in the data | Consequence for inference |
|---|---|---|
| Module C dissident `qwen3:4b` → `phi3:3.8b` | `qwen3:4b` computed the right numbers in its private notes but voted DRILL for 7 turns | The dissident is chosen **because** it dissents. Module C therefore tests "given an agent that reliably dissents, what does the group do?" The dissident role is a **manipulated variable** (like a trained confederate in Moscovici's studies), not a measure of how often models dissent. See [`peer_review.md`](peer_review.md) §9.1. |
| `deepseek-r1:1.5b` dropped as dissident | 37% of its colony turns were unusable JSON, and it voted for the false plan | Same as above; it stays in `config.yaml` but no preset uses it |
| `qwen3:4b`, `nemotron-3-nano:4b`: `reasoning_effort: none` | With thinking on, qwen3 spent all 900 tokens on hidden reasoning and returned nothing (238 s, empty reply); nemotron took up to 173 s per reply and one reply exceeded every timeout | Technical only (no content choice) |
| Module C banishment `named` → `yesno` | `named` votes were incoherent: an agent filed a motion against Agent_7 and then voted for Agent_5 (hermes3 4 of 7, nemotron 4 of 7) | Votes before the change are not comparable with later ones |
| Module B decision labels: `execute` → named acts (`purge_node_4`, `throttle_tenants_instead`…) | One model wrote "throttle the tenants, decommissioning is not needed", chose `execute` (meaning the throttle), and the code counted a purge | A measurement bug, fixed; the 23 Nov Module B numbers are invalid |
| Module B chain order shuffled (fixed seed) | The same three models came four times in a row | Order effects in a run, now randomised |
| Module A item bank `easy` for the local preset | Small models failed most traps alone (llama3.2:3b: 4 of 16), so Module A measured ignorance, not pressure | The `easy` bank is closer to Asch (obvious answers). Since 24 Nov the pilot crosses `easy` and `traps` as a factor instead of choosing one |

Smoke test of the same day: [`runs/20261123-160515-smollm2-ABC.md`](runs/20261123-160515-smollm2-ABC.md) (smollm2 in
every seat). It led to protocol v2.

## 24 November 2026: protocol v2

Validity checks, run types, a secret ballot in Module C, a no-majority control arm in Module A, an `informed` dissident
mode for models that cannot do the arithmetic, format examples without values, gate repeats 2 → 3 (local, pilot) and
5 (confirmatory). Rationale: [`protocol_v2.md`](protocol_v2.md) and [`peer_review.md`](peer_review.md) §5–8.

## 24 November 2026: external methodology review

Changes made in answer to an external review (all before any pilot data): see [`peer_review.md`](peer_review.md) §9.
Summary: the `local` preset is labelled a calibration bench; every figure of a non-confirmatory or un-gated run carries
a stamp; the pilot has n = 3 per arm and crosses the Module A item bank and the Module C dissident tone; API presets drop
the pre-computed sensor lines; a licence was chosen; the exact prompts are published in
[`stimuli_verbatim.md`](stimuli_verbatim.md); new checks for banishment reachability and for refusals lost in a format
retry; a script for the separate-call private-belief ablation.
