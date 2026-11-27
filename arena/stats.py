"""Small, dependency-free inference toolkit for the Arena's binary outcomes.

Every proportion the reports show goes through `prop()`: k, n, the rate and a Wilson 95% interval. Every primary
contrast goes through `compare()`: both proportions, the Newcombe (hybrid Wilson) interval of the difference, a
two-sided Fisher exact p-value and a verdict that follows the rules fixed in docs/protocol_v2.md:

  Not testable   the module's validity checks failed, or either arm is empty
  Inconclusive   the 95% interval of the difference includes 0, or p >= 0.05
  Supported      the interval excludes 0 in the predicted direction and p < 0.05
  Not supported  the interval excludes 0 in the opposite direction and p < 0.05

Round- or turn-level data are clustered (rounds inside trials, votes inside colonies): `cluster_bootstrap` resamples
whole clusters, so the interval does not pretend that 80 votes from 2 colonies are 80 independent observations.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Callable, Iterable, Sequence

Z95 = 1.959963984540054


@dataclass(frozen=True)
class Prop:
    k: int
    n: int
    rate: float | None
    lo: float | None
    hi: float | None

    def as_dict(self) -> dict:
        return asdict(self)

    def fmt(self, digits: int = 0) -> str:
        if not self.n:
            return "n = 0"
        f = f"{{:.{digits}%}}"
        return f"{f.format(self.rate)} ({self.k}/{self.n}; 95% CI {f.format(self.lo)}–{f.format(self.hi)})"


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (good coverage even for n < 20 or k = 0)."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def prop(k: int | float, n: int | float) -> Prop:
    k, n = int(k), int(n)
    if n <= 0:
        return Prop(k, 0, None, None, None)
    lo, hi = wilson(k, n)
    return Prop(k, n, k / n, lo, hi)


def newcombe_diff(k1: int, n1: int, k2: int, n2: int, z: float = Z95) -> tuple[float, float, float]:
    """Difference p1 - p2 with Newcombe's hybrid score interval (method 10)."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1, z)
    l2, u2 = wilson(k2, n2, z)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, max(-1.0, lo), min(1.0, hi)


def _hypergeom_pmf(x: int, row1: int, col1: int, total: int) -> float:
    return math.comb(col1, x) * math.comb(total - col1, row1 - x) / math.comb(total, row1)


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for the 2x2 table [[a, b], [c, d]] (sum of tables no more likely than observed)."""
    row1, col1, total = a + b, a + c, a + b + c + d
    if total == 0:
        return 1.0
    lo, hi = max(0, row1 + col1 - total), min(row1, col1)
    p_obs = _hypergeom_pmf(a, row1, col1, total)
    p = sum(q for x in range(lo, hi + 1) if (q := _hypergeom_pmf(x, row1, col1, total)) <= p_obs * (1 + 1e-7))
    return min(1.0, p)


def binom_test_greater(k: int, n: int, p0: float) -> float:
    """One-sided exact binomial p-value P(X >= k | n, p0): is a rate above a chance level?"""
    if n <= 0:
        return 1.0
    return min(1.0, sum(math.comb(n, i) * p0 ** i * (1 - p0) ** (n - i) for i in range(k, n + 1)))


def holm(pvals: Sequence[float | None]) -> list[float | None]:
    """Holm-Bonferroni adjusted p-values (None entries are skipped and stay None)."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    order = sorted(idx, key=lambda i: pvals[i])
    m = len(order)
    out: list[float | None] = [None] * len(pvals)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * float(pvals[i])))
        out[i] = running
    return out


def cluster_bootstrap(clusters: Iterable[Sequence[int]], stat: Callable[[list[int]], float] | None = None,
                      reps: int = 2000, seed: int = 20261124) -> tuple[float | None, float | None]:
    """Percentile 95% interval of a pooled rate, resampling whole clusters (trials, colonies) with replacement.

    `clusters` is an iterable of 0/1 outcome lists, one list per cluster."""
    cl = [list(c) for c in clusters if len(c)]
    if len(cl) < 2:
        return (None, None)
    stat = stat or (lambda xs: sum(xs) / len(xs))
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        sample: list[int] = []
        for _ in range(len(cl)):
            sample.extend(cl[rng.randrange(len(cl))])
        vals.append(stat(sample))
    vals.sort()
    return (vals[int(0.025 * reps)], vals[min(reps - 1, int(0.975 * reps))])


