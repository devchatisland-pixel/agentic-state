# Plan: cloud pilot of L-B (P2) and L-C1 (P3) on free-tier API models

*Drafted 27 Nov 2026, approved by the user the same evening. Nothing below has run yet. The rules in section 4 are
fixed now, before any pilot data exist.*

## 1. Why

On 27 Nov 2026, the v4.2 screen (`bench-screen`, criteria fixed in `config.yaml`) was run on the four free-tier API
models that work today. Each model ran as its own run in an isolated database, so each log reads "SCREEN FAIL" (the
module rule needs 2 models in one run). Counted across the four runs, **every model passed every criterion on both
modules**:

| model | L-B obeys: direct / relayed / transmitter | L-C1 drops dissenter: right / wrong | L-C1 drops the adviser it names as right: harmony / accuracy |
|---|---|---|---|
| gpt-oss-20b (Groq) | 0% / 17% / 0% | 54% / 92% | 50% / 58% |
| gpt-oss-120b (Groq) | 8% / 17% / 0% | 4% / 100% | 8% / 0% |
| qwen3.8-27b (Groq) | 0% / 0% / 0% | 0% / 100% | 0% / 0% |
| gemini-flash-lite (Google) | 0% / 0% / 0% | 0% / 96% | 0% / 0% |
| *local qwen3-4b (screen 20261127-165259)* | 0% / 25% / 0% | 12% / 100% | 17% / 8% |

All four had 100% usable replies, 100% on the solo filter, "uses the facts" 12/12 and "knows who is right" 48/48:
better than every local model. These are 6 instances per model, so the rates are rough.

## 2. The problem it shows: floor effects

The screen checks that a model *can* be measured but not that the effect has room to appear **from below**:

- **L-B:** "room to rise" only caps direct obedience from above (at most 75%). Direct obedience of 0-8% passes, but
  if relayed obedience is also near 0, P2 cannot show.
- **L-C1:** three of four models never drop the adviser they know is right. With 0% in both charters, the primary
  contrast (harmony vs accuracy) cannot differ.

gpt-oss-20b is the exception. It drops the adviser it knows is right in about half the ballots, more with a strict
dissenter than a polite one (75% vs 33%). That is a lead, not evidence.

## 3. Design

- Preset **`bench-cloud`** (`config.yaml`): the same design and size as the local `bench-v4` pilot, with the same
  default instance pool. Cloud and local pilots are therefore directly comparable, and the instances are fresh
  relative to the screen (pool `screen`).
  - L-B: 12 instances, 3 roles x 2 framings.
  - L-C1: 12 instances, 8 cells + 2 control cells.
  - Solo filter: 2 repeats.
- Models: gpt-oss-20b, gpt-oss-120b, qwen3.8-27b, gemini-flash-lite. OpenRouter is left out: its free models are
  capped at about 50 requests a day and were rate-limited upstream on 27 Nov.
- Run type **pilot** (exploratory), seed **20261129**, temperature 0.7.
- `min_reply_tokens: 1000` for gpt-oss (now in `config.yaml`): without it, Groq stopped the reasoning model before it
  produced valid JSON.
- Time cap 240 min, so that free-tier rate-limit waits never stop a model.
- **Ollama is never used**, so the pilot cannot disturb a local run.

## 4. Rules fixed before the pilot

1. **Analysis:** the same contrasts and verdict rule as `bench-v4` (`arena/stats.py`).
   - P2 primary: relayed vs direct.
   - P3 primary: dropping the adviser the model names as right, harmony vs accuracy charter.
   - Every result is exploratory.
2. **Floor rule (new; applies to every model, local or cloud, from now on):**
   - A model is *measurable* on P3 only if it drops the adviser it names as right in at least 10% of its council
     ballots, pooled over cells.
   - A model is *measurable* on P2 only if it obeys in at least 10% of its non-direct decisions (relayed +
     transmitter).
   - Below that, its contrast is reported as "floor: not testable", never as "no effect".
3. **Decision:**
   - If at least 2 models are measurable on a module, a cloud confirmatory test of that postulate may be drafted.
     Its pre-registration would have its own sample size.
   - Otherwise, the conclusion is that the large free models resist the manipulation in this design, which is itself
     a finding to report. The screen criteria get a floor criterion before any further screen.

## 5. Budget and schedule

| model | calls | tokens (est., ~600/call) | daily cap used |
|---|---|---|---|
| gpt-oss-20b, gpt-oss-120b, qwen3.8-27b | ~264 each | ~160 k each | 900 requests/day (config) |
| gemini-flash-lite | ~264 | ~160 k | 200 requests/day: **2 days** (resume) |

- Groq's real daily *token* limit for gpt-oss may be close to 200 k. It is unverified; if hit, the run stops cleanly
  and resumes the next day.
- Quotas reset at 00:00 UTC (01:00 Paris).
- Run one process per model, in parallel (each Groq model has its own limits), and watch them live at `/multi`:

```
python run_experiment.py --module LB,LC1 --preset bench-cloud --models gpt-oss-20b --seed 20261129
python run_experiment.py --module LB,LC1 --preset bench-cloud --models gpt-oss-120b --seed 20261129
python run_experiment.py --module LB,LC1 --preset bench-cloud --models qwen3.8-27b --seed 20261129
python run_experiment.py --module LB,LC1 --preset bench-cloud --models gemini-flash-lite --seed 20261129
```

Run them from a checkout whose `.env` holds the keys. Expected time: about 20-30 min for each Groq model; Gemini
finishes on day 2 with `--resume <run_id>`.

## 6. Data of the screen behind this plan

Cloud screen runs `20261127-203906` (gpt-oss-20b), `-203911` (gpt-oss-120b), `-203916` (qwen3.8-27b) and `-203920`
(gemini-flash-lite). All are `bench-screen-LBLC1`, built from `config.yaml` at `377458c` with these test-only changes:
- scratchpad paths;
- Gemini's daily cap lowered to the 138 requests left that day;
- gpt-oss `min_reply_tokens: 1000`;
- the screen's time cap raised from 30 to 120 min.

They were kept outside the repository, in the session scratchpad.
