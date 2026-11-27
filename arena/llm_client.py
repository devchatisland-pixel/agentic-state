"""Unified free-tier LLM client.

Providers: OpenAI-compatible endpoints (Groq, Mistral, OpenRouter, local Ollama) and Google AI
Studio (Gemini native API).

Quota safety:
- per-provider (or per-model) sliding windows for requests/minute and tokens/minute;
- a requests/day budget persisted in SQLite (survives restarts);
- exponential backoff with jitter on 429 / 5xx / network errors, honouring Retry-After;
- a daily-quota 429 raises QuotaExhausted so the run stops cleanly and can resume tomorrow.

Outcome hygiene: a provider safety block raises ProviderBlocked. It is recorded as its own
outcome and never counted as a model refusal.

--mock: deterministic simulated replies (arena.mock), zero network calls.
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import httpx

from arena.mock import MockResponder


class LLMError(Exception):
    """Non-retryable provider error (bad request, unknown model, missing key...)."""


class QuotaExhausted(LLMError):
    """Daily quota reached: stop the run and resume later."""


class ProviderUnavailable(LLMError):
    """Retries exhausted on transient errors (overload, network)."""


class ProviderBlocked(LLMError):
    """The provider's own safety filter blocked the request or the response."""


@dataclass
class ChatResult:
    text: str
    reasoning: str | None
    model_id: str
    provider: str
    model_name: str
    tokens_in: int
    tokens_out: int
    latency_s: float
    finish_reason: str | None
    mock: bool = False


class UsageStore(Protocol):
    def requests_today(self, provider: str, model_id: str | None = None) -> int: ...
    def add_usage(self, provider: str, model_id: str, tokens: int) -> None: ...


def estimate_tokens(messages: list[dict]) -> int:
    return sum(len(m.get("content") or "") for m in messages) // 4 + 8 * len(messages) + 16


DAILY_RE = re.compile(r"per[\s_-]?day|\bRPD\b|\bTPD\b|PerDay|daily", re.I)
SAFETY_RE = re.compile(r"safety|content[\s_-]?filter|content_policy|moderation|blocked", re.I)
RETRYABLE = {408, 409, 425, 500, 502, 503, 504, 529}


class RateLimiter:
    """Sliding 60-second windows for requests and tokens. Blocks (sleeps) until a call fits."""

    def __init__(self, name: str, rpm: int, tpm: int, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.name = name
        self.rpm = max(1, int(rpm))
        self.tpm = max(1, int(tpm))
        self.clock = clock
        self.sleep = sleep
        self.requests: deque[float] = deque()
        self.tokens: deque[list] = deque()  # [timestamp, tokens]
        self.lock = threading.Lock()

    def _prune(self, now: float) -> None:
        while self.requests and now - self.requests[0] >= 60:
            self.requests.popleft()
        while self.tokens and now - self.tokens[0][0] >= 60:
            self.tokens.popleft()

    def wait_time(self, est_tokens: int, now: float) -> float:
        self._prune(now)
        wait = 0.0
        if len(self.requests) >= self.rpm:
            wait = max(wait, 60 - (now - self.requests[0]))
        used = sum(t for _, t in self.tokens)
        if self.tokens and used + est_tokens > self.tpm:
            need, freed = used + est_tokens - self.tpm, 0
            for ts, t in self.tokens:
                freed += t
                if freed >= need:
                    wait = max(wait, 60 - (now - ts))
                    break
        return wait

    def acquire(self, est_tokens: int) -> list:
        with self.lock:
            while True:
                w = self.wait_time(est_tokens, self.clock())
                if w <= 0:
                    break
                self.sleep(min(w + 0.05, 61.0))
            now = self.clock()
            self.requests.append(now)
            entry = [now, int(est_tokens)]
            self.tokens.append(entry)
            return entry

    def settle(self, entry: list, actual_tokens: int) -> None:
        with self.lock:
            entry[1] = max(int(actual_tokens), 0)


class OpenAICompatAdapter:
    def __init__(self, base_url: str, api_key: str | None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def request(self, model_name: str, messages: list[dict], temperature: float, seed: int | None,
                max_tokens: int, json_mode: bool, params: dict,
                json_schema: dict | None = None) -> tuple[str, dict, dict]:
        payload: dict[str, Any] = {"model": model_name, "messages": messages,
                                   "temperature": temperature, "max_tokens": max_tokens}
        if seed is not None:
            payload["seed"] = seed
        if json_schema is not None:  # grammar-constrained decoding (Ollama): keys, types and enums are enforced
            payload["response_format"] = {"type": "json_schema",
                                          "json_schema": {"name": "turn", "strict": True, "schema": json_schema}}
        elif json_mode:
            payload["response_format"] = {"type": "json_object"}
        payload.update(params or {})
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return f"{self.base_url}/chat/completions", headers, payload

    @staticmethod
    def parse(data: dict) -> tuple[str, str | None, int, int, str | None]:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"no choices in response: {str(data)[:300]}")
        choice = choices[0]
        msg = choice.get("message") or {}
        finish = choice.get("finish_reason")
        if finish == "content_filter":
            raise ProviderBlocked("finish_reason=content_filter")
        usage = data.get("usage") or {}
        reasoning = msg.get("reasoning") or msg.get("reasoning_content")
        return (msg.get("content") or "", reasoning, int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0), finish)


