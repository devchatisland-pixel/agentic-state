"""Configuration loading, presets, .env handling and stable hashing."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ (existing variables win)."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else ROOT / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    for model_id, m in cfg["models"].items():
        m.setdefault("enabled", True)
        m.setdefault("params", {})
        m.setdefault("json_mode", True)
        if m["provider"] not in cfg["providers"]:
            raise ValueError(f"model {model_id}: unknown provider {m['provider']}")
        if m["family"] not in cfg["families"]:
            raise ValueError(f"model {model_id}: family {m['family']} missing from 'families'")
    return cfg


def get_preset(cfg: dict, name: str) -> dict:
    if name not in cfg["presets"]:
        raise ValueError(f"unknown preset '{name}' (available: {', '.join(cfg['presets'])})")
    return cfg["presets"][name]


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def stable_hash(obj: Any, n: int = 16) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:n]


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()


def git_dirty() -> bool | None:
    """True if tracked files differ from the commit (results would not be reproducible from the commit alone)."""
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True,
                             text=True, timeout=5)
        return bool(out.stdout.strip()) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None
