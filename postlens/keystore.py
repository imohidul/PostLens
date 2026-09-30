"""API key storage.

Keys go into the operating system's credential vault via the `keyring`
library: Windows Credential Manager, macOS Keychain, or the Secret Service
on Linux desktops. They are never written to the project folder, never
returned to the web page, and never included in exports or logs.

If no vault is available (e.g. a headless Linux server), we fall back to
~/.postlens/secrets.json with owner-only file permissions, and say so in
the UI.
"""
from __future__ import annotations

import json
import os
import threading

from .config import DATA_DIR, ensure_dirs

SERVICE = "PostLens"
_FALLBACK = DATA_DIR / "secrets.json"
_lock = threading.Lock()
_backend: str | None = None


def _keyring():
    try:
        import keyring
        from keyring.backends import fail

        kr = keyring.get_keyring()
        if isinstance(kr, fail.Keyring):
            return None
        if type(kr).__name__ == "ChainerBackend" and not getattr(kr, "backends", None):
            return None
        return keyring
    except Exception:
        return None


def backend() -> str:
    """'vault' or 'file' - shown in Settings so users know where keys live."""
    global _backend
    if _backend is None:
        kr = _keyring()
        if kr is None:
            _backend = "file"
        else:
            try:  # round-trip test; some backends import fine but fail at use
                kr.set_password(SERVICE, "__probe__", "1")
                kr.delete_password(SERVICE, "__probe__")
                _backend = "vault"
            except Exception:
                _backend = "file"
    return _backend


def _read_file() -> dict[str, str]:
    try:
        return json.loads(_FALLBACK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_file(data: dict[str, str]) -> None:
    ensure_dirs()
    tmp = _FALLBACK.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(_FALLBACK)


def get(name: str) -> str:
    with _lock:
        if backend() == "vault":
            try:
                return _keyring().get_password(SERVICE, name) or ""
            except Exception:
                return ""
        return _read_file().get(name, "")


def put(name: str, value: str) -> None:
    value = value.strip()
    with _lock:
        if backend() == "vault":
            _keyring().set_password(SERVICE, name, value)
            return
        data = _read_file()
        data[name] = value
        _write_file(data)


def remove(name: str) -> None:
    with _lock:
        if backend() == "vault":
            try:
                _keyring().delete_password(SERVICE, name)
            except Exception:
                pass
            return
        data = _read_file()
        if data.pop(name, None) is not None:
            _write_file(data)


def hint(value: str) -> str:
    """Last 4 characters only, for 'key ending ••••abcd'."""
    return value[-4:] if len(value) >= 12 else ""


def redact(text: str, *values: str) -> str:
    """Remove any secret (or a long piece of it) from a message before it
    reaches the UI or a log file."""
    for s in values:
        if s and len(s) >= 8:
            text = text.replace(s, "••••")
            text = text.replace(s[:12], "••••").replace(s[-12:], "••••")
    return text