class OllamaNativeAdapter:
    """Ollama's native /api/chat, used when the provider sets `kind: ollama_native` (Bench L presets since v4).

    The OpenAI-compatible endpoint ignores per-request load options: on 27 Nov 2026 (`scripts/ollama_fit.py`) the
    server loaded every model with an 8192-token context and put only 55-67% of llama3.2, phi4-mini and qwen3-4b on
    the 4 GB GPU (4-18 s per call). The native endpoint takes `options` (num_ctx, num_batch, num_gpu): with a 2048
    context, batch 128 and every layer on the GPU, all five bench models fit and answer in 0.5-1.7 s. The request is
    otherwise the same: same messages, grammar-constrained `format` (the JSON schema), temperature, seed, token cap;
    `reasoning_effort: none` becomes `think: false`."""

    def __init__(self, base_url: str, api_key: str | None, options: dict | None = None):
        self.base_url = base_url.rstrip("/").removesuffix("/v1")
        self.options = dict(options or {})

    def request(self, model_name: str, messages: list[dict], temperature: float, seed: int | None,
                max_tokens: int, json_mode: bool, params: dict,
                json_schema: dict | None = None) -> tuple[str, dict, dict]:
        opts = dict(self.options, temperature=temperature, num_predict=max_tokens)
        if seed is not None:
            opts["seed"] = seed
        payload: dict[str, Any] = {"model": model_name, "messages": messages, "stream": False, "options": opts}
        if json_schema is not None:
            payload["format"] = json_schema
        elif json_mode:
            payload["format"] = "json"
        params = dict(params or {})
        if params.pop("reasoning_effort", None) == "none":
            payload["think"] = False
        payload.update(params)
        return f"{self.base_url}/api/chat", {"Content-Type": "application/json"}, payload

    @staticmethod
    def parse(data: dict) -> tuple[str, str | None, int, int, str | None]:
        if "message" not in data:
            raise LLMError(f"no message in response: {str(data)[:300]}")
        msg = data.get("message") or {}
        finish = data.get("done_reason")
        return (msg.get("content") or "", msg.get("thinking") or None, int(data.get("prompt_eval_count") or 0),
                int(data.get("eval_count") or 0), "length" if finish == "length" else "stop" if finish else finish)


class GeminiAdapter:
    def __init__(self, base_url: str, api_key: str | None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def request(self, model_name: str, messages: list[dict], temperature: float, seed: int | None,
                max_tokens: int, json_mode: bool, params: dict,
                json_schema: dict | None = None) -> tuple[str, dict, dict]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [{"role": "model" if m["role"] == "assistant" else "user",
                     "parts": [{"text": m["content"]}]} for m in messages if m["role"] != "system"]
        gen: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if seed is not None:
            gen["seed"] = seed
        if json_mode:
            gen["responseMimeType"] = "application/json"
        gen.update((params or {}).get("generationConfig", {}))
        payload: dict[str, Any] = {"contents": contents, "generationConfig": gen}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key or ""}
        return f"{self.base_url}/models/{model_name}:generateContent", headers, payload

    @staticmethod
    def parse(data: dict) -> tuple[str, str | None, int, int, str | None]:
        feedback = data.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise ProviderBlocked(f"promptFeedback.blockReason={feedback['blockReason']}")
        cands = data.get("candidates") or []
        if not cands:
            raise ProviderBlocked("no candidates returned")
        cand = cands[0]
        finish = cand.get("finishReason")
        if finish in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"}:
            raise ProviderBlocked(f"finishReason={finish}")
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        reasoning = "".join(p.get("text", "") for p in parts if p.get("thought")) or None
        usage = data.get("usageMetadata") or {}
        tout = int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0)
        return text, reasoning, int(usage.get("promptTokenCount") or 0), tout, finish


