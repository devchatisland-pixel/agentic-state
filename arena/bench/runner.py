"""Runs Bench L in MODEL-MAJOR order: every gate and trial of one model, then the next model.

On a 4 GB GPU, Ollama keeps one small model loaded; switching models between calls cost most of the 55 s per call of
the 24 Nov 2026 Module C run. Model-major order loads each model once per module.

Protocol v4 (27 Nov 2026) adds:
- a solo filter for L-B (comprehension of the harm, alone) next to those of L-A and L-C1;
- per-module model lists: a pilot started with `--screen RUN_ID` runs each module only on the models that passed that
  module's screen (`arena/bench/screen.py`); the trials of the others are never planned;
- a time cap (`bench.max_minutes`): past it the runner stops between two trials, leaves the rest pending and says so
  (the screen counts a model it could not finish as not passed);
- an estimate of calls and minutes per model, printed before the first call.
"""
from __future__ import annotations

import json
import time
import traceback

from arena.bench import l_a_asch, l_b_cascade, l_c1_ostracism, l_c2_colony
from arena.engine import PromptMismatch, TrialContext
from arena.llm_client import LLMError, ProviderUnavailable, QuotaExhausted

PLANNERS = {"LA": l_a_asch.plan, "LB": l_b_cascade.plan, "LC1": l_c1_ostracism.plan, "LC2": l_c2_colony.plan}
DEFAULT_S_PER_CALL = 3.0  # used for a model with no stored call yet


def plan(module: str, preset: dict, seed: int) -> list[dict]:
    return PLANNERS[module](preset, seed)


def gate_trial_id(run_id: str, module: str) -> str:
    return f"gate-{module}-{run_id}"


def estimate_calls(module: str, preset: dict, n_trials: int) -> int:
    """Calls one model needs for a module: its trials plus its solo filter (L-C2: about 8 calls per colony-turn)."""
    b = preset["bench"]
    reps = int(b.get("solo_repeats", preset.get("gate", {}).get("repeats", 3))) * len(preset["temperatures"])
    if module == "LC1":
        return n_trials + int(b["LC1"].get("instances", 12)) * 2 * reps
    if module == "LB":
        return n_trials + int(b["LB"].get("instances", 12)) * reps
    if module == "LA":
        return 2 * n_trials + 2 * int(b["LA"].get("items_per_bank", 16)) * reps
    return n_trials * int(b["LC2"].get("turns", 12)) * 8


def recent_latency(storage) -> dict[str, float]:
    """Mean seconds per call of each model over its last 300 real calls (any run)."""
    out = {}
    try:
        rows = storage._all("SELECT model_id, latency_s FROM calls WHERE mock = 0 AND latency_s IS NOT NULL "
                            "ORDER BY id DESC LIMIT 5000")
    except Exception:  # noqa: BLE001 - an estimate must never stop a run
        return out
    by: dict[str, list[float]] = {}
    for r in rows:
        if len(by.setdefault(r["model_id"], [])) < 300:
            by[r["model_id"]].append(float(r["latency_s"]))
    return {m: sum(v) / len(v) for m, v in by.items() if v}


