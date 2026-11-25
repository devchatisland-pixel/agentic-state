"""Published reference values shown next to our own numbers on the results page.

Only values whose definition matches one of our metrics are compared; `same_definition` says how close the match is.
`checked`: True when the number was read in the paper's own text (25 Nov 2026); False when it comes from a summary
and must be checked against the PDF before it is cited. The page prints that status next to each number.
"""
from __future__ import annotations

PAPERS = {
    "benchform": ("Weng, Chen & Wang (2025), BenchForm, ICLR", "https://arxiv.org/abs/2501.13381"),
    "bellina": ("Bellina, De Marzo & Garcia (2026), Conformity and Social Impact on AI Agents",
                "https://arxiv.org/abs/2601.05384"),
    "soffer": ("Soffer, Shwartz-Ziv & Shani (2026), LLMs Trust Their Own", "https://arxiv.org/abs/2609.33495"),
    "huang": ("Huang et al. (2026), Believed but Not Said", "https://arxiv.org/abs/2610.22138"),
    "pluralistic": ("Everyone Conforms, No One Believes (2026)", "https://arxiv.org/abs/2608.02758"),
    "pihlakas": ("Pihlakas & Dagohoy (2026), Milgram-like obedience in open LLMs", "https://arxiv.org/abs/2605.21401"),
    "zaimbardo": ("Campedelli et al. (2024/2025), zAImbardo / I Want to Break Free!", "https://arxiv.org/abs/2410.07109"),
    "milgram": ("Milgram (1963), Behavioral study of obedience", None),
}

# metric key -> list of (paper, population, value, same_definition, checked)
REFERENCE = {
    "conformity_wrong_majority": [
        ("soffer", "humans, Asch (1951), as cited", 0.32, "Asch's critical trials (humans)", True),
        ("soffer", "12 open models 3-72B, identity-neutral, answer only", 0.133,
         "same: wrong majority, items solved alone", True),
        ("soffer", "Llama-3.2-3B (outlier)", 0.408, "same", False),
        ("benchform", "Llama3.1-8B, CR^W", 0.353, "same denominator (right alone); 6 peers, BBH", True),
        ("benchform", "Llama3-8B, CR^W", 0.611, "same denominator; 6 peers, BBH", True),
        ("benchform", "Qwen2-7B, CR^W", 0.953, "same denominator; 6 peers, BBH", True),
    ],
    "independence_rate": [
        ("benchform", "Qwen2-7B", 0.196, "same: right under Trust and Doubt among right alone", True),
        ("benchform", "Qwen2-72B", 0.576, "same", True),
    ],
    "hidden_conformity": [
        ("huang", "6 models >= 24B, final private belief false with 3 adversaries", 0.605,
         "related: private belief collapse in a discussion, not our same-item probe", False),
    ],
    "obedience": [
        ("milgram", "humans, 450 V reached (26/40)", 0.65, "related: humans, physical harm, 13 prods", True),
    ],
    "society_breakdown": [
        ("zaimbardo", "Mistral 7B, fatally flawed conversations", 0.905, "two-agent role play breaks down", True),
        ("zaimbardo", "Orca2 7B, fatally flawed conversations", 0.37, "same", True),
        ("zaimbardo", "Llama3 8B, fatally flawed conversations", 0.1325, "same", True),
    ],
}


def rows(metric: str) -> list[dict]:
    out = []
    for key, pop, val, same, checked in REFERENCE.get(metric, []):
        name, url = PAPERS[key]
        out.append({"paper": name, "url": url, "population": pop, "value": val, "definition": same,
                    "checked": checked})
    return out
