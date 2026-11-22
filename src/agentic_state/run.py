"""Fair-use runner around `inspect eval`.

- one connection per provider (configs/providers.yaml), so requests are sequential
- Inspect retries 429s with exponential backoff (never a tight loop)
- responses are cached by the tasks (generate(cache=True)): a prompt is never sent twice
- a daily ledger stops runs once the per-model daily budget (rpd) is used

Usage: uv run python -m agentic_state.run <task_file@task> <provider/model> [-T k=v ...]
"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from inspect_ai.log import list_eval_logs, read_eval_log

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "logs" / "request_ledger.json"


def dotenv(path: Path) -> dict:
    if not path.exists():
        return {}
    return dict(l.strip().split("=", 1) for l in path.read_text().splitlines()
                if "=" in l and not l.startswith("#"))


def count_model_calls(log_path) -> int:
    log = read_eval_log(log_path)
    return sum(1 for s in (log.samples or []) for e in s.events if e.event == "model" and e.cache != "read")


def main() -> None:
    task, model, *rest = sys.argv[1:]
    limits = yaml.safe_load((ROOT / "configs" / "providers.yaml").read_text())[model.split("/")[0]]
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    key = f"{dt.date.today()}:{model}"
    used = ledger.get(key, 0)
    if "rpd" in limits and used >= limits["rpd"]:
        sys.exit(f"Daily budget for {model} used ({used}/{limits['rpd']}). Resume tomorrow.")
    cmd = ["uv", "run", "inspect", "eval", task, "--model", model, "--log-dir", str(ROOT / "logs"),
           "--max-connections", str(limits["max_connections"]), "--max-retries", "5",
           "--timeout", "180", "--display", "plain", *rest]
    before = {l.name for l in list_eval_logs(str(ROOT / "logs"))}
    subprocess.run(cmd, cwd=ROOT, env={**os.environ, **dotenv(ROOT / ".env")})
    new = [l for l in list_eval_logs(str(ROOT / "logs")) if l.name not in before]
    ledger[key] = used + sum(count_model_calls(l) for l in new)
    LEDGER.write_text(json.dumps(ledger, indent=1))
    print(f"[fair-use] {model}: {ledger[key]} uncached requests today"
          + (f" / budget {limits['rpd']}" if "rpd" in limits else ""))


if __name__ == "__main__":
    main()
