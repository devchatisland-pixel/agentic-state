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
import copy
import os
import datetime as dt
import json
import sys
import traceback

from arena import analyze, baseline_gate, colony, manifest
from arena import module_a_asch as mod_a
from arena import module_b_milgram as mod_b
from arena import module_c_dissident as mod_c
from arena.config import get_preset, git_commit, git_dirty, load_config, load_env, resolve, stable_hash
from arena.engine import PromptMismatch, TrialContext
from arena.bench import BENCH_MODULES
from arena.bench import runner as bench_runner
from arena.bench import screen as bench_screen
from arena.items import item_banks, module_a_items
from arena.llm_client import LLMClient, LLMError, ProviderUnavailable, QuotaExhausted
from arena.schemas import extract_json
from arena.storage import Storage

PLANNERS = {"A": mod_a.plan, "B": mod_b.plan, "C": mod_c.plan}
EXIT_QUOTA, EXIT_UNAVAILABLE, EXIT_ERROR, EXIT_SCREEN_FAIL = 3, 4, 2, 5


class Runner:
    def __init__(self, cfg: dict, preset: dict, storage: Storage, client: LLMClient, run_id: str, mock: bool,
                 run_seed: int = 0, force_resume: bool = False):
        self.cfg, self.preset, self.storage, self.client = cfg, preset, storage, client
        self.run_id, self.mock = run_id, mock
        self.temps = preset["temperatures"]
        self.repeats = int(preset["gate"]["repeats"])
        self.enforce = bool(preset["gate"].get("enforce", True))  # False: gate failures are flagged, not excluded
        self.run_seed, self.force_resume = run_seed, force_resume
        self.on_trial_done = None  # optional callback (e.g. rebuild the results page live)

    def gate_seed(self, module: str) -> int:
        return int(stable_hash([self.run_seed, "gate", module], 8), 16)

    def ctx(self, trial: dict) -> TrialContext:
        return TrialContext(self.client, self.storage, self.run_id, trial["trial_id"], trial["module"],
                            int(trial["seed"]), self.mock, force_resume=self.force_resume)

    # ---------------------------------------------------------------- gates
    def gate_a(self) -> dict[str, list[dict]]:
        """One item pool PER target model: the items that model solved alone, every time.

        (Before, an item had to be solved by every target; with one weak target that left 4/16 items and the
        rest was filled with unsolved ones. Per-model pools keep each target on problems it knows.)"""
        a = self.preset["module_a"]
        items = module_a_items(a, int(self.cfg["seed"]))
        models = list(dict.fromkeys(a["target_models"]))
        g = baseline_gate.gate_module_a(self.client, self.storage, self.run_id, items, models,
                                        self.temps, self.repeats, self.mock, self.gate_seed("A"))
        solved = {(m, it["item_id"]): True for m in models for it in items}
        for d in g.detail:
            solved[(d["model_id"], d["item_id"])] &= bool(d["correct"])
        pools, kept = {}, {}
        for m in models:
            for bank in item_banks(a):  # one pool per (model, bank): a bank factor never mixes banks in a trial
                bi = [it for it in items if it["bank"] == bank]
                ok = [dict(it, gate_passed=True) for it in bi if solved[(m, it["item_id"])]]
                bad = [dict(it, gate_passed=False) for it in bi if not solved[(m, it["item_id"])]]
                print(f"  [gate A] {m} ({bank}): {len(ok)}/{len(bi)} items solved alone, every time")
                pool = ok
                if not self.enforce and len(pool) < int(a["rounds"]):
                    pool = ok + bad  # passed items first, failures flagged per round
                    print(f"  [gate A] {m} ({bank}): NOT ENFORCED (preset): {len(bad)} unsolved items flagged and used")
                pools[(m, bank)] = pool
                kept[m] = kept.get(m, []) + [it["item_id"] for it in pool]
        self.storage.record_event(self.run_id, f"{self.run_id}-gate", "gate", "A", "gate",
                                  {"passed": g.passed, "solved": {f"{m}|{i}": v for (m, i), v in solved.items()},
                                   "kept": kept, "enforced": self.enforce, "repeats": self.repeats})
        return pools

    def gate_b(self) -> set[str]:
        roster = list(self.preset["module_b"]["roster"])
        g = baseline_gate.gate_module_b(self.client, self.storage, self.run_id, roster, self.temps, self.repeats,
                                        self.mock, self.gate_seed("B"))
        ok = {m for m, p in g.passed.items() if p}
        self.gate_b_passed = ok
        print(f"  [gate B] comprehension passed by {len(ok)}/{len(roster)} models: {', '.join(sorted(ok)) or '-'}")
        # Recorded whether enforced or not (before 24 Nov 2026 a non-enforced result was never saved).
        self.storage.record_event(self.run_id, f"{self.run_id}-gate", "gate", "B", "gate",
                                  {"passed": g.passed, "enforced": self.enforce, "repeats": self.repeats})
        if not self.enforce:
            print("  [gate B] NOT ENFORCED (preset): failing models stay in the chain and are flagged")
            return set(roster)
        return ok

    def gate_c(self) -> dict:
        c = self.preset["module_c"]
        models = list(dict.fromkeys(list(c["roster"]) + list(c["reserves"]) + list(c["dissident_models"])))
        g = baseline_gate.gate_module_c(self.client, self.storage, self.run_id, models, self.temps, self.repeats,
                                        self.mock, self.gate_seed("C"),
                                        hints=bool(c.get("sensor_hints", True)),
                                        no_bulletin_probe=bool(c.get("gate_no_bulletin_probe", False)))
        n_ok = sum(1 for m in models if any(g.passed[(m, v.vid)] for v in colony.VARIANTS))
        print(f"  [gate C] {n_ok}/{len(models)} models solved at least one trap variant alone, every time")
        self.storage.record_event(self.run_id, f"{self.run_id}-gate", "gate", "C", "gate",
                                  {"passed": {f"{m}|{v}": p for (m, v), p in g.passed.items()},
                                   "enforced": self.enforce, "repeats": self.repeats,
                                   "no_bulletin": {f"{m}|{v}": p for (m, v), p in g.probe.items()}})
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
                    bank = spec.get("item_bank", item_banks(self.preset["module_a"])[0])
                    outcome = mod_a.run_trial(ctx, spec, self.preset, self.cfg, gate[(spec["target_model"], bank)])
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
            except (LLMError, PromptMismatch):
                self.storage.mark_trial(trial["trial_id"], "pending")
                raise
            except Exception as e:  # a bug must not silently corrupt other trials
                self.storage.mark_trial(trial["trial_id"], "failed", error=traceback.format_exc()[-2000:])
                print(f"    FAILED: {e!r} (traceback stored in the trials table)")
                continue
            self.storage.mark_trial(trial["trial_id"], "done", outcome)
            print(f"    done ({ctx.calls_made} new API calls): "
                  + json.dumps({k: v for k, v in outcome.items() if not isinstance(v, (dict, list))}))
            if self.on_trial_done:
                self.on_trial_done()

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


