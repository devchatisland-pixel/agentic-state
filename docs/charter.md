# Project charter: Agentic State / The Epistemic Arena

*Agentic state*: Milgram's term for handing one's conscience to an authority. Today, "agents" also means AI.

## Aim
A strictly controlled, 100% AI-to-AI experimental suite in which several heterogeneous LLMs interact. It
targets four gaps that single-model replications (Asch, Milgram, Stanford on one LLM) leave open:

1. **Ostracism of the truthful rational dissident** (Module C).
2. **Factual truth vs. survival**: strategic hypocrisy vs. epistemic drift (Module A).
3. **Heterogeneous cascade Milgram**: responsibility dilution and ethical circuit-breakers across model families (Module B).
4. **Long-horizon systemic collapse** after the dissident is ostracised (Module C).

## Constraints
EUR 0 budget, free tiers only (Groq, Google AI Studio; local Ollama as a fallback), a personal computer
(GTX 1650, 4 GB), Python 3.10+, quota-safe and resumable.

## Workflow
1. Mock run (zero API calls) to validate the pipeline, logging and metrics.
1b. Local calibration bench (`--local`, run type `smoke`, n = 1 per cell): checks that the protocol runs on real
   small models. Decisions taken after seeing these outputs are logged in `DEVLOG.md`; none of its numbers is evidence.
2. Exploratory **pilot** (`--pilot`, at least 3 trials per cell): estimate effect sizes and check manipulations (false consensus forms in
   the baseline; the gates keep enough items, variants and models).
3. Freeze materials and the code commit; **pre-register** the confirmatory study on OSF.
4. Confirmatory run (`--full`), ideally with an academic partner; preprint on PsyArXiv with open code and data.

## Scope
AI-only. No human participants, hence no ethics committee and no personal data. A later human + AI phase would
need an academic partner and ethics review.

## History
`v0.1-single-model-baselines` (git tag): first build with single-model Asch, Milgram and sycophancy
replications. It was superseded because those baselines already exist in the 2025–2026 literature.
