"""Website statistics and on-page checks for the Overview tab (no AI needed)."""
from __future__ import annotations

from collections import Counter
from typing import Any

from ..analytics import keywords


def site_overview(pages: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [p for p in pages if (p.get("status") or 200) < 400]
    words = [p["word_count"] for p in ok]
    titles = Counter(p["title"].strip().lower() for p in ok if p["title"].strip())

    def ref(p: dict) -> dict:
        return {"id": p["id"], "no": p["_no"], "url": p["url"], "title": p["title"] or p["url"]}

    for n, p in enumerate(pages, 1):
        p["_no"] = n

    checks = [
        ("error", "Broken pages", "Returned an error status (4xx/5xx).",
         [p for p in pages if (p.get("status") or 200) >= 400]),
        ("warning", "Missing title", "Search engines and browser tabs show no title.",
         [p for p in ok if not p["title"].strip()]),
        ("warning", "Duplicate titles", "Several pages share the same title.",
         [p for p in ok if p["title"].strip() and titles[p["title"].strip().lower()] > 1]),
        ("warning", "Missing meta description", "Search results will show an auto-generated snippet.",
         [p for p in ok if not p["description"].strip()]),
        ("warning", "No H1 heading", "Each page should have one main heading.",
         [p for p in ok if p["meta"].get("h1_count", 0) == 0]),
        ("info", "Several H1 headings", "Usually one H1 per page is clearest.",
         [p for p in ok if p["meta"].get("h1_count", 0) > 1]),
        ("warning", "Thin content", "Fewer than 300 words of main content.",
         [p for p in ok if 0 < p["word_count"] < 300]),
        ("info", "Images without alt text", "Hurts accessibility and image search.",
         [p for p in ok if p["meta"].get("images_no_alt", 0) > 0]),
        ("info", "Slow response", "Server took over 2 seconds to answer.",
         [p for p in ok if (p["meta"].get("elapsed_ms") or 0) > 2000]),
        ("info", "Needs JavaScript", "Content only appears after scripts run, which some crawlers and AI tools can't see.",
         [p for p in ok if p.get("rendered")]),
    ]
    issues = [
        {"severity": sev, "title": t, "detail": d, "count": len(lst), "pages": [ref(p) for p in lst[:25]]}
        for sev, t, d, lst in checks if lst
    ]
    langs = Counter(p["lang"] for p in ok if p.get("lang"))
    return {
        "type": "website",
        "totals": {
            "pages": len(pages),
            "ok_pages": len(ok),
            "words": sum(words),
            "avg_words": round(sum(words) / len(words)) if words else 0,
            "issues": sum(i["count"] for i in issues if i["severity"] != "info"),
            "rendered": sum(1 for p in ok if p.get("rendered")),
            "avg_ms": round(sum(p["meta"].get("elapsed_ms") or 0 for p in ok) / len(ok)) if ok else 0,
        },
        "languages": [{"lang": k, "pages": v} for k, v in langs.most_common(5)],
        "keywords": keywords([p["title"] + " " + p["text"] for p in ok], 30),
        "pages": [
            {**ref(p), "words": p["word_count"], "status": p.get("status"), "ms": p["meta"].get("elapsed_ms")}
            for p in pages
        ],
        "issues": issues,
    }
