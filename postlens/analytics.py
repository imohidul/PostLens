"""Quick statistics computed without AI, for the Overview dashboard."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

WORD = re.compile(r"[^\W\d_][\w'’ঀ-৿]*", re.UNICODE)

STOPWORDS = set("""
a about above after again against all am an and any are aren't as at be because been before being below between both
but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from further had
hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his how how's i i'd
i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off on once only
or other ought our ours ourselves out over own same shan't she she'd she'll she's should shouldn't so some such than that
that's the their theirs them themselves then there there's these they they'd they'll they're they've this those through
to too under until up very was wasn't we we'd we'll we're we've were weren't what what's when when's where where's which
while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your yours yourself yourselves
also just like get got will one can us im dont its u ur yes ok okay pls please thanks thank really much many even still
now new last would could see know go going make made want need well way good time day people user photo video caption without
আমি আমরা তুমি তোমার আপনি আপনার সে তারা এই সেই ও এবং কিন্তু বা যে যা কি কী না নয় হয় হবে হয়ে ছিল আছে করে করা
জন্য থেকে দিয়ে সাথে মধ্যে উপর পর আর তো ই ভাই আপু
""".split())


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def keywords(texts: list[str], n: int = 30) -> list[dict[str, Any]]:
    c: Counter[str] = Counter()
    for t in texts:
        seen = set()
        for w in WORD.findall(t.lower()):
            w = w.strip("'’")
            if len(w) < 3 or w in STOPWORDS or w == "@user":
                continue
            if w not in seen:  # count documents, not repetitions
                c[w] += 1
                seen.add(w)
    return [{"word": w, "count": k} for w, k in c.most_common(n)]


def overview(posts: list[dict[str, Any]]) -> dict[str, Any]:
    comments = [c for p in posts for c in p["comments"]]
    post_times = [p["created_at"] for p in posts if p.get("created_at")]
    comment_times = [c["created_at"] for c in comments if c.get("created_at")]

    timeline: dict[str, dict[str, int]] = {}
    for t in post_times:
        timeline.setdefault(_day(t), {"posts": 0, "comments": 0})["posts"] += 1
    for t in comment_times:
        timeline.setdefault(_day(t), {"posts": 0, "comments": 0})["comments"] += 1

    hours = [0] * 24
    for t in comment_times:
        hours[datetime.fromtimestamp(t).hour] += 1  # local time of the user's PC

    def brief(p: dict) -> dict:
        return {
            "id": p["id"], "text": p["text"][:220], "created_at": p.get("created_at"),
            "comments": len(p["comments"]), "reactions": p.get("reactions"),
            "shares": p.get("shares"), "comment_total": p.get("comment_total"),
        }

    most_discussed = sorted(posts, key=lambda p: len(p["comments"]), reverse=True)[:5]
    most_reacted = sorted([p for p in posts if p.get("reactions")], key=lambda p: p["reactions"], reverse=True)[:5]

    avg_len = round(sum(len(c["text"]) for c in comments) / len(comments)) if comments else 0
    total_reactions = sum(p.get("reactions") or 0 for p in posts)

    return {
        "totals": {
            "posts": len(posts),
            "comments": len(comments),
            "replies": sum(1 for c in comments if c.get("is_reply")),
            "reactions": total_reactions,
            "avg_comments_per_post": round(len(comments) / len(posts), 1) if posts else 0,
            "avg_comment_length": avg_len,
        },
        "range": {
            "first": min(post_times) if post_times else None,
            "last": max(post_times) if post_times else None,
        },
        "timeline": [{"date": d, **v} for d, v in sorted(timeline.items())],
        "hours": hours,
        "post_keywords": keywords([p["text"] for p in posts], 20),
        "comment_keywords": keywords([c["text"] for c in comments], 30),
        "most_discussed": [brief(p) for p in most_discussed],
        "most_reacted": [brief(p) for p in most_reacted],
    }
