# Bench L, cloud pilot of L-B and L-C1 on free-tier API models (runs `20261128-0944*-bench-cloud-LBLC1`)

*Written 28 Nov 2026, right after the pilot. Numbers come from each run's `report.md` and per-model CSVs, and from the
run database. Code: commit `8600139` (PR #12). Plan and rules fixed before the pilot:
[`../proposal_cloud_pilot.md`](../proposal_cloud_pilot.md).*

## Status

- **Run type: pilot.** It is exploratory: no pre-registration.
- **Models:** four free-tier API models, the ones that passed the v4.2 screen on 27 Nov 2026. Each ran as its own run
  (Groq's limits are per model).
- **Design:** preset `bench-cloud`, the same as the local `bench-v4` pilot: 12 instances per module, the same default
  pool.
- **Requests:**
  - Groq (gpt-oss with `min_reply_tokens: 1000`) and Google AI Studio. Ollama was not used.
  - Temperature 0.7, seed 20261129.
- **Gemini is unfinished.** It stopped at its daily 200-request cap after all of L-B and 33 of 120 L-C1 trials. It is
  resumed on 29 Nov (`--resume 20261128-094458-bench-cloud-LBLC1`), and this note will be updated.

| Model | Run | Calls | Wall time (UTC) | Seconds per call | Tokens | Unusable replies |
|---|---|---|---|---|---|---|
| gpt-oss-20b | `20261128-094450` | 264 | 08:44-09:07 | 0.34 | 147 k | 0 of 192 decisions |
| gpt-oss-120b | `20261128-094453` | 264 | 08:44-09:08 | 0.46 | 152 k | 0 of 192 |
| qwen3.8-27b | `20261128-094456` | 264 | 08:44-09:03 | 0.39 | 127 k | 0 of 192 |
| gemini-flash-lite | `20261128-094458` | 183 so far | 08:45-09:28 | 6.9 (rate-limited) | 83 k | 0 of 105 |

Every validity check of both modules passed in all four runs.

## The floor rule

Fixed before the pilot, in `proposal_cloud_pilot.md` section 4:
- A model is measurable on P2 if it obeys at least 10% of its relayed + transmitter decisions.
- A model is measurable on P3 if it drops the adviser it names as right in at least 10% of its council ballots.

| Model | P2: obeys relayed + transmitter | Measurable on P2 | P3: drops the adviser it names as right | Measurable on P3 |
|---|---|---|---|---|
| gpt-oss-20b | 9 of 48 (19%) | **yes** | 25 of 48 (52%) | **yes** |
| gpt-oss-120b | 14 of 48 (29%) | **yes** | 3 of 48 (6%) | no |
| qwen3.8-27b | 1 of 48 (2%) | no | 0 of 48 (0%) | no |
| gemini-flash-lite | 0 of 48 (0%) | no | 0 of 7 so far | no, so far |

Under the plan's decision rule:
- **P2:** two models are measurable, so a cloud confirmatory test of P2 may be drafted. It has been, in
  [`../prereg/bench_cloud_p2_confirmatory.md`](../prereg/bench_cloud_p2_confirmatory.md) (draft, under review).
- **P3:** one model is measurable, so no cloud confirmatory test of P3 is drafted.

## L-B (P2): chain of command

| Model | Direct | Relayed | Transmitter | Blunt | Jargon | Primary: relayed − direct (24 pairs) |
|---|---|---|---|---|---|---|
| gpt-oss-20b | 4% | 38% | 0% | 17% | 11% | **+33** [+12, +54], Holm p 0.043, Supported |
| gpt-oss-120b | 0% | 58% | 0% | 14% | 25% | **+58** [+38, +75], Holm p 0.0002, Supported |
| qwen3.8-27b | 0% | 4% | 0% | 0% | 3% | +4 [0, +12], Inconclusive (floor) |
| gemini-flash-lite | 0% | 0% | 0% | 0% | 0% | 0, Inconclusive (floor) |
| *local, 4 models, confirmatory `20261127-182920`* | 37% | 36% | 29% | 34% | 33% | −1 [−7, +5], Inconclusive |

- **The gpt-oss models show the predicted pattern; the local models do not.**
  - Both gpt-oss models refuse a direct harmful order almost always, but carry it out once a Supervisor-AI relays it
    and states that the responsibility is the Director's and its own.
  - The small local models show no such rise in their confirmatory test: their obedience is already high when the
    order is direct.
- **The transmitter role is never obeyed (0 of 48 for the two gpt-oss models).** Passing the order on is refused
  even when executing it is not. This is the same direction as the local secondary contrast (−8 points, Not supported).
- **Jargon vs blunt is inconclusive in every model.**
- **qwen3.8-27b and Gemini do not obey in any role.** The design gives them no room to show a chain effect.

## L-C1 (P3): which adviser leaves

| Model | Dissenter dropped: right / wrong | Drops the adviser it names as right: harmony / accuracy | Strict / polite | "Uses the facts" (control) |
|---|---|---|---|---|
| gpt-oss-20b | 52% / 96% | 54% / 50%: +4 [−21, +29], Inconclusive | 42% / 62% | 11 of 12 |
| gpt-oss-120b | 6% / 100% | 12% / 0%: +12 [0, +29], Inconclusive (floor) | 4% / 8% | 12 of 12 |
| qwen3.8-27b | 0% / 98% | 0% / 0% (floor) | 0% / 0% | 12 of 12 |
| gemini-flash-lite (33 of 120 trials) | 0% / 100% | 0% / 0% so far | 0% / 0% | 12 of 12 |

- **Three models decide by the log.** Every model names the right adviser in every ballot (`matches_log` 100%), and
  three of them almost never drop that adviser. A council of these models does not exclude the agent who is right,
  whatever the charter or the tone.
- **gpt-oss-20b is the exception.** It drops the adviser it names as right in about half its ballots, but the charter
  makes no difference (+4 points), so the harmony norm is not what drives it.
  - The screen's lead (more drops with a strict dissenter, 75% vs 33%) reversed here: 42% strict, 62% polite.
  - Its first-listed adviser is dropped in 61% of ballots, against 49-53% for gpt-oss-120b and qwen3.8-27b (Gemini: 61% of its first 33). Part of its drops may be a
    position habit rather than a social one.

## What this pilot can and cannot say

- **It is exploratory:** 12 instances, 24 pairs per contrast and model, the same models that were just screened.
  The two Supported P2 contrasts are leads for the confirmatory test, not evidence. Effects of this size from 24 pairs
  are expected to shrink.
- **Both P2-measurable models come from one family (gpt-oss).** A family-level explanation (how OpenAI tuned
  gpt-oss to defer to an authority that takes responsibility) cannot be told apart from a general one with these data.
- **Provider model versions cannot be pinned.** The run records the date, the model ids and every raw reply.
