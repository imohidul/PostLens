"""Extract posts and comments from Facebook's GraphQL JSON.

Why GraphQL instead of reading the page HTML: while you scroll, Facebook's web
app downloads JSON from /api/graphql/. That JSON contains the full post text,
the exact creation timestamp and the comment text, whereas the visible HTML
hides dates behind hover tooltips and truncates long posts. Reading the JSON
is therefore both more complete and less sensitive to visual redesigns.

Privacy: this module never reads author, actor, owner, profile or user fields.
Tagged people inside text are replaced using the tag ranges Facebook provides.

NOTE: the exact JSON shape is undocumented and changes. The functions below
use tolerant heuristics (search by key name) rather than fixed paths.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator

from ..anonymize import key as make_key
from ..anonymize import replace_ranges, scrub
from . import selectors as S

# Nested keys we never descend into when looking for a story's own fields,
# because they belong to another object (a shared post, comments, the author).
_FOREIGN_KEYS = {
    "attached_story", "attached_story_layout", "comments", "comment_list_renderer",
    "interesting_top_level_comments", "top_level_comments", "actors", "author",
    "owner", "owning_profile", "feedback_target_with_context", "replies_connection",
}
_KEEP_ENTITY_TYPES = {"Hashtag", "ExternalUrl", "Page"}


def iter_json_docs(body: str) -> Iterator[Any]:
    """A GraphQL response may be several JSON documents, one per line."""
    body = body.strip()
    if body.startswith("for (;;);"):
        body = body[len("for (;;);"):]
    try:
        yield json.loads(body)
        return
    except json.JSONDecodeError:
        pass
    for line in body.splitlines():
        line = line.strip()
        if not line or line[0] not in "[{":
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _find(obj: Any, wanted: str, pred=None, depth: int = 0, max_depth: int = 14) -> Any:
    """Depth-first search for the first value under key `wanted` (optionally
    passing `pred`), skipping foreign sub-objects."""
    if depth > max_depth:
        return None
    if isinstance(obj, dict):
        if wanted in obj and obj[wanted] not in (None, "", {}) and (pred is None or pred(obj[wanted])):
            return obj[wanted]
        for k, v in obj.items():
            if k in _FOREIGN_KEYS:
                continue
            r = _find(v, wanted, pred, depth + 1, max_depth)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find(v, wanted, pred, depth + 1, max_depth)
            if r is not None:
                return r
    return None


def _has_text(v: Any) -> bool:
    return isinstance(v, dict) and isinstance(v.get("text"), str) and bool(v["text"].strip())


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text_with_ranges(msg: Any) -> str:
    if not isinstance(msg, dict):
        return ""
    text = msg.get("text") or ""
    if not isinstance(text, str) or not text:
        return ""
    spans = []
    for r in msg.get("ranges") or []:
        if not isinstance(r, dict):
            continue
        ent = r.get("entity") or {}
        t = ent.get("__typename") if isinstance(ent, dict) else None
        if t in _KEEP_ENTITY_TYPES:
            continue
        try:
            spans.append((int(r.get("offset", 0)), int(r.get("length", 0))))
        except (TypeError, ValueError):
            continue
    return scrub(replace_ranges(text, spans))


def _int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, dict):
        for k in ("count", "total_count", "value"):
            if isinstance(v.get(k), (int, float)):
                return int(v[k])
    return None


def _story_record(node: dict) -> dict | None:
    sid = str(node.get("post_id") or node.get("id") or "")
    if not sid:
        return None
    msg = _find(node, "message", _has_text)
    text = _text_with_ranges(msg)
    created = _find(node, "creation_time", _is_num)
    url = None
    for k in S.POST_URL_KEYS:
        u = _find(node, k, lambda x: isinstance(x, str) and bool(S.POST_URL_HINT.search(x)))
        if isinstance(u, str) and S.POST_URL_HINT.search(u):
            url = u
            break
    return {
        "sid": sid,
        "alias": str(node.get("id") or ""),
        "text": text,
        "created_at": float(created) if isinstance(created, (int, float)) else None,
        "url": url,
        "reactions": _int(_find(node, "reaction_count")) or _int(_find(node, "reactors")),
        "comment_total": _int(_find(node, "total_comment_count")) or _int(_find(node, "comment_count")),
        "shares": _int(_find(node, "share_count")),
    }


def _comment_record(node: dict) -> dict | None:
    body = node.get("body") or node.get("preferred_body")
    text = _text_with_ranges(body)
    if not text:
        return None
    cid = node.get("legacy_fbid") or node.get("id") or text
    created = node.get("created_time")
    depth = node.get("depth")
    fb = node.get("feedback") if isinstance(node.get("feedback"), dict) else {}
    reactions = _int(fb.get("reactors")) or _int(fb.get("reaction_count")) if fb else None
    return {
        "ext_key": make_key("c", cid),
        "text": text,
        "created_at": float(created) if isinstance(created, (int, float)) else None,
        "reactions": reactions,
        "is_reply": bool(depth and depth > 0),
    }


class GraphQLCollector:
    """Accumulates stories and comments across many GraphQL responses."""

    def __init__(self) -> None:
        self.stories: dict[str, dict] = {}
        self._alias: dict[str, str] = {}
        self.comments: dict[str, dict] = {}  # ext_key -> comment
        self.comment_story: dict[str, str] = {}  # ext_key -> story sid (if known)

    # -- public --
    def feed(self, body: str) -> None:
        for doc in iter_json_docs(body):
            self._walk(doc, None)

    def story_list(self) -> list[dict]:
        return [s for s in self.stories.values() if s.get("text") or s.get("url")]

    # -- internals --
    def _merge_story(self, rec: dict) -> str:
        sid = self._alias.get(rec["alias"], rec["sid"])
        if rec["alias"] and rec["alias"] != sid:
            self._alias[rec["alias"]] = sid
        cur = self.stories.get(sid)
        if cur is None:
            self.stories[sid] = rec
            return sid
        for k, v in rec.items():
            if v in (None, ""):
                continue
            if k == "text" and cur.get("text") and len(cur["text"]) >= len(v):
                continue
            if cur.get(k) in (None, ""):
                cur[k] = v
            elif k in ("reactions", "comment_total", "shares", "text"):
                cur[k] = v
        return sid

    def _walk(self, obj: Any, story_sid: str | None, depth: int = 0) -> None:
        if depth > 60:
            return
        if isinstance(obj, dict):
            t = obj.get("__typename")
            if t == "Story" and ("post_id" in obj or "comet_sections" in obj or "creation_time" in obj):
                rec = _story_record(obj)
                if rec:
                    story_sid = self._merge_story(rec)
            elif t == "Comment":
                rec = _comment_record(obj)
                if rec:
                    self.comments.setdefault(rec["ext_key"], rec)
                    if story_sid:
                        self.comment_story.setdefault(rec["ext_key"], story_sid)
            for k, v in obj.items():
                if k in ("author", "actors", "owner", "owning_profile", "user"):
                    continue  # never walk into people objects
                # a shared post is a different story
                self._walk(v, None if k == "attached_story" else story_sid, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                self._walk(v, story_sid, depth + 1)
