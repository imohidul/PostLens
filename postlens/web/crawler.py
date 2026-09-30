"""Collect pages from any website.

Approach (standard practice for polite, reliable crawling):
  1. Read robots.txt and obey it (disallowed paths, crawl-delay).
  2. Discover pages from the XML sitemap(s) first - the site's own list of
     its pages - then fall back to following links from the start page.
  3. Fetch with a plain HTTP client (fast). Only when a page turns out to
     be a JavaScript app shell, render it in a real headless browser.
  4. Extract the main content (see extract.py) and stream each page to the
     database as soon as it's ready, so partial results survive a stop.
"""
from __future__ import annotations

import gzip
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from lxml import etree

from .. import __version__
from .extract import extract_page, needs_browser, normalize_link, same_site

USER_AGENT = (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              f"Chrome/124.0 Safari/537.36 PostLens/{__version__}")
ROBOTS_AGENT = "PostLens"


class CrawlError(Exception):
    """Message safe to show the user."""


class Cancelled(CrawlError):
    pass


@dataclass
class WebOptions:
    url: str
    mode: str = "site"            # "page" = only this URL, "site" = crawl the site
    max_pages: int = 30
    render: str = "auto"          # "auto" | "always" | "never"
    respect_robots: bool = True
    delay_s: float = 0.5          # minimum pause between requests to the site


