"""Run manifest: everything needed to say exactly what produced a run's data (results/<run_id>/manifest.json).

Written when a run is created (code commit and dirty flag, preset snapshot, seeds, run type, pre-registration hash,
Python and package versions, OS, Ollama version and the digest of every local model used) and updated by each
analysis (the commit of the analysis code). Ollama digests identify the exact weights: a tag such as smollm2:1.7b can
point to different weights after a re-pull. Network lookups are skipped in mock mode and never fail a run.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import urllib.request
from importlib import metadata
from pathlib import Path

from arena.config import git_commit, git_dirty, stable_hash
from arena.storage import now_iso

PACKAGES = ("pandas", "matplotlib", "pydantic", "httpx", "pyyaml")


def _ollama(base_url: str, path: str, payload: dict | None = None) -> dict | None:
    root = base_url.rstrip("/").removesuffix("/v1")
    try:
        req = urllib.request.Request(root + path, data=json.dumps(payload).encode() if payload else None,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read().decode())
    except (OSError, ValueError):
        return None


def models_used(preset: dict, modules: list[str]) -> list[str]:
    out: list[str] = []
    a, b, c = preset.get("module_a") or {}, preset.get("module_b") or {}, preset.get("module_c") or {}
    if "A" in modules:
        out += list(a.get("target_models", [])) + list(a.get("confederate_models") or [a.get("confederate_model")])
    if "B" in modules:
        out += list(b.get("roster", []))
    if "C" in modules:
        out += list(c.get("roster", [])) + list(c.get("reserves", [])) + list(c.get("dissident_models", []))
    return [m for m in dict.fromkeys(out) if m]


def build(run: dict, cfg: dict, preset: dict, mock: bool) -> dict:
    modules = (run.get("modules") or "").split(",")
    pk = {}
    for name in PACKAGES:
        try:
            pk[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pk[name] = None
    models = {}
    ollama_version = None
    for mid in models_used(preset, modules):
        m = cfg["models"].get(mid, {})
        prov = cfg["providers"].get(m.get("provider"), {})
        entry = {"provider": m.get("provider"), "model": m.get("model"), "family": m.get("family"),
                 "max_tokens": m.get("max_tokens"), "params": m.get("params")}
        if prov.get("base_url", "").startswith("http://localhost") and not mock:
            if ollama_version is None:
                ollama_version = (_ollama(prov["base_url"], "/api/version") or {}).get("version")
            tags = _ollama(prov["base_url"], "/api/tags") or {}
            hit = next((x for x in tags.get("models", []) if x.get("name") == m.get("model")), None)
            if hit:
                entry.update(digest=hit.get("digest"), size=hit.get("size"),
                             quantization=(hit.get("details") or {}).get("quantization_level"),
                             parameter_size=(hit.get("details") or {}).get("parameter_size"))
        models[mid] = entry
    return {"run_id": run["run_id"], "created_at": run.get("created_at"), "run_type": run.get("run_type"),
            "prereg_hash": run.get("prereg_hash"), "preset": run.get("preset"), "modules": modules,
            "mock": bool(mock), "run_seed": run.get("run_seed"), "config_seed": cfg.get("seed"),
            "config_hash": run.get("config_hash"), "preset_snapshot": preset,
            "code": {"commit": run.get("git_commit"), "dirty": git_dirty()},
            "python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine(),
            "packages": pk, "ollama": {"version": ollama_version,
                                       "OLLAMA_CONTEXT_LENGTH": os.environ.get("OLLAMA_CONTEXT_LENGTH")},
            "models": models, "analyses": []}


def write(path: Path, manifest: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def record_analysis(path: Path, run: dict) -> None:
    """Append the analysis code version to an existing manifest (or start a minimal one for old runs)."""
    try:
        man = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "run_id": run["run_id"], "note": "manifest created at analysis time (run predates manifests)",
            "code": {"commit": run.get("git_commit"), "dirty": None}, "analyses": []}
    except ValueError:
        return
    man.setdefault("analyses", []).append({"at": now_iso(), "commit": git_commit(), "dirty": git_dirty(),
                                           "python": sys.version.split()[0]})
    man["analyses"] = man["analyses"][-20:]
    write(path, man)


def prereg_hash(path: str | Path) -> str:
    return stable_hash(Path(path).read_text(encoding="utf-8"), 64)
