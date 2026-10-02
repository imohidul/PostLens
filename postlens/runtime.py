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


def _chromium_check() -> tuple[bool, str]:
    """Is Playwright's Chromium on disk? Returns (installed, error text).

    Runs in its own short-lived thread: Playwright's sync API refuses to start
    in a thread that is already running Playwright (e.g. when this is called
    from inside a `with sync_playwright()` block), and that refusal used to be
    misread as "not installed"."""
    result = {"ok": False, "err": ""}

    def check():
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                result["ok"] = Path(p.chromium.executable_path).exists()
                if not result["ok"]:
                    result["err"] = f"Chromium not found at {p.chromium.executable_path}"
        except Exception as e:  # noqa: BLE001
            result["err"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=check, name="browser-check", daemon=True)
    t.start()
    t.join(timeout=60)
    return result["ok"], result["err"]


def _chromium_installed() -> bool:
    return _chromium_check()[0]


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
        ok, err = (False, "") if r.returncode != 0 else _chromium_check()
        if not ok:
            if r.returncode != 0:
                msg = "Couldn't download the browser engine. Check your internet connection."
            else:
                msg = "The browser engine is installed but couldn't be started. See ~/.postlens/logs/browser-install.log"
            state.update(browser="error", message=msg)
            (LOG_DIR / "browser-install.log").write_text(
                f"exit code: {r.returncode}\ncheck error: {err}\n\n--- stdout ---\n{r.stdout or ''}\n--- stderr ---\n{r.stderr or ''}\n",
                encoding="utf-8")
            raise RuntimeError(state["message"])
        state.update(browser="ready", message="")