class WebCrawler:
    def __init__(self, opts: WebOptions, on_progress: Callable[[dict], None],
                 on_page: Callable[[dict], None], cancel: threading.Event) -> None:
        self.o = opts
        self.on_progress = on_progress
        self.on_page = on_page
        self.cancel = cancel
        self.stats = {"pages_found": 0, "pages_done": 0, "words": 0, "errors": 0}
        self.title = ""
        self._pw = None
        self._browser = None
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml",
                     "Accept-Language": "en-US,en;q=0.8"},
            follow_redirects=True, timeout=httpx.Timeout(20, connect=10), http2=False,
        )
        self.robots: RobotFileParser | None = None
        self.delay = opts.delay_s

    # ------------------------------------------------------------ plumbing

    def _progress(self, stage: str, message: str) -> None:
        self.on_progress({"stage": stage, "message": message, **self.stats, "title": self.title})

    def _check(self) -> None:
        if self.cancel.is_set():
            raise Cancelled("Cancelled")

    def _allowed(self, url: str) -> bool:
        return not self.o.respect_robots or self.robots is None or self.robots.can_fetch(ROBOTS_AGENT, url)

    # ------------------------------------------------------------ discovery

    def _load_robots(self, root: str) -> list[str]:
        sitemaps: list[str] = []
        try:
            r = self.client.get(f"{root}/robots.txt")
            if r.status_code == 200 and "text" in r.headers.get("content-type", "text"):
                rp = RobotFileParser()
                rp.parse(r.text.splitlines())
                self.robots = rp
                cd = rp.crawl_delay(ROBOTS_AGENT) or rp.crawl_delay("*")
                if cd:
                    self.delay = max(self.delay, min(float(cd), 10.0))
                sitemaps = [ln.split(":", 1)[1].strip() for ln in r.text.splitlines()
                            if ln.lower().startswith("sitemap:")]
        except httpx.HTTPError:
            pass
        return sitemaps or [f"{root}/sitemap.xml", f"{root}/sitemap_index.xml"]

    def _sitemap_urls(self, sitemaps: list[str], start: str, limit: int) -> list[str]:
        found: list[str] = []
        todo, seen = deque(sitemaps), set()
        while todo and len(found) < limit and len(seen) < 20:
            sm = todo.popleft()
            if sm in seen:
                continue
            seen.add(sm)
            try:
                r = self.client.get(sm)
                if r.status_code != 200:
                    continue
                data = r.content
                if sm.endswith(".gz") or data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
                root = etree.fromstring(data, parser=etree.XMLParser(recover=True, resolve_entities=False))
            except (httpx.HTTPError, OSError, etree.XMLSyntaxError, ValueError):
                continue
            if root is None:
                continue
            locs = [el.text.strip() for el in root.iter("{*}loc") if el.text]
            if root.tag.endswith("sitemapindex"):
                todo.extend(locs[:20])
            else:
                for u in locs:
                    n = normalize_link(start, u)
                    if n and same_site(n, start):
                        found.append(n)
        return found[:limit]

    # ------------------------------------------------------------ fetching

    def _render(self, url: str) -> str | None:
        try:
            if self._browser is None:
                from .. import runtime
                runtime.ensure_browser(lambda m: self._progress("pages", m))
                from playwright.sync_api import sync_playwright
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch(headless=True)
            page = self._browser.new_page(user_agent=USER_AGENT)
            try:
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2500)
                return page.content()
            finally:
                page.close()
        except Exception:
            return None

    def _fetch(self, url: str) -> dict | None:
        t0 = time.perf_counter()
        html, status, final_url, size = None, None, url, None
        if self.o.render != "always":
            try:
                r = self.client.get(url)
                status, final_url, size = r.status_code, str(r.url), len(r.content)
                ctype = r.headers.get("content-type", "")
                if "html" not in ctype and "xml" not in ctype:
                    return None
                html = r.text
            except httpx.HTTPError:
                status = None
        elapsed = int((time.perf_counter() - t0) * 1000)
        page = extract_page(html, final_url, status, elapsed, size) if html else None
        if self.o.render != "never" and (page is None or self.o.render == "always" or needs_browser(page, html or "")):
            rendered = self._render(url)
            if rendered:
                page = extract_page(rendered, final_url, status or 200, elapsed, size)
                page["rendered"] = True
        return page

    @staticmethod
    def _site_title(page: dict, url: str, host: str) -> str:
        """Site name: declared og:site_name, else guess from the title.
        Home pages are usually "Site — tagline"; inner pages "Page | Site"."""
        sn = (page.get("site_name") or "").strip()
        looks_like_host = bool(re.fullmatch(r"[\w.-]+(:\d+)?", sn)) and "." in sn
        if sn and not looks_like_host:
            return sn
        parts = [p.strip() for p in re.split(r"\s[|\-–—·:]\s", page.get("title") or "") if p.strip()]
        if not parts:
            return host
        generic = {"home", "homepage", "home page", "welcome", "index", "start"}
        if urlparse(url).path in ("", "/") and parts[0].lower() not in generic:
            return parts[0]
        return parts[-1]

    # ------------------------------------------------------------ run

    def run(self) -> str:
        start = normalize_link(self.o.url, self.o.url)
        if not start:
            raise CrawlError("That doesn't look like a web address. Paste a link starting with https://")
        u = urlparse(start)
        root = f"{u.scheme}://{u.netloc}"
        self._progress("starting", "Checking the site…")
        try:
            sitemaps = self._load_robots(root)
            if not self._allowed(start):
                raise CrawlError("This site's robots.txt asks automated tools not to read this page, so PostLens won't.")

            queue: deque[str] = deque([start])
            seen = {start}
            if self.o.mode == "site":
                self._progress("discover", "Reading the sitemap…")
                for s in self._sitemap_urls(sitemaps, start, self.o.max_pages * 3):
                    if s not in seen:
                        seen.add(s)
                        queue.append(s)
            self.stats["pages_found"] = min(len(queue), self.o.max_pages)

            done = 0
            while queue and done < self.o.max_pages:
                self._check()
                url = queue.popleft()
                if not self._allowed(url):
                    continue
                self._progress("pages", f"Reading page {done + 1} of {self.stats['pages_found']}…")
                page = self._fetch(url)
                time.sleep(self.delay)
                if page is None:
                    self.stats["errors"] += 1
                    continue
                if (page.get("status") or 0) >= 400:
                    self.stats["errors"] += 1
                if not self.title:
                    self.title = self._site_title(page, url, u.netloc)
                links = page.pop("_links", [])
                if self.o.mode == "site":
                    for ln in links:
                        if ln not in seen and same_site(ln, start):
                            seen.add(ln)
                            queue.append(ln)
                    self.stats["pages_found"] = min(done + 1 + len(queue), self.o.max_pages)
                if page["word_count"] > 0 or (page.get("status") or 200) >= 400:
                    self.on_page(page)
                    done += 1
                    self.stats["pages_done"] = done
                    self.stats["words"] += page["word_count"]
            if done == 0:
                raise CrawlError("No readable pages found. The site may block automated access or need a login.")
        finally:
            self.client.close()
            try:
                if self._browser:
                    self._browser.close()
                if self._pw:
                    self._pw.stop()
            except Exception:
                pass
        self._progress("done", "Finished")
        return self.title or u.netloc
