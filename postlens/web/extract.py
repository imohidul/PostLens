"""Turn one HTML page into clean, analyzable data.

Main content: Trafilatura, the open-source extractor that has scored highest
in independent main-text extraction benchmarks. It strips menus, footers,
cookie banners and ads and returns the article/body as Markdown, keeping
headings, lists and tables, which LLMs read well.

SEO/structure facts (title, meta description, headings, links, images) are
read separately with lxml from the full HTML.

Privacy: reader comments are excluded, and e-mail addresses and phone
numbers are removed from the text (same rules as for Facebook).
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import trafilatura
from lxml import html as lxml_html

from ..anonymize import scrub

SKIP_EXT = re.compile(
    r"\.(jpg|jpeg|png|gif|webp|svg|ico|bmp|pdf|zip|rar|7z|gz|tar|mp3|mp4|m4a|avi|mov|wmv|webm|"
    r"css|js|json|xml|rss|atom|woff2?|ttf|eot|exe|dmg|apk|msi|docx?|xlsx?|pptx?)$",
    re.IGNORECASE,
)
TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|ref_)", re.IGNORECASE)


def normalize_link(base: str, href: str) -> str | None:
    """Absolute URL without #fragment and tracking parameters, or None."""
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None
    url, _ = urldefrag(urljoin(base, href.strip()))
    u = urlparse(url)
    if u.scheme not in ("http", "https") or SKIP_EXT.search(u.path):
        return None
    query = "&".join(p for p in u.query.split("&") if p and not TRACKING.match(p.split("=")[0]))
    path = u.path or "/"
    return f"{u.scheme}://{u.netloc.lower()}{path}" + (f"?{query}" if query else "")


def same_site(a: str, b: str) -> bool:
    ha, hb = urlparse(a).netloc.lower(), urlparse(b).netloc.lower()
    return ha.removeprefix("www.") == hb.removeprefix("www.")


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.text_content() or "").strip()


def extract_page(html: str, url: str, status: int | None = None, elapsed_ms: int | None = None,
                 size_bytes: int | None = None) -> dict[str, Any]:
    try:
        doc = lxml_html.fromstring(html)
    except (ValueError, lxml_html.etree.ParserError):
        doc = None

    title = description = canonical = lang = robots_meta = site_name = ""
    headings: list[list] = []
    links_internal: set[str] = set()
    links_external: set[str] = set()
    images = images_no_alt = 0
    if doc is not None:
        t = doc.find(".//title")
        title = _text(t) if t is not None else ""
        for m in doc.iter("meta"):
            name = (m.get("name") or m.get("property") or "").lower()
            if name == "description" and not description:
                description = (m.get("content") or "").strip()
            elif name == "og:title" and not title:
                title = (m.get("content") or "").strip()
            elif name in ("og:site_name", "application-name") and not site_name:
                site_name = (m.get("content") or "").strip()
            elif name == "robots":
                robots_meta = (m.get("content") or "").lower()
        for ln in doc.iter("link"):
            if (ln.get("rel") or "").lower() == "canonical":
                canonical = ln.get("href") or ""
        lang = (doc.get("lang") or "").split("-")[0].lower()
        for h in doc.xpath("//h1|//h2|//h3"):
            txt = _text(h)
            if txt:
                headings.append([int(h.tag[1]), txt[:200]])
        for a in doc.iter("a"):
            n = normalize_link(url, a.get("href") or "")
            if n:
                (links_internal if same_site(n, url) else links_external).add(n)
        for img in doc.iter("img"):
            images += 1
            if not (img.get("alt") or "").strip():
                images_no_alt += 1

    body = trafilatura.extract(
        html, url=url, output_format="markdown", include_tables=True, include_comments=False,
        include_formatting=True, include_links=False, include_images=False, favor_recall=True,
    ) or ""
    try:
        meta = trafilatura.extract_metadata(html, default_url=url)
    except Exception:  # metadata is a bonus; never lose the page over it
        meta = None
    published = getattr(meta, "date", None) if meta else None
    if not title and meta is not None:
        title = meta.title or ""
    if not site_name and meta is not None:
        site_name = getattr(meta, "sitename", "") or ""

    body = scrub(body)
    words = len(re.findall(r"\w+", body))
    h1_count = sum(1 for h in headings if h[0] == 1)
    return {
        "url": url,
        "status": status,
        "title": title[:300],
        "site_name": site_name[:120],
        "description": description[:500],
        "lang": lang or None,
        "published": published,
        "text": body,
        "word_count": words,
        "headings": headings[:80],
        "meta": {
            "canonical": canonical,
            "robots": robots_meta,
            "h1_count": h1_count,
            "links_internal": len(links_internal),
            "links_external": len(links_external),
            "images": images,
            "images_no_alt": images_no_alt,
            "elapsed_ms": elapsed_ms,
            "size_kb": round(size_bytes / 1024) if size_bytes else None,
        },
        "_links": sorted(links_internal),  # used by the crawler, not stored
    }


def needs_browser(page: dict[str, Any], html: str) -> bool:
    """Heuristic for JavaScript-rendered sites (React/Vue/Angular shells):
    almost no readable text but an app container or many scripts."""
    if page["word_count"] >= 80:
        return False
    markers = ('id="root"', "id='root'", 'id="app"', "__next", "ng-version", "data-reactroot", "nuxt",
               "enable javascript", "requires javascript")
    low = html.lower()
    return any(m in low for m in markers) or low.count("<script") >= 5
