"""SQLite storage. Uses only the standard library so installs stay light.

A "dataset" is one scrape run of one Facebook link. It owns posts, each post
owns comments, and a dataset can have chat conversations about it.
No author names, profile links or user IDs are ever written here.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url   TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|error|cancelled
    error        TEXT,
    range_days   INTEGER NOT NULL DEFAULT 30,
    created_at   REAL NOT NULL,
    finished_at  REAL
);
CREATE TABLE IF NOT EXISTS posts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id     INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    ext_key        TEXT NOT NULL,          -- hash used to de-duplicate, not a user id
    text           TEXT NOT NULL,
    created_at     REAL,                   -- unix seconds, may be NULL if unknown
    reactions      INTEGER,
    shares         INTEGER,
    comment_total  INTEGER,                -- count Facebook reports (may exceed scraped)
    UNIQUE(dataset_id, ext_key)
);
CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    ext_key     TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  REAL,
    reactions   INTEGER,
    is_reply    INTEGER NOT NULL DEFAULT 0,
    UNIQUE(post_id, ext_key)
);
CREATE TABLE IF NOT EXISTS chats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    title       TEXT NOT NULL DEFAULT 'New chat',
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,       -- user|assistant
    content     TEXT NOT NULL,
    meta        TEXT,                -- json: sources, model
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id    INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    status        INTEGER,
    title         TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    lang          TEXT,
    published     TEXT,
    text          TEXT NOT NULL DEFAULT '',   -- main content as Markdown
    word_count    INTEGER NOT NULL DEFAULT 0,
    headings      TEXT,                       -- json [[level, text], ...]
    meta          TEXT,                       -- json: links, images, timing, seo
    rendered      INTEGER NOT NULL DEFAULT 0, -- 1 = needed a real browser (JavaScript site)
    fetched_at    REAL NOT NULL,
    UNIQUE(dataset_id, url)
);
-- Search index used by the AI: text chunks + optional embedding vectors
CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    ref_no      INTEGER NOT NULL,   -- Post #n / Page #n shown to the user
    text        TEXT NOT NULL,
    embedding   BLOB
);
-- Instant answers for repeated questions
CREATE TABLE IF NOT EXISTS answer_cache (
    key         TEXT PRIMARY KEY,
    dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    answer      TEXT NOT NULL,
    meta        TEXT,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pages_ds ON pages(dataset_id);
CREATE INDEX IF NOT EXISTS idx_chunks_ds ON chunks(dataset_id, seq);
CREATE INDEX IF NOT EXISTS idx_posts_ds ON posts(dataset_id);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
"""

_local = threading.local()


def _connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = _connect()
        _local.conn = c
    return c


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    c = conn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise


def _migrate(c: sqlite3.Connection) -> None:
    cols = {r[1] for r in c.execute("PRAGMA table_info(datasets)")}
    if "source_type" not in cols:  # v0.1 databases were Facebook-only
        c.execute("ALTER TABLE datasets ADD COLUMN source_type TEXT NOT NULL DEFAULT 'facebook'")
    if "options" not in cols:
        c.execute("ALTER TABLE datasets ADD COLUMN options TEXT")
    if "index_state" not in cols:  # '', 'building', 'ready', 'keyword-only'
        c.execute("ALTER TABLE datasets ADD COLUMN index_state TEXT NOT NULL DEFAULT ''")


def init() -> None:
    with tx() as c:
        c.executescript(SCHEMA)
        _migrate(c)
        # A crash or closed app can leave runs marked "running" forever.
        c.execute(
            "UPDATE datasets SET status='error', error='Interrupted (app was closed)' "
            "WHERE status IN ('pending','running')"
        )


