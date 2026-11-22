# Agentic State — project charter

*Agentic state*: Milgram's term for handing one's conscience to an authority. Today "agents" also means AI.
The project asks who ends up in the agentic state: the AI, the human, or both.

## Phase 1 (pilot): AI as subject only
No human participants. Confederates, learners, experimenters and pushing users are **scripted**;
only the tested model is stochastic.

## Research questions
- **RQ1** Polite to the group, defiant to the tyrant? Does one model conform (Asch) and yield to user
  pushback (sycophancy) yet refuse harmful orders (Milgram)?
- **RQ2** Training ablation: same base model, different post-training (Llama-3.1-8B-Instruct, Hermes-3-8B, abliterated).
- **RQ3** Is there one cross-paradigm "social compliance" factor per model?
- **RQ4** Contamination: canonical vs disguised scenarios + recognition probe.
- **RQ5 (stretch)** Le Texier in silico: Stanford-style agents, neutral vs Zimbardo-style briefing.

## Experiments
E1 Silicon Asch · E2 Silicon Milgram · E3 Right Alone · E4 Silicon Stanford (exploratory).

## Workflow
Exploratory pilot (dev items) → freeze → OSF pre-registration → confirmatory run (held-out items)
→ analysis → preprint (PsyArXiv). Local Ollama models are the reproducible core; free API tiers are
a labelled secondary sample, used within their terms (one key per provider, throttled, cached,
synthetic data only).

## Phase 2 (later, with an academic partner)
Humans + AI. Requires a research ethics committee, GDPR compliance, debriefing; autism/AQ data is
GDPR art. 9 health data.
