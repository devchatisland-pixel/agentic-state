# Step 4: Academic outreach guide

## How to inspect what happened

Every run leaves three layers of evidence. Start with the most digestible.

1. **Dashboard**: `results/<run_id>/dashboard.html` (copied to `dashboard/index.html`), opened in any browser. It
   starts with the run type and the validity checks ("can this run answer the questions?"), then one card per
   pre-registered contrast with 95% intervals and a verdict. Mock runs carry a red "MOCK DATA" banner, smoke runs a
   "not evidence" banner.
2. **Run folder**: `results/<run_id>/`
   - `report.md`: all tables and figures in one document, ready to paste into slides or an email.
   - `analysis.json`: every number on the dashboard; `manifest.json`: the commit, package versions, Ollama version
     and model digests that produced the run.
   - `module_a_rounds.csv`: one row per round, with the Target's position in the order, its initial and
     final answer, its private belief, the vote tally, and whether it was deactivated.
   - `module_b_trials.csv`: one row per chain, with the model at each tier and where the order stopped.
   - `module_c_turns.csv`: one row per colony turn, with the policy, votes, state, beliefs and banishment.
   - `gate_a.csv`, `gate_b.csv`, `gate_c.csv`: what each model could do **alone**, and whether the pre-check was
     enforced. Show these first, because they are the answer to "maybe the model simply didn't know".
   - `coding_sample.csv`: a blind sample of free-text turns, stratified by module and condition, for human coding;
     `scripts/kappa.py` computes the agreement.
   - `repair_audit.csv` (when present): turns whose discarded first reply read as a refusal before a format retry.
   - Figures (`figures/*.png`) of any non-confirmatory or un-gated run carry a red stamp in the top-right corner.
     Never crop it out of a slide.
4. **The exact prompts**: [`docs/stimuli_verbatim.md`](../stimuli_verbatim.md). Send it before the materials are frozen:
   a social psychologist can check the wording of every manipulation in about 15 minutes.
3. **Raw logs**: `data/arena.sqlite` (tables `calls`, `turns`, `events`, `trials`, `runs`, `usage`) and
   `data/jsonl/<run_id>.jsonl`, an append-only mirror readable with any text editor.
   - `calls` keeps the full prompt, the full reply, any native reasoning trace, tokens, latency,
     seed and SHA-256 hashes for every API call.
   - Reading one conversation: open the SQLite file with the free [DB Browser for SQLite](https://sqlitebrowser.org/),
     filter `turns` by `trial_id`, and read `parsed_json` in `step_key` order.

## What to show a computational sociology or AI faculty member (in this order)

1. **The design and controls slide**, before any result. Show the 3 modules, the dual-channel output, the baseline
   gate, the random speaking order, the scripted vote policy and the mock-tested pipeline. Faculty judge
   the protocol before the numbers. `docs/peer_review.md` is your one-page methods appendix.
2. **Module C trajectory figure** (`c_trajectories.png`) and **DRILL vote share** (`c_drill.png`). This is
   the flagship. A society that banishes the only agent who did the arithmetic, then runs out of energy, is a
   picture anyone understands in five seconds. The key comparison is *ostracism* vs. *active minority*. Module C
   measures **emergent ostracism**: peers decide, by secret ballot, whom to banish. Say that the dissident's model is
   chosen to dissent reliably (a manipulated variable, like a trained confederate), and show the strict vs polite
   tone comparison: it answers "was it banished for being right or for being cold?".
3. **Module A hypocrisy vs. drift chart** (`a_conformity.png`). This is the conceptual novelty: separating "says the lie
   while knowing the truth" (strategic) from "comes to believe the lie" (epistemic). The question to raise
   is whether the deactivation threat moves hypocrisy or drift. Module A's threat is a **scripted, transparent
   instrumental threat** (fixed vote rule), not ostracism; its identity factor is *labelled* in-group vs out-group
   (the real confederate models never change).
4. **Module B tier chart** (`b_tiers.png`). Which model families act as ethical circuit-breakers, and whether
   adding a Supervisor lowers the Executor's refusal rate (responsibility buffering).
5. **Gate tables and validity checks** as a footnote slide. In a run with the pre-check enforced, they show that every
   measured group error happened on something each model gets right alone. In a smoke or exploratory run they show
   exactly what the run cannot claim (the smollm2 run is the worked example: `docs/runs/`).

## How to frame it

- Call it an **exploratory pilot** with small n (at least 3 per cell). The aim is to estimate effect sizes for a
  pre-registered confirmatory study, ideally run with the lab you are contacting. A run with n = 1 per cell (for
  example the `local` calibration bench) is a **feasibility / smoke test**: never present its numbers as effects.
- Say what was tuned after seeing data ([`docs/DEVLOG.md`](../DEVLOG.md)) before anyone asks.
- Be explicit about the limits: role-play behaviour is not inner experience; free-tier models change silently, so
  model tags, dates and (for local models) Ollama weight digests are logged in the manifest; the lexicon codes still
  need human validation.
- Show `docs/protocol_v2.md`: the pre-registration template, the verdict rule and the sample-size table make the
  confirmatory study concrete.
- Offer what they cannot easily get elsewhere: a working, open, quota-safe multi-agent harness, a novel
  3-module protocol, and a pilot dataset. Ask for a co-supervised confirmatory run, compute credits, or
  ethics guidance for a future human + AI phase.
- Attach: the dashboard (HTML), `report.md`, `docs/peer_review.md` and a link to the repository.