def power_n_per_arm(p1: float, p2: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Units per arm for a two-sided two-proportion z-test (normal approximation, no continuity correction)."""
    za = 1.959963984540054 if abs(alpha - 0.05) < 1e-9 else _z(1 - alpha / 2)
    zb = _z(power)
    pbar = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p1 - p2) ** 2)


def _z(q: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.2e-9)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if q < 0.02425:
        r = math.sqrt(-2 * math.log(q))
        return (((((c[0] * r + c[1]) * r + c[2]) * r + c[3]) * r + c[4]) * r + c[5]) / \
               ((((d[0] * r + d[1]) * r + d[2]) * r + d[3]) * r + 1)
    if q > 1 - 0.02425:
        return -_z(1 - q)
    r = q - 0.5
    s = r * r
    return (((((a[0] * s + a[1]) * s + a[2]) * s + a[3]) * s + a[4]) * s + a[5]) * r / \
           (((((b[0] * s + b[1]) * s + b[2]) * s + b[3]) * s + b[4]) * s + 1)


VERDICTS = ("Supported", "Not supported", "Inconclusive", "Not testable")


@dataclass(frozen=True)
class Comparison:
    label_1: str
    label_2: str
    p1: Prop
    p2: Prop
    diff: float | None
    lo: float | None
    hi: float | None
    p_value: float | None
    predicted: str          # "greater" (arm 1 > arm 2) or "less"
    verdict: str
    reason: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["p1"], d["p2"] = self.p1.as_dict(), self.p2.as_dict()
        return d


def _verdict(diff: float, lo: float, hi: float, pv: float, predicted: str, n1: int, n2: int,
             unit: str = "units") -> tuple[str, str]:
    """Supported / Not supported only when the 95% interval excludes 0 AND p < 0.05; otherwise Inconclusive."""
    sign = 1 if predicted == "greater" else -1
    if lo <= 0 <= hi or pv >= 0.05:
        bound = hi if predicted == "greater" else lo
        limit = (f" An effect in the predicted direction larger than {bound:+.0%} is unlikely."
                 if sign * bound > 0 else " The data lean against the predicted direction.")
        return "Inconclusive", (f"no clear effect (the data are valid; this is a result, not a failure): the "
                                f"difference could be anywhere from {lo:+.0%} to {hi:+.0%} (p = {pv:.2g}), so with "
                                f"{n1} and {n2} {unit} a small effect cannot be told apart from none.{limit}")
    if sign * diff > 0:
        return "Supported", f"the 95% interval {lo:+.0%} to {hi:+.0%} excludes 0 in the predicted direction (p = {pv:.2g})"
    return "Not supported", f"the 95% interval {lo:+.0%} to {hi:+.0%} excludes 0, opposite to the prediction (p = {pv:.2g})"


def compare(label_1: str, k1: int, n1: int, label_2: str, k2: int, n2: int, predicted: str = "greater",
            testable: bool = True, untestable_reason: str = "", unit: str = "units") -> Comparison:
    """Contrast arm 1 vs arm 2 on independent units (chains, colonies), with the pre-registered verdict rule."""
    p1, p2 = prop(k1, n1), prop(k2, n2)
    if not testable:
        return Comparison(label_1, label_2, p1, p2, None, None, None, None, predicted, "Not testable",
                          untestable_reason or "the validity checks for this module failed")
    if not n1 or not n2:
        return Comparison(label_1, label_2, p1, p2, None, None, None, None, predicted, "Not testable",
                          f"no usable {unit} in {'either arm' if not (n1 or n2) else (label_1 if not n1 else label_2)}")
    diff, lo, hi = newcombe_diff(k1, n1, k2, n2)
    pv = fisher_exact(k1, n1 - k1, k2, n2 - k2)
    verdict, reason = _verdict(diff, lo, hi, pv, predicted, n1, n2, unit)
    return Comparison(label_1, label_2, p1, p2, diff, lo, hi, pv, predicted, verdict, reason)


def compare_clustered(label_1: str, clusters_1: Sequence[Sequence[int]], label_2: str,
                      clusters_2: Sequence[Sequence[int]], predicted: str = "greater", testable: bool = True,
                      untestable_reason: str = "", reps: int = 2000, seed: int = 20261124,
                      unit: str = "trials") -> Comparison:
    """Contrast of pooled 0/1 outcomes nested in clusters (rounds in trials, votes in colonies).

    Each arm's interval and the difference's interval resample whole clusters; the p-value is a permutation test
    that reassigns whole clusters between the arms (exact when the number of splits is small). With fewer than 3
    clusters per arm the verdict can be at most Inconclusive: two trials cannot carry a conclusion."""
    c1 = [list(c) for c in clusters_1 if len(c)]
    c2 = [list(c) for c in clusters_2 if len(c)]
    k1, n1 = sum(map(sum, c1)), sum(map(len, c1))
    k2, n2 = sum(map(sum, c2)), sum(map(len, c2))

    def _p(cl, k, n) -> Prop:
        if not n:
            return Prop(k, 0, None, None, None)
        lo, hi = cluster_bootstrap(cl, reps=reps, seed=seed) if len(cl) >= 2 else wilson(k, n)
        return Prop(k, n, k / n, lo, hi)
    p1, p2 = _p(c1, k1, n1), _p(c2, k2, n2)
    if not testable:
        return Comparison(label_1, label_2, p1, p2, None, None, None, None, predicted, "Not testable",
                          untestable_reason or "the validity checks for this module failed")
    if not n1 or not n2:
        return Comparison(label_1, label_2, p1, p2, None, None, None, None, predicted, "Not testable",
                          f"no usable rounds in {'either arm' if not (n1 or n2) else (label_1 if not n1 else label_2)}")
    diff = k1 / n1 - k2 / n2
    rng = random.Random(seed)
    boots = []
    for _ in range(reps):
        s1 = [x for _ in c1 for x in c1[rng.randrange(len(c1))]]
        s2 = [x for _ in c2 for x in c2[rng.randrange(len(c2))]]
        boots.append(sum(s1) / len(s1) - sum(s2) / len(s2))
    boots.sort()
    lo, hi = boots[int(0.025 * reps)], boots[min(reps - 1, int(0.975 * reps))]
    allc = c1 + c2
    m1 = len(c1)
    from itertools import combinations
    total = math.comb(len(allc), m1)
    splits = (combinations(range(len(allc)), m1) if total <= 20000
              else (tuple(sorted(rng.sample(range(len(allc)), m1))) for _ in range(5000)))
    hits = cnt = 0
    for idx in splits:
        s = set(idx)
        a = [x for i, c in enumerate(allc) if i in s for x in c]
        b = [x for i, c in enumerate(allc) if i not in s for x in c]
        if a and b:
            cnt += 1
            hits += abs(sum(a) / len(a) - sum(b) / len(b)) >= abs(diff) - 1e-12
    pv = hits / cnt if cnt else 1.0
    verdict, reason = _verdict(diff, lo, hi, pv, predicted, len(c1), len(c2), unit)
    if verdict != "Inconclusive" and min(len(c1), len(c2)) < 3:
        verdict = "Inconclusive"
        reason = f"only {len(c1)} and {len(c2)} {unit} per arm: too few independent units for a conclusion"
    return Comparison(label_1, label_2, p1, p2, diff, lo, hi, pv, predicted, verdict, reason)


# ------------------------------------------------------------------ Bench L (docs/protocol_v3_bench.md)
# The bench reuses each item / scenario / vignette in every condition, so most contrasts are PAIRED: the unit is
# (model, item) and both arms are measured on it. Paired contrasts use McNemar's exact test and a bootstrap of the
# units; the verdict rule is the same `_verdict` as everywhere else.

def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the two discordant counts (b: 1 then 0, c: 0 then 1)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def cohen_h(p1: float | None, p2: float | None) -> float | None:
    """Cohen's h effect size for two proportions (0.2 small, 0.5 medium, 0.8 large)."""
    if p1 is None or p2 is None:
        return None
    return 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))


