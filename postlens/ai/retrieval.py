"""Pick which posts/comments to show the AI for a question.

Small free models can only read a limited amount of text at once (their
"context window"). If the whole dataset fits in the budget we send all of it;
otherwise we rank chunks with BM25 - the classic keyword-relevance formula
search engines used before neural search - and send the best ones plus a
statistical summary so the model still knows the overall picture.
Pure Python: no vector database or embedding model to install.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime
from typing import Any

from ..analytics import STOPWORDS

TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


def _date(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "unknown date"


def build_chunks(posts: list[dict[str, Any]], max_chars: int = 1800) -> list[dict[str, Any]]:
    """One chunk = a post header + its text + a slice of its comments.
    Long comment threads are split across several chunks, each repeating the
    post header so the model always knows which post a comment belongs to."""
    chunks: list[dict[str, Any]] = []
    for n, p in enumerate(posts, start=1):
        meta = [_date(p.get("created_at"))]
        if p.get("reactions") is not None:
            meta.append(f"{p['reactions']} reactions")
        meta.append(f"{len(p['comments'])} comments collected")
        header = f"[Post #{n} · " + " · ".join(meta) + "]"
        post_text = p["text"].strip()
        if len(post_text) > 1200:
            post_text = post_text[:1200] + "…"
        base = f"{header}\nPOST: {post_text}\n"
        cur = base + "COMMENTS:\n" if p["comments"] else base
        part_has_comments = False
        for c in p["comments"]:
            line = f"- {'↳ ' if c.get('is_reply') else ''}{c['text'].strip()[:500]}\n"
            if part_has_comments and len(cur) + len(line) > max_chars:
                chunks.append({"post_no": n, "post_id": p["id"], "text": cur})
                cur = f"{header} (continued)\nCOMMENTS:\n"
            cur += line
            part_has_comments = True
        chunks.append({"post_no": n, "post_id": p["id"], "text": cur})
    return chunks


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(_tokens(d)) for d in docs]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lens) / len(self.lens)) if self.lens else 0
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = _tokens(query)
        out = []
        for d, ln in zip(self.docs, self.lens):
            s = 0.0
            for t in q:
                f = d.get(t)
                if not f:
                    continue
                s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / (self.avg or 1)))
            out.append(s)
        return out


def summary_block(title: str, posts: list[dict[str, Any]], overview: dict[str, Any]) -> str:
    t = overview["totals"]
    r = overview["range"]
    kw = ", ".join(k["word"] for k in overview["comment_keywords"][:15]) or "n/a"
    lines = [
        f"SOURCE: {title}",
        f"Posts collected: {t['posts']} (from {_date(r['first'])} to {_date(r['last'])})",
        f"Comments collected: {t['comments']} (replies: {t['replies']})",
        f"Average comments per post: {t['avg_comments_per_post']}",
        f"Most frequent words in comments: {kw}",
        "Post index (number · date · comments · first words):",
    ]
    for n, p in enumerate(posts, start=1):
        lines.append(f"  #{n} · {_date(p.get('created_at'))} · {len(p['comments'])} c · {p['text'][:70].replace(chr(10), ' ')}")
    return "\n".join(lines)


def select_context(question: str, posts: list[dict[str, Any]], budget_chars: int) -> tuple[str, list[int], bool]:
    """Returns (context_text, post_numbers_used, is_complete)."""
    chunks = build_chunks(posts)
    total = sum(len(c["text"]) for c in chunks)
    if total <= budget_chars:
        return "\n".join(c["text"] for c in chunks), sorted({c["post_no"] for c in chunks}), True

    scores = BM25([c["text"] for c in chunks]).scores(question)
    # If the question has no useful keywords ("summarize this"), all scores are 0:
    # fall back to spreading the budget across posts in order.
    if not any(scores):
        order = sorted(range(len(chunks)), key=lambda i: ("(continued)" in chunks[i]["text"].split("\n", 1)[0], i))
    else:
        order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    picked, used = [], 0
    for i in order:
        L = len(chunks[i]["text"])
        if used + L > budget_chars:
            continue
        picked.append(i)
        used += L
    picked.sort()
    return "\n".join(chunks[i]["text"] for i in picked), sorted({chunks[i]["post_no"] for i in picked}), False
