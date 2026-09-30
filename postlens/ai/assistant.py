"""Answer questions about a dataset as fast as possible.

How a reply is kept fast (all established production techniques):

1. Streaming - words appear as the model writes them.
2. Cache-friendly prompt layout - the big, unchanging part (instructions +
   dataset overview, or the whole dataset when it fits) always comes first and
   is byte-for-byte identical for every question about that dataset. Providers
   then re-use their cached copy instead of re-reading it:
     * Anthropic: the system block is marked with cache_control.
     * OpenAI and Gemini: identical prefixes are cached automatically.
     * Local AI (Ollama): the processed prompt stays in memory (KV cache).
   Only the question-specific part (retrieved passages + question) comes last.
3. Pre-built hybrid search index (see index.py) - no work at question time
   except one tiny embedding.
4. Warm-up - opening "Ask AI" pre-loads the local model and pre-processes the
   dataset prompt before the first question is typed.
5. Answer cache - asking the same opening question about the same data with
   the same model returns the saved answer instantly.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime
from typing import Any, Iterator

from .. import analytics, db
from ..config import load_settings
from ..web.analysis import site_overview
from . import index
from .providers import PROVIDERS, AIError, resolve_model, stream_chat
from .retrieval import summary_block

RULES = {
    "facebook": """You are PostLens, an analyst answering questions about posts and comments collected from a Facebook page.

Rules:
- Base every answer ONLY on the DATA and EXCERPTS provided. If they don't contain the answer, say so plainly.
- Cite posts by number, e.g. "Post #4", so the user can check them.
- Commenters are anonymous. Never guess anyone's identity. "@user" marks a removed name.
- When you estimate (sentiment, shares of opinion), say it's an estimate from the collected comments.
- Answer in the user's language. Lead with the answer, then short bullets. Use bold for key findings.""",
    "website": """You are PostLens, an analyst answering questions about the content of a website that was collected page by page.

Rules:
- Base every answer ONLY on the DATA and EXCERPTS provided. If they don't contain the answer, say so plainly.
- Cite pages by number, e.g. "Page #3", so the user can check them.
- For SEO, content or messaging questions, be specific and practical.
- Answer in the user's language. Lead with the answer, then short bullets. Use bold for key findings.""",
}


