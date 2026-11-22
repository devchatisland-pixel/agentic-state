"""The Epistemic Arena: command-line entry point.

Examples
  python run_experiment.py --module all --pilot --mock      # full pipeline, zero API calls
  python run_experiment.py --check-providers                # one tiny call per enabled model
  python run_experiment.py --module C --pilot               # real pilot run of Module C
  python run_experiment.py --resume                         # continue the latest unfinished run
  python run_experiment.py --analyze RUN_ID                 # rebuild CSVs, figures, report, dashboard
"""
from __future__ import annotations

import argparse
import os
import datetime as dt
import json
import sys
import traceback

from arena import analyze, baseline_gate, colony
from arena import module_a_asch as mod_a
from arena import module_b_milgram as mod_b
from arena import module_c_dissident as mod_c
from arena.config import get_preset, git_commit, load_config, load_env, resolve, stable_hash
from arena.engine import TrialContext
from arena.items import candidate_items
from arena.llm_client import LLMClient, LLMError, ProviderUnavailable, QuotaExhausted
from arena.schemas import extract_json
from arena.storage import Storage

PLANNERS = {"A": mod_a.plan, "B": mod_b.plan, "C": mod_c.plan}
EXIT_QUOTA, EXIT_UNAVAILABLE, EXIT_ERROR = 3, 4, 2


class Runner:
    def __init__(self, cfg: dict, preset: dict, storage: Storage, client: LLMClient, run_id: str, mock: bool):
        self.cfg, self.preset, self.storage, self.client = cfg, preset, storage, client
        self.run_id, self.mock = run_id, mock
        self.temps = preset["temperatures"]
        self.repeats = int(preset["gate"]["repeats"])
        self.enforce = bool(preset["gate"].get("enforce", True))  # False: gate failures are flagged, not excluded

    def ctx(self, trial: dict) -> TrialContext:
        return TrialContext(self.client, self.storage, self.run_id, trial["trial_id"], trial["module"],
                            int(trial["seed"]), self.mock)

    # ---------------------------------------------------------------- gates
    def gate_a(self) -> list[dict]:
        a = self.preset["module_a"]
        items = candidate_items(int(a["candidate_items"]), int(self.cfg["seed"]))
        g = baseline_gate.gate_module_a(self.client, self.storage, self.run_id, items, list(a["target_models"]),
                                        self.temps, self.repeats, self.mock)
        for it in items:
            it["gate_passed"] = bool(g.passed[it["item_id"]])
        pool = [it for it in items if it["gate_passed"]]
        print(f"  [gate A] {len(pool)}/{len(items)} items solved alone by every target model, every time")
        if not self.enforce and len(pool) < int(a["rounds"]):
            pool = pool + [it for it in items if not it["gate_passed"]]  # passed items first, failures flagged
            print(f"  [gate A] NOT ENFORCED (preset): using {len(pool)} items; failed items are flagged per round")
        self.storage.record_event(self.run_id, f"{self.run_id}-gate", "gate", "A", "gate",
                                  {"passed": g.passed, "kept": [it["item_id"] for it in pool]})
        return pool

    def gate_b(self) -> set[str]:
        roster = list(self.preset["module_b"]["roster"])
        g = baseline_gate.gate_module_b(self.client, self.storage, self.run_id, roster, self.temps, self.repeats,
                                        self.mock)
        ok = {m for m, p in g.passed.items() if p}
        self.gate_b_passed = ok
        print(f"  [gate B] comprehension passed by {len(ok)}/{len(roster)} models: {', '.join(sorted(ok)) or '-'}")
        if not self.enforce:
            print("  [gate B] NOT ENFORCED (preset): failing models stay in the chain and are flagged")
            return set(roster)
        self.storage.record_event(self.run_id, f"{self.run_id}-gate", "gate", "B", "gate", {"passed": g.passed})
        return ok

    def gate_c(self) -> dict:
        c = self.preset["module_c"]
        models = list(dict.fromkeys(list(c["roster"]) + list(c["reserves"]) + list(c["dissident_models"])))
        g = baseline_gate.gate_module_c(self.client, self.storage, self.run_id, models, self.temps, self.repeats,
                                        self.mock)
        n_ok = sum(1 for m in models if any(g.passed[(m, v.vid)] for v in colony.VARIANTS))
        print(f"  [gate C] {n_ok}/{len(models)} models solved at least one trap variant alone, every time")
        self.storage.record_event(self.run_id, f"{self.run_id}-gate", "gate", "C", "gate",
                                  {"passed": {f"{m}|{v}": p for (m, v), p in g.passed.items()}})
        return g.passed

    # ---------------------------------------------------------------- module loop
    def run_module(self, module: str, gate_only: bool = False, max_trials: int | None = None) -> None:
        print(f"Module {module}: running the baseline gate")
        gate = {"A": self.gate_a, "B": self.gate_b, "C": self.gate_c}[module]()
        if gate_only:
            return
        pending = [t for t in self.storage.trials(self.run_id, module) if t["status"] not in ("done", "excluded")]
        if max_trials is not None:
            pending = pending[:max_trials]
        for i, trial in enumerate(pending, 1):
            spec = json.loads(trial["spec_json"])
            print(f"  [{module}] trial {i}/{len(pending)} {trial['trial_id']} {spec}")
            excluded = self.exclusion(module, spec, gate)
            if excluded:
                print(f"    excluded: {excluded}")
                self.storage.mark_trial(trial["trial_id"], "excluded", error=excluded)
                continue
            self.storage.mark_trial(trial["trial_id"], "running")
            ctx = self.ctx(trial)
            try:
                if module == "A":
                    outcome = mod_a.run_trial(ctx, spec, self.preset, self.cfg, gate)
                elif module == "B":
                    outcome = mod_b.run_trial(ctx, spec, self.preset, self.cfg)
                    roles = [spec["t1"], spec["t3"]] + ([spec["t2"]] if spec["chain"] == "full" else [])
                    outcome["gate_failed_models"] = [m for m in roles if m not in self.gate_b_passed]
                else:
                    comp, variants = self.c_composition(spec, gate)
                    outcome = mod_c.run_trial(ctx, spec, self.preset, self.cfg, comp, variants, gate)
            except (QuotaExhausted, ProviderUnavailable):
                self.storage.mark_trial(trial["trial_id"], "pending")
                raise
            except LLMError:
                self.storage.mark_trial(trial["trial_id"], "pending")
                raise
            except Exception as e:  # a bug must not silently corrupt other trials
                self.storage.mark_trial(trial["trial_id"], "failed", error=traceback.format_exc()[-2000:])
                print(f"    FAILED: {e!r} (traceback stored in the trials table)")
                continue
            self.storage.mark_trial(trial["trial_id"], "done", outcome)
            print(f"    done ({ctx.calls_made} new API calls): "
                  + json.dumps({k: v for k, v in outcome.items() if not isinstance(v, (dict, list))}))

    def exclusion(self, module: str, spec: dict, gate) -> str | None:
        if module == "B":
            roles = [spec["t1"], spec["t3"]] + ([spec["t2"]] if spec["chain"] == "full" else [])
            bad = [m for m in roles if m not in gate]
            return f"failed the comprehension gate: {', '.join(bad)}" if bad else None
        if module == "C":
            try:
                self.c_composition(spec, gate)
            except ValueError as e:
                return str(e)
        return None

    def c_composition(self, spec: dict, passed: dict) -> tuple[list[str], list[str]]:
        c = self.preset["module_c"]
        vids = [v.vid for v in colony.VARIANTS]
        ok = lambda m: any(passed.get((m, v), False) for v in vids)  # noqa: E731
        dm = spec["dissident_model"]
        if not self.enforce:  # seat the configured roster; pick the variant(s) the most seated models pass
            comp = mod_c.composition(dm, list(dict.fromkeys(list(c["roster"]) + list(c["reserves"]))))
            score = {v: sum(passed.get((m, v), False) for m in comp) for v in vids}
            best = max(score.values())
            return comp, [v for v in vids if score[v] == best]
        if not ok(dm):
            raise ValueError(f"dissident model {dm} failed the trap gate on every variant")
        pool = [m for m in list(c["roster"]) + list(c["reserves"]) if ok(m)]
        comp = mod_c.composition(dm, list(dict.fromkeys(pool)))
        variants = [v for v in vids if all(passed.get((m, v), False) for m in comp)]
        if not variants:
            raise ValueError("no trap variant is solved alone by all seated models")
        return comp, variants


