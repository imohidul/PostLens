"""Search index for fast, relevant answers.

Built once, right after collection finishes, so asking a question only
costs one tiny query embedding plus a lookup:

* Chunking: Facebook posts are grouped with their comments; web pages are
  split at their headings into ~1,500-character passages. Every chunk
  starts with a "[Post #n …]" / "[Page #n …]" label so answers can cite it.
* Hybrid retrieval: BM25 keyword ranking (exact names, numbers, product
  codes) fused with multilingual semantic embeddings (paraphrases, other
  languages such as Bangla) using Reciprocal Rank Fusion - the standard way
  production search systems combine the two.
* Embeddings run locally on the CPU with FastEmbed (ONNX Runtime, no GPU or
  PyTorch needed) using paraphrase-multilingual-MiniLM-L12-v2 (~220 MB,
  downloaded once). If it can't load, PostLens falls back to keyword-only
  search and says so.
"""
from __future__ import annotations

import re
import threading
from typing import Any

from .. import db
from ..config import DATA_DIR
from .retrieval import BM25, build_chunks

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBED_DIR = DATA_DIR / "models"
RRF_K = 60  # standard Reciprocal Rank Fusion constant

_embedder = None
_embedder_failed = False
_lock = threading.Lock()


# ------------------------------------------------------------------ embeddings

def embedder():
    """Load the embedding model once per app run (thread-safe)."""
    global _embedder, _embedder_failed
    if _embedder is not None or _embedder_failed:
        return _embedder
    with _lock:
        if _embedder is None and not _embedder_failed:
            try:
                from fastembed import TextEmbedding
                EMBED_DIR.mkdir(parents=True, exist_ok=True)
                _embedder = TextEmbedding(EMBED_MODEL, cache_dir=str(EMBED_DIR))
            except Exception:
                _embedder_failed = True
    return _embedder


def embed(texts: list[str]):
    """Unit-length float32 vectors (numpy array) or None if unavailable."""
    m = embedder()
    if m is None or not texts:
        return None
    import numpy as np
    vecs = np.array(list(m.embed(texts, batch_size=32)), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    return vecs


# ------------------------------------------------------------------ chunking

def _split_markdown(text: str, max_chars: int) -> list[str]:
    """Split at headings, then paragraphs, keeping chunks under max_chars."""
    blocks = re.split(r"\n(?=#{1,3} )", text)
    out: list[str] = []
    for b in blocks:
        b = b.strip()
        while len(b) > max_chars:
            cut = b.rfind("\n\n", 0, max_chars)
            cut = cut if cut > max_chars // 3 else b.rfind(". ", 0, max_chars) + 1 or max_chars
            out.append(b[:cut].strip())
            b = b[cut:].strip()
        if b:
            out.append(b)
    # merge tiny neighbours so we don't waste labels on 2-line chunks
    merged: list[str] = []
    for b in out:
        if merged and len(merged[-1]) + len(b) < max_chars // 2:
            merged[-1] += "\n\n" + b
        else:
            merged.append(b)
    return merged


def website_chunks(pages: list[dict[str, Any]], max_chars: int = 1500) -> list[dict[str, Any]]:
    chunks = []
    for n, p in enumerate(pages, 1):
        if (p.get("status") or 200) >= 400 or not p["text"].strip():
            continue
        label = f"[Page #{n} · {p['title'] or 'Untitled'} · {p['url']}]"
        parts = _split_markdown(p["text"], max_chars)
        for i, part in enumerate(parts):
            chunks.append({"ref_no": n, "text": f"{label}{' (continued)' if i else ''}\n{part}\n"})
    return chunks


def dataset_chunks(ds: dict[str, Any]) -> list[dict[str, Any]]:
    if ds.get("source_type") == "website":
        return website_chunks(db.pages(ds["id"]))
    return [{"ref_no": c["post_no"], "text": c["text"]} for c in build_chunks(db.posts_with_comments(ds["id"]))]


def build_index(ds_id: int) -> str:
    """Chunk + embed a dataset. Returns 'ready' or 'keyword-only'."""
    ds = db.get_dataset(ds_id)
    if not ds:
        return ""
    db.update_dataset(ds_id, index_state="building")
    chunks = dataset_chunks(ds)
    state = "keyword-only"
    try:
        vecs = embed([c["text"] for c in chunks])
        if vecs is not None:
            for c, v in zip(chunks, vecs):
                c["embedding"] = v.tobytes()
            state = "ready"
    except Exception:
        state = "keyword-only"
    db.replace_chunks(ds_id, chunks)
    db.clear_answers(ds_id)
    db.update_dataset(ds_id, index_state=state)
    return state


def load_chunks(ds: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = db.get_chunks(ds["id"])
    if not chunks:  # datasets from before the index existed
        build_index(ds["id"])
        chunks = db.get_chunks(ds["id"])
    return chunks


# ------------------------------------------------------------------ search

def hybrid_rank(question: str, chunks: list[dict[str, Any]]) -> list[int]:
    """Chunk indexes, best first: BM25 and semantic ranks fused with RRF."""
    n = len(chunks)
    if n == 0:
        return []
    bm = BM25([c["text"] for c in chunks]).scores(question)
    ranks: list[list[int]] = []
    if any(bm):
        ranks.append(sorted(range(n), key=lambda i: bm[i], reverse=True))

    if all(c.get("embedding") for c in chunks):
        q = embed([question])
        if q is not None:
            import numpy as np
            mat = np.frombuffer(b"".join(c["embedding"] for c in chunks), dtype=np.float32).reshape(n, -1)
            sims = mat @ q[0]
            ranks.append(list(np.argsort(-sims)))

    if not ranks:  # no keywords and no embeddings: keep document order
        return list(range(n))
    score = [0.0] * n
    for r in ranks:
        for pos, i in enumerate(r):
            score[int(i)] += 1.0 / (RRF_K + pos + 1)
    return sorted(range(n), key=lambda i: score[i], reverse=True)


def pick(question: str, chunks: list[dict[str, Any]], budget_chars: int) -> list[dict[str, Any]]:
    picked, used = [], 0
    for i in hybrid_rank(question, chunks):
        L = len(chunks[i]["text"])
        if used + L > budget_chars:
            continue
        picked.append(i)
        used += L
    picked.sort()  # keep reading order - models answer better
    return [chunks[i] for i in picked]
