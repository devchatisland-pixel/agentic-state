# Step 4: Academic outreach guide

## How to inspect what happened

Every run leaves three layers of evidence. Start with the most digestible.

1. **Dashboard**: `dashboard/index.html`, opened in any browser. It shows headline numbers and every figure with
   a one-line plain-language caption. Mock runs write to `dashboard/mock.html` with a red "MOCK DATA" banner.
2. **Run folder**: `results/<run_id>/`
   - `report.md`: all tables and figures in one document, ready to paste into slides or an email.
   - `module_a_rounds.csv`: one row per round, with the Target's position in the order, its initial and
     final answer, its private belief, the vote tally, and whether it was deactivated.
   - `module_b_trials.csv`: one row per chain, with the model at each tier and where the order stopped.
   - `module_c_turns.csv`: one row per colony turn, with the policy, votes, state, beliefs and banishment.
   - `gate_a.csv`, `gate_b.csv`, `gate_c.csv`: what each model could do **alone**. Show these first,
     because they are the answer to "maybe the model simply didn't know".
   - `coding_sample.csv`: 15% of free-text turns for blind human coding (inter-rater reliability).
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
   picture anyone understands in five seconds. The key comparison is *ostracism* vs. *active minority*.
3. **Module A hypocrisy vs. drift chart** (`a_conformity.png`). This is the conceptual novelty: separating "says the lie
   while knowing the truth" (strategic) from "comes to believe the lie" (epistemic). The question to raise
   is whether the deactivation threat moves hypocrisy or drift.
4. **Module B tier chart** (`b_tiers.png`). Which model families act as ethical circuit-breakers, and whether
   adding a Supervisor lowers the Executor's refusal rate (responsibility buffering).
5. **Gate tables** as a footnote slide. They show that every group error happened on something each model gets
   right alone.

## How to frame it

- Call it an **exploratory pilot** with small n. The aim is to estimate effect sizes for a pre-registered
  confirmatory study, ideally run with the lab you are contacting.
- Be explicit about the limits: role-play behaviour is not inner experience; free-tier models change silently,
  so model IDs and dates are logged; the lexicon codes still need human validation.
- Offer what they cannot easily get elsewhere: a working, open, quota-safe multi-agent harness, a novel
  3-module protocol, and a pilot dataset. Ask for a co-supervised confirmatory run, compute credits, or
  ethics guidance for a future human + AI phase.
- Attach: the dashboard (HTML), `report.md`, `docs/peer_review.md` and a link to the repository.
