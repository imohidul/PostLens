"""Start PostLens.

    python -m postlens            open in its own app window (falls back to your browser)
    python -m postlens --browser  open in your default web browser instead
    python -m postlens --server   run the server only (for development)

The installed desktop app runs this same code.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

DEFAULT_PORT = 8765


def _running_instance(port: int) -> bool:
    """Is PostLens already running on this port? (single instance)"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as r:
            return "version" in json.loads(r.read().decode())
    except Exception:
        return False


def _free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred


def _wait_until_up(port: int, timeout: float = 30) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if _running_instance(port):
            return True
        time.sleep(0.2)
    return False


def _start_server(port: int):
    import uvicorn

    from .server import app

    # 127.0.0.1 only: the app is never reachable from other computers.
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True, name="server")
    t.start()
    return server, t


def _open_window(url: str) -> bool:
    """Show the UI in a native window. Returns False if that's not possible
    here (e.g. no WebView2 runtime on an old Windows), so we can fall back."""
    try:
        import webview
    except ImportError:
        return False
    from . import __version__
    from .config import DATA_DIR

    try:
        webview.settings["ALLOW_DOWNLOADS"] = True                 # CSV / JSON exports
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # links to websites open in your browser
        webview.create_window(f"PostLens {__version__}", url, width=1360, height=880, min_size=(1100, 700))
        webview.start(private_mode=False, storage_path=str(DATA_DIR / "webview"))
        return True
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(prog="postlens", description="PostLens - analyze websites and Facebook pages with AI")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--browser", action="store_true", help="open in your web browser instead of an app window")
    mode.add_argument("--server", "--no-browser", dest="server", action="store_true", help="run the server only")
    args = ap.parse_args()

    from . import runtime
    runtime.configure()

    # Already running (e.g. the user clicked the icon twice)? Just show it.
    if _running_instance(args.port):
        url = f"http://127.0.0.1:{args.port}"
        if args.browser or not _open_window(url):
            webbrowser.open(url)
        return

    port = _free_port(args.port)
    url = f"http://127.0.0.1:{port}"
    server, thread = _start_server(port)
    if not _wait_until_up(port):
        print("PostLens could not start. See ~/.postlens/logs/app.log", file=sys.stderr)
        sys.exit(1)
    print(f"\n  PostLens is running at {url}\n  Press Ctrl+C to stop.\n")

    if args.server:
        pass
    elif not args.browser and _open_window(url):
        # Closing the app window quits PostLens.
        server.should_exit = True
        thread.join(timeout=5)
        return
    else:
        webbrowser.open(url)

    try:
        while thread.is_alive():
            thread.join(0.5)
    except KeyboardInterrupt:
        server.should_exit = True


if __name__ == "__main__":
    main()