def rows(sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def row(sql: str, args: tuple = ()) -> dict[str, Any] | None:
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


# ---------- datasets ----------

def create_dataset(source_url: str, range_days: int, source_type: str = "facebook", options: dict | None = None) -> int:
    with tx() as c:
        cur = c.execute(
            "INSERT INTO datasets(source_url, range_days, created_at, status, source_type, options) VALUES (?,?,?, 'pending', ?, ?)",
            (source_url, range_days, time.time(), source_type, json.dumps(options or {})),
        )
        return int(cur.lastrowid)


def update_dataset(ds_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with tx() as c:
        c.execute(f"UPDATE datasets SET {cols} WHERE id=?", (*fields.values(), ds_id))


def list_datasets() -> list[dict[str, Any]]:
    return rows(
        """
        SELECT d.*,
          (SELECT COUNT(*) FROM posts p WHERE p.dataset_id=d.id) AS post_count,
          (SELECT COUNT(*) FROM comments c JOIN posts p ON p.id=c.post_id WHERE p.dataset_id=d.id) AS comment_count,
          (SELECT COUNT(*) FROM pages g WHERE g.dataset_id=d.id) AS page_count,
          (SELECT COALESCE(SUM(word_count),0) FROM pages g WHERE g.dataset_id=d.id) AS word_count
        FROM datasets d ORDER BY d.created_at DESC
        """
    )


def get_dataset(ds_id: int) -> dict[str, Any] | None:
    for d in list_datasets():
        if d["id"] == ds_id:
            return d
    return None


def delete_dataset(ds_id: int) -> None:
    with tx() as c:
        c.execute("DELETE FROM datasets WHERE id=?", (ds_id,))


def delete_all() -> None:
    with tx() as c:
        c.execute("DELETE FROM datasets")


# ---------- posts / comments ----------

def upsert_post(ds_id: int, p: dict[str, Any]) -> int:
    """Insert a post, or fill in missing fields if we've seen it already."""
    with tx() as c:
        existing = c.execute(
            "SELECT id, created_at, reactions, shares, comment_total FROM posts WHERE dataset_id=? AND ext_key=?",
            (ds_id, p["ext_key"]),
        ).fetchone()
        if existing:
            c.execute(
                """UPDATE posts SET
                     created_at = COALESCE(created_at, ?),
                     reactions = COALESCE(?, reactions),
                     shares = COALESCE(?, shares),
                     comment_total = COALESCE(?, comment_total)
                   WHERE id=?""",
                (p.get("created_at"), p.get("reactions"), p.get("shares"), p.get("comment_total"), existing["id"]),
            )
            return int(existing["id"])
        cur = c.execute(
            "INSERT INTO posts(dataset_id, ext_key, text, created_at, reactions, shares, comment_total) VALUES (?,?,?,?,?,?,?)",
            (ds_id, p["ext_key"], p["text"], p.get("created_at"), p.get("reactions"), p.get("shares"), p.get("comment_total")),
        )
        return int(cur.lastrowid)


def add_comments(post_id: int, comments: list[dict[str, Any]]) -> int:
    added = 0
    with tx() as c:
        for cm in comments:
            cur = c.execute(
                "INSERT OR IGNORE INTO comments(post_id, ext_key, text, created_at, reactions, is_reply) VALUES (?,?,?,?,?,?)",
                (post_id, cm["ext_key"], cm["text"], cm.get("created_at"), cm.get("reactions"), int(bool(cm.get("is_reply")))),
            )
            added += cur.rowcount
    return added


def posts_with_comments(ds_id: int) -> list[dict[str, Any]]:
    posts = rows(
        "SELECT * FROM posts WHERE dataset_id=? ORDER BY COALESCE(created_at, 0) DESC, id", (ds_id,)
    )
    if not posts:
        return []
    by_id = {p["id"]: p for p in posts}
    for p in posts:
        p["comments"] = []
    placeholders = ",".join("?" * len(by_id))
    for cm in rows(
        f"SELECT * FROM comments WHERE post_id IN ({placeholders}) ORDER BY COALESCE(created_at, 0), id",
        tuple(by_id),
    ):
        by_id[cm["post_id"]]["comments"].append(cm)
    return posts


# ---------- chats ----------

def create_chat(ds_id: int, title: str = "New chat") -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO chats(dataset_id, title, created_at) VALUES (?,?,?)", (ds_id, title, time.time()))
        return int(cur.lastrowid)


def list_chats(ds_id: int) -> list[dict[str, Any]]:
    return rows("SELECT * FROM chats WHERE dataset_id=? ORDER BY created_at DESC", (ds_id,))


def rename_chat(chat_id: int, title: str) -> None:
    with tx() as c:
        c.execute("UPDATE chats SET title=? WHERE id=?", (title, chat_id))


def delete_chat(chat_id: int) -> None:
    with tx() as c:
        c.execute("DELETE FROM chats WHERE id=?", (chat_id,))


def add_message(chat_id: int, role: str, content: str, meta: dict | None = None) -> int:
    with tx() as c:
        cur = c.execute(
            "INSERT INTO messages(chat_id, role, content, meta, created_at) VALUES (?,?,?,?,?)",
            (chat_id, role, content, json.dumps(meta) if meta else None, time.time()),
        )
        return int(cur.lastrowid)


def list_messages(chat_id: int) -> list[dict[str, Any]]:
    out = rows("SELECT * FROM messages WHERE chat_id=? ORDER BY id", (chat_id,))
    for m in out:
        m["meta"] = json.loads(m["meta"]) if m["meta"] else None
    return out


# ---------- website pages ----------

def upsert_page(ds_id: int, p: dict[str, Any]) -> int:
    with tx() as c:
        cur = c.execute(
            """INSERT INTO pages(dataset_id, url, status, title, description, lang, published, text, word_count,
                                 headings, meta, rendered, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(dataset_id, url) DO UPDATE SET status=excluded.status, title=excluded.title,
                 description=excluded.description, text=excluded.text, word_count=excluded.word_count,
                 headings=excluded.headings, meta=excluded.meta, rendered=excluded.rendered""",
            (ds_id, p["url"], p.get("status"), p.get("title", ""), p.get("description", ""), p.get("lang"),
             p.get("published"), p.get("text", ""), p.get("word_count", 0), json.dumps(p.get("headings") or []),
             json.dumps(p.get("meta") or {}), int(bool(p.get("rendered"))), time.time()),
        )
        return int(cur.lastrowid)


def pages(ds_id: int) -> list[dict[str, Any]]:
    out = rows("SELECT * FROM pages WHERE dataset_id=? ORDER BY id", (ds_id,))
    for p in out:
        p["headings"] = json.loads(p["headings"] or "[]")
        p["meta"] = json.loads(p["meta"] or "{}")
    return out


# ---------- search index ----------

def replace_chunks(ds_id: int, chunks: list[dict[str, Any]]) -> None:
    with tx() as c:
        c.execute("DELETE FROM chunks WHERE dataset_id=?", (ds_id,))
        c.executemany(
            "INSERT INTO chunks(dataset_id, seq, ref_no, text, embedding) VALUES (?,?,?,?,?)",
            [(ds_id, i, ch["ref_no"], ch["text"], ch.get("embedding")) for i, ch in enumerate(chunks)],
        )


def get_chunks(ds_id: int) -> list[dict[str, Any]]:
    return rows("SELECT seq, ref_no, text, embedding FROM chunks WHERE dataset_id=? ORDER BY seq", (ds_id,))


# ---------- answer cache ----------

def cached_answer(key: str) -> dict[str, Any] | None:
    r = row("SELECT answer, meta FROM answer_cache WHERE key=?", (key,))
    if r:
        r["meta"] = json.loads(r["meta"]) if r["meta"] else None
    return r


def store_answer(key: str, ds_id: int, answer: str, meta: dict | None) -> None:
    with tx() as c:
        c.execute(
            "INSERT OR REPLACE INTO answer_cache(key, dataset_id, answer, meta, created_at) VALUES (?,?,?,?,?)",
            (key, ds_id, answer, json.dumps(meta) if meta else None, time.time()),
        )


def clear_answers(ds_id: int) -> None:
    with tx() as c:
        c.execute("DELETE FROM answer_cache WHERE dataset_id=?", (ds_id,))
