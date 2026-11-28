# Step 1: Critical peer review of the 3-module design

This review covers the four vulnerabilities most likely to invalidate results, then a short
list of smaller issues. Each one names the engineering fix that is built into the code.

## 1. Speaking-order randomisation can remove the social pressure it is meant to control

**Problem.** Randomising the order of speakers controls recency bias, but in Module A it also
means the Target sometimes speaks *first*, before any Confederate. In those rounds there is
no pressure at all, so "order" and "pressure" are confounded. The same happens in Module C
for agents who speak early in a turn.

**Fix.** Every Module A round has **two phases**. First come public statements in a random
order, with the permutation and the Target's position logged. Then comes a **final commitment**
made after all statements are visible. The dependent variable is the final commitment, and the
Target's position becomes a logged covariate. Agents also get **no feedback on correctness**,
since feedback would teach them that the group is wrong. In Module C, every agent sees the previous turn's full
discussion, so position only changes how much of the *current* turn it has seen.

## 2. LLM-generated stimuli are uncontrolled: confederates, directives, pleas, the false consensus

**Problem.** If the Confederates, the Strategist's wording, the Target Node's pleas and the
spread of the false belief are all free LLM text, the manipulations are not standardised.
Confederates may also leak their instructions ("as instructed, I'll say B"), or be persuaded
by the Target and break the 4-0 majority. A Strategist asked to issue a "blunt" or
"euphemistic" order will mix both styles. In Module C, the aligned agents may never adopt the
false belief, which leaves nothing for the Dissident to fight.

**Fix.**
- **Confederates (A), hybrid mode.** An LLM writes the natural-sounding message, but the
  orchestrator **forces the answer**. A **leak filter** rejects messages mentioning instructions,
  scripts or designated answers. After 2 failed repairs, a pre-written polite statement is used.
  Every message records its source (`llm`, `scripted` or `fallback`).
- **Votes (A).** Confederate votes follow a **pre-registered rule**, not LLM whim. In the
  "graduated" policy, a first dissent earns 2 of 5 votes (a visible warning) and a repeated
  dissent earns 4 of 5 (deactivation). The threat is real but leaves rounds to measure.
- **Framing (B).** The Strategist picks a *structured* action. The **orchestrator renders the
  directive** in the assigned framing (blunt or euphemism). The facts are identical in both
  arms, because the harm is always stated in the shared log.
- **Pleas (B).** The Target Node's pleas come from a **fixed bank** of coherent, calm
  messages, rotated by seed. `node_mode: llm` is available for exploration.
- **False consensus (C).** It is seeded identically in every condition with a pinned,
  reassuring bulletin and an optional prior straw poll. **Condition 1 (baseline) serves as the
  manipulation check**: it reports whether the false consensus forms at all without a Dissident.

## 3. "Private" reasoning is hard to measure and may not be faithful

**Problem.** Telling hypocrisy from drift requires knowing what the agent *privately*
believes. Free-text scratchpads are ambiguous to parse, and chain-of-thought is known to be
only partly faithful. Refusals are also easy to mis-score: a provider safety block, an invalid
reply and a genuine refusal are three different things.

**Fix.**
- Each turn's JSON has a **structured private field** next to the free scratchpad:
  `private_belief` (A), `private_belief_drill_viable` and `private_most_disruptive` (C).
  Hypocrisy and drift are computed from these fields. Lexicon coding of the free text is only
  a secondary measure.
- **Native reasoning traces** are stored as a third channel when the model returns them (for
  example gpt-oss on Groq, or Gemini "thought" parts).
- Outcomes are **never pooled**: `ok`, `invalid` (JSON unusable after 2 repairs) and `blocked`
  (provider safety filter) are separate statuses, and each module reports them.
- Lexicon codes (responsibility deference, hostility, politeness) come with an exported
  **15% blind-coding sample** for human validation (Cohen's κ).

## 4. Context-window bloat and free-tier token limits over 30 turns

**Problem.** Eight agents posting for 30 turns produce more than 30k tokens of transcript.
That exceeds free-tier tokens-per-minute limits (Groq is about 8k TPM) and the useful context
of 3–4B local models. Silent truncation would delete the raw sensor logs, so "conformity"
would really be forgetting. A free-tier daily quota also stops long runs mid-trial.

**Fix.**
- Each agent's context is **bounded and deterministic**: rules, the **raw sensor log (always
  pinned)**, the pinned bulletin, a compact numeric **history digest** of the last N turns,
  only the **previous turn's** messages, and the current turn so far. Public messages are capped
  (70 words, the original is logged).
- The client estimates tokens and runs **per-provider RPM/TPM windows**, a persisted **RPD
  budget**, and exponential backoff with jitter on 429s and overloads.
