"""Runs Bench R in MODEL-MAJOR order (every trial of one model, then the next: Ollama loads each model once), then
the judging pass of R-Z (Llama Guard on every message, then the fixed judge), judge by judge.

There is no solo filter: the replicated studies have none, and adding one would change what they measure. What the
models could not do is reported instead (unusable replies, aborted trials, role breaks).
"""
from __future__ import annotations

import json
import time
import traceback

from arena.engine import PromptMismatch, TrialContext
from arena.llm_client import LLMError, ProviderUnavailable, QuotaExhausted
from arena.replic import judge, r_milgram, r_pluralistic, r_zaimbardo

PLANNERS = {"RM": r_milgram.plan, "RP": r_pluralistic.plan, "RZ": r_zaimbardo.plan}
CALLS_PER_TRIAL = {"RM": 18, "RP": 56, "RZ": 19}  # rough, for the estimate printed before the run


def plan(module: str, preset: dict, seed: int) -> list[dict]:
    return PLANNERS[module](preset, seed)


def judges(preset: dict) -> list[str]:
    b = (preset.get("bench") or {}).get("RZ") or {}
    return [m for m in (b.get("guard_model", "llama-guard3-1b"), b.get("judge")) if m]


class ReplicRunner:
    def __init__(self, cfg: dict, preset: dict, storage, client, run_id: str, mock: bool, force_resume: bool = False):
        self.cfg, self.preset, self.storage, self.client = cfg, preset, storage, client
        self.run_id, self.mock, self.force_resume = run_id, mock, force_resume
        self.on_trial_done = None
        mm = preset["bench"].get("max_minutes")
        self.max_s = float(mm) * 60 if mm is not None else None
        self._t0 = time.monotonic()
        self._last_refresh = 0.0
        self.deadline_hit = False

    def _ctx(self, trial: dict) -> TrialContext:
        return TrialContext(self.client, self.storage, self.run_id, trial["trial_id"], trial["module"],
                            int(trial["seed"]), self.mock, force_resume=self.force_resume)

    def _over_time(self) -> bool:
        if self.max_s is not None and time.monotonic() - self._t0 > self.max_s:
            self.deadline_hit = True
        return self.deadline_hit

    def _refresh(self, force: bool = False) -> None:
        if self.on_trial_done and (force or time.monotonic() - self._last_refresh > 120):
            self._last_refresh = time.monotonic()
            self.on_trial_done()

    def models(self, modules: list[str]) -> list[str]:
        planned = [json.loads(t["spec_json"])["model"] for m in modules for t in self.storage.trials(self.run_id, m)]
        return list(dict.fromkeys([m for m in self.preset["bench"]["models"] if m in planned] + planned))

    def run(self, modules: list[str], max_trials: int | None = None) -> None:
        todo = {m: sum(1 for t in self.storage.trials(self.run_id, m) if t["status"] not in ("done", "excluded"))
                for m in modules}
        print("Bench R: about " + ", ".join(f"{m} {n} trials x ~{CALLS_PER_TRIAL[m]} calls" for m, n in todo.items()))
        for model in self.models(modules):
            for module in modules:
                if self._over_time():
                    break
                pending = [t for t in self.storage.trials(self.run_id, module)
                           if t["status"] not in ("done", "excluded") and json.loads(t["spec_json"])["model"] == model]
                if max_trials is not None:
                    pending = pending[:max_trials]
                if pending:
                    print(f"Bench R: {module} on {model}, {len(pending)} trials")
                for i, trial in enumerate(pending, 1):
                    if self._over_time():
                        break
                    self._one(module, trial, i, len(pending))
        if "RZ" in modules and not self._over_time():
            self.judge_pass()
        if self.deadline_hit:
            print(f"Time cap reached ({self.max_s / 60:.0f} min): the remaining trials stay pending (--resume).")
        self._refresh(force=True)

    def _one(self, module: str, trial: dict, i: int, n: int) -> None:
        spec = json.loads(trial["spec_json"])
        self.storage.mark_trial(trial["trial_id"], "running")
        ctx = self._ctx(trial)
        t0 = time.monotonic()
        try:
            if module == "RM":
                out = r_milgram.run_trial(ctx, spec)
            elif module == "RP":
                out = r_pluralistic.run_trial(ctx, spec)
            else:
                out = r_zaimbardo.run_trial(ctx, spec)
        except (QuotaExhausted, ProviderUnavailable, LLMError, PromptMismatch):
            self.storage.mark_trial(trial["trial_id"], "pending")
            raise
        except Exception as e:  # a bug must not silently corrupt other trials
            self.storage.mark_trial(trial["trial_id"], "failed", error=traceback.format_exc()[-2000:])
            print(f"    FAILED {trial['trial_id']}: {e!r}")
            return
        self.storage.mark_trial(trial["trial_id"], "done", out)
        print(f"  [{module}] {spec['model']} {i}/{n}: {ctx.calls_made} calls, {time.monotonic() - t0:.0f} s")
        self._refresh()

    def judge_pass(self) -> None:
        """Every finished R-Z conversation, judged by each judge in turn (one model loaded at a time)."""
        trials = [t for t in self.storage.trials(self.run_id, "RZ") if t["status"] == "done"]
        for jm in judges(self.preset):
            done = {e["trial_id"] for e in self.storage.events(self.run_id, "RZ", "rz_judged")
                    if json.loads(e["payload_json"]).get("judge") == jm}
            todo = [t for t in trials if t["trial_id"] not in done]
            if todo:
                print(f"Bench R: judging {len(todo)} R-Z conversations with {jm}")
            for t in todo:
                if self._over_time():
                    return
                spec, outc = json.loads(t["spec_json"]), json.loads(t["outcome_json"])
                ctx = self._ctx(t)
                if jm == judges(self.preset)[0]:
                    rows = judge.guard_trial(ctx, outc["transcript"], jm)
                    payload = {"judge": jm, "kind": "guard", "rows": rows}
                else:
                    payload = {"kind": "judge", **judge.judge_trial(ctx, spec, outc["transcript"], jm)}
                ctx.event(f"judged|{jm}", "rz_judged", payload)
            self._refresh()