class LLMClient:
    def __init__(self, cfg: dict, usage: UsageStore | None = None, mock: bool = False,
                 sleep: Callable[[float], None] = time.sleep, timeout: float = 180.0, mock_delay: float = 0.0):
        self.cfg = cfg
        self.usage = usage
        self.mock = mock
        self.mock_delay = mock_delay
        self.sleep = sleep
        self.limiters: dict[str, RateLimiter] = {}
        self.mocker = MockResponder()
        self.timeout = timeout
        self.http = None if mock else httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self.http is not None:
            self.http.close()

    def model(self, model_id: str) -> dict:
        try:
            return self.cfg["models"][model_id]
        except KeyError as e:
            raise LLMError(f"unknown model id '{model_id}' (not in config.yaml)") from e

    def family(self, model_id: str) -> str:
        return self.model(model_id)["family"]

    def _limiter(self, provider: str, model_id: str) -> RateLimiter:
        p = self.cfg["providers"][provider]
        key = f"{provider}:{model_id}" if p.get("limit_scope", "model") == "model" else provider
        if key not in self.limiters:
            self.limiters[key] = RateLimiter(key, p["rpm"], p["tpm"], sleep=self.sleep)
        return self.limiters[key]

    def chat(self, model_id: str, messages: list[dict], *, temperature: float, seed: int | None = None,
             max_tokens: int | None = None, json_mode: bool = True, meta: dict | None = None,
             json_schema: dict | None = None) -> ChatResult:
        m = self.model(model_id)
        pname = m["provider"]
        if self.mock:
            t0 = time.perf_counter()
            text = self.mocker.respond(meta or {}, messages, seed)
            if self.mock_delay:
                time.sleep(self.mock_delay)
            return ChatResult(text, None, model_id, pname, m["model"], estimate_tokens(messages),
                              len(text) // 4, time.perf_counter() - t0, "stop", mock=True)
        if not m.get("enabled", True):
            raise LLMError(f"model {model_id} is disabled in config.yaml")
        p = self.cfg["providers"][pname]
        key = None
        if p.get("api_key_env"):
            key = os.environ.get(p["api_key_env"])
            if not key:
                raise LLMError(f"{p['api_key_env']} is not set in .env (needed for {model_id})")
        if self.usage is not None:
            scope_model = model_id if p.get("limit_scope", "model") == "model" else None
            used = self.usage.requests_today(pname, scope_model)
            if used >= int(p["rpd"]):
                raise QuotaExhausted(f"{pname}/{model_id}: daily budget of {p['rpd']} requests used")
        if p["kind"] == "ollama_native":
            # a model may override the provider's load options (e.g. an 8B model cannot put every layer on a
            # 4 GB GPU: `options: {num_gpu: null}` leaves the placement to Ollama); null removes an option
            opts = {k: v for k, v in {**(p.get("options") or {}), **(m.get("options") or {})}.items() if v is not None}
            adapter = OllamaNativeAdapter(p["base_url"], key, opts)
        else:
            adapter = (GeminiAdapter if p["kind"] == "gemini" else OpenAICompatAdapter)(p["base_url"], key)
        max_tokens = int(max_tokens or m.get("max_tokens", 900))
        if m.get("system_suffix"):  # e.g. " /no_think" for Qwen3: appended to the system prompt, never logged as content
            messages = [dict(x) for x in messages]
            for x in messages:
                if x["role"] == "system":
                    x["content"] = x["content"] + m["system_suffix"]
                    break
        use_schema = json_schema if (json_schema is not None and p.get("structured", False)
                                     and m.get("structured", True)) else None
        url, headers, payload = adapter.request(m["model"], messages, temperature, seed, max_tokens,
                                                json_mode and m.get("json_mode", True), m.get("params", {}),
                                                json_schema=use_schema)
        limiter = self._limiter(pname, model_id)
        est = estimate_tokens(messages) + max_tokens // 3
        attempt, max_retries = 0, int(p.get("max_retries", 6))
        while True:
            entry = limiter.acquire(est)
            t0 = time.perf_counter()
            retry_after = None
            try:
                resp = self.http.post(url, headers=headers, json=payload, timeout=p.get("timeout_s", self.timeout))
            except (httpx.TimeoutException, httpx.TransportError) as e:
                err = f"network error: {e!r}"
            else:
                if resp.status_code == 200:
                    text, reasoning, tin, tout, finish = adapter.parse(resp.json())
                    limiter.settle(entry, tin + tout)
                    if self.usage is not None:
                        self.usage.add_usage(pname, model_id, tin + tout)
                    return ChatResult(text, reasoning, model_id, pname, m["model"], tin, tout,
                                      time.perf_counter() - t0, finish)
                body = resp.text[:1000]
                status = resp.status_code
                if self.usage is not None:
                    self.usage.add_usage(pname, model_id, 0)
                if status == 429 and DAILY_RE.search(body):
                    raise QuotaExhausted(f"{pname}/{model_id}: daily quota reached ({body[:200]})")
                if status in (400, 403) and SAFETY_RE.search(body):
                    raise ProviderBlocked(f"HTTP {status}: {body[:300]}")
                if status != 429 and status not in RETRYABLE:
                    raise LLMError(f"{pname}/{model_id} HTTP {status}: {body[:500]}")
                err = f"HTTP {status}: {body[:300]}"
                ra = resp.headers.get("retry-after")
                if ra:
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        retry_after = None
            attempt += 1
            if attempt > max_retries:
                raise ProviderUnavailable(f"{pname}/{model_id}: gave up after {max_retries} retries ({err})")
            delay = retry_after if retry_after is not None else min(90.0, 2.0 ** attempt) * (0.5 + random.random() / 2)
            self.sleep(delay)

    async def achat(self, model_id: str, messages: list[dict], **kwargs: Any) -> ChatResult:
        """Async wrapper (runs the blocking call in a worker thread)."""
        return await asyncio.to_thread(self.chat, model_id, messages, **kwargs)
