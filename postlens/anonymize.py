"""Remove personal information from scraped text.

What we remove:
  * tagged people (Facebook gives us the exact character ranges of tags)
  * @mentions typed as plain text
  * links to Facebook profiles, e-mail addresses, phone numbers

What we never collect in the first place: author names, profile URLs,
profile pictures, user IDs. See scraper/graphql_parser.py.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

USER_TOKEN = "@user"

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 8+ digits allowing spaces, dashes, dots, brackets and a leading +. Avoids
# eating years ("2024") and small numbers ("3 days").
_PHONE = re.compile(r"(?<![\w])(?:\+?\d[\s\-.()]*){8,}\d(?![\w])")
_FB_PROFILE_URL = re.compile(
    r"(?:https?://)?(?:www\.|m\.|web\.|mbasic\.)?(?:facebook|fb)\.com/"
    r"(?:profile\.php\?id=\d+|people/[^\s/]+/\d+|(?!groups/|events/|photo|watch|hashtag/|share/|story\.php|permalink\.php)[A-Za-z0-9.]{5,})"
    r"[^\s]*",
    re.IGNORECASE,
)
_AT_MENTION = re.compile(r"(?<![\w@])@[\w.]{2,}(?:\s[A-Z][\w]+)?")
_WS = re.compile(r"[ \t]{2,}")


def replace_ranges(text: str, ranges: Iterable[tuple[int, int]]) -> str:
    """Replace [offset, offset+length) spans with @user.

    Facebook reports offsets in UTF-16 code units (JavaScript string indexes),
    so we convert to Python indexes before slicing. Emoji and many non-Latin
    characters (e.g. Bengali combined with emoji) would otherwise shift spans.
    """
    spans = sorted({(o, l) for o, l in ranges if l and l > 0}, reverse=True)
    if not spans:
        return text
    # Map utf-16 offset -> python index
    u16_to_py: dict[int, int] = {}
    u16 = 0
    for i, ch in enumerate(text):
        u16_to_py[u16] = i
        u16 += 2 if ord(ch) > 0xFFFF else 1
    u16_to_py[u16] = len(text)
    for off, length in spans:
        start = u16_to_py.get(off)
        end = u16_to_py.get(off + length)
        if start is None or end is None or end <= start:
            continue
        text = text[:start] + USER_TOKEN + text[end:]
    return text


def scrub(text: str) -> str:
    if not text:
        return ""
    t = _FB_PROFILE_URL.sub("[profile link]", text)
    t = _EMAIL.sub("[email]", t)
    t = _PHONE.sub("[phone]", t)
    t = _AT_MENTION.sub(USER_TOKEN, t)
    t = _WS.sub(" ", t)
    return t.strip()


def key(*parts: object) -> str:
    """Stable, non-reversible key used only for de-duplication."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return h[:20]
