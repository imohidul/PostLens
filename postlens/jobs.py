"""Run scrapes in background threads and keep their live progress in memory.

Playwright's synchronous API must be used from a single thread, so each
scrape gets its own worker thread. The web UI polls /api/jobs/{id}.
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Any

from . import db
from .config import LOG_DIR, load_settings
from .ai import index
from .scraper.facebook import Cancelled, FacebookScraper, ScrapeError, ScrapeOptions
from .web.crawler import Cancelled as CrawlCancelled
from .web.crawler import CrawlError, WebCrawler, WebOptions


class Job:
    def __init__(self, dataset_id: int) -> None:
        self.dataset_id = dataset_id
        self.cancel = threading.Event()
        self.state: dict[str, Any] = {
            "dataset_id": dataset_id, "status": "pending", "stage": "queued",
            "message": "Waiting to start…", "posts_found": 0, "posts_done": 0,
            "comments": 0, "started_at": time.time(), "error": None,
        }
        self.thread: threading.Thread | None = None


_jobs: dict[int, Job] = {}
_lock = threading.Lock()


def get(dataset_id: int) -> dict | None:
    j = _jobs.get(dataset_id)
    return dict(j.state) if j else None


def active() -> list[dict]:
    return [dict(j.state) for j in _jobs.values() if j.state["status"] in ("pending", "running")]


def cancel(dataset_id: int) -> bool:
    j = _jobs.get(dataset_id)
    if j and j.state["status"] in ("pending", "running"):
        j.cancel.set()
        return True
    return False


def start(url: str, range_days: int, max_posts: int | None = None) -> int:
    """Start a Facebook collection run."""
    with _lock:
        if active():
            raise ScrapeError("A collection is already running. Wait for it to finish or stop it.")
        s = load_settings()["scraper"]
        ds_id = db.create_dataset(url, range_days, "facebook")
        job = Job(ds_id)
        opts = ScrapeOptions(
            url=url,
            range_days=range_days,
            max_posts=int(max_posts or s["max_posts"]),
            max_comments_per_post=int(s["max_comments_per_post"]),
            headless=bool(s["headless"]),
            scroll_pause_ms=int(s["scroll_pause_ms"]),
        )
        job.thread = threading.Thread(target=_run_facebook, args=(job, opts), daemon=True, name=f"scrape-{ds_id}")
        _jobs[ds_id] = job
        job.thread.start()
        return ds_id


def start_website(url: str, mode: str, max_pages: int | None = None) -> int:
    """Start a website collection run."""
    with _lock:
        if active():
            raise ScrapeError("A collection is already running. Wait for it to finish or stop it.")
        w = load_settings()["web"]
        opts = WebOptions(url=url, mode=mode, max_pages=1 if mode == "page" else int(max_pages or w["max_pages"]),
                          render=w["render"], respect_robots=bool(w["respect_robots"]), delay_s=float(w["delay_s"]))
        ds_id = db.create_dataset(url, 0, "website", {"mode": mode, "max_pages": opts.max_pages})
        job = Job(ds_id)
        job.thread = threading.Thread(target=_run_website, args=(job, opts), daemon=True, name=f"crawl-{ds_id}")
        _jobs[ds_id] = job
        job.thread.start()
        return ds_id


def _progress_fn(job: Job):
    def on_progress(p: dict) -> None:
        job.state.update({k: v for k, v in p.items() if k in job.state or k in ("title", "pages_found", "pages_done", "words")})
        if p.get("title"):
            db.update_dataset(job.dataset_id, title=p["title"])
    return on_progress


def _finish(job: Job, runner, fallback_title: str) -> None:
    """Shared success/cancel/error handling + building the search index."""
    ds = job.dataset_id
    job.state["status"] = "running"
    db.update_dataset(ds, status="running")
    try:
        title = runner()
        job.state.update(stage="indexing", message="Preparing fast AI answers…")
        index.build_index(ds)
        db.update_dataset(ds, status="done", title=title or fallback_title, finished_at=time.time())
        job.state.update(status="done", stage="done", message="Finished")
    except (Cancelled, CrawlCancelled):
        # keep what we already collected - it is still useful
        index.build_index(ds)
        db.update_dataset(ds, status="cancelled", finished_at=time.time())
        job.state.update(status="cancelled", stage="cancelled", message="Stopped - partial data kept")
    except (ScrapeError, CrawlError) as e:
        db.update_dataset(ds, status="error", error=str(e), finished_at=time.time())
        job.state.update(status="error", stage="error", message=str(e), error=str(e))
    except Exception as e:  # unexpected - log the traceback for bug reports
        (LOG_DIR / f"run-{ds}.log").write_text(traceback.format_exc(), encoding="utf-8")
        msg = f"Unexpected error: {e}. Details saved in ~/.postlens/logs/run-{ds}.log"
        db.update_dataset(ds, status="error", error=msg, finished_at=time.time())
        job.state.update(status="error", stage="error", message=msg, error=msg)


def _run_facebook(job: Job, opts: ScrapeOptions) -> None:
    def on_post(post: dict, comments: list[dict]) -> None:
        pid = db.upsert_post(job.dataset_id, post)
        db.add_comments(pid, comments)

    _finish(job, lambda: FacebookScraper(opts, _progress_fn(job), on_post, job.cancel).run(), "Facebook page")


def _run_website(job: Job, opts: WebOptions) -> None:
    job.state.update(pages_found=0, pages_done=0, words=0)
    _finish(job, lambda: WebCrawler(opts, _progress_fn(job), lambda p: db.upsert_page(job.dataset_id, p), job.cancel).run(),
            "Website")
