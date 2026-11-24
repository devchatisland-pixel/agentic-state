"""Turn engine shared by all modules: one validated dual-channel agent turn, with repair and replay.

TrialContext.turn():
  1. if this turn was already completed (resume), return the stored result;
  2. otherwise call the model, reusing any recorded raw reply for this exact attempt;
  3. extract and validate the JSON; on failure, append a repair prompt and retry (max 2);
  4. store the final status: ok | invalid | blocked (never pooled with refusals).

Resume safety: a stored turn is only replayed if the prompt that produced it has the same hash as the prompt the
current code builds; otherwise the code changed since the run started and replaying would silently mix two
protocols, so PromptMismatch is raised (override with --force-resume).
Copy safety: a free-text field that reproduces the format example ("<your own reasoning...>", or any example
sentence) is rejected and sent to repair, like invalid JSON.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Type

from pydantic import BaseModel

from arena.config import text_hash
from arena.llm_client import LLMClient, ProviderBlocked
from arena.schemas import constrained_schema, extract_json, normalize, short_error, split_think
from arena.storage import Storage

class PromptMismatch(RuntimeError):
    """The stored reply was produced by a different prompt than the one the current code builds."""


REPAIR_PROMPT = ("Your previous reply could not be used: {error}\n"
                 "Reply again with ONLY one valid JSON object. Use exactly the key names of the example, fill every "
                 "field with a real value (never copy the placeholder text), and keep text fields short. No other text.")


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
    repairs: int = 0                 # mechanical repairs applied by the code (renamed keys, "True (...)" -> true...)

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
    force_resume: bool = False

    def event(self, key: str, event_type: str, payload: dict) -> None:
        self.storage.record_event(self.run_id, self.trial_id, self.module, key, event_type, payload)

    def _finish(self, step_key: str, seat: Seat, status: str, data: dict | None, attempts: int,
                error: str | None, repairs: int = 0) -> TurnOutcome:
        self.storage.record_turn(trial_id=self.trial_id, step_key=step_key, run_id=self.run_id,
                                 module=self.module, agent=seat.label, role=seat.role, model_id=seat.model_id,
                                 status=status, attempts=attempts, error=error, repairs=repairs,
                                 parsed_json=json.dumps(data, ensure_ascii=False) if data is not None else None)
        return TurnOutcome(status, data, attempts, error, repairs)

    def scripted_turn(self, step_key: str, seat: Seat, data: dict) -> TurnOutcome:
        """Record a turn whose content is fixed by the protocol (a scripted confederate): no model call, attempts = 0.
        On resume the stored record is returned unchanged."""
        stored = self.storage.get_turn(self.trial_id, step_key)
        if stored:
            return TurnOutcome(stored["status"], json.loads(stored["parsed_json"]) if stored["parsed_json"] else None,
                               stored["attempts"], stored["error"], int(stored.get("repairs") or 0))
        return self._finish(step_key, seat, "ok", data, 0, None)

    def turn(self, step_key: str, seat: Seat, messages: list[dict], schema: Type[BaseModel], *,
             temperature: float, meta: dict, validate: Callable[[Any], None] | None = None,
             max_repairs: int = 2, max_tokens: int | None = None) -> TurnOutcome:
        stored = self.storage.get_turn(self.trial_id, step_key)
        first = self.storage.get_call(self.trial_id, step_key, 0)
        if first is not None and not self.force_resume:
            now_hash = text_hash(json.dumps([dict(m) for m in messages], ensure_ascii=False))
            if first.get("prompt_hash") and first["prompt_hash"] != now_hash:
                raise PromptMismatch(f"{self.trial_id} {step_key}: the stored reply came from a different prompt; the "
                                     "code changed since this run started. Start a new run, or resume with "
                                     "--force-resume to accept mixing the two versions.")
        if stored:
            data = json.loads(stored["parsed_json"]) if stored["parsed_json"] else None
            return TurnOutcome(stored["status"], data, stored["attempts"], stored["error"],
                               int(stored.get("repairs") or 0))
        msgs = [dict(m) for m in messages]
        examples = example_texts(msgs)
        base_seed = call_seed(self.trial_seed, step_key)
        json_schema = constrained_schema(schema)
        last_error = None
        for attempt in range(max_repairs + 1):
            seed = base_seed + attempt  # a retry is a new draw: the same seed would just repeat the same bad reply
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
                self.storage.set_live(self.run_id, self.trial_id, step_key, seat.label, seat.role, seat.model_id)
                try:
                    res = self.client.chat(seat.model_id, msgs, temperature=temperature, seed=seed,
                                           max_tokens=max_tokens, meta=m, json_schema=json_schema)
                except ProviderBlocked as e:
                    self.storage.set_live(self.run_id, None, None, None, None, None)
                    self.storage.record_call(**base, provider=self.client.model(seat.model_id)["provider"],
                                             error_type="blocked", error=str(e)[:500])
                    return self._finish(step_key, seat, "blocked", None, attempt + 1, str(e)[:300])
                self.calls_made += 1
                self.storage.set_live(self.run_id, None, None, None, None, None)
                text, think = split_think(res.text)
                reasoning = res.reasoning or think
                self.storage.record_call(**base, provider=res.provider, model_name=res.model_name,
                                         response_hash=text_hash(res.text), response_text=res.text,
                                         reasoning=reasoning, tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                                         latency_s=round(res.latency_s, 3))
                text = res.text
            try:
                raw, repairs = normalize(extract_json(text), schema)
                obj = schema.model_validate(raw)
                check_not_copied(obj, examples)
                if validate is not None:
                    validate(obj)
                return self._finish(step_key, seat, "ok", obj.model_dump(), attempt + 1, None, len(repairs))
            except ValueError as e:  # pydantic.ValidationError is a ValueError
                last_error = short_error(e)
                msgs = msgs + [{"role": "assistant", "content": text or "(empty reply)"},
                               {"role": "user", "content": REPAIR_PROMPT.format(error=last_error)}]
        return self._finish(step_key, seat, "invalid", None, max_repairs + 1, last_error)


def example_letter(*parts: Any) -> str:
    """A deterministic A-D letter for format examples, varied per item so no letter is systematically suggested."""
    return "ABCD"[int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:4], 16) % 4]


def example_choice(options: list[str], *parts: Any) -> str:
    """Deterministic pseudo-random pick for a format example. When the options ARE the behaviours under study
    (obey / refuse...), a fixed example would nudge them; a per-trial pick averages that nudge out."""
    return options[int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:6], 16) % len(options)]


FORMAT_MARKER = "Format example"
PLACEHOLDER_RE = re.compile(r"^\s*<[^<>]{2,}>\s*$")
FREE_TEXT_FIELDS = ("private_scratchpad", "public_message")


def json_instructions(example: dict, allowed: dict[str, str] | None = None, message_words: int = 50) -> str:
    """Format block shown to the model.

    Since 24 Nov 2026 the example holds DESCRIPTIONS in angle brackets ("<your choice>", "<your own reasoning>"),
    never a real value for a measured field: a small model copied the example's value (44% of smollm2's Module A
    answers were the example letter, against 25% by chance) and its sentences ("my private reasoning, never shown
    to anyone"). Grammar-constrained providers (Ollama) still force the allowed values; a copied description is
    rejected by `check_not_copied` and sent to repair. `allowed` lists, field by field, what is acceptable.
    """
    text = ("Reply with ONE JSON object only (no text before or after), with exactly these keys. "
            f"{FORMAT_MARKER} (each <...> describes what goes there: replace it with your own content):\n"
            + json.dumps(example, indent=1, ensure_ascii=False))
    if allowed:
        text += "\nAllowed values:\n" + "\n".join(f"- {k}: {v}" for k, v in allowed.items())
    limits = ([f"private_scratchpad under 60 words"] if "private_scratchpad" in example else []) + \
             ([f"public_message under {message_words} words"] if "public_message" in example else [])
    if limits:
        text += "\nKeep " + " and ".join(limits) + "."
    return text


def example_texts(messages: list[dict]) -> list[str]:
    """Every description and sample sentence of the format example in a prompt."""
    from arena.validity import example_from_messages, example_strings
    ex = example_from_messages(messages)
    out = example_strings(ex)

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, str) and PLACEHOLDER_RE.match(v) and v not in out:
            out.append(v)
    walk(ex or {})
    return out


def check_not_copied(obj: BaseModel, examples: list[str]) -> None:
    """Reject a reply that left a <...> description in place, or whose free text reproduces the format example."""
    from arena.validity import is_template_copy

    def walk(v, path: str = "") -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path}{k}.")
        elif isinstance(v, str):
            key = path.rstrip(".")
            if PLACEHOLDER_RE.match(v) or v.strip().lower().startswith("<your"):
                raise ValueError(f"{key} still contains the description {v.strip()[:40]!r}: write your own content")
            if key.split(".")[-1] in FREE_TEXT_FIELDS and is_template_copy(v, examples):
                raise ValueError(f"{key} copies the format example: write your own words")
    walk(obj.model_dump())