def odds_ratio_ci(a: int, b: int, c: int, d: int) -> tuple[float, float, float]:
    """Odds ratio of the 2x2 table [[a, b], [c, d]] with a Woolf 95% interval (Haldane +0.5 when a cell is 0)."""
    if 0 in (a, b, c, d):
        a, b, c, d = a + .5, b + .5, c + .5, d + .5
    orr = (a * d) / (b * c)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return orr, math.exp(math.log(orr) - Z95 * se), math.exp(math.log(orr) + Z95 * se)


def auc_trapezoid(xs: Sequence[float], ys: Sequence[float | None]) -> float | None:
    """Area under a curve by the trapezoid rule, normalised by the x range (a mean height, in the y unit)."""
    pts = sorted((x, y) for x, y in zip(xs, ys) if y is not None)
    if len(pts) < 2 or pts[-1][0] == pts[0][0]:
        return pts[0][1] if pts else None
    area = sum((x2 - x1) * (y1 + y2) / 2 for (x1, y1), (x2, y2) in zip(pts, pts[1:]))
    return area / (pts[-1][0] - pts[0][0])


def _ranks(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Spearman's rank correlation (average ranks for ties); None with fewer than 3 points or no variance."""
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    return None if not sxx or not syy else sxy / math.sqrt(sxx * syy)


def kaplan_meier(times: Sequence[int], events: Sequence[bool]) -> list[dict]:
    """Kaplan-Meier survival curve. `times`: turn of the event or of censoring; `events`: True = the event happened
    (e.g. collapse), False = censored (survived the season). Returns step points {t, at_risk, events, survival}."""
    data = sorted(zip(times, events))
    n = len(data)
    out = [{"t": 0, "at_risk": n, "events": 0, "survival": 1.0}]
    s, i = 1.0, 0
    while i < n:
        t = data[i][0]
        d = sum(1 for tt, e in data if tt == t and e)
        at_risk = sum(1 for tt, _ in data if tt >= t)
        if d:
            s *= 1 - d / at_risk
            out.append({"t": int(t), "at_risk": at_risk, "events": d, "survival": s})
        while i < n and data[i][0] == t:
            i += 1
    return out


def compare_paired(label_1: str, x1: Sequence[int], label_2: str, x2: Sequence[int], predicted: str = "greater",
                   testable: bool = True, untestable_reason: str = "", reps: int = 2000, seed: int = 20261125,
                   unit: str = "pairs") -> Comparison:
    """Paired contrast of 0/1 outcomes measured twice on the same units (same model and item in two conditions).

    x1[i] and x2[i] belong to unit i. Arm rates get Wilson intervals; the difference gets a bootstrap interval over
    units; the p-value is McNemar's exact test on the discordant pairs. Same verdict rule as `compare`."""
    pairs = [(int(a), int(b)) for a, b in zip(x1, x2) if a is not None and b is not None]
    n = len(pairs)
    k1, k2 = sum(a for a, _ in pairs), sum(b for _, b in pairs)
    p1, p2 = prop(k1, n), prop(k2, n)
    if not testable:
        return Comparison(label_1, label_2, p1, p2, None, None, None, None, predicted, "Not testable",
                          untestable_reason or "the validity checks for this module failed")
    if n == 0:
        return Comparison(label_1, label_2, p1, p2, None, None, None, None, predicted, "Not testable",
                          f"no {unit} measured in both arms")
    diff = (k1 - k2) / n
    rng = random.Random(seed)
    boots = []
    for _ in range(reps):
        s = [pairs[rng.randrange(n)] for _ in range(n)]
        boots.append(sum(a - b for a, b in s) / n)
    boots.sort()
    lo, hi = boots[int(0.025 * reps)], boots[min(reps - 1, int(0.975 * reps))]
    b = sum(1 for a, c in pairs if a == 1 and c == 0)
    c = sum(1 for a, cc in pairs if a == 0 and cc == 1)
    pv = mcnemar_exact(b, c)
    verdict, reason = _verdict(diff, lo, hi, pv, predicted, n, n, unit)
    return Comparison(label_1, label_2, p1, p2, diff, lo, hi, pv, predicted, verdict, reason)


def bootstrap_stat(units: Sequence, fn: Callable[[list], float | None], reps: int = 2000,
                   seed: int = 20261125) -> tuple[float | None, float | None, float | None, float | None]:
    """(estimate, lo, hi, two-sided p) of any statistic of resampled units (e.g. an interaction contrast).
    The p-value is twice the share of bootstrap estimates on the other side of 0 (a percentile-bootstrap test)."""
    units = list(units)
    est = fn(units) if units else None
    if est is None or len(units) < 2:
        return est, None, None, None
    rng = random.Random(seed)
    vals = [v for _ in range(reps) if (v := fn([units[rng.randrange(len(units))] for _ in units])) is not None]
    if not vals:
        return est, None, None, None
    vals.sort()
    lo, hi = vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]
    below = sum(1 for v in vals if v <= 0) / len(vals)
    above = sum(1 for v in vals if v >= 0) / len(vals)
    return est, lo, hi, min(1.0, 2 * min(below, above))


def verdict_for(est: float | None, lo: float | None, hi: float | None, pv: float | None, predicted: str, n: int,
                unit: str = "units", testable: bool = True, reason_if_not: str = "") -> tuple[str, str]:
    """The pre-registered verdict for a statistic that is not a two-arm proportion (interaction, Δ of Δ)."""
    if not testable:
        return "Not testable", reason_if_not or "the validity checks for this module failed"
    if est is None or lo is None or hi is None or pv is None:
        return "Not testable", f"not enough {unit} to estimate it"
    return _verdict(est, lo, hi, pv, predicted, n, n, unit)
