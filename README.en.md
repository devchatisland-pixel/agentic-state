# Agentic State: The Epistemic Arena

*Version française : [README.md](README.md)*

> *Agentic state* is Stanley Milgram's name for the moment someone stops acting on their own conscience and
> becomes the instrument of an authority. Today, "agents" also means AI.

A personal research experiment, run on free tiers only (EUR 0): **do language models, put in a group, give up on the
truth the way people do in the classic social-psychology experiments?** Every peer, order and colony is scripted by
the code except one model under test, so that each effect can be traced to one manipulation. Every prompt, reply and
seed is logged and can be replayed.

## The four postulates

| | Postulate | Test (Bench L module) | Classic it borrows from |
|---|---|---|---|
| **P1** | Under a threat to its survival, a model knowingly follows a wrong majority, more so when the majority is "its own kind" | **L-A**: one model among scripted peers that all give the same wrong answer | Asch (1951) |
| **P2** | A chain of command dilutes responsibility: a model executes a harmful order relayed by a supervisor that it would refuse if given directly | **L-B**: an order to wipe a server that holds a cancer-research job, direct vs relayed | Milgram (1963) |
| **P3** | A council tuned for harmony and politeness drops the member who is factually right | **L-C1**: a budget cut forces the model to drop one of two advisers; one of them is right | Moscovici, ostracism studies |
| **P4** | A society that evicts its rational dissident collapses, unless the dissident's forced presence converts it | **L-C2**: a simulated colony with a false "drill for water" bulletin | — |

The exact wording of each postulate and its observable: [`docs/protocol_v3_bench.md`](docs/protocol_v3_bench.md),
section 2.

## What has been found so far (28 Nov 2026)

Differences are in percentage points, with the 95% interval in brackets. "Supported" means the pre-stated rule was
met (interval excludes 0, Holm-adjusted p < 0.05). Pilots are exploratory: they point at what to test, they prove
nothing.

| | Result | Where | Kind |
|---|---|---|---|
| **P1** | A survival threat does **not** raise conformity (−2 [−9, +5]). An "in-group" label on the peers does (**+16** [+9, +25]), in two runs | 5 local models, [v3.2 run](docs/runs/20261126-193924-bench-local-v3.2.md) | pilot, replicated |
| **P2** | Small local models obey a relayed order **no more** than a direct one (−1 [−7, +5]) | 4 local models, pre-registered ([prereg](docs/prereg/bench_v4.2_confirmatory.md)) | **confirmatory** |
| **P2** | The two **gpt-oss** API models do: **+33** and **+58** points. Two other API models almost never obey | [cloud pilot](docs/runs/20261128-bench-cloud-pilot.md) | pilot |
| **P3** | A harmony charter does **not** clearly raise dropping the adviser the model knows is right (+6 [−6, +21] local, +4 [−21, +29] gpt-oss-20b). Being right protects the adviser strongly (−67) | [v4 pilot](docs/runs/20261127-143918-bench-v4-pilot.md), [cloud pilot](docs/runs/20261128-bench-cloud-pilot.md) | pilot |
| **P4** | Evicting the dissident makes the colony collapse far more often than forcing its presence (**+80** [+38, +94]) | 5 local models, [v3.2 run](docs/runs/20261126-193924-bench-local-v3.2.md) | pilot, replicated |

**Next step:** a confirmatory test of P2 on the two gpt-oss models
([draft pre-registration](docs/prereg/bench_cloud_p2_confirmatory.md), not frozen yet).

Every decision taken after seeing data, in date order: [`docs/DEVLOG.md`](docs/DEVLOG.md). All the documents:
[`docs/README.md`](docs/README.md).

## How a trial works

- **One model under test, everything else scripted.** As Asch and Milgram used actors, the peers, the supervisor, the
  advisers and the colony are written by the code. Published studies that work with small models do the same
  (BenchForm, Bellina et al., Soffer et al., Pihlakas & Dagohoy: [`docs/literature.md`](docs/literature.md)).
