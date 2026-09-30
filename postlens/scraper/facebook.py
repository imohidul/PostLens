"""Drive a real Chromium browser to read a Facebook page's posts and comments.

How it works
------------
1. The browser uses a persistent profile stored in ~/.postlens/browser-profile.
   The user logs in to Facebook ONCE in a normal browser window (we never see
   or store the password - Facebook sets a session cookie in that profile).
2. For a page/profile/group link we scroll the feed and listen to the
   GraphQL JSON the Facebook web app downloads (see graphql_parser.py).
   We stop when posts are older than the chosen date range, when we reach
   the post limit, or when nothing new loads.
3. For each post we open its permalink, switch comment sorting to
   "All comments", click "View more comments" until the limit, and collect
   the comment JSON.
4. If Facebook's JSON can't be read, we fall back to reading visible text.

Everything is slow on purpose (pauses between actions). Fast, aggressive
scrolling is what gets accounts rate-limited.
"""
from __future__ import annotations

import random
import re
import shutil
import threading
import time
from dataclasses import dataclass
from typing import Callable

from ..anonymize import key as make_key
from ..anonymize import scrub
from .. import runtime
from ..config import BROWSER_PROFILE_DIR, ensure_dirs
from . import selectors as S
from .graphql_parser import GraphQLCollector

PROFILE_LOCK = threading.Lock()  # a browser profile can only be open once


class ScrapeError(Exception):
    """Error with a message that is safe to show the user."""


class NotLoggedIn(ScrapeError):
    pass


class Cancelled(ScrapeError):
    pass


@dataclass
class ScrapeOptions:
    url: str
    range_days: int = 30
    max_posts: int = 60
    max_comments_per_post: int = 150
    headless: bool = False
    scroll_pause_ms: int = 1800


ProgressFn = Callable[[dict], None]
PostFn = Callable[[dict, list[dict]], None]


# ---------------------------------------------------------------- browser

def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise ScrapeError("Playwright is not installed. Run the installer again.") from e
    return sync_playwright()


