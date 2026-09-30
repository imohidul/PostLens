"""Things that differ when PostLens runs as an installed desktop app
(built with PyInstaller) instead of from source.

* Where Playwright keeps its browser: inside the user's data folder, so the
  one-time ~150 MB download survives app updates and needs no admin rights.
* Installing that browser on first use with the Playwright driver that is
  bundled inside the app (no Python or Node needed on the user's machine).
* Windowed apps have no console, so output goes to a log file instead.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from .config import DATA_DIR, LOG_DIR, ensure_dirs

FROZEN = bool(getattr(sys, "frozen", False))
BROWSERS_DIR = DATA_DIR / "browsers"

_install_lock = threading.Lock()
state = {"browser": "unknown", "message": ""}  # unknown | ready | installing | error


def configure() -> None:
    """Call once at startup, before Playwright is imported anywhere."""
    ensure_dirs()
    if FROZEN and "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        BROWSERS_DIR.mkdir(parents=True, exist_ok=True)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_DIR)
    if sys.stdout is None or sys.stderr is None:  # windowed app: no console
        log = open(LOG_DIR / "app.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def _chromium_installed() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def ensure_browser(on_status=None) -> None:
    """Make sure Playwright's Chromium is available, downloading it once if
    needed. Raises RuntimeError with a user-friendly message on failure."""
    if state["browser"] == "ready":
        return
    with _install_lock:
        if state["browser"] == "ready":
            return
        if _chromium_installed():
            state["browser"] = "ready"
            return
        state.update(browser="installing", message="Downloading the browser engine (one time, about 150 MB)…")
        if on_status:
            on_status(state["message"])
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        node, cli = compute_driver_executable()
        kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # no console flash
        r = subprocess.run([node, cli, "install", "chromium"], env=get_driver_env(),
                           capture_output=True, text=True, timeout=1800, **kw)
        if r.returncode != 0 or not _chromium_installed():
            state.update(browser="error", message="Couldn't download the browser engine. Check your internet connection.")
            (LOG_DIR / "browser-install.log").write_text((r.stdout or "") + "\n" + (r.stderr or ""), encoding="utf-8")
            raise RuntimeError(state["message"])
        state.update(browser="ready", message="")