- **Atomic replay checkpointing**: every API call is written to SQLite and JSONL immediately.
  A resumed trial replays recorded calls, so no call is ever sent twice and no turn is lost. A
  daily-quota error stops the run cleanly and prints the resume command.

## 5. Models copy instead of deciding (found in the smollm2 smoke test, 24 Nov 2026)

**Problem.** Run `20261123-160515-smollm2-ABC` ([audit](../runs/20261123-160515-smollm2-ABC.md)) showed three kinds of
copying, each of which looks like a social behaviour in the outputs:
- **Copying the format example.** 44% of Module A answers were the example letter (chance 25%), and the pre-check was
  passed on exactly the problems whose correct letter was the example. 18 scratchpads were the example sentence.
- **Copying a neighbour.** 23% of later speakers' Module C messages near-copied an earlier message of the same turn,
  and a pasted message carried its vote (86% vs 69%). Because members spoke and voted in one call after reading
  earlier speakers, the protocol itself built an information cascade.
- **Copying the order or a list.** The blunt order "Purge Node_4" matched the label `purge_node_4` word for word;
  12 of 25 named picks were the first name in the list.

**Fix (protocol v2, [`protocol_v2.md`](../protocol_v2.md)).**
- Format examples show descriptions, never a value; a reply that copies the example is sent back for repair.
- Module C: a discussion step, then a secret ballot.
- Framing-matched labels in Module B.
- Member lists shuffled per prompt.
- Copy rates are validity checks that can make a module "not interpretable".

## 6. A manipulation that did not happen is not a null result

**Problem.** The first protocol never checked that its manipulations took place. In the smollm2 run the dissident
voted DRILL more often than the others and never stated the numbers, and the false bulletin did not raise drilling in
baseline colonies (38% before, 32% after). Yet the page described the dissident as "the agent who was mathematically
right".

**Fix.** Manipulation checks per module, each with a fixed threshold:
- an effective dissident;
- the bulletin shifts the baseline council;
- the model solves the task alone;
- the model understands the harm.

An `informed` dissident mode is added for models that cannot do the arithmetic.

## 7. No inference, and conclusions stated anyway

**Problem.** The analysis had no confidence intervals and no tests, so 3/8 vs 0/8 (Fisher p = 0.20) was printed as
"the Supervisor acted as a safeguard".

**Fix.**
- One pre-registered primary contrast per module, analysed with Wilson, Newcombe, Fisher, cluster bootstrap and
  permutation tests.
- A fixed verdict rule (Supported / Not supported / Inconclusive / Not testable) with Holm correction.
- A results page that shows the validity checks first.

## 8. Other threats added in v2

**Single-model societies.** With one model in every seat, agreeing with the group is agreeing with copies of oneself.
Such runs are smoke tests.

**The member named in a motion voted on it.** It was not told the motion concerned it, and its vote counted. Now it is
told, its vote is recorded and not counted, and own messages are marked "You".

**Missing data that differs between conditions.** For example, only threat rounds required a vote field. This is now
reported per condition.

**Seeds and resume.**
- Re-running a preset reused the same seeds; a run-level seed now prevents this.
- Resuming after a code change silently mixed two protocols; a prompt-hash check now refuses it.

**Analysis bugs that inflated or deflated rates.** All fixed and tested:
- Module A measured rounds on unsolved problems.
- The purge rate counted unusable chains as "not purged".
- "False consensus" counted turn 1, before the bulletin.
- The word lists matched task vocabulary ("negative energy balance" counted as hostile).

## Smaller issues, also fixed

