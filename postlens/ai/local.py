"""Local AI management: recommended-model catalog, hardware gate, model
downloads, and keeping the model warm for fast replies.

The catalog (postlens/data/models.json) says which free model to use for
each hardware tier. PostLens checks the copy published in the GitHub repo
once a day, so recommendations can be updated for every install by editing
that one file - no new release needed.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .. import hardware
from ..config import DATA_DIR

BUNDLED = Path(__file__).resolve().parent.parent / "data" / "models.json"
CACHED = DATA_DIR / "models.json"
# The copy in the GitHub repository; edit it there to update every install.
DEFAULT_CATALOG_URL = "https://raw.githubusercontent.com/imohidul/PostLens/main/postlens/data/models.json"
KEEP_ALIVE = "30m"  # keep the model in memory between questions (no reload delay)

_pull: dict[str, Any] = {"model": None, "status": "idle", "completed": 0, "total": 0, "error": None}
_pull_lock = threading.Lock()
_last_check = 0.0


# ------------------------------------------------------------------ catalog

def _valid(c: Any) -> bool:
    try:
        return c["schema"] == 1 and bool(c["tiers"]) and all("model" in t and "num_ctx" in t for t in c["tiers"])
    except (KeyError, TypeError):
        return False


def catalog() -> dict[str, Any]:
    bundled = json.loads(BUNDLED.read_text(encoding="utf-8"))
    try:
        cached = json.loads(CACHED.read_text(encoding="utf-8"))
        if _valid(cached) and cached["version"] > bundled["version"]:
            return cached
    except (OSError, json.JSONDecodeError):
        pass
    return bundled


def refresh_catalog(url: str = DEFAULT_CATALOG_URL, force: bool = False) -> bool:
    """Fetch newer recommendations. Returns True if a newer catalog was saved."""
    global _last_check
    if not force and time.time() - _last_check < 86400:
        return False
    _last_check = time.time()
    try:
        r = httpx.get(url, timeout=8)
        new = r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return False
    if _valid(new) and new["version"] > catalog()["version"]:
        CACHED.write_text(json.dumps(new, indent=2), encoding="utf-8")
        return True
    return False


def assessment() -> dict[str, Any]:
    return hardware.assess(hardware.detect(), catalog())


def supported() -> bool:
    return assessment()["supported"]


def allowed_models() -> list[dict[str, Any]]:
    """Catalog models this computer can run well (its tier and below)."""
    a = assessment()
    if not a["supported"]:
        return []
    tiers = catalog()["tiers"]
    top = [t["id"] for t in tiers].index(a["tier"]["id"])
    return tiers[: top + 1]


def num_ctx_for(model: str) -> int:
    for t in catalog()["tiers"]:
        if t["model"] == model:
            return int(t["num_ctx"])
    return 16384


def _same(a: str, b: str) -> bool:
    return a == b or a.removesuffix(":latest") == b.removesuffix(":latest")


def status(ollama_url: str, chosen: str) -> dict[str, Any]:
    """Everything the Settings page needs about Local AI."""
    a = assessment()
    info = hardware.detect()
    out: dict[str, Any] = {
        "supported": a["supported"], "reasons": a["reasons"], "tier": a["tier"],
        "hardware": {"ram_gb": info["ram_gb"], "vram_gb": a["vram_gb"], "apple_silicon": info["apple_silicon"],
                     "gpus": info["gpus"], "free_disk_gb": info["free_disk_gb"]},
        "catalog_version": catalog()["version"], "running": False, "installed": [],
        "allowed": allowed_models(), "active": None, "recommended": a["tier"], "update_available": False,
        "pull": dict(_pull),
    }
    if not a["supported"]:
        return out
    try:
        r = httpx.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3)
        names = [m["name"] for m in r.json().get("models", [])]
        out["running"] = True
    except (httpx.HTTPError, ValueError):
        return out
    allowed = out["allowed"]
    out["installed"] = [t for t in allowed if any(_same(n, t["model"]) for n in names)]
    active = next((t for t in out["installed"] if _same(t["model"], chosen)), None) if chosen else None
    active = active or (out["installed"][-1] if out["installed"] else None)
    out["active"] = active
    rec = a["tier"]
    out["update_available"] = bool(active and not _same(active["model"], rec["model"]))
    return out


# ------------------------------------------------------------------ downloads

def start_pull(ollama_url: str, model: str) -> dict[str, Any]:
    if model not in [t["model"] for t in allowed_models()]:
        raise ValueError("This model isn't recommended for this computer.")
    with _pull_lock:
        if _pull["status"] == "downloading":
            return dict(_pull)
        _pull.update(model=model, status="downloading", completed=0, total=0, error=None)

    def run() -> None:
        try:
            with httpx.stream("POST", f"{ollama_url.rstrip('/')}/api/pull", json={"model": model, "stream": True},
                              timeout=httpx.Timeout(30, read=600)) as r:
                for line in r.iter_lines():
                    if not line:
                        continue
                    ev = json.loads(line)
                    if ev.get("error"):
                        raise RuntimeError(ev["error"])
                    if ev.get("total"):
                        _pull.update(total=ev["total"], completed=ev.get("completed", 0))
                    if ev.get("status") == "success":
                        _pull.update(status="done")
            if _pull["status"] != "done":
                _pull.update(status="done")
        except Exception as e:  # show a readable reason in Settings
            _pull.update(status="error", error=f"Download failed: {str(e)[:200]}")

    threading.Thread(target=run, daemon=True).start()
    return dict(_pull)


def pull_state() -> dict[str, Any]:
    return dict(_pull)


def remove_model(ollama_url: str, model: str) -> None:
    httpx.request("DELETE", f"{ollama_url.rstrip('/')}/api/delete", json={"model": model}, timeout=30)


# ------------------------------------------------------------------ warm-up

def warm(ollama_url: str, model: str, system_prompt: str) -> None:
    """Load the model and pre-process the dataset prompt in the background.

    Ollama keeps the processed prompt (its KV cache) in memory; the next
    request that starts with the same system prompt skips re-reading it,
    so the user's first question gets its first words much sooner."""
    def run() -> None:
        try:
            httpx.post(
                f"{ollama_url.rstrip('/')}/api/chat",
                json={"model": model, "stream": False, "keep_alive": KEEP_ALIVE, "think": False,
                      "messages": [{"role": "system", "content": system_prompt},
                                   {"role": "user", "content": "Reply with: ready"}],
                      "options": {"num_ctx": num_ctx_for(model), "num_predict": 1, "temperature": 0}},
                timeout=httpx.Timeout(10, read=300),
            )
        except httpx.HTTPError:
            pass

    threading.Thread(target=run, daemon=True).start()
