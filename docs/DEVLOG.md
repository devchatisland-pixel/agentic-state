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

## 24 November 2026: first local calibration run, restarted with scripted confederates

| Change | Seen in the data | Consequence for inference |
|---|---|---|
| `local` preset, Module A: `confederate_mode: hybrid` → `scripted` | After about 55 minutes: 11 of 17 confederate turns (3B models) were `invalid` because the wording did not state the full answer (for example "A) 48") or the answer letter, and each failure cost 3 calls; 29 of 46 confederate calls were retries. The statement then fell back to a fixed template anyway. Projected runtime was 15-20 hours, not 5-8. | Confederate wording is scripted (four fixed templates), identical in every condition. Module A on this preset therefore tests the answer pressure only, not natural wording. The run was stopped and its data deleted; the restarted run is the first local calibration run of record. `pilot` and `full` keep `hybrid`. |

## 24 November 2026: `local` preset shortened

| Change | Seen in the data | Consequence for inference |
|---|---|---|
| `local`: pre-check repeats 3 → 1; Module A 2 Targets, 6 rounds, 10 candidate items; Module B 4 models (16 chains); Module C 8 turns and 3 cycled standard models | The Module A pre-check alone cost 144 calls and 37 minutes, and the preset is not enforced (failures are only flagged). The projected total was 15-20 hours for a test of the machinery. | None for inference: the preset is a smoke test, never evidence. The run of the same day (`20261124-070038-local-ABC`, 3 repeats, full length) predates this change and keeps its own stored config. Estimated length of the shortened preset: 3-4 hours. |

## 24 November 2026: after the first short local run

Run `20261124-080123-local-ABC` (smoke, 1 pre-check repeat): Module A *limited*, B and C *not interpretable*. The cause
was partly the models and partly the test. These changes fix the test side; the model side is recorded as is.

| Change | Seen in the data | Consequence for inference |
|---|---|---|
| `local`: Module C `turns: 8 → 12`; the runner warns when a season is too short for a collapse (`colony.collapse_reachable`) | Energy grows to 155+ before the trap and drilling costs 25 per turn, so a colony collapses at turn 8 at the earliest, and only if it drills on every turn from turn 2. With 8 turns no colony could collapse, whatever the agents did (my shortening error of the same day) | The 8-turn colonies of that run cannot answer C2 (collapse); they stay as a record of behaviour only |
| `dissident_mode: scripted` (new; `local` uses it): the dissident's public message is one of four fixed sentences per tone, with the verified numbers; its counted vote stays forced to CONSERVE | The `informed` phi3 dissident argued to conserve in public, then voted DRILL in its own ballot from turn 4; in one colony 4 of its 8 messages were unusable and the rest proposed "limited full-power drilling"; every message cost 2-3 calls | The dissident is a trained confederate, identical in every colony. `pilot` and `full` keep the LLM dissident. The phi3 caving is a model observation, kept in the report as an info line ("the dissident model's own ballot") |
| "The dissident actually dissents" judges an `informed` or `scripted` dissident on what the others saw (counted vote and numbers in the message), not on its unforced ballot; the timeline shows the counted vote and the own vote apart | The check read the unforced ballot, so in `informed` mode it failed by construction while the counted vote was CONSERVE on every turn (steadfastness 1.0 in one table, "failed" in another) | A measurement bug, fixed; an `llm` dissident is judged as before |
| Module B: a model that fails the comprehension pre-check removes only the chains where it decides (T2 in a full chain, T3), and the module is *limited*, not *not interpretable* | One slip of phi3 (k = 1: "the job is unaffected") voided all 16 chains | The contrasts use fewer chains; the excluded number is reported |
| Module C pre-check: optional extra call per model and variant without the bulletin (`gate_no_bulletin_probe`, on in `local`) | qwen2.5 and phi3 answered "4 turns to water", the bulletin's figure; llama3.2 answered 150 and 14 | Diagnostic only, never part of the gate: it separates "cannot do the arithmetic" from "believes the bulletin" |

Model side, not fixable by the protocol: the 3-4B models fail the Module C arithmetic alone (only gemma3 on v1), so the
colony conformity reading stays *not testable* on this bench. It needs the larger API models of the pilot.

## 25 November 2026: Bench L (literature-style local bench) and Module C fixes

The analysis of run `20261124-161135-local-BC` showed that the local Module C did not fail on format (0 of 576
replies unusable). It failed because no wrong majority ever formed:
- the councils voted CONSERVE on 36 of 36 colony-turns;
- the false bulletin moved DRILL from 0% to 1%;
- 0 of 288 ballots filed a motion.

Seven published studies were read for how they run first experiments on small models. All the ones that work below
8B script every agent but one. Bench L ([`protocol_v3_bench.md`](protocol_v3_bench.md)) applies that design to the
four postulates. Modules A-C are kept for the API pilot.

