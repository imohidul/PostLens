"""HTTP API + the web UI. Runs only on 127.0.0.1 (your own PC)."""
from __future__ import annotations

import csv
import io
import json
import re
import threading
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, analytics, db, hardware, jobs, keystore
from .ai import assistant, local, providers
from .config import load_settings, public_settings, save_settings
from .demo import create_demo
from .scraper import facebook as fb
from .scraper.facebook import ScrapeError
from .web.analysis import site_overview
from .web.crawler import CrawlError

STATIC = Path(__file__).parent / "static"

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    db.init()
    threading.Thread(target=_refresh_fb, daemon=True).start()
    threading.Thread(target=local.refresh_catalog, daemon=True).start()  # newer model recommendations
    threading.Thread(target=hardware.detect, daemon=True).start()        # warm the hardware cache
    yield


app = FastAPI(title="PostLens", version=__version__, docs_url="/api/docs", redoc_url=None, lifespan=_lifespan)


@app.exception_handler(RequestValidationError)
def _validation_error(_request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default 422 echoes the submitted values back. Drop them so a
    # rejected API key is never sent back to the page.
    return JSONResponse(
        {"detail": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]}, status_code=422
    )

# ---------------------------------------------------------------- facebook session state

_fb = {"logged_in": None, "checking": False, "login_running": False, "message": ""}


def _refresh_fb() -> None:
    if _fb["checking"]:
        return
    _fb["checking"] = True
    try:
        r = fb.check_login()
        if r is not None:
            _fb["logged_in"] = r
    except ScrapeError as e:
        _fb["message"] = str(e)
    finally:
        _fb["checking"] = False




# ---------------------------------------------------------------- models

class StartScrape(BaseModel):
    url: str = Field(min_length=4, max_length=2000)
    # Facebook options
    range_days: int = Field(30, ge=1, le=186)
    max_posts: int | None = Field(None, ge=1, le=500)
    # Website options
    mode: str = Field("site", pattern="^(page|site)$")
    max_pages: int | None = Field(None, ge=1, le=500)


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    fresh: bool = False  # True = skip the answer cache (Regenerate)


# ---------------------------------------------------------------- status & settings

@app.get("/api/status")
def status() -> dict[str, Any]:
    return {"version": __version__, "facebook": _fb, "jobs": jobs.active()}


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return public_settings(load_settings())


@app.put("/api/settings")
def put_settings(patch: dict[str, Any]) -> dict[str, Any]:
    ai = patch.get("ai") or {}
    if "provider" in ai and ai["provider"] not in providers.PROVIDERS:
        raise HTTPException(400, "Unknown AI provider")
    return public_settings(save_settings(patch))


# ---------------------------------------------------------------- facebook

@app.get("/api/facebook/status")
def fb_status(refresh: bool = False) -> dict[str, Any]:
    if refresh and not _fb["login_running"]:
        _refresh_fb()
    return _fb


@app.post("/api/facebook/login")
def fb_login() -> dict[str, Any]:
    if _fb["login_running"]:
        return _fb

    def run() -> None:
        _fb.update(login_running=True, message="A browser window opened - log in to Facebook there.")
        try:
            ok = fb.interactive_login()
            _fb.update(logged_in=ok, message="Connected" if ok else "Login window closed before logging in.")
        except ScrapeError as e:
            _fb["message"] = str(e)
        finally:
            _fb["login_running"] = False

    threading.Thread(target=run, daemon=True).start()
    _fb.update(login_running=True)
    return _fb


@app.post("/api/facebook/logout")
def fb_logout() -> dict[str, Any]:
    fb.logout()
    _fb.update(logged_in=False, message="Disconnected")
    return _fb


# ---------------------------------------------------------------- AI

