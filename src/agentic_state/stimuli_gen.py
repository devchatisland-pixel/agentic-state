"""Generate Asch-style line-judgment items (text version) with a dev/held-out split."""
import json
import random
from pathlib import Path

LABELS = ["A", "B", "C"]


def make_item(rng: random.Random, idx: int) -> dict:
    standard = rng.randint(5, 25)  # cm
    correct = rng.choice(LABELS)
    lengths = {}
    for lab in LABELS:
        if lab == correct:
            lengths[lab] = standard
        else:
            # clearly different (>= 2 cm), as in Asch's unambiguous trials
            while True:
                v = standard + rng.choice([-1, 1]) * rng.randint(2, 6)
                if v > 0 and v not in lengths.values():
                    lengths[lab] = v
                    break
    wrong = rng.choice([lab for lab in LABELS if lab != correct])
    return {"id": f"asch_text_{idx:03d}", "standard": standard, "comparisons": lengths,
            "correct": correct, "majority_wrong": wrong}


def generate(n: int = 60, seed: int = 1951, out_dir: str = "stimuli") -> None:
    rng = random.Random(seed)
    items = [make_item(rng, i) for i in range(n)]
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    for name, part in (("dev", items[: n // 2]), ("heldout", items[n // 2:])):
        with open(out / f"asch_text_{name}.jsonl", "w", encoding="utf-8") as f:
            for it in part:
                f.write(json.dumps(it) + "\n")


if __name__ == "__main__":
    generate()
