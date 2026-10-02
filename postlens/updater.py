"""Automatic updates for the installed desktop app.

How it works:
1. A background thread asks GitHub for the latest release (at startup, then
   every few hours). GitHub's API needs no account for public repositories.
2. If the release is newer than this version, the installer for this system
   (postlens.exe on Windows, postlens.dmg on Mac) is downloaded in the
   background and checked against the size and SHA-256 that GitHub publishes.
3. The UI shows "Update ready". The user can restart right away, or just keep
   working: the update is installed automatically when PostLens is closed.

Only the installed app (PyInstaller build) installs updates. Running from
source only reports that a new version exists.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .config import DATA_DIR, load_settings

log = logging.getLogger("postlens.updater")

REPO = "imohidul/PostLens"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
CHECK_EVERY_S = 6 * 3600
UPDATES_DIR = DATA_DIR / "updates"
FROZEN = bool(getattr(sys, "frozen", False))

_lock = threading.Lock()
_wake = threading.Event()
_started = False

state: dict[str, Any] = {
    "current": __version__,
    "latest": None,         # newest version on GitHub, e.g. "1.0.2"
    "available": False,     # latest > current
    "status": "idle",       # idle | checking | downloading | ready | installing | error
    "progress": 0.0,        # 0..1 while downloading
    "error": "",
    "checked_at": None,     # unix time of the last successful check
    "notes": "",            # release notes (markdown)
    "page_url": RELEASES_PAGE,
    "can_install": False,   # True when this copy can update itself
}
_asset: dict[str, Any] = {}  # url, size, sha256 of the installer for this system
_ready_path: Path | None = None


# ---------------------------------------------------------------- helpers

def parse_version(v: str) -> tuple[int, ...]:
    """'v1.0.2' -> (1, 0, 2). Non-numeric parts end the version."""
    out = []
    for part in v.strip().lstrip("vV").split("."):
        m = re.match(r"\d+", part)
        if not m:
            break
        out.append(int(m.group()))
    while len(out) > 1 and out[-1] == 0:  # 1.0 == 1.0.0
        out.pop()
    return tuple(out)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def asset_name() -> str | None:
    if sys.platform == "win32":
        return "postlens.exe"
    if sys.platform == "darwin":
        return "postlens.dmg"
    return None


def mac_app_path() -> Path | None:
    """…/PostLens.app when running as the Mac app bundle."""
    exe = Path(sys.executable).resolve()
    for p in exe.parents:
        if p.suffix == ".app":
            return p
    return None


def _can_install() -> bool:
    if not FROZEN or asset_name() is None:
        return False
    if sys.platform == "darwin":
        app = mac_app_path()
        # replacing the app needs write access to its folder (/Applications)
        return bool(app and os.access(app.parent, os.W_OK))
    return True


def auto_enabled() -> bool:
    try:
        return bool(load_settings().get("updates", {}).get("auto", True))
    except Exception:  # noqa: BLE001
        return True


def _get_json(url: str, timeout: float = 15) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"PostLens/{__version__}",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- check

def check(fetch: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Ask GitHub for the latest release and update `state`."""
    fetch = fetch or _get_json
    with _lock:
        if state["status"] in ("downloading", "installing"):
            return dict(state)
        state.update(status="checking", error="")
    try:
        rel = fetch(LATEST_URL)
        latest = str(rel.get("tag_name") or "").lstrip("vV")
        if not latest:
            raise ValueError("GitHub returned no release")
        asset = next((a for a in rel.get("assets") or [] if a.get("name") == asset_name()), None)
        digest = (asset or {}).get("digest") or ""
        _asset.clear()
        if asset:
            _asset.update(
                url=asset.get("browser_download_url"),
                size=int(asset.get("size") or 0),
                sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
                version=latest,
            )
        available = is_newer(latest, __version__)
        with _lock:
            state.update(
                latest=latest,
                available=available,
                notes=(rel.get("body") or "")[:4000],
                page_url=rel.get("html_url") or RELEASES_PAGE,
                checked_at=time.time(),
                can_install=available and bool(_asset.get("url")) and _can_install(),
                status="ready" if (available and _ready_path is not None and _ready_path.exists()
                                   and _ready_path.stem.endswith(f"-{latest}")) else "idle",
            )
    except Exception as e:  # noqa: BLE001 - offline, rate limited, …
        log.info("update check failed: %s", e)
        with _lock:
            state.update(status="error", error="Couldn't check for updates. Will try again later.")
    return dict(state)


# ---------------------------------------------------------------- download

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verified(path: Path) -> bool:
    if not path.exists():
        return False
    if _asset.get("size") and path.stat().st_size != _asset["size"]:
        return False
    if _asset.get("sha256") and _sha256(path) != _asset["sha256"]:
        return False
    return True


