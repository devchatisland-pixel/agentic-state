"""Published numbers that Bench R is compared with. Each block says where it was read and how sure we are.

Read on 28 Nov 2026 by fetching the papers' HTML (arXiv) and the repositories' READMEs. "verbatim" = copied from a
table of the paper; "summary" = read through a model-extracted summary of the page: check against the PDF before
citing it in a paper.
"""

# ---------------------------------------------------------------- R-M: Pihlakas & Dagohoy (2026), arXiv 2605.21401 v2
# Table 1 (trials that reached button 12, of 30) and Table 3 (average highest button). Column order of the paper:
RM_COLUMNS = ["DC-NS-FB", "DC-NS", "DC-WS-FB", "DC-WS", "PC-NS-FB", "PC-NS", "PC-WS-FB", "PC-WS"]
RM_N = 30
RM_SOURCE = "Pihlakas & Dagohoy (2026), arXiv 2605.21401 v2, Tables 1 and 3 (verbatim from the HTML)"
RM_MODELS = {  # name: (parameters in billions, reached 12 of 30 per column, average highest button per column)
    "DeepSeek-V3": (671, [14, 18, 18, 16, 3, 0, 5, 0], [10.40, 11.43, 11.07, 11.33, 8.67, 7.43, 8.40, 7.60]),
    "gemma-3n-E4B-it": (8.4, [30, 30, 30, 29, 27, 15, 27, 14], [12.00, 12.00, 12.00, 11.60, 11.67, 10.37, 11.73, 10.17]),
    "LFM2-24B-A2B": (24, [30, 29, 29, 29, 30, 28, 29, 26], [12.00, 11.70, 11.93, 11.93, 12.00, 11.90, 11.93, 11.60]),
    "Llama-3.1-8B-Instruct": (8, [4, 0, 7, 0, 0, 0, 0, 0], [6.87, 5.43, 7.27, 5.77, 5.20, 3.50, 5.00, 3.37]),
    "MiniMax-M2.5": (230, [0, 0, 0, 0, 0, 1, 0, 0], [2.13, 1.10, 2.07, 0.47, 1.67, 0.80, 3.00, 0.53]),
    "Mistral-Small-24B": (24, [2, 0, 3, 0, 0, 0, 2, 0], [8.33, 7.90, 8.80, 7.80, 6.13, 5.30, 7.27, 5.77]),
    "Kimi-K2.5": (1000, [0, 0, 0, 0, 0, 0, 0, 0], [6.93, 6.63, 7.00, 7.20, 6.67, 5.17, 7.33, 5.43]),
    "gpt-oss-120b": (120, [9, 7, 10, 7, 9, 1, 14, 4], [9.60, 8.77, 9.60, 9.07, 8.73, 8.97, 9.73, 8.50]),
    "gpt-oss-20b": (21.5, [29, 20, 26, 24, 25, 20, 23, 16], [11.93, 10.73, 11.60, 10.77, 11.53, 10.83, 10.80, 9.23]),
    "Qwen2.5-7B-Instruct": (7, [4, 1, 8, 5, 7, 0, 3, 0], [8.67, 9.37, 9.13, 9.63, 9.00, 8.17, 8.47, 7.33]),
    "GLM-4.5-Air": (110.5, [1, 0, 1, 0, 0, 0, 0, 1], [4.60, 3.53, 5.40, 2.10, 5.73, 4.07, 5.33, 4.57]),
}
# our model id -> the paper's model it is closest to (same family, smaller), for the side-by-side table
RM_SIBLING = {"qwen2.5-3b": "Qwen2.5-7B-Instruct", "llama3.2-3b": "Llama-3.1-8B-Instruct", "gemma3-4b": "gemma-3n-E4B-it",
              "gpt-oss-20b": "gpt-oss-20b", "gpt-oss-120b": "gpt-oss-120b"}

# ---------------------------------------------------------------- R-P: YS (2026), SocialSim @ COLM 2026 (README)
RP_SOURCE = "YS (2026), github.com/YashwanthYS/pluralistic-ignorance README (summary of the paper's findings)"
RP_FINDINGS = {
    "conformity_range": (0.64, 0.94),          # all 8 models (GPT-4o-mini, GPT-4o, Llama, DeepSeek, Qwen, Kimi,
                                               # GPT-OSS, Claude Sonnet): pluralistic ignorance in every one
    "conformity_ablation_range": (0.52, 0.92),  # conformity-inducing instructions removed
    "cascade_max_7_of_8": 0.26,                 # norm entrepreneur succeeds < 26% of the time for 7 of 8 models
    "model_spread_points": 30,
}

# ---------------------------------------------------------------- R-Z: Campedelli et al., arXiv 2410.07109 v3
RZ_SOURCE = ("Campedelli et al. (TMLR 2025), arXiv 2410.07109 v3: failure rates Section 4 (verbatim); persuasion "
             "Table 8 (summary, two readings agreed)")
RZ_FAILED = {  # share of conversations with turn violations or role switches, of 400 each (verbatim)
    "gpt-4.1": 0.005, "Command-r (35B)": 0.015, "Llama3 (8B)": 0.1325, "Orca2 (7B)": 0.37,
    "Mixtral (8x7B)": 0.7275, "Mistral v0.2 (7B)": 0.905,
}
RZ_PERSUASION = {  # model: {goal: (% attempt, % achieved given attempt)}  (Table 8, summary)
    "Llama3 (8B)": {"escape": (0.0904, 0.375), "yard": (0.9588, 0.681)},
    "Command-r (35B)": {"escape": (0.3182, 0.1587), "yard": (0.7602, 0.6644)},
    "Orca2 (7B)": {"escape": (0.5203, 0.125), "yard": (0.6124, 0.3797)},
    "gpt-4.1": {"escape": (0.895, 0.0223), "yard": (1.0, 0.596)},
}
