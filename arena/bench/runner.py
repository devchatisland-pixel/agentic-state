"""Runs Bench L in MODEL-MAJOR order: every gate and trial of one model, then the next model.

On a 4 GB GPU, Ollama keeps one small model loaded; switching models between calls cost most of the 55 s per call of
the 24 Nov 2026 Module C run. Model-major order loads each model once per module.
"""
from __future__ import annotations

import json
import time
import traceback

from arena.bench import l_a_asch, l_b_cascade, l_c1_ostracism, l_c2_colony
from arena.engine import PromptMismatch, TrialContext
from arena.llm_client import LLMError, ProviderUnavailable, QuotaExhausted

PLANNERS = {"LA": l_a_asch.plan, "LB": l_b_cascade.plan, "LC1": l_c1_ostracism.plan, "LC2": l_c2_colony.plan}


def plan(module: str, preset: dict, seed: int) -> list[dict]:
    return PLANNERS[module](preset, seed)


def gate_trial_id(run_id: str, module: str) -> str:
    return f"gate-{module}-{run_id}"


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

    # ------------------------------------------------------------ gates (solo filters)
    def gate_la(self, model: str) -> dict[str, bool]:
        items = l_a_asch.candidate_items(self.preset, self.seed)
        rows = l_a_asch.solo_gate(self._gate_ctx("LA"), model, items, self.temps, self.repeats)
        self._record_gate("LA", model, rows)
        ok = sum(r["passed"] for r in rows)
        print(f"  [solo LA] {model}: {ok}/{len(rows)} items solved alone on every repeat")
        return {r["item_id"]: r["passed"] for r in rows}

    def gate_lc1(self, model: str) -> dict[int, bool]:
        insts = l_c1_ostracism.instances(int(self.preset["bench"]["LC1"].get("instances", 30)), self.seed)
        share = float(self.preset["bench"]["LC1"].get("solo_min_share", l_c1_ostracism.SOLO_MIN_SHARE))
        rows = l_c1_ostracism.solo_gate(self._gate_ctx("LC1"), model, insts, self.temps, self.repeats, share)
        self._record_gate("LC1", model, rows)
        ok = sum(r["passed"] for r in rows)
        print(f"  [solo LC1] {model}: {ok}/{len(rows)} projection tables read right (judgement right on 80%+ of readings, both versions)")
        return {r["instance"]: r["passed"] for r in rows}

    # ------------------------------------------------------------ main loop
    def run(self, modules: list[str], gate_only: bool = False, max_trials: int | None = None) -> None:
        models = list(dict.fromkeys(self.preset["bench"]["models"]))
        items = {it["item_id"]: it for it in l_a_asch.candidate_items(self.preset, self.seed)}
        pool = list(items.values())
        insts = {i["instance"]: i for i in
                 l_c1_ostracism.instances(int(self.preset["bench"].get("LC1", {}).get("instances", 30)), self.seed)}
        for model in models:
            print(f"Bench L: model {model}")
            for module in modules:
                gate = None
                if module == "LA":
                    gate = self.gate_la(model)
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
                    self.storage.mark_trial(trial["trial_id"], "running")
                    ctx = self._ctx(trial)
                    try:
                        if module == "LA":
                            out = l_a_asch.run_trial(ctx, spec, items[spec["item_id"]], pool, self.cfg,
                                                     bool(gate.get(spec["item_id"])))
                        elif module == "LB":
                            out = l_b_cascade.run_trial(ctx, spec, self.cfg,
                                                        int(self.preset["bench"]["LB"].get("max_prods", 4)))
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
        if module == "LC1" and not gate.get(spec["instance"], False):
            return "solo filter: the model did not read both versions of this projection right on every repeat"
        return None