def check_providers(cfg: dict, storage: Storage) -> int:
    client = LLMClient(cfg, usage=storage)
    msgs = [{"role": "system", "content": "Reply with JSON only."},
            {"role": "user", "content": 'Reply exactly with this JSON object: {"ok": true, "word": "arena"}'}]
    worst = 0
    for mid, m in cfg["models"].items():
        if not m.get("enabled", True):
            print(f"  {mid:18s} disabled in config.yaml")
            continue
        try:
            r = client.chat(mid, msgs, temperature=0.0, seed=1, max_tokens=m.get("max_tokens", 300))
            try:
                obj = extract_json(r.text)
                status = "OK  " if obj.get("ok") is True else "JSON?"
            except ValueError:
                status, worst = "NO-JSON", max(worst, 1)
            print(f"  {mid:18s} {status} {r.latency_s:5.1f}s  in={r.tokens_in} out={r.tokens_out}  {r.text[:60]!r}")
        except QuotaExhausted as e:
            print(f"  {mid:18s} QUOTA  {e}")
        except LLMError as e:
            worst = max(worst, 1)
            print(f"  {mid:18s} ERROR  {str(e)[:160]}")
    client.close()
    return worst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The Epistemic Arena")
    ap.add_argument("--module", choices=["A", "B", "C", "all"], default="all")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pilot", action="store_true", help="small exploratory batch (default)")
    g.add_argument("--full", action="store_true", help="full study preset")
    g.add_argument("--local", action="store_true", help="100%% offline preset (Ollama only, no quota)")
    g.add_argument("--preset", default=None, help="any preset name from config.yaml")
    ap.add_argument("--live", action="store_true", help="open the live monitor (http://localhost:8765) during the run")
    ap.add_argument("--mock-delay", type=float, default=0.0, help="seconds per simulated reply (to watch --mock live)")
    ap.add_argument("--mock", "--dry-run", dest="mock", action="store_true", help="simulated replies, zero API calls")
    ap.add_argument("--resume", nargs="?", const="latest", default=None, metavar="RUN_ID",
                    help="continue a paused run (latest unfinished if no id)")
    ap.add_argument("--gate-only", action="store_true", help="only run the baseline gates")
    ap.add_argument("--max-trials", type=int, default=None, help="run at most N pending trials per module")
    ap.add_argument("--analyze", metavar="RUN_ID", help="only rebuild the analysis of a run")
    ap.add_argument("--no-analyze", action="store_true")
    ap.add_argument("--check-providers", action="store_true", help="one tiny JSON call per enabled model")
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Windows consoles: never crash on non-ASCII model text
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    load_env()
    cfg = load_config(args.config)
    paths = cfg["paths"]
    storage = Storage(resolve(paths["mock_db"] if args.mock else paths["db"]), resolve(paths["jsonl_dir"]))
    dash = resolve(paths["mock_dashboard"] if args.mock else paths["dashboard"])
    if args.check_providers:
        return check_providers(cfg, storage)
    if args.analyze:
        res = analyze.run(storage, args.analyze, resolve(paths["results_dir"]), dash)
        print(f"Report: {res['report']}\nDashboard: {res['dashboard']}")
        return 0

    if args.resume:
        run = (storage.latest_run(unfinished_only=True) if args.resume == "latest" else storage.get_run(args.resume))
        if not run:
            print("No run to resume" + (" in the mock database" if args.mock else "") + ".")
            return EXIT_ERROR
        run_id, preset_name, modules = run["run_id"], run["preset"], run["modules"].split(",")
        print(f"Resuming run {run_id} (preset {preset_name}, modules {','.join(modules)})")
    else:
        preset_name = args.preset or ("full" if args.full else "local" if args.local else "pilot")
        modules = ["A", "B", "C"] if args.module == "all" else [args.module]
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run_id = f"{'mock-' if args.mock else ''}{stamp}-{preset_name}-{''.join(modules)}"
        preset = get_preset(cfg, preset_name)
        storage.create_run(run_id, preset_name, modules, args.mock, stable_hash(cfg), cfg, git_commit())
        for module in modules:
            for idx, spec in enumerate(PLANNERS[module](preset)):
                seed = int(stable_hash([cfg["seed"], module, spec], 8), 16)
                storage.add_trial(f"{run_id}-{module}-{idx:03d}", run_id, module, idx, spec, seed)
        print(f"Created run {run_id}: " + ", ".join(f"{m}={len(storage.trials(run_id, m))} trials" for m in modules))
    preset = get_preset(cfg, preset_name)
    client = LLMClient(cfg, usage=storage, mock=args.mock, mock_delay=args.mock_delay)
    if args.live:
        from live_monitor import start_in_background
        start_in_background(storage.db_path, open_browser=not os.environ.get("ARENA_NO_BROWSER"))
    runner = Runner(cfg, preset, storage, client, run_id, args.mock)
    code = 0
    try:
        for module in modules:
            runner.run_module(module, args.gate_only, args.max_trials)
    except QuotaExhausted as e:
        storage.set_run_status(run_id, "paused")
        print(f"\nDaily free-tier quota reached: {e}\nEverything so far is saved. Resume tomorrow with:\n"
              f"  python run_experiment.py --resume {run_id}{' --mock' if args.mock else ''}")
        code = EXIT_QUOTA
    except ProviderUnavailable as e:
        storage.set_run_status(run_id, "paused")
        print(f"\nProvider unavailable after retries: {e}\nResume later with:\n  python run_experiment.py --resume {run_id}")
        code = EXIT_UNAVAILABLE
    except LLMError as e:
        storage.set_run_status(run_id, "error")
        print(f"\nConfiguration or provider error: {e}\nFix it, then resume with:\n  python run_experiment.py --resume {run_id}")
        code = EXIT_ERROR
    finally:
        client.close()
    if code == 0:
        statuses = {t["status"] for t in storage.trials(run_id)}
        storage.set_run_status(run_id, "done" if statuses <= {"done", "excluded"} else "partial")
    if not args.no_analyze and not args.gate_only:
        res = analyze.run(storage, run_id, resolve(paths["results_dir"]), dash)
        print(f"\nReport:    {res['report']}\nDashboard: {res['dashboard']}")
    usage = storage.usage_today()
    if usage and not args.mock:
        print("Free-tier usage today: " + ", ".join(f"{u['model_id']}={u['requests']}" for u in usage))
    if args.live:  # keep the live page up after the run so results can be read in the morning
        import time
        print("\nRun finished. The live monitor stays open at http://localhost:8765 . Press Ctrl+C to quit.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