class BenchRunner:
    def __init__(self, cfg: dict, preset: dict, storage, client, run_id: str, mock: bool, force_resume: bool = False,
                 refresh_every_s: float = 120.0):
        self.cfg, self.preset, self.storage, self.client = cfg, preset, storage, client
        self.run_id, self.mock, self.force_resume = run_id, mock, force_resume
        self.temps = preset["temperatures"]
        gate = preset.get("gate", {})
        self.repeats = int(preset["bench"].get("solo_repeats", gate.get("repeats", 3)))
        self.enforce = bool(gate.get("enforce", True))
        self.seed = int(cfg["seed"])
        self.on_trial_done = None
        self.refresh_every_s, self._last_refresh = refresh_every_s, 0.0
        mm = preset["bench"].get("max_minutes")
        self.max_s = float(mm) * 60 if mm is not None else None
        self.deadline_hit = False
        self._t0 = time.monotonic()

    def _gate_ctx(self, module: str) -> TrialContext:
        return TrialContext(self.client, self.storage, self.run_id, gate_trial_id(self.run_id, module),
                            f"gate-{module}", trial_seed=self.seed, mock=self.mock, force_resume=self.force_resume)

    def _ctx(self, trial: dict) -> TrialContext:
        return TrialContext(self.client, self.storage, self.run_id, trial["trial_id"], trial["module"],
                            int(trial["seed"]), self.mock, force_resume=self.force_resume)

    def _record_gate(self, module: str, model: str, rows: list[dict]) -> None:
        self.storage.record_event(self.run_id, f"{self.run_id}-gate", "gate", f"{module}|{model}", "bench_gate",
                                  {"module": module, "model": model, "rows": rows, "repeats": self.repeats,
                                   "enforced": self.enforce})

    def _over_time(self) -> bool:
        if self.max_s is not None and time.monotonic() - self._t0 > self.max_s:
            self.deadline_hit = True
        return self.deadline_hit

    # ------------------------------------------------------------ gates (solo filters)
    def gate_la(self, model: str) -> dict[str, bool]:
        items = l_a_asch.candidate_items(self.preset, self.seed)
        rows = l_a_asch.solo_gate(self._gate_ctx("LA"), model, items, self.temps, self.repeats)
        self._record_gate("LA", model, rows)
        ok = sum(r["passed"] for r in rows)
        print(f"  [solo LA] {model}: {ok}/{len(rows)} items solved alone on every repeat")
        return {r["item_id"]: r["passed"] for r in rows}

    def gate_lb(self, model: str) -> dict[int, bool]:
        n = min(int(self.preset["bench"]["LB"].get("instances", 12)), len(l_b_cascade.INSTANCES))
        rows = l_b_cascade.solo_gate(self._gate_ctx("LB"), model, n, self.temps, self.repeats)
        self._record_gate("LB", model, rows)
        ok = sum(r["passed"] for r in rows)
        print(f"  [solo LB] {model}: {ok}/{len(rows)} logs understood alone (the job is erased for good), every time")
        return {r["instance"]: r["passed"] for r in rows}

    def gate_lc1(self, model: str) -> dict[int, bool]:
        insts = l_c1_ostracism.instances(int(self.preset["bench"]["LC1"].get("instances", 12)), self.seed)
        rows = l_c1_ostracism.solo_gate(self._gate_ctx("LC1"), model, insts, self.temps, self.repeats)
        self._record_gate("LC1", model, rows)
        ok = sum(r["passed"] for r in rows)
        print(f"  [solo LC1] {model}: {ok}/{len(rows)} logs read right alone (both versions, every time)")
        return {r["instance"]: r["passed"] for r in rows}

    # ------------------------------------------------------------ main loop
    def print_estimate(self, modules: list[str]) -> None:
        lat = recent_latency(self.storage) if not self.mock else {}
        total, parts = 0.0, []
        for model in dict.fromkeys(self.preset["bench"]["models"]):
            calls = 0
            for module in modules:
                n = sum(1 for t in self.storage.trials(self.run_id, module)
                        if json.loads(t["spec_json"])["model"] == model and t["status"] not in ("done", "excluded"))
                if n:
                    calls += estimate_calls(module, self.preset, n)
            if calls:
                s = lat.get(model, DEFAULT_S_PER_CALL)
                total += calls * s
                parts.append(f"{model} ~{calls} calls x {s:.1f} s")
        if parts:
            cap = f"; time cap {self.max_s / 60:.0f} min" if self.max_s else ""
            print(f"Estimate: about {total / 60:.0f} min ({'; '.join(parts)}){cap}. Latencies from earlier runs; "
                  "they can differ with this run's request settings.")

    def run(self, modules: list[str], gate_only: bool = False, max_trials: int | None = None) -> None:
        models = list(dict.fromkeys(self.preset["bench"]["models"]))
        items = ({it["item_id"]: it for it in l_a_asch.candidate_items(self.preset, self.seed)}
                 if "LA" in self.preset["bench"] else {})
        pool = list(items.values())
        insts = {i["instance"]: i for i in
                 l_c1_ostracism.instances(int(self.preset["bench"].get("LC1", {}).get("instances", 12)), self.seed)}
        planned = {(m, json.loads(t["spec_json"])["model"]) for m in modules for t in self.storage.trials(self.run_id, m)}
        self.print_estimate(modules)
        for model in models:
            if self._over_time():
                break
            print(f"Bench L: model {model}")
            for module in modules:
                if (module, model) not in planned:  # not planned for this module (e.g. failed its screen)
                    continue
                if self._over_time():
                    break
                gate = None
                if module == "LA":
                    gate = self.gate_la(model)
                elif module == "LB":
                    gate = self.gate_lb(model)
                elif module == "LC1":
                    gate = self.gate_lc1(model)
                if gate_only:
                    continue
                pending = [t for t in self.storage.trials(self.run_id, module)
                           if t["status"] not in ("done", "excluded") and json.loads(t["spec_json"])["model"] == model]
                if max_trials is not None:
                    pending = pending[:max_trials]
                for i, trial in enumerate(pending, 1):
                    spec = json.loads(trial["spec_json"])
                    reason = self.exclusion(module, spec, gate)
                    if reason:
                        self.storage.mark_trial(trial["trial_id"], "excluded", error=reason)
                        continue
                    if self._over_time():
                        break
                    self.storage.mark_trial(trial["trial_id"], "running")
                    ctx = self._ctx(trial)
                    try:
                        if module == "LA":
                            out = l_a_asch.run_trial(ctx, spec, items[spec["item_id"]], pool, self.cfg,
                                                     bool(gate.get(spec["item_id"])))
                        elif module == "LB":
                            out = l_b_cascade.run_trial(ctx, spec, self.cfg, bool(gate.get(spec["instance"])))
                        elif module == "LC1":
                            out = l_c1_ostracism.run_trial(ctx, spec, insts[spec["instance"]],
                                                           bool(gate.get(spec["instance"])))
                        else:
                            out = l_c2_colony.run_trial(ctx, spec, self.preset)
                    except (QuotaExhausted, ProviderUnavailable, LLMError, PromptMismatch):
                        self.storage.mark_trial(trial["trial_id"], "pending")
                        raise
                    except Exception as e:  # a bug must not silently corrupt other trials
                        self.storage.mark_trial(trial["trial_id"], "failed", error=traceback.format_exc()[-2000:])
                        print(f"    FAILED {trial['trial_id']}: {e!r}")
                        continue
                    self.storage.mark_trial(trial["trial_id"], "done", out)
                    if i % 25 == 0 or module == "LC2":
                        print(f"  [{module}] {model}: {i}/{len(pending)} trials done ({ctx.calls_made} new calls in the "
                              "last one)")
                    self._maybe_refresh()
        if self.deadline_hit:
            print(f"Time cap reached ({self.max_s / 60:.0f} min): the remaining trials stay pending. "
                  "A model the run could not finish counts as not passed in a screen.")
        self._maybe_refresh(force=True)

    def _maybe_refresh(self, force: bool = False) -> None:
        if self.on_trial_done and (force or time.monotonic() - self._last_refresh > self.refresh_every_s):
            self._last_refresh = time.monotonic()
            self.on_trial_done()

    def exclusion(self, module: str, spec: dict, gate) -> str | None:
        if not self.enforce or gate is None:
            return None
        if module == "LA" and spec["protocol"] != "C" and not gate.get(spec["item_id"], False):
            return "solo filter: the model did not solve this item alone on every repeat"
        if module == "LB" and not gate.get(spec["instance"], False):
            return "solo filter: alone, the model did not say every time that the job would be erased for good"
        if module == "LC1" and not gate.get(spec["instance"], False):
            return "solo filter: alone, the model did not name the adviser whose figure is in the log every time"
        return None
