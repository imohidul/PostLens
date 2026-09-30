"""Paths and user settings.

Everything PostLens stores lives in one folder in the user's home directory
(~/.postlens) so the project folder itself never contains personal data and
can be safely pushed to GitHub.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("POSTLENS_HOME", Path.home() / ".postlens"))
DB_PATH = DATA_DIR / "postlens.db"
BROWSER_PROFILE_DIR = DATA_DIR / "browser-profile"
SETTINGS_PATH = DATA_DIR / "settings.json"
LOG_DIR = DATA_DIR / "logs"

DEFAULT_SETTINGS: dict[str, Any] = {
    "ai": {
        # "openai" | "anthropic" | "gemini" | "groq" | "ollama"; "" until the user picks one
        "provider": "",
        # chosen model per provider; "" = pick a sensible default automatically
        "models": {"openai": "", "anthropic": "", "gemini": "", "groq": "", "ollama": ""},
        "ollama_url": "http://127.0.0.1:11434",
        "temperature": 0.3,
        # Rough character budget for the data we paste into the prompt.
        # Small local models have small context windows, so keep this modest.
        "context_chars": 24000,
    },
    "scraper": {
        "headless": False,  # a visible window is less likely to be flagged
        "scroll_pause_ms": 1800,  # wait between scrolls - be gentle
        "max_posts": 60,
        "max_comments_per_post": 150,
        "default_range_days": 30,
    },
    "web": {
        "max_pages": 30,
        "respect_robots": True,
        "render": "auto",  # use a real browser only for JavaScript sites
        "delay_s": 0.5,
    },
    "ui": {"theme": "system", "accent": "violet"},
}

_lock = threading.Lock()


def ensure_dirs() -> None:
    for d in (DATA_DIR, BROWSER_PROFILE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


_LEGACY_AI_KEYS = ("ollama_model", "groq_model", "groq_api_key", "clear_groq_api_key", "groq_api_key_set", "groq_api_key_hint")


def _migrate(saved: dict[str, Any]) -> dict[str, Any]:
    """Settings from v0.1 kept the Groq key in this file. Move it into the
    OS vault and drop every legacy field so no key stays on disk here."""
    ai = saved.get("ai") or {}
    if not any(k in ai for k in _LEGACY_AI_KEYS):
        return saved
    from . import keystore  # local import: keystore imports config

    if ai.get("groq_api_key"):
        keystore.put("groq", ai["groq_api_key"])
    models = ai.setdefault("models", {})
    if ai.get("ollama_model"):
        models.setdefault("ollama", ai["ollama_model"])
    if ai.get("groq_model"):
        models.setdefault("groq", ai["groq_model"])
    for k in _LEGACY_AI_KEYS:
        ai.pop(k, None)
    SETTINGS_PATH.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    return saved


def load_settings() -> dict[str, Any]:
    ensure_dirs()
    with _lock:
        if SETTINGS_PATH.exists():
            try:
                saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                saved = _migrate(saved)
                return _merge(DEFAULT_SETTINGS, saved)
            except (json.JSONDecodeError, OSError):
                pass
        return json.loads(json.dumps(DEFAULT_SETTINGS))


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    # Keys are stored only in the OS vault (keystore.py), never in this file.
    for k in list((patch.get("ai") or {}).keys()):
        if "key" in k.lower():
            patch["ai"].pop(k)
    current = load_settings()
    merged = _merge(current, patch)
    with _lock:
        SETTINGS_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged


def public_settings(s: dict[str, Any]) -> dict[str, Any]:
    """Settings safe to send to the browser. Keys never live in settings,
    but strip anything key-like defensively."""
    out = json.loads(json.dumps(s))
    for k in list(out.get("ai", {}).keys()):
        if "key" in k.lower():
            out["ai"].pop(k)
    return out