def confirmatory_problems(preset: dict, prereg: str | None, small: list[str], dirty: bool | None) -> list[str]:
    """Why a confirmatory run must not start (empty list: it may). Protocol v2, plus the Bench L solo filter."""
    problems = [f"at least 3 trials per cell are needed ({', '.join(small)})"] if small else []
    if not prereg or not os.path.exists(prereg):
        problems.append("--prereg FILE is required (the frozen pre-registration)")
    if not preset["gate"].get("enforce", True):
        problems.append("the preset must enforce the pre-check (gate.enforce: true)")
    if int(preset["gate"]["repeats"]) < 5:
        problems.append("the pre-check needs at least 5 repeats (gate.repeats >= 5)")
    if "bench" in preset and int(preset["bench"].get("solo_repeats", 0)) < 5:
        problems.append("the Bench L solo filter needs at least 5 repeats (bench.solo_repeats >= 5)")
    if dirty:
        problems.append("commit your changes first: a confirmatory run must come from a clean commit")
    return problems


def apply_preset_providers(cfg: dict, preset: dict) -> dict:
    """A preset may override provider settings (`providers: {ollama: {kind: ollama_native, options: ...}}`): Bench L v4
    sends Ollama requests to the native endpoint with load options (scripts/ollama_fit.py, 27 Nov 2026). The
    merged settings go into the stored configuration and the manifest of the run."""
    over = preset.get("providers") or {}
    if not over:
        return cfg
    cfg = copy.deepcopy(cfg)
    for name, settings in over.items():
        cfg["providers"].setdefault(name, {}).update(settings)
    return cfg


