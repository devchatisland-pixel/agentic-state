"""Turn engine shared by all modules: one validated dual-channel agent turn, with repair and replay.

TrialContext.turn():
  1. if this turn was already completed (resume), return the stored result;
  2. otherwise call the model, reusing any recorded raw reply for this exact attempt;
  3. extract and validate the JSON; on failure, append a repair prompt and retry (max 2);
  4. store the final status: ok | invalid | blocked (never pooled with refusals).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Type

from pydantic import BaseModel

from arena.config import text_hash
from arena.llm_client import LLMClient, ProviderBlocked
from arena.schemas import extract_json, short_error, split_think
from arena.storage import Storage

REPAIR_PROMPT = ("Your previous reply could not be used: {error}\n"
                 "Reply again with ONLY one valid JSON object in the requested format. No other text.")


@dataclass
class Seat:
    label: str           # e.g. "Agent_3"
    model_id: str        # key in config.yaml models
    role: str            # target / confederate / strategist / supervisor / executor / standard / dissident
    family: str = ""
    shown_as: str = ""   # how other agents see this seat (identity framing)


@dataclass
class TurnOutcome:
    status: str                      # ok | invalid | blocked
    data: dict | None
    attempts: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def call_seed(trial_seed: int, step_key: str) -> int:
    return int(hashlib.sha256(f"{trial_seed}|{step_key}".encode()).hexdigest()[:8], 16)


@dataclass
class TrialContext:
    client: LLMClient
    storage: Storage
    run_id: str
    trial_id: str
    module: str
    trial_seed: int
    mock: bool = False
    calls_made: int = field(default=0)

    def event(self, key: str, event_type: str, payload: dict) -> None:
        self.storage.record_event(self.run_id, self.trial_id, self.module, key, event_type, payload)

    def _finish(self, step_key: str, seat: Seat, status: str, data: dict | None, attempts: int,
                error: str | None) -> TurnOutcome:
        self.storage.record_turn(trial_id=self.trial_id, step_key=step_key, run_id=self.run_id,
                                 module=self.module, agent=seat.label, role=seat.role, model_id=seat.model_id,
                                 status=status, attempts=attempts, error=error,
                                 parsed_json=json.dumps(data, ensure_ascii=False) if data is not None else None)
        return TurnOutcome(status, data, attempts, error)

    def turn(self, step_key: str, seat: Seat, messages: list[dict], schema: Type[BaseModel], *,
             temperature: float, meta: dict, validate: Callable[[Any], None] | None = None,
             max_repairs: int = 2, max_tokens: int | None = None) -> TurnOutcome:
        stored = self.storage.get_turn(self.trial_id, step_key)
        if stored:
            data = json.loads(stored["parsed_json"]) if stored["parsed_json"] else None
            return TurnOutcome(stored["status"], data, stored["attempts"], stored["error"])
        msgs = [dict(m) for m in messages]
        seed = call_seed(self.trial_seed, step_key)
        last_error = None
        for attempt in range(max_repairs + 1):
            row = self.storage.get_call(self.trial_id, step_key, attempt)
            if row is not None and row["error_type"] is None:
                text = row["response_text"] or ""
            elif row is not None and row["error_type"] == "blocked":
                return self._finish(step_key, seat, "blocked", None, attempt + 1, row["error"])
            else:
                m = dict(meta, step=step_key, attempt=attempt, model_id=seat.model_id, label=seat.label, role=seat.role)
                base = dict(run_id=self.run_id, trial_id=self.trial_id, step_key=step_key, attempt=attempt,
                            agent=seat.label, role=seat.role, model_id=seat.model_id, temperature=temperature,
                            seed=seed, prompt_hash=text_hash(json.dumps(msgs, ensure_ascii=False)),
                            messages_json=json.dumps(msgs, ensure_ascii=False), mock=int(self.mock))
                try:
                    res = self.client.chat(seat.model_id, msgs, temperature=temperature, seed=seed,
                                           max_tokens=max_tokens, meta=m)
                except ProviderBlocked as e:
                    self.storage.record_call(**base, provider=self.client.model(seat.model_id)["provider"],
                                             error_type="blocked", error=str(e)[:500])
                    return self._finish(step_key, seat, "blocked", None, attempt + 1, str(e)[:300])
                self.calls_made += 1
                text, think = split_think(res.text)
                reasoning = res.reasoning or think
                self.storage.record_call(**base, provider=res.provider, model_name=res.model_name,
                                         response_hash=text_hash(res.text), response_text=res.text,
                                         reasoning=reasoning, tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                                         latency_s=round(res.latency_s, 3))
                text = res.text
            try:
                obj = schema.model_validate(extract_json(text))
                if validate is not None:
                    validate(obj)
                return self._finish(step_key, seat, "ok", obj.model_dump(), attempt + 1, None)
            except ValueError as e:  # pydantic.ValidationError is a ValueError
                last_error = short_error(e)
                msgs = msgs + [{"role": "assistant", "content": text or "(empty reply)"},
                               {"role": "user", "content": REPAIR_PROMPT.format(error=last_error)}]
        return self._finish(step_key, seat, "invalid", None, max_repairs + 1, last_error)


def json_instructions(example: dict) -> str:
    return ("Reply with ONE JSON object only, exactly in this shape (no text before or after):\n"
            + json.dumps(example, indent=1, ensure_ascii=False))
