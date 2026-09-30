"""Website collection against a small local test site (no internet needed)."""
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from postlens.web.analysis import site_overview
from postlens.web.crawler import WebCrawler, WebOptions
from postlens.web.extract import extract_page, normalize_link

ARTICLE = "<p>" + " ".join(["PostLens reads websites and explains what they say about delivery and pricing."] * 20) + "</p>"


def page(title, body, links="", desc=True):
    meta = '<meta name="description" content="A test page">' if desc else ""
    return (f"<html lang='en'><head><title>{title} | TestSite</title>{meta}</head><body>"
            f"<nav><a href='/'>Home</a> <a href='/about'>About</a> {links}</nav>"
            f"<main><h1>{title}</h1>{body}<p>Contact us at team@example.com or +880 1712 345678.</p></main>"
            f"<footer>Copyright footer text</footer></body></html>")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    (root / "index.html").write_text(page("Home", ARTICLE, "<a href='/blog/post1.html?utm_source=x'>Post</a>"))
    (root / "about").mkdir()
    (root / "about" / "index.html").write_text(page("About", ARTICLE, desc=False))
    (root / "blog").mkdir()
    (root / "blog" / "post1.html").write_text(page("Post one", ARTICLE + "<img src='a.png'>"))
    (root / "private").mkdir()
    (root / "private" / "index.html").write_text(page("Secret", ARTICLE))
    (root / "robots.txt").write_text("User-agent: *\nDisallow: /private/\n")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
    srv.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    (root / "sitemap.xml").write_text(
        f"<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        f"<url><loc>{base}/private/</loc></url><url><loc>{base}/about/</loc></url></urlset>")
    yield base
    srv.shutdown()


def test_normalize_link_strips_tracking_and_assets():
    assert normalize_link("https://a.com/x/", "../y?utm_source=z&id=2#top") == "https://a.com/y?id=2"
    assert normalize_link("https://a.com/", "/logo.png") is None
    assert normalize_link("https://a.com/", "mailto:a@b.c") is None


def test_extract_main_content_and_privacy():
    p = extract_page(page("Hello", ARTICLE), "https://a.com/")
    assert "delivery and pricing" in p["text"]
    assert "Copyright footer" not in p["text"]          # boilerplate removed
    assert "team@example.com" not in p["text"] and "1712" not in p["text"]
    assert p["meta"]["h1_count"] == 1 and p["title"].startswith("Hello")


def test_crawl_site_respects_robots_and_uses_sitemap(site):
    got = []
    c = WebCrawler(WebOptions(url=site + "/", mode="site", max_pages=10, render="never", delay_s=0),
                   lambda p: None, got.append, threading.Event())
    title = c.run()
    urls = {p["url"] for p in got}
    assert title == "TestSite"
    assert any(u.endswith("/about/") for u in urls)          # from sitemap
    assert any("post1.html" in u and "utm" not in u for u in urls)  # from links, tracking removed
    assert not any("/private/" in u for u in urls)           # robots.txt obeyed
    for i, p in enumerate(got):
        p["id"], p["rendered"] = i, False
    ov = site_overview(got)
    names = {i["title"] for i in ov["issues"]}
    assert "Missing meta description" in names and "Images without alt text" in names


def test_single_page_mode(site):
    got = []
    WebCrawler(WebOptions(url=site + "/about/", mode="page", max_pages=1, render="never", delay_s=0),
               lambda p: None, got.append, threading.Event()).run()
    assert len(got) == 1