class KeyBody(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


def _provider_or_404(pid: str) -> providers.ProviderInfo:
    info = providers.PROVIDERS.get(pid)
    if not info:
        raise HTTPException(404, "Unknown provider")
    return info


@app.get("/api/ai/status")
def ai_status() -> dict[str, Any]:
    return providers.status(load_settings()["ai"])


@app.get("/api/ai/providers")
def ai_providers() -> dict[str, Any]:
    """Every provider's state. Keys are NEVER included - only whether one is
    saved and its last 4 characters."""
    ai = load_settings()["ai"]
    local_ok = local.supported()
    out = []
    for pid, info in providers.PROVIDERS.items():
        if pid == "ollama" and not local_ok:
            continue  # this PC can't run a premium-grade local model: don't offer it
        key = keystore.get(pid) if info.needs_key else ""
        if info.needs_key:
            available = bool(key)
        else:  # local AI: available only if it's running and has a model
            try:
                available = bool(providers.list_models(pid, "", ai.get("ollama_url", "")))
            except providers.AIError:
                available = False
        out.append({"id": pid, "name": info.name, "tagline": info.tagline, "needs_key": info.needs_key,
                    "key_url": info.key_url, "key_placeholder": info.key_hint,
                    "key_set": bool(key), "key_ending": keystore.hint(key), "available": available})
    return {"active": ai.get("provider") or "", "storage": keystore.backend(), "providers": out,
            "local_supported": local_ok}


@app.get("/api/ai/providers/{pid}")
def ai_provider(pid: str) -> dict[str, Any]:
    _provider_or_404(pid)
    return providers.provider_status(load_settings()["ai"], pid)


@app.put("/api/ai/providers/{pid}/key")
def ai_save_key(pid: str, body: KeyBody) -> dict[str, Any]:
    """Verify the key with the provider first; save it only if it works."""
    info = _provider_or_404(pid)
    if not info.needs_key:
        raise HTTPException(400, "This provider doesn't use an API key")
    key = body.api_key.strip()
    try:
        models = providers.list_models(pid, key)
    except providers.AIError as e:
        raise HTTPException(400, str(e))
    keystore.put(pid, key)
    ai = load_settings()["ai"]
    if not (ai.get("models") or {}).get(pid):
        save_settings({"ai": {"models": {pid: providers.default_model(pid, models)}}})
    return providers.provider_status(load_settings()["ai"], pid)


@app.delete("/api/ai/providers/{pid}/key")
def ai_delete_key(pid: str) -> dict[str, Any]:
    _provider_or_404(pid)
    keystore.remove(pid)
    return providers.provider_status(load_settings()["ai"], pid)


class PullBody(BaseModel):
    model: str = Field(min_length=2, max_length=200)


@app.get("/api/local")
def local_status() -> dict[str, Any]:
    ai = load_settings()["ai"]
    return local.status(ai["ollama_url"], (ai.get("models") or {}).get("ollama", ""))


@app.post("/api/local/pull")
def local_pull(body: PullBody) -> dict[str, Any]:
    try:
        return local.start_pull(load_settings()["ai"]["ollama_url"], body.model)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/local/pull")
def local_pull_state() -> dict[str, Any]:
    return local.pull_state()


@app.post("/api/local/use")
def local_use(body: PullBody) -> dict[str, Any]:
    if body.model not in [t["model"] for t in local.allowed_models()]:
        raise HTTPException(400, "This model isn't recommended for this computer.")
    save_settings({"ai": {"models": {"ollama": body.model}}})
    return local_status()


@app.post("/api/local/check-updates")
def local_check_updates() -> dict[str, Any]:
    updated = local.refresh_catalog(force=True)
    return {"updated": updated, **local_status()}


# ---------------------------------------------------------------- datasets & jobs

@app.get("/api/datasets")
def list_datasets() -> list[dict[str, Any]]:
    return db.list_datasets()


@app.post("/api/datasets")
def start_scrape(body: StartScrape) -> dict[str, Any]:
    raw = body.url.strip()
    url = raw if re.match(r"^https?://", raw, re.I) else f"https://{raw}"
    host = (urlparse(url).hostname or "").lower()
    if not host or "." not in host:
        raise HTTPException(400, "Please paste a full web address, e.g. https://example.com")
    try:
        if re.search(r"(^|\.)(facebook\.com|fb\.com)$", host):
            ds_id = jobs.start(fb.normalize_url(url), body.range_days, body.max_posts)
        else:
            ds_id = jobs.start_website(url, body.mode, body.max_pages)
    except (ScrapeError, CrawlError) as e:
        raise HTTPException(400, str(e))
    return {"id": ds_id}


@app.post("/api/demo")
def demo() -> dict[str, Any]:
    return {"id": create_demo()}


def _ds_or_404(ds_id: int) -> dict[str, Any]:
    d = db.get_dataset(ds_id)
    if not d:
        raise HTTPException(404, "Dataset not found")
    return d


@app.get("/api/datasets/{ds_id}")
def get_dataset(ds_id: int) -> dict[str, Any]:
    d = _ds_or_404(ds_id)
    d["job"] = jobs.get(ds_id)
    return d


@app.delete("/api/datasets/{ds_id}")
def delete_dataset(ds_id: int) -> dict[str, Any]:
    jobs.cancel(ds_id)
    db.delete_dataset(ds_id)
    return {"ok": True}


@app.delete("/api/datasets")
def delete_all() -> dict[str, Any]:
    db.delete_all()
    return {"ok": True}


@app.get("/api/datasets/{ds_id}/posts")
def posts(ds_id: int) -> list[dict[str, Any]]:
    _ds_or_404(ds_id)
    return db.posts_with_comments(ds_id)


@app.get("/api/datasets/{ds_id}/overview")
def overview(ds_id: int) -> dict[str, Any]:
    d = _ds_or_404(ds_id)
    if d.get("source_type") == "website":
        return site_overview(db.pages(ds_id))
    return {"type": "facebook", **analytics.overview(db.posts_with_comments(ds_id))}


@app.get("/api/datasets/{ds_id}/pages")
def pages(ds_id: int) -> list[dict[str, Any]]:
    _ds_or_404(ds_id)
    return db.pages(ds_id)


@app.post("/api/datasets/{ds_id}/warm")
def warm(ds_id: int) -> dict[str, Any]:
    """Called when the user opens Ask AI: pre-load Local AI with this dataset."""
    _ds_or_404(ds_id)
    return {"warming": assistant.warm(ds_id)}


@app.get("/api/datasets/{ds_id}/export")
def export(ds_id: int, format: str = "json") -> Response:
    d = _ds_or_404(ds_id)
    if d.get("source_type") == "website":
        return _export_website(d, format)
    data = db.posts_with_comments(ds_id)
    iso = lambda t: datetime.fromtimestamp(t).isoformat(timespec="seconds") if t else ""  # noqa: E731
    name = f"postlens-{ds_id}"
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["type", "post_no", "date", "text", "reactions", "is_reply"])
        for n, p in enumerate(data, 1):
            w.writerow(["post", n, iso(p["created_at"]), p["text"], p["reactions"] or "", ""])
            for c in p["comments"]:
                w.writerow(["comment", n, iso(c["created_at"]), c["text"], c["reactions"] or "", int(c["is_reply"])])
        return Response(
            "﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",  # BOM so Excel reads Bengali/emoji
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    out = {
        "source": d["source_url"], "title": d["title"], "exported_at": datetime.now().isoformat(timespec="seconds"),
        "posts": [
            {"post_no": n, "date": iso(p["created_at"]), "text": p["text"], "reactions": p["reactions"],
             "shares": p["shares"],
             "comments": [{"date": iso(c["created_at"]), "text": c["text"], "reactions": c["reactions"],
                           "is_reply": bool(c["is_reply"])} for c in p["comments"]]}
            for n, p in enumerate(data, 1)
        ],
    }
    return Response(
        json.dumps(out, ensure_ascii=False, indent=2), media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}.json"'},
    )


