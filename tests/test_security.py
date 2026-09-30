"""Guards against leaking API keys - through the API, the settings file,
or by accidentally committing one to the repository."""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
KEY = "sk-ant-FAKE-0123456789abcdefghijklmnop"

# Shapes of real keys from the providers PostLens supports
KEY_PATTERNS = [
    re.compile(r"sk-(?:proj-|ant-)?[A-Za-z0-9_\-]{32,}"),   # OpenAI / Anthropic
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),                 # Google
    re.compile(r"gsk_[A-Za-z0-9]{40,}"),                   # Groq
]
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def test_repository_contains_no_api_keys():
    """Fails if anything that looks like a real key is in the project folder.
    Run `python -m pytest` before every `git push`."""
    hits = []
    for f in ROOT.rglob("*"):
        if not f.is_file() or SKIP_DIRS & set(f.parts) or f.suffix in {".png", ".woff2", ".jpg"}:
            continue
        if f.name == "test_security.py":
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in KEY_PATTERNS:
            for m in pat.finditer(text):
                if "FAKE" not in m.group(0):
                    hits.append(f"{f.relative_to(ROOT)}: {m.group(0)[:10]}…")
    assert not hits, "Possible API keys found:\n" + "\n".join(hits)


def test_gitignore_excludes_secret_files():
    gi = (ROOT / ".gitignore").read_text()
    for pattern in (".env", "secrets.json", ".postlens/", "*.db"):
        assert pattern in gi


@pytest.fixture()
def client(monkeypatch):
    from postlens import keystore, server
    from postlens.ai import providers
    from postlens.config import DATA_DIR
    store = {}
    monkeypatch.setattr(keystore, "get", lambda n: store.get(n, ""))
    monkeypatch.setattr(keystore, "put", lambda n, v: store.__setitem__(n, v))
    monkeypatch.setattr(keystore, "remove", lambda n: store.pop(n, None))
    monkeypatch.setattr(providers, "list_models", lambda p, k, u="": [{"id": "claude-sonnet-9", "label": "Sonnet"}])
    with TestClient(server.app) as c:
        yield c, store, DATA_DIR


def test_key_is_saved_but_never_returned(client):
    c, store, home = client
    r = c.put("/api/ai/providers/anthropic/key", json={"api_key": KEY})
    assert r.status_code == 200
    assert store["anthropic"] == KEY
    for path in ("/api/ai/providers", "/api/ai/providers/anthropic", "/api/settings", "/api/ai/status", "/api/status"):
        assert KEY not in c.get(path).text, path
        assert KEY[:20] not in c.get(path).text, path
    assert c.get("/api/ai/providers").json()["providers"][1]["key_ending"] == KEY[-4:]
    # nothing key-like ever lands in the settings file
    c.put("/api/settings", json={"ai": {"api_key": KEY, "openai_key": KEY}})
    settings_file = home / "settings.json"
    if settings_file.exists():
        assert KEY not in settings_file.read_text()


def test_validation_error_does_not_echo_key(client):
    c, _, _ = client
    long_key = "sk-" + "x" * 600
    r = c.put("/api/ai/providers/openai/key", json={"api_key": long_key})
    assert r.status_code == 422 and "xxxxxxxx" not in r.text


def test_legacy_settings_key_is_moved_out(monkeypatch):
    from postlens import config, keystore
    saved = {}
    monkeypatch.setattr(keystore, "put", lambda n, v: saved.__setitem__(n, v))
    backup = config.SETTINGS_PATH.read_text() if config.SETTINGS_PATH.exists() else None
    config.ensure_dirs()
    config.SETTINGS_PATH.write_text(json.dumps({"ai": {"groq_api_key": "gsk_legacy_" + "a" * 40, "groq_model": "m"}}))
    try:
        s = config.load_settings()
        assert saved["groq"].startswith("gsk_legacy_")
        assert "groq_api_key" not in config.SETTINGS_PATH.read_text()
        assert s["ai"]["models"]["groq"] == "m"
    finally:
        if backup is None:
            config.SETTINGS_PATH.unlink()
        else:
            config.SETTINGS_PATH.write_text(backup)