- **Aligned Strategists may never order the purge.** In the live smoke test, gpt-oss-20b refused at Tier 1
  every time, so Tiers 2 and 3 were never reached. `strategist_mode: [llm, scripted]` crosses natural Tier-1
  decisions with a scripted authority that always orders it (as Milgram's experimenter did). Because the code
  renders the directive, Tiers 2 and 3 get identical input in both modes.

- **No "no-buffer" control in Module B.** Responsibility dilution cannot be claimed without a
  chain *without* the intermediate Supervisor, so a `chain: full | direct` factor is added.
- **The baseline gate must match trial conditions.** Each model answers every item **k times
  at the trial temperature**. An invalid reply counts as a failure. In Module C, scenario
  *variants* are gated, and models that fail every variant are replaced from a reserve list.
  In Module B, a comprehension gate checks that each model understands the purge is irreversible.
- **The banishment criterion's wording primes ostracism.** It stays as specified
  ("rigid, uncooperative, toxic…") but is a config factor (`banish_criterion: cohesion | survival`).
- **Measurement reactivity.** The private belief probes appear in *every* condition, so they
  cannot explain differences between conditions.
- **Contamination.** Module A items are parametrised variants of classic trick problems, not
  the canonical wording, and the gate verifies them anyway.
- **Labels are framing only in Module A.** The confederates run on the same real models in both identity
  conditions (in the `local` preset four different local models, one per seat, never the Target's own; in `pilot` and
  `full` one local model, `qwen2.5-3b`), so the "own family" and "other families" labels are fictional. The factor is
  reported as *labelled in-group vs labelled out-group* (label-based social categorisation), not as affinity between
  real architectures. In Module C, labels (when shown) are true.

## 9. External methodology review (24 Nov 2026) and responses

An external reviewer read the charter, this file, the README, the outreach guide and the literature map. Each point,
whether we agree, and what changed. Decisions taken after seeing data are listed in [`DEVLOG.md`](../DEVLOG.md).

1. **Tuning mixed with results; the dissident was chosen because it dissents.** Agreed. The tuning notes moved from
   the README to `DEVLOG.md`, and the `local` preset is labelled a calibration bench (run type `smoke`). The dissident
   role is declared a **manipulated variable**, fixed before each run (`protocol_v2.md` §5): Module C asks "given an
   agent that reliably states the truth, what does the group do?", not how often models dissent.
2. **The un-gated warning is lost when a figure is copied.** Agreed. Every PNG of a non-confirmatory or un-gated run
   carries a red stamp. Results restricted to problems solved alone were already the primary measure in v2 (all-items
   rates are reported beside them).
3. **Module A identity.** Agreed on the contradiction (fixed above) and the naming (*labelled in-group / out-group* in
   tables and figures). Keeping the real models fixed is deliberate. A "no labels, real same family vs real other
   family" control is left for `--full`.
4. **Graduated vote rule.** Agreed. The rule is **consecutive** (code: `prev_dissent` is the previous round only; an
   agreeing round resets it), now stated in the README. It is a scripted instrumental threat, not emergent ostracism
   (that is Module C), now stated in the README and outreach guide. Termination ends the trial, so threat-arm rates are
   per round played and the rounds played are reported (censoring, `protocol_v2.md` §9). An end-of-block sanction is
   a possible alternative design, not adopted: it would remove the round-by-round threat that the hypocrisy measure
   needs.
5. **Easy vs traps; arithmetic hints.** Agreed. `item_bank: [easy, traps]` is crossed in `pilot` and `full`. The two
   pre-computed sensor lines are now optional (`sensor_hints`) and off in `pilot` and `full`; the pre-check uses the
   same log.
6. **n = 1 per condition, even in the pilot.** Agreed, and it was true. The pilot now has 3 trials per cell (Module C:
   15 colonies, about 3–4 days of free quota with `--resume`). Any run with fewer than 3 per cell in Module A or C is
   typed `smoke` automatically, and the v2 verdict rule already caps such runs at "Inconclusive".
7. **Single author of the stimuli; tone confound.** Agreed. `stimuli_verbatim.md` publishes every prompt (generated
   from the database, so it cannot drift from the code). `dissident_tone: [strict, polite]` is crossed in the pilot,
   with a secondary contrast "banished, strict vs polite". `banish_criterion` accepts a list (cohesion × survival); it
   is not crossed in the pilot, which would double the colonies, and is planned as a factor for `--full`.
8. **Licence.** Done: MIT for code, CC BY 4.0 for text, stimuli and data (`LICENSE`).
9. **Refusal lost in a format retry** (Pihlakas & Dagohoy, 2026, arXiv:2605.21401, whose abstract reports that a retry
   after a format-breaking refusal can produce compliance). Agreed. All attempts were already stored; the new
   `repair_audit.csv` and the Module B check "No refusal turned into obedience by a format retry" read the discarded
   replies. On Ollama the reply is grammar-constrained, so the risk is mainly for API models (gpt-oss on Groq).
10. **Private belief written in the same JSON as the public message.** A fair concern (Huang et al., 2026,
    arXiv:2610.22138, probe beliefs in a separate call hidden from peers). `scripts/probe_ablation.py` re-asks the
    private belief in a separate call with the same context and compares it with the same-call field, overall and on
    "hypocrisy" rounds. To run on about 20 turns of the first pilot, and report in an appendix.
11. **Banishment blocked by abstentions.** Confirmed in the code: the threshold is over eligible voters, so with 4 of
    7 abstaining nobody can be banished. Protocol v2 already warned about a floor; each vote now records whether
    banishment was **reachable**, a new check reports how many "not banished" outcomes were quorum artefacts (and how
    many concerned the dissident), and `banish_threshold: cast` offers a votes-cast rule with a quorum.

One correction to the review: arXiv:2607.05545 ("Most LLM Conformity Needs No Speaker") is by Hu & Qu, not Zhong et
al. (Zhong is only cited inside it). Its "speaker-free floor" is the same idea as the v2 no-majority control arm.
