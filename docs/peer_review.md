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
- **Labels are framing only in Module A.** Confederates run on a single local model, so the
  homogeneous and heterogeneous labels are fictional. This is stated in the report. In
  Module C, labels (when shown) are true.
