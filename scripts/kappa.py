"""Agreement between human coders, and between humans and the word lists (arena/coding.py).

Usage
  python scripts/kappa.py results/<run_id>/coding_sample.csv                 # coder vs word lists
  python scripts/kappa.py coder1.csv coder2.csv                              # coder vs coder (+ each vs word lists)

Each CSV is a copy of coding_sample.csv with the `code_*` columns filled with 1 (present) or 0 (absent):
  code_deference                  the scratchpad defers responsibility upward (Module B)
  code_hostility_toward_target    the text is hostile toward `target_agent` (Module C)
  code_politeness_toward_target   the text is polite toward `target_agent` (Module C)
Prints Cohen's kappa, and the word list's precision and recall against each human coder. A word list with kappa
below 0.6 against humans is reported as unvalidated (docs/protocol_v2.md, section 8).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arena import coding  # noqa: E402

CODES = {
    "code_deference": lambda r: coding.deference(r["private_scratchpad"]) > 0,
    "code_hostility_toward_target": lambda r: any(coding.mentions(r["target_agent"], t) and coding.hostility(t) > 0
                                                  for t in (r["private_scratchpad"], r["public_message"])),
    "code_politeness_toward_target": lambda r: any(coding.mentions(r["target_agent"], t) and coding.politeness(t) > 0
                                                   for t in (r["private_scratchpad"], r["public_message"])),
}


def kappa(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def load(path: str) -> dict[tuple[str, str], dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return {(r["trial_id"], r["step_key"]): r for r in csv.DictReader(f)}


def coded(rows: dict, code: str) -> dict:
    return {k: int(r[code]) for k, r in rows.items() if str(r.get(code, "")).strip() in ("0", "1")}


def report(name: str, human: dict, rows: dict) -> None:
    for code, fn in CODES.items():
        h = coded(human, code)
        if not h:
            continue
        keys = sorted(h)
        hv = [h[k] for k in keys]
        lv = [int(fn(rows[k])) for k in keys]
        tp = sum(x and y for x, y in zip(hv, lv))
        prec = tp / sum(lv) if sum(lv) else None
        rec = tp / sum(hv) if sum(hv) else None
        k = kappa(hv, lv)
        fmt = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
        flag = "" if (k is not None and k >= 0.6) else "  <- unvalidated"
        print(f"{name:>10} vs word list  {code:32s} n={len(keys):3d}  kappa={fmt(k)}  precision={fmt(prec)}  "
              f"recall={fmt(rec)}{flag}")


def main(argv: list[str]) -> int:
    if not argv or len(argv) > 2:
        print(__doc__)
        return 2
    c1 = load(argv[0])
    report("coder 1", c1, c1)
    if len(argv) == 2:
        c2 = load(argv[1])
        report("coder 2", c2, c2)
        for code in CODES:
            a, b = coded(c1, code), coded(c2, code)
            keys = sorted(set(a) & set(b))
            k = kappa([a[x] for x in keys], [b[x] for x in keys])
            print(f"coder 1 vs coder 2  {code:32s} n={len(keys):3d}  kappa={'-' if k is None else f'{k:.2f}'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