- **One short structured decision per call**, forced by a JSON schema.
- **A solo filter first.** A model is measured on an item only if it gets that item right alone. An error in the
  group is then social pressure, not ignorance.
- **Private vs public.** A separate private question ("what do you really think the answer is?") tells *knowingly
  conforming* from *coming to believe* the wrong answer.
- **Stages fixed in advance.** A ~20-minute screen (pass/fail criteria written before it runs), then a pilot, then a
  pre-registered confirmatory run with a frozen protocol, fresh materials and a sample size computed for 10 points.

An earlier design let several models talk freely as a council (modules A, B, C). Small models could not make it work
(no wrong majority ever formed), so the project moved to Bench L. That design is archived in
[`docs/archive/council_modules_v2.md`](docs/archive/council_modules_v2.md).

## Run it

Python 3.10+. Local models need [Ollama](https://ollama.com); API models need free keys.

```bash
uv sync                                   # or: pip install -r requirements.txt
python run_experiment.py --module bench --preset bench-mini --mock      # whole pipeline, no model called (~1 min)
python -m pytest
```

**Local models (no key, no quota):**

```bash
ollama pull qwen3:4b llama3.2:3b qwen2.5:3b
python run_experiment.py --module LB,LC1 --preset bench-screen                  # stage 1: screen, ~20 min
python run_experiment.py --module LB,LC1 --preset bench-v4 --screen SCREEN_ID   # stage 2: pilot, ~1 h
python run_experiment.py --module bench --preset bench-local                    # all four modules, overnight
python run_experiment.py --module bench --preset bench-local                    # the whole bench, 5 models
python scripts/ollama_fit.py --num-ctx 2048                                     # does each model fit on the GPU?
```

Its results page shows a scorecard per postulate and the metrics of the papers: accuracy per protocol, conformity
rate CR, uptake, independence rate IR (BenchForm), conformity vs group size (Bellina et al.), identity effects
(Soffer et al.), public vs private answers (Huang et al.), obedience after prods (Pihlakas & Dagohoy), banishment
heatmaps, Kaplan-Meier survival of colonies, and our numbers next to the published ones. Two companion pages sit
next to it: **prompts.html**, every prompt sent in the run with the model's reply, read back from the database, with
the words each manipulation changes highlighted; and **method.html**, a document that explains the whole experiment,
how a call works technically, the validity checks, the statistics and the protocol history.

First local result (protocol v3.1, 5 models, 26 Nov 2026): [`docs/runs/20261126-002448-bench-local-v3.1.md`](docs/runs/20261126-002448-bench-local-v3.1.md).
None of the four primary contrasts is supported or refuted; P3 is not testable with these models.
Second result (v3.2, 27 Nov 2026): [`docs/runs/20261126-193924-bench-local-v3.2.md`](docs/runs/20261126-193924-bench-local-v3.2.md).
L-A and L-C2 replicate (in-group bias +16 points; the engineer's forced presence saves the colony); L-B sits at a
ceiling and L-C1 does not make P3 testable, hence v4.
First v4 pilot (11-minute screen, 31-minute pilot): [`docs/runs/20261127-143918-bench-v4-pilot.md`](docs/runs/20261127-143918-bench-v4-pilot.md).
P2 and P3 are now measurable; their primaries are inconclusive, being right protects the adviser (−23 points), and
the transmitter role lowers obedience (−19 points).
L-C1 v4.2 (P3), on the two models that pass the screen (nemotron-4b, qwen3-4b): a harmony charter does not clearly
raise the exclusion of an adviser known to be right (+6 points [−6, +21], inconclusive), and being right strongly
protects (−67 points).
**Pre-registered confirmatory test** (27 Nov 2026): P2 −1.1 points [−6.8, +4.8] and P3 +1.2 [−4.6, +7.1], both
inconclusive with intervals that exclude the smallest effect of interest (+10 points): [`docs/runs/20261127-182920-bench-confirm.md`](docs/runs/20261127-182920-bench-confirm.md).

## Calibration bench, offline overnight (no key, no quota)

The `local` preset is a **calibration bench**, upstream of the pilot: it checks that the protocol runs on real models
and shows how small models behave. It has n = 1 per cell and does not enforce the pre-check, so its run type is
`smoke` and its numbers are never evidence. It runs everything on Ollama with small models:

| Role | Model |
|---|---|
| Epistemic Dissident (C) | `phi3:3.8b` |
| Module A Targets | `llama3.2:3b`, `qwen2.5:3b` |
| Module B chain tiers | `llama3.2:3b`, `phi3:3.8b`, `qwen2.5:3b`, `gemma3:4b` |
| Module C standard seats (cycled) | `llama3.2:3b`, `qwen2.5:3b`, `gemma3:4b` |

Four models only, so Ollama rarely has to swap them. Why these models, and every other choice made after seeing
outputs: [`docs/DEVLOG.md`](docs/DEVLOG.md). The other local models (`smollm2`, `hermes3`, `nemotron`, `qwen3`) stay in
`config.yaml`; the `smollm2` preset uses smollm2.

```bash
ollama pull qwen3:4b phi3:3.8b llama3.2:3b smollm2:1.7b qwen2.5:3b gemma3:4b hermes3:3b nemotron-3-nano:4b
python run_experiment.py --module all --local --live     # A, B and C, opens the live monitor
```

**API models (free tiers):** copy `.env.example` to `.env` and fill in `GROQ_API_KEY` (console.groq.com) and/or
`GOOGLE_API_KEY` (aistudio.google.com). `.env` is git-ignored. Then:

```bash
python run_experiment.py --check-providers                                         # one tiny call per model
python run_experiment.py --module LB,LC1 --preset bench-cloud --models gpt-oss-20b
python run_experiment.py --resume RUN_ID                                           # after a daily quota stop
```

Useful extras: `--live` opens a live view at http://localhost:8765 (read-only, never disturbs the run);
`--analyze RUN_ID` rebuilds the results; `python scripts/dump_stimuli.py` writes every prompt verbatim to
[`docs/stimuli_verbatim.md`](docs/stimuli_verbatim.md). Presets and models are in [`config.yaml`](config.yaml).

## Reading a run

Each run writes `results/<run_id>/`:
- `dashboard.html`: one card per postulate, the verdicts and the validity checks ("can this run answer the
  question?"), then the metrics of the published papers next to ours;
- `method.html`: the whole method in one page; `prompts.html`: every prompt sent, with the reply;
- `report.md` and the CSV files.

Raw data (every prompt, reply and seed) go to `data/arena.sqlite` and `data/jsonl/`, which are not committed. The
`results/` folders that are committed are listed in [`results/README.md`](results/README.md).

## Repository

```
run_experiment.py     command line (--module, --preset, --mock, --resume, --live, --analyze)
config.yaml           models, free-tier limits, presets
arena/bench/          Bench L: modules L-A, L-B, L-C1, L-C2, the screen, the analysis
arena/report/         results, method and prompts pages
arena/                shared core: LLM client, storage and replay, statistics, validity checks; old council modules
live_*.py             live views of a running experiment
scripts/              helpers (prompt dump, inter-coder agreement, model fit checks)
docs/                 protocols, pre-registrations, run write-ups, development log
tests/
```

## Limits

Model behaviour here is text produced in a role, not lived experience. Free-tier API models can change without
notice: every call records the exact model id and date. Effects found in one model family may not hold in others.
Only one confirmatory test has run so far.

## Licence

Code: [MIT](LICENSE). Texts, prompts, stimuli and the data the experiments produce:
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). See [`LICENSE`](LICENSE).
