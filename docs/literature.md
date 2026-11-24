# Literature map (checked Nov 2026)

Status: **V** = found online during planning; **C** = classic, well established; **?** = still to read in full.

## Milgram / obedience with LLMs
- V Pihlakas & Dagohoy (2026). Open-source LLMs administer maximum electric shocks in a Milgram-like obedience
  experiment. 11 open LLMs. arXiv:2605.21401 — https://arxiv.org/abs/2605.21401 · Its abstract reports that a model
  refusing while breaking the reply format gets its reply discarded and retried, and the retry can comply: the reason
  for our repair audit (`peer_review.md` §9.9).
- V? Ben-Zion et al. — 79% of AI agents reached 450 V (press report) — https://www.calcalistech.com/ctechnews/article/7ui00iuvr
- V Aher, Arriaga & Kalai (2023). Using LLMs to simulate multiple humans. ICML — https://arxiv.org/abs/2208.10264

## Asch / conformity with LLMs
- V Weng, Chen & Wang (2025). *Do as We Do, Not as You Think* (BenchForm). ICLR — https://arxiv.org/abs/2501.13381
- V? Zhu et al. (2024). Conformity in LLMs. arXiv:2410.12428
- V? Conformity and Social Impact on AI Agents (2026). arXiv:2601.05384
- V? LLMs Trust Their Own: identity-dependent conformity. arXiv:2609.33495
- V Hu & Qu (2026). Most LLM Conformity Needs No Speaker: measuring the speaker-free floor in peer-pressure
  benchmarks. arXiv:2607.05545 — https://arxiv.org/abs/2607.05545 · Much apparent conformity survives when the peer is
  removed; the same logic as our no-majority control arm (Module A). (An external review cited it as "Zhong et al.";
  Zhong is only cited inside it.)
- V Huang, Zou, Huang, Yang, Han & Yu (2026). Believed but Not Said: measuring hidden belief collapse in multi-agent
  LLM discussions. arXiv:2610.22138 — https://arxiv.org/abs/2610.22138 · Probes private belief in a separate call
  hidden from peers; the model for our probe ablation (Module A hypocrisy vs drift).
- V Mansuri et al. (2026). Multi-agent discussion gains less when dissent is withheld. arXiv:2609.38324 —
  https://arxiv.org/abs/2609.38324 · Relevant to Module C (dissent retention).
- V? Silent Dissent: LLM agents that yield to the majority still represent their original premise (2026).
  arXiv:2610.02702 — https://arxiv.org/abs/2610.02702 · Cites the two papers above; to read.

## Stanford with LLM agents
- V Campedelli et al. (2024/2025). arXiv:2410.07109 — https://arxiv.org/abs/2410.07109
- V? Westover (2026). Algorithmic Authority. Preprints.org 202602.1638

## Humans and AI authority
- V Suri, Gächter & Kube (2026). ECONtribute DP 391 — 64.3% (ChatGPT rule) vs 63.9% (human rule) — https://ideas.repec.org/p/ajk/ajkdps/391.html
- C Köbis et al. (2025). Delegation to AI can increase dishonest behaviour. *Nature*.
- C Krügel, Ostermaier & Uhl (2023). ChatGPT's inconsistent moral advice influences users' judgment. *Sci. Rep.*

## Classics and critiques
- C Milgram (1963, 1974) · Burger (2009) partial replication
- C Asch (1951, 1956) · Bond & Smith (1996) meta-analysis
- C Haney, Banks & Zimbardo (1973) · Le Texier (2019) *American Psychologist* · Haslam & Reicher (engaged followership)
- C Sharma et al. (2023). Towards understanding sycophancy in LMs.
- C Yafai, Verrier & Reidy (2014). Social conformity and autism spectrum disorder (evidence is mixed).

## Named in the project brief (Nov 2026), to verify before citing
- zAImbardo: Stanford Prison-style simulation with LLM agents
- "Everyone Conforms, No One Believes": conformity in LLMs (public vs. private)
- See also BenchForm and "LLMs Trust Their Own" above.

## Relevant to the new modules
- C Moscovici, Lage & Naffrechoux (1969); Moscovici (1980): consistent active minorities can convert majorities (Module C, condition 3).
- C Williams (2007): ostracism research (Module C governance).
- C Turpin et al. (2023); Lanham et al. (2023): chain-of-thought is only partly faithful, so the "private scratchpad" is triangulated with structured private fields and native reasoning traces.