def _date(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "unknown date"


def _website_summary(ds: dict[str, Any], pages: list[dict[str, Any]]) -> str:
    ov = site_overview(pages)
    t = ov["totals"]
    lines = [
        f"SOURCE: {ds['title'] or ds['source_url']} ({ds['source_url']})",
        f"Pages collected: {t['pages']} ({t['ok_pages']} readable) · {t['words']} words of main content",
        "Frequent words: " + (", ".join(k["word"] for k in ov["keywords"][:15]) or "n/a"),
        "On-page issues: " + ("; ".join(f"{i['title']} ({i['count']})" for i in ov["issues"]) or "none found"),
        "Page index (number · title · words · url):",
    ]
    for n, p in enumerate(pages, 1):
        lines.append(f"  #{n} · {(p['title'] or 'Untitled')[:70]} · {p['word_count']} w · {p['url']}")
    return "\n".join(lines)


def build_prompt(ds: dict[str, Any], budget: int) -> tuple[str, list[dict[str, Any]], bool]:
    """(system prompt, chunks, complete). The system prompt depends only on the
    dataset and the budget - never on the question - so it can be cached."""
    kind = ds.get("source_type") or "facebook"
    if kind == "website":
        summary = _website_summary(ds, db.pages(ds["id"]))
    else:
        posts = db.posts_with_comments(ds["id"])
        summary = summary_block(ds["title"] or ds["source_url"], posts, analytics.overview(posts))
    chunks = index.load_chunks(ds)
    total = sum(len(c["text"]) for c in chunks)
    complete = total + len(summary) <= budget
    body = "\n".join(c["text"] for c in chunks) if complete else ""
    note = "" if complete else (
        "\nThe full data is larger than you can read at once. Each question comes with the most relevant EXCERPTS; "
        "use them together with the overview above. Mention it if a question needs every item (e.g. exact counts)."
    )
    system = f"{RULES[kind]}{note}\n\nDATA\n====\n{summary}\n\n{body}".rstrip() + "\n"
    return system, chunks, complete


def _budget(ai: dict[str, Any], provider: str, model: str) -> int:
    budget = int(ai.get("context_chars", 24000))
    if provider == "ollama":
        from . import local
        # leave room for history, excerpts and the answer inside the fixed window
        budget = min(budget, int(local.num_ctx_for(model) * 3.0 * 0.6))
    return max(6000, budget)


def _cache_key(ds: dict[str, Any], provider: str, model: str, question: str) -> str:
    norm = re.sub(r"\s+", " ", question.strip().lower()).rstrip("?!. ")
    raw = f"{ds['id']}|{ds.get('finished_at')}|{provider}|{model}|{norm}"
    return hashlib.sha256(raw.encode()).hexdigest()


def warm(dataset_id: int) -> bool:
    """Pre-load the local model with this dataset's prompt (Local AI only)."""
    ai = load_settings()["ai"]
    if ai.get("provider") != "ollama":
        return False
    ds = db.get_dataset(dataset_id)
    if not ds:
        return False
    try:
        provider, model = resolve_model(ai)
    except AIError:
        return False
    system, _, _ = build_prompt(ds, _budget(ai, provider, model))
    from . import local
    local.warm(ai["ollama_url"], model, system)
    return True


def answer(chat_id: int, dataset_id: int, question: str, use_cache: bool = True) -> Iterator[dict[str, Any]]:
    """Yields events: meta, token..., done | error."""
    t0 = time.perf_counter()
    ai = load_settings()["ai"]
    ds = db.get_dataset(dataset_id)
    if not ds:
        yield {"type": "error", "message": "Dataset not found"}
        return
    try:
        provider, model = resolve_model(ai)
    except AIError as e:
        yield {"type": "error", "message": str(e)}
        return

    history = db.list_messages(chat_id)[-8:]
    db.add_message(chat_id, "user", question)
    if not history:
        db.rename_chat(chat_id, question[:60])

    system, chunks, complete = build_prompt(ds, _budget(ai, provider, model))
    meta: dict[str, Any] = {"model": model, "provider": provider, "provider_name": PROVIDERS[provider].name,
                            "complete": complete}

    # 5. Instant answer for a repeated opening question
    key = _cache_key(ds, provider, model, question)
    if use_cache and not history:
        hit = db.cached_answer(key)
        if hit:
            meta.update(hit["meta"] or {}, cached=True, ttft_ms=int((time.perf_counter() - t0) * 1000))
            yield {"type": "meta", **meta}
            yield {"type": "token", "text": hit["answer"]}
            db.add_message(chat_id, "assistant", hit["answer"], meta)
            yield {"type": "done", "meta": meta}
            return

    # 3. Question-specific excerpts go LAST so the cached prefix stays identical
    user_msg = question
    if not complete:
        excerpt_budget = max(3000, _budget(ai, provider, model) - len(system))
        picked = index.pick(question, chunks, excerpt_budget)
        meta["refs_used"] = sorted({c["ref_no"] for c in picked})
        user_msg = "EXCERPTS\n========\n" + "\n".join(c["text"] for c in picked) + f"\n\nQUESTION: {question}"

    messages = [{"role": "system", "content": system}]
    turns = [{"role": m["role"], "content": m["content"]} for m in history] + [{"role": "user", "content": user_msg}]
    for t in turns:  # Claude and Gemini need strictly alternating turns
        if len(messages) > 1 and messages[-1]["role"] == t["role"]:
            messages[-1]["content"] += "\n\n" + t["content"]
        else:
            messages.append(t)
    if messages[1]["role"] == "assistant":
        messages.pop(1)

    yield {"type": "meta", **meta}
    out: list[str] = []
    try:
        for piece in stream_chat(ai, provider, model, messages, cache_key=f"postlens-ds{ds['id']}"):
            if not out:
                meta["ttft_ms"] = int((time.perf_counter() - t0) * 1000)
            out.append(piece)
            yield {"type": "token", "text": piece}
    except AIError as e:
        if out:
            db.add_message(chat_id, "assistant", "".join(out), meta)
        yield {"type": "error", "message": str(e)}
        return
    except Exception:  # never echo raw exceptions: they could contain request details
        yield {"type": "error", "message": "The AI request failed unexpectedly. Please try again."}
        return
    meta["total_ms"] = int((time.perf_counter() - t0) * 1000)
    text = "".join(out)
    db.add_message(chat_id, "assistant", text, meta)
    if not history and text.strip():
        db.store_answer(key, ds["id"], text, {k: v for k, v in meta.items() if k not in ("ttft_ms", "total_ms")})
    yield {"type": "done", "meta": meta}