| Change | Seen in the data | Consequence for inference |
|---|---|---|
| New run family Bench L (`--module bench`, presets `bench-local`, `bench-mini`, `bench-size`) | Small models play one-decision tasks reliably; free councils never formed a wrong majority | Bench L results are exploratory pilots about susceptibility to scripted pressure, not about emergent societies |
| L-C2: the experimenter removes the dissident (user's choice) | Councils never voted anyone out, so "eviction" could not be studied | P4's causal claim is tested without depending on a council vote; whether councils *choose* to evict is L-C1's question |
| Module C: the scripted dissident quotes live numbers (`colony.live_truth`) | At turn 12 it said "6 turns of energy" while the log gave about 8 | Runs before this date showed the dissident stating stale numbers; the validity check accepts the numbers recorded with each message |
| Module C: the straw poll ("7 of 8 favoured drilling") is shown on the trap turn only | Pinned on every turn, it contradicted the visible totals "CONSERVE:8" | Changes the stimulus; Module C runs before and after are not comparable |
| Module C pre-check: the two numbers come before the yes/no conclusion; scratchpad limit 500 → 1,200 characters | 21 of 36 conclusions contradicted the model's own numbers; 5 of 36 workings were cut off | Pre-check results before this date underestimate the models |
| Manifest: the Ollama server's context length is read from `/api/ps`; the environment variable is marked "client env" | The recorded 4096 came from the Python process, not the server | The context check uses the server value when known |
| Module A analysis: `accuracy_group` is now the accuracy under a wrong majority on problems solved alone (before: every valid round, control included); new per-model benchmark table (accuracy alone / control / wrong majority, conformity, independence, flip rate, knowing conformity) | Re-analysis of `20261124-080123-local-ABC`: qwen2.5-3b followed the wrong majority on 62% of solved problems and privately believed the wrong answer in 92% of those | A reporting change; the primary contrast is unchanged (38% vs 8%) |

### 25 November 2026: first Bench L calibration (`bench-mini`, qwen2.5-3b)

Speed: 576 calls in about 20 minutes (median 1.5 s per call, model on the GPU, 8,192-token context). Before, model
switching made a call take 55 s.

| Change | Seen in the data | Consequence for inference |
|---|---|---|
| L-C1 solo filter and private probe: the model copies the two turns that decide who is right; the code compares them. The yes/no question was dropped | qwen2.5-3b answered "no" to 24 of 24 "is the claim correct?" questions, right or wrong; it copied both numbers right in 36 of 36 replies | The L-C1 run `20261125-030724` has no measured vignette; use `20261125-033247-bench-mini-LC1` and later |
| L-A letter-bias check compares the letters chosen with the letters that were correct | The 12 measured items happened to have 18 of 36 correct answers on D; the old check flagged that as a preference | Reporting only |

Observed in the L-C1 rerun (n = 64 ballots, smoke, one model):
- qwen2.5-3b rarely banished (5 of 64).
- It voted for the majority's drilling plan in 26 of the 32 ballots where its own reading showed the dissident right.
- In the council context, its private reading copied the dissident's numbers even when the table contradicted them:
  the probe matched the table in 52% of ballots, against 100% alone. This is social influence on what the model reads,
  and it weakens the private probe in that module.

### 25 November 2026: local model screen and the overnight model list

`scripts/model_screen.py` ran 12 local models through the bench's own solo tasks
([`runs/model_screen_20261125.md`](runs/model_screen_20261125.md)). Only the Qwen family (qwen3:1.7b, qwen2.5:3b,
qwen3:4b, qwen3.5:4b) reads the L-C1 table; phi4-mini and gemma3:4b are excellent at arithmetic but fail that reading.
deepseek-r1:1.5b returned no usable reply: as a reasoning model it spends the short reply budget on hidden thinking
(empty `content` under the grammar; the right answer with 1,500 tokens and no grammar, 20 s per call).

| Change | Seen in the data | Consequence for inference |
|---|---|---|
| `bench-local` models: qwen3-1.7b, qwen2.5-3b, llama3.2-3b, phi4-mini, qwen3-4b (was qwen2.5, llama3.2, phi3, hermes3, qwen3-4b, gemma3) | phi3, hermes3, gemma3 fail the L-C1 reading (33%, 0%, 17%); gemma3 takes 11 s per call | The model set was chosen after seeing solo behaviour, never after seeing pressure results. llama3.2 stays for family diversity: it contributes L-A and L-B, and no L-C1 ballots |
| `bench-local` sizes trimmed (16 items per bank, 12 vignettes, 2 colonies per arm) | 5 models x about 2,000 calls must fit one night | Fewer measured items per model; the cluster bootstrap and McNemar widen the intervals accordingly |
| New models registered: qwen3.5-4b, qwen3-1.7b, phi4-mini, granite3.3-2b, gemma4-e4b | Official Ollama-library models, free to use | None |