def _open_context(p, headless: bool):
    ensure_dirs()
    try:
        runtime.ensure_browser()
    except RuntimeError as e:
        raise ScrapeError(str(e)) from e
    try:
        return p.chromium.launch_persistent_context(
            str(BROWSER_PROFILE_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            args=["--disable-blink-features=AutomationControlled"],
        )
    except Exception as e:
        msg = str(e)
        if "Executable doesn't exist" in msg:
            raise ScrapeError("Browser not installed. Run: python -m playwright install chromium") from e
        raise ScrapeError(f"Could not start the browser: {msg.splitlines()[0]}") from e


def _is_logged_in(ctx) -> bool:
    return any(c["name"] == "c_user" for c in ctx.cookies("https://www.facebook.com"))


def check_login(timeout: float = 20) -> bool | None:
    """True/False, or None if the browser is busy with a scrape."""
    if not PROFILE_LOCK.acquire(timeout=0.1):
        return None
    try:
        if not BROWSER_PROFILE_DIR.exists() or not any(BROWSER_PROFILE_DIR.iterdir()):
            return False
        with _playwright() as p:
            ctx = _open_context(p, headless=True)
            try:
                return _is_logged_in(ctx)
            finally:
                ctx.close()
    finally:
        PROFILE_LOCK.release()


def interactive_login(timeout_s: int = 300) -> bool:
    """Open a visible browser on the Facebook login page and wait until the
    user has logged in (session cookie appears) or closes the window."""
    if not PROFILE_LOCK.acquire(timeout=1):
        raise ScrapeError("The browser is busy with a scrape. Try again when it finishes.")
    try:
        with _playwright() as p:
            ctx = _open_context(p, headless=False)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                if _is_logged_in(ctx):
                    page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
                    time.sleep(1.5)
                    return True
                page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
                end = time.time() + timeout_s
                while time.time() < end:
                    if not ctx.pages:  # user closed the window
                        return False
                    if _is_logged_in(ctx):
                        time.sleep(2)  # let Facebook finish its redirects
                        return True
                    time.sleep(1.5)
                return False
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
    finally:
        PROFILE_LOCK.release()


def logout() -> None:
    """Forget the Facebook session by deleting the browser profile."""
    with PROFILE_LOCK:
        shutil.rmtree(BROWSER_PROFILE_DIR, ignore_errors=True)
        ensure_dirs()


# ---------------------------------------------------------------- helpers

def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    url = re.sub(r"^https?://(m|mbasic|web|touch|mobile)\.facebook\.com", "https://www.facebook.com", url, flags=re.I)
    url = re.sub(r"^https?://facebook\.com", "https://www.facebook.com", url, flags=re.I)
    url = re.sub(r"^https?://fb\.com", "https://www.facebook.com", url, flags=re.I)
    if not re.match(r"^https://(www\.)?facebook\.com/", url, re.I):
        raise ScrapeError("Please paste a facebook.com link.")
    return url


def is_single_post(url: str) -> bool:
    return bool(S.SINGLE_POST_URL.search(url))


def _pause(opts: ScrapeOptions, factor: float = 1.0) -> None:
    base = opts.scroll_pause_ms / 1000 * factor
    time.sleep(base * random.uniform(0.75, 1.35))


def _page_state(page) -> str | None:
    try:
        body = (page.inner_text("body", timeout=5000) or "").lower()[:4000]
    except Exception:
        return None
    if any(h in body for h in S.CONTENT_UNAVAILABLE_HINTS):
        return "unavailable"
    if any(h in body for h in S.LOGIN_WALL_HINTS) and "/login" in page.url:
        return "login"
    return None


def _feed_embedded_json(page, collector: GraphQLCollector) -> None:
    """The first posts arrive inside <script type="application/json"> tags,
    not through GraphQL requests."""
    try:
        blobs = page.eval_on_selector_all(
            'script[type="application/json"]',
            "els => els.map(e => e.textContent).filter(t => t && (t.includes('creation_time') || t.includes('\"Comment\"')))",
        )
    except Exception:
        return
    for b in blobs:
        try:
            collector.feed(b)
        except Exception:
            continue


def _click_text_button(page, pattern: re.Pattern, limit: int = 3) -> int:
    clicked = 0
    try:
        buttons = page.get_by_role("button", name=pattern)
        n = min(buttons.count(), limit)
        for i in range(n):
            b = buttons.nth(i)
            if b.is_visible():
                b.click(timeout=3000)
                clicked += 1
                time.sleep(random.uniform(0.6, 1.2))
    except Exception:
        pass
    return clicked


def _choose_all_comments(page) -> None:
    try:
        btn = page.get_by_role("button", name=S.SORT_BUTTON_TEXT).first
        if btn.count() and btn.is_visible():
            btn.click(timeout=3000)
            time.sleep(1.0)
            item = page.get_by_role("menuitem", name=S.ALL_COMMENTS_TEXT).first
            if item.count():
                item.click(timeout=3000)
                time.sleep(1.5)
            else:
                page.keyboard.press("Escape")
    except Exception:
        pass


def _dom_post_texts(page) -> list[str]:
    try:
        texts = page.eval_on_selector_all(S.POST_MESSAGE, "els => els.map(e => e.innerText)")
    except Exception:
        return []
    return [t for t in (scrub(x) for x in texts) if t]


def _dom_comment_texts(page) -> list[str]:
    """Fallback: read comment bubbles. We read only the text node(s) of the
    comment body, never the author link."""
    js = """
    els => els
      .filter(a => (a.getAttribute('aria-label') || '').toLowerCase().startsWith('comment') ||
                   (a.getAttribute('aria-label') || '').toLowerCase().startsWith('reply'))
      .map(a => Array.from(a.querySelectorAll('div[dir="auto"]'))
                  .filter(d => !d.closest('a'))
                  .map(d => d.innerText).join('\\n'))
    """
    try:
        texts = page.eval_on_selector_all(S.ARTICLE, js)
    except Exception:
        return []
    return [t for t in (scrub(x) for x in texts) if t]


# ---------------------------------------------------------------- main

class FacebookScraper:
    def __init__(self, opts: ScrapeOptions, on_progress: ProgressFn, on_post: PostFn,
                 cancel: threading.Event) -> None:
        self.opts = opts
        self.on_progress = on_progress
        self.on_post = on_post
        self.cancel = cancel
        self.collector = GraphQLCollector()
        self.title = ""
        self.stats = {"posts_found": 0, "posts_done": 0, "comments": 0}

    # -- plumbing --
    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled("Cancelled")

    def _progress(self, stage: str, message: str) -> None:
        self.on_progress({"stage": stage, "message": message, **self.stats, "title": self.title})

    def _on_response(self, resp) -> None:
        try:
            if S.GRAPHQL_URL_PART in resp.url and resp.status == 200:
                self.collector.feed(resp.text())
        except Exception:
            pass  # body not available (redirect, aborted) - ignore

    # -- run --
    def run(self) -> str:
        opts = self.opts
        opts.url = normalize_url(opts.url)
        if not PROFILE_LOCK.acquire(timeout=2):
            raise ScrapeError("Another scrape is already running.")
        try:
            try:
                runtime.ensure_browser(lambda m: self._progress("starting", m))
            except RuntimeError as e:
                raise ScrapeError(str(e)) from e
            with _playwright() as p:
                self._progress("starting", "Opening browser…")
                ctx = _open_context(p, opts.headless)
                try:
                    if not _is_logged_in(ctx):
                        raise NotLoggedIn("Connect your Facebook account first (Settings → Facebook).")
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.on("response", self._on_response)
                    self._open(page, opts.url)
                    if is_single_post(opts.url):
                        story = self._best_story_for_single_post()
                        story = story or {"sid": opts.url, "text": "", "url": opts.url}
                        story["url"] = opts.url
                        self.stats["posts_found"] = 1
                        self._scrape_post(page, story, already_open=True)
                    else:
                        stories = self._collect_feed(page)
                        for s in stories:
                            self._check_cancel()
                            self._scrape_post(page, s)
                            _pause(opts, 0.8)
                finally:
                    try:
                        ctx.close()
                    except Exception:
                        pass
        finally:
            PROFILE_LOCK.release()
        self._progress("done", "Finished")
        return self.title

    def _open(self, page, url: str) -> None:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            raise ScrapeError(f"Could not open the link: {str(e).splitlines()[0]}") from e
        time.sleep(3)
        state = _page_state(page)
        if state == "login":
            raise NotLoggedIn("Facebook asked to log in again. Reconnect your account in Settings.")
        if state == "unavailable":
            raise ScrapeError("Facebook says this content isn't available (private, deleted, or restricted).")
        if not self.title:
            t = (page.title() or "").replace("| Facebook", "").strip()
            self.title = re.sub(r"^\(\d+\)\s*", "", t) or "Facebook page"  # drop "(3) " notification counter
        _feed_embedded_json(page, self.collector)

    def _best_story_for_single_post(self) -> dict | None:
        stories = [s for s in self.collector.story_list() if s.get("text")]
        return max(stories, key=lambda s: len(s["text"]), default=None)

    def _collect_feed(self, page) -> list[dict]:
        opts = self.opts
        cutoff = time.time() - opts.range_days * 86400
        no_growth = 0
        last = 0
        for i in range(400):  # hard ceiling
            self._check_cancel()
            stories = self.collector.story_list()
            dated = [s for s in stories if s.get("created_at")]
            in_range = [s for s in stories if not s.get("created_at") or s["created_at"] >= cutoff]
            older = [s for s in dated if s["created_at"] < cutoff]
            self.stats["posts_found"] = len(in_range)
            self._progress("feed", f"Scrolling the page… {len(in_range)} posts in range")

            if len(in_range) >= opts.max_posts:
                break
            # Pinned/featured posts can be old, so require several old ones.
            if len(older) >= 3:
                break
            if len(stories) == last:
                no_growth += 1
                if no_growth >= 6:
                    break
            else:
                no_growth = 0
            last = len(stories)

            page.mouse.wheel(0, random.randint(1800, 2800))
            _pause(opts)

        stories = [s for s in self.collector.story_list() if not s.get("created_at") or s["created_at"] >= cutoff]
        stories.sort(key=lambda s: s.get("created_at") or 0, reverse=True)
        stories = stories[: opts.max_posts]

        if not stories:  # fallback: visible text only
            texts = _dom_post_texts(page)
            stories = [{"sid": make_key("dom", t[:200]), "text": t, "url": None, "created_at": None} for t in texts]
            stories = stories[: opts.max_posts]
        self.stats["posts_found"] = len(stories)
        if not stories:
            raise ScrapeError(
                "No posts found. The page may be private, have no posts in this date range, "
                "or Facebook's layout changed (see README → Troubleshooting)."
            )
        return stories

    def _scrape_post(self, page, story: dict, already_open: bool = False) -> None:
        opts = self.opts
        self._check_cancel()
        n = self.stats["posts_done"] + 1
        self._progress("comments", f"Reading comments for post {n} of {self.stats['posts_found']}…")

        # Comments already seen in the feed for this post (preview comments)
        comments = {k: c for k, c in self.collector.comments.items()
                    if self.collector.comment_story.get(k) == story.get("sid")}

        url = story.get("url")
        if url and not already_open:
            # fresh collector so comments are attributed to this post only
            self.collector_backup, self.collector = self.collector, GraphQLCollector()
            try:
                self._open(page, url)
                self._expand_comments(page)
                comments.update(self.collector.comments)
                # the post page may carry a fuller text / timestamp
                better = self._best_story_for_single_post()
                if better:
                    for k in ("text", "created_at", "reactions", "comment_total", "shares"):
                        if not story.get(k) and better.get(k):
                            story[k] = better[k]
            except ScrapeError:
                pass  # skip a broken post, keep going
            finally:
                self.collector = self.collector_backup
        elif already_open:
            self._expand_comments(page)
            comments.update(self.collector.comments)
            better = self._best_story_for_single_post()
            if better:
                for k in ("text", "created_at", "reactions", "comment_total", "shares"):
                    if not story.get(k) and better.get(k):
                        story[k] = better[k]

        clist = list(comments.values())
        if not clist and url:
            clist = [{"ext_key": make_key("domc", t), "text": t, "created_at": None} for t in _dom_comment_texts(page)]
        clist = clist[: opts.max_comments_per_post]

        post = {
            "ext_key": make_key("p", story.get("sid") or url),
            "text": story.get("text") or "(photo or video without a caption)",
            "created_at": story.get("created_at"),
            "reactions": story.get("reactions"),
            "shares": story.get("shares"),
            "comment_total": story.get("comment_total"),
        }
        self.on_post(post, clist)
        self.stats["posts_done"] += 1
        self.stats["comments"] += len(clist)

    def _expand_comments(self, page) -> None:
        opts = self.opts
        _choose_all_comments(page)
        stalls = 0
        for _ in range(60):
            self._check_cancel()
            have = len(self.collector.comments)
            if have >= opts.max_comments_per_post:
                break
            clicked = _click_text_button(page, S.MORE_COMMENTS_TEXT, limit=2)
            clicked += _click_text_button(page, S.MORE_REPLIES_TEXT, limit=2)
            page.mouse.wheel(0, random.randint(900, 1600))
            _pause(opts, 0.7)
            if len(self.collector.comments) == have and not clicked:
                stalls += 1
                if stalls >= 3:
                    break
            else:
                stalls = 0
