"""SQLite + JSONL logging with atomic, call-level checkpointing.

Every API call is written immediately (SQLite in WAL mode with autocommit, plus an append-only
JSONL mirror). Trials are deterministic functions of their seed and of the recorded replies, so
resuming a trial *replays* recorded calls instead of re-sending them: an interrupted run loses
nothing and never spends quota twice.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, created_at TEXT, preset TEXT, modules TEXT, mock INTEGER,
  config_hash TEXT, config_json TEXT, git_commit TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS trials(
  trial_id TEXT PRIMARY KEY, run_id TEXT, module TEXT, idx INTEGER, spec_json TEXT, seed INTEGER,
  status TEXT, outcome_json TEXT, started_at TEXT, finished_at TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, trial_id TEXT, step_key TEXT, attempt INTEGER,
  agent TEXT, role TEXT, model_id TEXT, provider TEXT, model_name TEXT, temperature REAL, seed INTEGER,
  prompt_hash TEXT, response_hash TEXT, messages_json TEXT, response_text TEXT, reasoning TEXT,
  tokens_in INTEGER, tokens_out INTEGER, latency_s REAL, error_type TEXT, error TEXT, mock INTEGER,
  created_at TEXT, UNIQUE(trial_id, step_key, attempt));
CREATE TABLE IF NOT EXISTS turns(
  trial_id TEXT, step_key TEXT, run_id TEXT, module TEXT, agent TEXT, role TEXT, model_id TEXT,
  status TEXT, attempts INTEGER, error TEXT, parsed_json TEXT, created_at TEXT,
  PRIMARY KEY(trial_id, step_key));
CREATE TABLE IF NOT EXISTS events(
  trial_id TEXT, event_key TEXT, run_id TEXT, module TEXT, event_type TEXT, payload_json TEXT,
  created_at TEXT, PRIMARY KEY(trial_id, event_key));
CREATE TABLE IF NOT EXISTS usage(
  day TEXT, provider TEXT, model_id TEXT, requests INTEGER, tokens INTEGER,
  PRIMARY KEY(day, provider, model_id));
CREATE TABLE IF NOT EXISTS live(
  id INTEGER PRIMARY KEY CHECK (id = 1), run_id TEXT, trial_id TEXT, step_key TEXT, agent TEXT, role TEXT,
  model_id TEXT, started_at TEXT);
CREATE INDEX IF NOT EXISTS idx_turns_run ON turns(run_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def utc_day() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


class Storage:
    def __init__(self, db_path: str | Path, jsonl_dir: str | Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_dir = Path(jsonl_dir)
        self.jsonl_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.db_path = db_path

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------ helpers
    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, params)

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        row = self._exec(sql, params).fetchone()
        return dict(row) if row else None

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in self._exec(sql, params).fetchall()]

    def _mirror(self, run_id: str | None, table: str, record: dict) -> None:
        path = self.jsonl_dir / f"{run_id or 'misc'}.jsonl"
        with self.lock, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"table": table, **record}, ensure_ascii=False, default=str) + "\n")

    # ------------------------------------------------------------ runs & trials
    def create_run(self, run_id: str, preset: str, modules: list[str], mock: bool, cfg_hash: str,
                   cfg: dict, commit: str | None) -> None:
        rec = dict(run_id=run_id, created_at=now_iso(), preset=preset, modules=",".join(modules),
                   mock=int(mock), config_hash=cfg_hash, config_json=json.dumps(cfg, default=str),
                   git_commit=commit, status="running")
        self._exec("INSERT INTO runs(run_id,created_at,preset,modules,mock,config_hash,config_json,"
                   "git_commit,status) VALUES(?,?,?,?,?,?,?,?,?)", tuple(rec.values()))
        self._mirror(run_id, "runs", {k: v for k, v in rec.items() if k != "config_json"})

    def get_run(self, run_id: str) -> dict | None:
        return self._one("SELECT * FROM runs WHERE run_id=?", (run_id,))

    def latest_run(self, unfinished_only: bool = False) -> dict | None:
        sql = "SELECT * FROM runs " + ("WHERE status!='done' " if unfinished_only else "") + "ORDER BY created_at DESC, run_id DESC LIMIT 1"
        return self._one(sql)

    def set_run_status(self, run_id: str, status: str) -> None:
        self._exec("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))

    def add_trial(self, trial_id: str, run_id: str, module: str, idx: int, spec: dict, seed: int) -> None:
        self._exec("INSERT OR IGNORE INTO trials(trial_id,run_id,module,idx,spec_json,seed,status) "
                   "VALUES(?,?,?,?,?,?,'pending')", (trial_id, run_id, module, idx, json.dumps(spec), seed))

    def trials(self, run_id: str, module: str | None = None) -> list[dict]:
        if module:
            return self._all("SELECT * FROM trials WHERE run_id=? AND module=? ORDER BY idx", (run_id, module))
        return self._all("SELECT * FROM trials WHERE run_id=? ORDER BY module, idx", (run_id,))

    def mark_trial(self, trial_id: str, status: str, outcome: dict | None = None, error: str | None = None) -> None:
        ts = now_iso()
        if status == "running":
            self._exec("UPDATE trials SET status=?, started_at=COALESCE(started_at, ?) WHERE trial_id=?",
                       (status, ts, trial_id))
        else:
            self._exec("UPDATE trials SET status=?, outcome_json=?, finished_at=?, error=? WHERE trial_id=?",
                       (status, json.dumps(outcome) if outcome is not None else None, ts, error, trial_id))
        row = self._one("SELECT run_id FROM trials WHERE trial_id=?", (trial_id,))
        self._mirror(row["run_id"] if row else None, "trials",
                     {"trial_id": trial_id, "status": status, "outcome": outcome, "error": error, "at": ts})

    # ------------------------------------------------------------ calls (one row per API call)
    def get_call(self, trial_id: str, step_key: str, attempt: int) -> dict | None:
        return self._one("SELECT * FROM calls WHERE trial_id=? AND step_key=? AND attempt=?",
                         (trial_id, step_key, attempt))

    def record_call(self, **rec: Any) -> None:
        rec.setdefault("created_at", now_iso())
        cols = ["run_id", "trial_id", "step_key", "attempt", "agent", "role", "model_id", "provider",
                "model_name", "temperature", "seed", "prompt_hash", "response_hash", "messages_json",
                "response_text", "reasoning", "tokens_in", "tokens_out", "latency_s", "error_type",
                "error", "mock", "created_at"]
        vals = tuple(rec.get(c) for c in cols)
        self._exec(f"INSERT OR REPLACE INTO calls({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)
        self._mirror(rec.get("run_id"), "calls", {c: rec.get(c) for c in cols if c != "messages_json"})

    # ------------------------------------------------------------ turns (validated agent turns)
    def get_turn(self, trial_id: str, step_key: str) -> dict | None:
        return self._one("SELECT * FROM turns WHERE trial_id=? AND step_key=?", (trial_id, step_key))

    def record_turn(self, **rec: Any) -> None:
        rec.setdefault("created_at", now_iso())
        cols = ["trial_id", "step_key", "run_id", "module", "agent", "role", "model_id", "status",
                "attempts", "error", "parsed_json", "created_at"]
        self._exec(f"INSERT OR REPLACE INTO turns({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                   tuple(rec.get(c) for c in cols))
        self._mirror(rec.get("run_id"), "turns", {c: rec.get(c) for c in cols})

    # ------------------------------------------------------------ events (idempotent on resume)
    def record_event(self, run_id: str, trial_id: str, module: str, event_key: str, event_type: str,
                     payload: dict) -> None:
        existing = self._one("SELECT 1 AS x FROM events WHERE trial_id=? AND event_key=?", (trial_id, event_key))
        self._exec("INSERT OR REPLACE INTO events VALUES(?,?,?,?,?,?,?)",
                   (trial_id, event_key, run_id, module, event_type, json.dumps(payload, default=str), now_iso()))
        if not existing:
            self._mirror(run_id, "events", {"trial_id": trial_id, "event_key": event_key,
                                            "event_type": event_type, "payload": payload})

    def events(self, run_id: str, module: str | None = None, event_type: str | None = None) -> list[dict]:
        sql, params = "SELECT * FROM events WHERE run_id=?", [run_id]
        if module:
            sql += " AND module=?"
            params.append(module)
        if event_type:
            sql += " AND event_type=?"
            params.append(event_type)
        return self._all(sql + " ORDER BY trial_id, event_key", tuple(params))

    def turns_for_run(self, run_id: str, module: str | None = None) -> list[dict]:
        if module:
            return self._all("SELECT * FROM turns WHERE run_id=? AND module=? ORDER BY trial_id, step_key", (run_id, module))
        return self._all("SELECT * FROM turns WHERE run_id=? ORDER BY trial_id, step_key", (run_id,))

    # ------------------------------------------------------------ live marker (for the live monitor)
    def set_live(self, run_id: str | None, trial_id: str | None, step_key: str | None, agent: str | None,
                 role: str | None, model_id: str | None) -> None:
        self._exec("INSERT OR REPLACE INTO live VALUES(1,?,?,?,?,?,?,?)",
                   (run_id, trial_id, step_key, agent, role, model_id, now_iso() if step_key else None))

    # ------------------------------------------------------------ usage (daily request budget)
    def add_usage(self, provider: str, model_id: str, tokens: int) -> None:
        day = utc_day()
        self._exec("INSERT INTO usage VALUES(?,?,?,1,?) ON CONFLICT(day,provider,model_id) "
                   "DO UPDATE SET requests=requests+1, tokens=tokens+excluded.tokens",
                   (day, provider, model_id, int(tokens)))

    def requests_today(self, provider: str, model_id: str | None = None) -> int:
        if model_id:
            row = self._one("SELECT COALESCE(SUM(requests),0) AS n FROM usage WHERE day=? AND provider=? AND model_id=?",
                            (utc_day(), provider, model_id))
        else:
            row = self._one("SELECT COALESCE(SUM(requests),0) AS n FROM usage WHERE day=? AND provider=?",
                            (utc_day(), provider))
        return int(row["n"]) if row else 0

    def usage_today(self) -> list[dict]:
        return self._all("SELECT * FROM usage WHERE day=? ORDER BY provider, model_id", (utc_day(),))
