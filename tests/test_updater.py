"""Automatic updates: version comparison, the GitHub check, verified
downloads, and the pieces of the release pipeline the updater relies on."""
import hashlib
import io
import re
from pathlib import Path

import pytest

from postlens import __version__, updater

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "UPDATES_DIR", tmp_path / "updates")
    monkeypatch.setattr(updater, "_ready_path", None)
    monkeypatch.setattr(updater, "asset_name", lambda: "postlens.exe")
    monkeypatch.setattr(updater, "state", dict(updater.state, status="idle", available=False, latest=None, error=""))
    updater._asset.clear()
    yield
    updater._asset.clear()


def release(tag, data=b"", name="postlens.exe", digest=True):
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/imohidul/PostLens/releases/tag/{tag}",
        "body": "notes",
        "assets": [{
            "name": name,
            "size": len(data),
            "browser_download_url": f"https://example.invalid/{name}",
            **({"digest": "sha256:" + hashlib.sha256(data).hexdigest()} if digest else {}),
        }],
    }


class FakeResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


@pytest.mark.parametrize("a,b", [("1.0.1", "1.0.0"), ("1.0.10", "1.0.9"), ("v2.0.0", "1.9.9"), ("1.1", "1.0.5")])
def test_newer_versions(a, b):
    assert updater.is_newer(a, b)
    assert not updater.is_newer(b, a)


@pytest.mark.parametrize("a,b", [("1.0.0", "1.0"), ("v1.0.1", "1.0.1"), ("1.0.1", "1.0.1")])
def test_same_versions_are_not_updates(a, b):
    assert not updater.is_newer(a, b)


def test_check_finds_a_newer_release():
    s = updater.check(fetch=lambda url: release("v99.0.0", b"x"))
    assert s["available"] and s["latest"] == "99.0.0"
    assert updater._asset["url"].endswith("postlens.exe")
    assert updater._asset["sha256"] == hashlib.sha256(b"x").hexdigest()
    assert not s["can_install"]  # tests run from source, never the installed app


def test_check_ignores_the_current_version():
    s = updater.check(fetch=lambda url: release(f"v{__version__}"))
    assert not s["available"] and s["status"] == "idle"


def test_check_survives_being_offline():
    def offline(url):
        raise OSError("no network")
    s = updater.check(fetch=offline)
    assert s["status"] == "error" and not s["available"]


def test_download_verifies_the_checksum():
    data = b"installer bytes" * 1000
    updater.check(fetch=lambda url: release("v99.0.0", data))
    assert updater.download(opener=lambda url: FakeResponse(data))
    assert updater.state["status"] == "ready"
    assert updater._ready_path.read_bytes() == data
    assert updater._ready_path.name == "postlens-99.0.0.exe"


def test_download_rejects_a_tampered_file():
    data = b"real installer"
    updater.check(fetch=lambda url: release("v99.0.0", data))
    assert not updater.download(opener=lambda url: FakeResponse(b"evil installe"[: len(data)].ljust(len(data), b"!")))
    assert updater.state["status"] == "error"
    assert not any(updater.UPDATES_DIR.iterdir())  # nothing left behind


def test_nothing_is_installed_when_running_from_source():
    assert updater.start_installer(relaunch=True) is False


def test_release_pipeline_publishes_the_files_the_updater_downloads():
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "files: dist/postlens.exe" in wf
    assert "files: dist/postlens.dmg" in wf
    assert "OutputBaseFilename=postlens" in (ROOT / "packaging" / "windows" / "installer.iss").read_text(encoding="utf-8")
    assert 'OUT="$ROOT/dist/postlens.dmg"' in (ROOT / "packaging" / "macos" / "make_dmg.sh").read_text(encoding="utf-8")


def test_windows_installer_reopens_the_app_after_an_automatic_update():
    iss = (ROOT / "packaging" / "windows" / "installer.iss").read_text(encoding="utf-8")
    assert re.search(r"Check: ShouldRelaunch", iss)
    assert "{param:RELAUNCH|0}" in iss
    assert "/RELAUNCH=" in (ROOT / "postlens" / "updater.py").read_text(encoding="utf-8")


def test_update_api():
    from fastapi.testclient import TestClient

    from postlens import server

    with TestClient(server.app) as c:
        r = c.get("/api/update").json()
        assert r["current"] == __version__ and r["auto"] is True
        # nothing downloaded yet -> refuse to restart
        assert c.post("/api/update/install").status_code == 409
        # from source the app can't replace itself
        assert c.post("/api/update/download").status_code == 400
