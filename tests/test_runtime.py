"""The browser-engine check must work even when called from code that is
already running Playwright (connecting Facebook, checking the login).
Regression test for 1.0.0's false "Couldn't download the browser engine"."""
import asyncio

from postlens import runtime


def test_browser_check_works_inside_a_running_event_loop():
    # Playwright's sync API refuses to start in a thread with a running
    # asyncio loop - exactly the situation inside `with sync_playwright()`.
    async def inside_loop():
        return runtime._chromium_check()

    ok, err = asyncio.run(inside_loop())
    assert "asyncio loop" not in err, err