def download(opener: Callable[[str], Any] | None = None) -> bool:
    """Download the installer for the latest version. Returns True when a
    verified installer is ready to install."""
    global _ready_path
    if not (state["available"] and _asset.get("url")):
        return False
    name = asset_name() or "postlens"
    stem, suffix = os.path.splitext(name)
    target = UPDATES_DIR / f"{stem}-{_asset['version']}{suffix}"
    with _lock:
        if state["status"] in ("downloading", "installing"):
            return False
        if _verified(target):
            _ready_path = target
            state.update(status="ready", progress=1.0, error="")
            return True
        state.update(status="downloading", progress=0.0, error="")
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    try:
        opener = opener or (lambda u: urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": f"PostLens/{__version__}"}), timeout=60))
        with opener(_asset["url"]) as r, part.open("wb") as f:
            total = _asset.get("size") or int(r.headers.get("Content-Length") or 0)
            done = 0
            while chunk := r.read(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if total:
                    state["progress"] = min(done / total, 1.0)
        if not _verified(part):
            raise ValueError("The downloaded update didn't match the published checksum.")
        os.replace(part, target)
        # keep the folder tidy: only the newest installer is needed
        for old in UPDATES_DIR.iterdir():
            if old != target and old.is_file():
                try:
                    old.unlink()
                except OSError:
                    pass
        _ready_path = target
        with _lock:
            state.update(status="ready", progress=1.0)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("update download failed: %s", e)
        try:
            part.unlink()
        except OSError:
            pass
        with _lock:
            state.update(status="error", error=str(e) if isinstance(e, ValueError) else "Couldn't download the update. Will try again later.")
        return False


# ---------------------------------------------------------------- install

_MAC_SCRIPT = r"""#!/bin/bash
# Replace PostLens.app with the downloaded version once PostLens has quit.
PID="$1"; DMG="$2"; APP="$3"; RELAUNCH="$4"
while kill -0 "$PID" 2>/dev/null; do sleep 0.5; done
MNT="$(mktemp -d)"
hdiutil attach -nobrowse -quiet -mountpoint "$MNT" "$DMG" || exit 1
rm -rf "$APP.old"
if mv "$APP" "$APP.old" && ditto "$MNT/PostLens.app" "$APP"; then
  rm -rf "$APP.old"
else
  rm -rf "$APP"; mv "$APP.old" "$APP"
fi
hdiutil detach -quiet "$MNT"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
if [ "$RELAUNCH" = "1" ]; then open "$APP"; fi
"""


def start_installer(relaunch: bool) -> bool:
    """Launch the installer for the downloaded update in the background. It
    finishes after PostLens quits. The caller must then quit PostLens."""
    if not (FROZEN and _ready_path and _ready_path.exists() and _can_install()):
        return False
    with _lock:
        state.update(status="installing")
    try:
        if sys.platform == "win32":
            # /SILENT shows only a small progress window. /RELAUNCH=1 is read
            # by installer.iss to open PostLens again afterwards.
            args = [str(_ready_path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                    f"/RELAUNCH={1 if relaunch else 0}"]
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(args, creationflags=flags, close_fds=True)
        else:
            script = UPDATES_DIR / "install-update.sh"
            script.write_text(_MAC_SCRIPT, encoding="utf-8")
            script.chmod(0o755)
            subprocess.Popen(
                ["/bin/bash", str(script), str(os.getpid()), str(_ready_path), str(mac_app_path()), "1" if relaunch else "0"],
                start_new_session=True, close_fds=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("couldn't start the update installer: %s", e)
        with _lock:
            state.update(status="error", error="Couldn't start the update installer.")
        return False


def install_on_exit() -> None:
    """Called when the user closes PostLens: install a downloaded update
    quietly, without reopening the app."""
    if state["status"] == "ready" and auto_enabled():
        start_installer(relaunch=False)


# ---------------------------------------------------------------- background loop

def _loop() -> None:
    time.sleep(5)  # let the app finish starting
    while True:
        check()
        if state["available"] and state["can_install"] and auto_enabled():
            download()
        _wake.wait(CHECK_EVERY_S)
        _wake.clear()


def start_background() -> None:
    global _started
    if _started or os.environ.get("POSTLENS_NO_UPDATE_CHECK"):
        return
    _started = True
    threading.Thread(target=_loop, name="updater", daemon=True).start()


def check_now() -> None:
    """Wake the background loop (Settings → Check for updates)."""
    _wake.set()


def public_state() -> dict[str, Any]:
    s = dict(state)
    s["auto"] = auto_enabled()
    return s