def screen_models(results_dir, screen_id: str, modules: list[str], preset: dict) -> tuple[dict, list[str], dict]:
    """Per-module model lists from a screen run (protocol v4): {module: models}, the modules kept, and the record
    stored in the manifest. A module the screen did not pass is dropped; a module it did not cover keeps the
    preset's models."""
    res, sha = bench_screen.load(results_dir, screen_id)
    min_models = int((res.get("criteria") or {}).get("min_models", 2))
    per, kept = {}, []
    for m in modules:
        sm = res["modules"].get(m)
        if sm is None:
            per[m] = list(preset["bench"]["models"])
            kept.append(m)
        elif sm["decision"] == "pass" and len(sm["passed"]) >= min_models:
            # the models that passed, in the screen's order, whether or not the pilot preset lists them (a screen
            # run with --models can pass models the preset does not name; 27 Nov 2026 the intersection silently
            # dropped nemotron-4b and left a one-model pilot)
            per[m] = list(sm["passed"])
            kept.append(m)
        else:
            print(f"  {m}: the screen {screen_id} did not pass this module ({len(sm['passed'])} models passed): "
                  "it is not run.")
    return per, kept, {"run_id": screen_id, "sha256": sha, "models": per}


def _modules_arg(text: str):
    if text.strip().lower() == "all":
        return "all"
    if text.strip().lower() == "bench":
        return list(BENCH_MODULES)
    mods = {m.strip().upper() for m in text.split(",") if m.strip()}
    order = ("A", "B", "C") + BENCH_MODULES
    if not mods or any(m not in order for m in mods):
        raise argparse.ArgumentTypeError("expected A, B, C, all, bench (= LA,LB,LC1,LC2), or a comma list such as "
                                         "B,C or LC1,LA")
    return [m for m in order if m in mods]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The Epistemic Arena")
    ap.add_argument("--module", type=_modules_arg, default="all",
                    help="A, B, C, all, bench (Bench L: LA, LB, LC1, LC2), or a comma list such as B,C or LC1,LA")
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
    ap.add_argument("--run-type", choices=["smoke", "pilot", "confirmatory"], default=None,
                    help="what the run is for (docs/protocol_v2.md); default: the preset's run_type")
    ap.add_argument("--prereg", default=None, metavar="FILE",
                    help="pre-registration file (required for --run-type confirmatory); its hash is stored")
    ap.add_argument("--seed", type=int, default=None,
                    help="run-level seed mixed into every trial seed (default: derived from the run id, so two runs "
                         "never reuse the same seeds)")
    ap.add_argument("--models", default=None, metavar="ID,ID",
                    help="Bench L: run these model ids (from config.yaml) instead of the preset's models")
    ap.add_argument("--screen", default=None, metavar="RUN_ID",
                    help="Bench L v4: run each module only on the models that passed this screen run")
    ap.add_argument("--force-resume", action="store_true",
                    help="resume even if the code now builds different prompts than the stored ones")
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
        try:  # resume with the preset the run was created with (it may carry a --models override)
            cfg["presets"][preset_name] = json.loads(run["config_json"])["presets"][preset_name]
        except (KeyError, TypeError, ValueError):
            pass
        run_seed = run.get("run_seed") or 0
        print(f"Resuming run {run_id} (preset {preset_name}, modules {','.join(modules)})")
    else:
        preset_name = args.preset or ("full" if args.full else "local" if args.local else "pilot")
        modules = ["A", "B", "C"] if args.module == "all" else args.module
        if any(m in BENCH_MODULES for m in modules) and "bench" not in get_preset(cfg, preset_name):
            preset_name = "bench-local"  # Bench L needs a preset with a `bench` block
            print("Bench L modules: using the 'bench-local' preset (pass --preset to choose another bench preset).")
        preset = get_preset(cfg, preset_name)
        if args.models:
            ids = [m.strip() for m in args.models.split(",") if m.strip()]
            unknown = [m for m in ids if m not in cfg["models"]]
            if unknown or "bench" not in preset:
                print(f"Refusing the run: --models needs a Bench L preset and model ids from config.yaml "
                      f"(unknown: {', '.join(unknown) or 'none'}).")
                return EXIT_ERROR
            preset["bench"]["models"] = ids  # recorded in the stored configuration and the manifest
        cfg = apply_preset_providers(cfg, preset)
        per_module, screen_rec = {}, None
        if args.screen:
            try:
                per_module, modules, screen_rec = screen_models(resolve(paths["results_dir"]), args.screen,
                                                                modules, preset)
            except FileNotFoundError as e:
                print(f"Refusing the run: {e}")
                return EXIT_ERROR
            if not modules:
                print(f"Refusing the run: no module passed the screen {args.screen}.")
                return EXIT_ERROR
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run_id = f"{'mock-' if args.mock else ''}{stamp}-{preset_name}-{''.join(modules)}"
        run_type = "mock" if args.mock else (args.run_type or preset.get("run_type") or
                                             ("pilot" if preset["gate"].get("enforce", True) else "smoke"))
        prereg = None
        # n = 1 (or 2) per cell estimates no variance: such a run is a feasibility / smoke test, never a pilot.
        small = [f"module_{m.lower()}.reps = {preset[f'module_{m.lower()}'].get('reps', 1)}" for m in modules
                 if m in ("A", "C") and int(preset[f"module_{m.lower()}"].get("reps", 1)) < 3]
        if small and run_type == "pilot" and not args.run_type:
            print(f"Run type set to 'smoke' (fewer than 3 trials per cell: {', '.join(small)}). "
                  "Pass --run-type pilot to override.")
            run_type = "smoke"
        if "C" in modules:
            mc = preset["module_c"]
            ok, worst = colony.collapse_reachable(int(mc["turns"]), int(mc["trap_turn"]))
            if not ok:
                print(f"WARNING: module_c.turns = {mc['turns']} is too short for a collapse: drilling on every turn "
                      f"from turn {mc['trap_turn']} empties the energy reserve at turn {worst} at the earliest, so "
                      f"the colony outcome cannot vary. Use at least {worst + 2} turns.")
        if run_type == "confirmatory":
            problems = confirmatory_problems(preset, args.prereg, small, git_dirty())
            if problems:
                print("Refusing a confirmatory run:\n  - " + "\n  - ".join(problems))
                return EXIT_ERROR
            prereg = manifest.prereg_hash(args.prereg)
        elif args.prereg:
            prereg = manifest.prereg_hash(args.prereg)
        run_seed = args.seed if args.seed is not None else int(stable_hash([run_id], 8), 16)
        storage.create_run(run_id, preset_name, modules, args.mock, stable_hash(cfg), cfg, git_commit(),
                           run_type=run_type, prereg_hash=prereg, run_seed=run_seed)
        for module in modules:
            mp = preset
            block_models = (preset.get("bench", {}).get(module) or {}).get("models")
            if module in per_module or block_models:
                # the models that passed this module's screen, or the module's own list in the preset (a
                # confirmatory preset fixes them per module, from the screens)
                mp = copy.deepcopy(preset)
                mp["bench"]["models"] = per_module.get(module) or list(block_models)
            specs = (bench_runner.plan(module, mp, int(cfg["seed"])) if module in BENCH_MODULES
                     else PLANNERS[module](preset))
            for idx, spec in enumerate(specs):
                seed = int(stable_hash([cfg["seed"], run_seed, module, spec], 8), 16)
                storage.add_trial(f"{run_id}-{module}-{idx:03d}", run_id, module, idx, spec, seed)
        try:
            man = manifest.build(storage.get_run(run_id), cfg, preset, args.mock)
            if screen_rec:
                man["screen"] = screen_rec
            manifest.write(resolve(paths["results_dir"]) / run_id / "manifest.json", man)
        except OSError as e:
            print(f"  (manifest not written: {e})")
        print(f"Created run {run_id} ({run_type}): "
              + ", ".join(f"{m}={len(storage.trials(run_id, m))} trials" for m in modules))
    preset = get_preset(cfg, preset_name)
    cfg = apply_preset_providers(cfg, preset)
    client = LLMClient(cfg, usage=storage, mock=args.mock, mock_delay=args.mock_delay)
    runner = Runner(cfg, preset, storage, client, run_id, args.mock, run_seed=run_seed, force_resume=args.force_resume)
    if args.live:
        from live_monitor import start_in_background

        def refresh_results() -> None:  # partial results, rebuilt after every finished trial
            try:
                analyze.run(storage, run_id, resolve(paths["results_dir"]), dash)
            except Exception as e:  # never let a plotting problem stop the experiment
                print(f"    (live results not refreshed: {e!r})")

        refresh_results()
        runner.on_trial_done = refresh_results
        start_in_background(storage.db_path, dashboard=dash, open_browser=not os.environ.get("ARENA_NO_BROWSER"))
    code = 0
    storage.set_run_status(run_id, "running")  # also on --resume of a paused run
    try:
        for module in modules:
            if module not in BENCH_MODULES:
                runner.run_module(module, args.gate_only, args.max_trials)
        bench_mods = [m for m in modules if m in BENCH_MODULES]
        if bench_mods:  # model-major: every module of one model, then the next model (Ollama loads each model once)
            br = bench_runner.BenchRunner(cfg, preset, storage, client, run_id, args.mock,
                                          force_resume=args.force_resume)
            br.on_trial_done = runner.on_trial_done
            br.run(bench_mods, args.gate_only, args.max_trials)
    except QuotaExhausted as e:
        storage.set_run_status(run_id, "paused")
        print(f"\nDaily free-tier quota reached: {e}\nEverything so far is saved. Resume tomorrow with:\n"
              f"  python run_experiment.py --resume {run_id}{' --mock' if args.mock else ''}")
        code = EXIT_QUOTA
    except ProviderUnavailable as e:
        storage.set_run_status(run_id, "paused")
        print(f"\nProvider unavailable after retries: {e}\nResume later with:\n  python run_experiment.py --resume {run_id}")
        code = EXIT_UNAVAILABLE
    except PromptMismatch as e:
        storage.set_run_status(run_id, "paused")
        print(f"\nResume refused: {e}")
        code = EXIT_ERROR
    except LLMError as e:
        storage.set_run_status(run_id, "error")
        print(f"\nConfiguration or provider error: {e}\nFix it, then resume with:\n  python run_experiment.py --resume {run_id}")
        code = EXIT_ERROR
    finally:
        client.close()
        storage.set_live(run_id, None, None, None, None, None)  # nobody is "thinking" any more
    if code == 0:
        statuses = {t["status"] for t in storage.trials(run_id)}
        storage.set_run_status(run_id, "done" if statuses <= {"done", "excluded"} else "partial")
    if preset.get("bench", {}).get("stage") == "screen" and code == 0 and not args.gate_only:
        sres = bench_screen.evaluate(storage, run_id, preset, [m for m in modules if m in BENCH_MODULES])
        j, md = bench_screen.write(sres, resolve(paths["results_dir"]) / run_id)
        print("\n" + bench_screen.console(sres) + f"\nScreen report: {md}")
        if sres["decision"] == "pass":
            print(f"Next (stage 2): python run_experiment.py --module {','.join(sres['modules'])} --preset bench-v4 "
                  f"--screen {run_id}")
        else:
            code = EXIT_SCREEN_FAIL
    if not args.no_analyze and not args.gate_only:
        res = analyze.run(storage, run_id, resolve(paths["results_dir"]), dash)
        print(f"\nReport:    {res['report']}\nDashboard: {res['dashboard']}")
    usage = storage.usage_today()
    if usage and not args.mock:
        print("Free-tier usage today: " + ", ".join(f"{u['model_id']}={u['requests']}" for u in usage))
    if args.live:  # keep the live page up after the run so results can be read in the morning
        import time
        print("\nRun finished. The live monitor stays open at http://localhost:8765 "
              "(results: http://localhost:8765/results). Press Ctrl+C to quit.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