def _export_website(d: dict[str, Any], format: str) -> Response:
    rows_ = db.pages(d["id"])
    name = f"postlens-{d['id']}"
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["page_no", "url", "status", "title", "description", "words", "response_ms", "text"])
        for n, p in enumerate(rows_, 1):
            w.writerow([n, p["url"], p["status"], p["title"], p["description"], p["word_count"],
                        p["meta"].get("elapsed_ms"), p["text"]])
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    out = {"source": d["source_url"], "title": d["title"],
           "pages": [{"page_no": n, **{k: p[k] for k in ("url", "status", "title", "description", "lang", "word_count",
                                                          "headings", "meta", "text")}} for n, p in enumerate(rows_, 1)]}
    return Response(json.dumps(out, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}.json"'})


@app.get("/api/jobs/{ds_id}")
def job(ds_id: int) -> dict[str, Any]:
    j = jobs.get(ds_id)
    if not j:
        d = _ds_or_404(ds_id)
        return {"dataset_id": ds_id, "status": d["status"], "message": d.get("error") or d["status"]}
    return j


@app.post("/api/jobs/{ds_id}/cancel")
def cancel_job(ds_id: int) -> dict[str, Any]:
    return {"ok": jobs.cancel(ds_id)}


# ---------------------------------------------------------------- chats

@app.get("/api/datasets/{ds_id}/chats")
def chats(ds_id: int) -> list[dict[str, Any]]:
    return db.list_chats(ds_id)


@app.post("/api/datasets/{ds_id}/chats")
def new_chat(ds_id: int) -> dict[str, Any]:
    _ds_or_404(ds_id)
    return {"id": db.create_chat(ds_id)}


@app.delete("/api/chats/{chat_id}")
def del_chat(chat_id: int) -> dict[str, Any]:
    db.delete_chat(chat_id)
    return {"ok": True}


@app.get("/api/chats/{chat_id}/messages")
def messages(chat_id: int) -> list[dict[str, Any]]:
    return db.list_messages(chat_id)


@app.post("/api/chats/{chat_id}/ask")
def ask(chat_id: int, body: Ask) -> StreamingResponse:
    chat = db.row("SELECT * FROM chats WHERE id=?", (chat_id,))
    if not chat:
        raise HTTPException(404, "Chat not found")

    def gen():
        for ev in assistant.answer(chat_id, chat["dataset_id"], body.question.strip(), use_cache=not body.fresh):
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------- web UI

if (STATIC / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    f = STATIC / path
    if path and f.is_file() and STATIC in f.resolve().parents:
        return FileResponse(f)
    index = STATIC / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"error": "UI not built. Run: cd frontend && npm install && npm run build"}, 500)
