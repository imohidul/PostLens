"""Provider tests against a local fake server that speaks each provider's
documented streaming format. No real API keys or network needed.

These prove our parsing and error handling; they can't prove the real
services behave identically, so test with real keys before a release."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

FAKE_KEY = "sk-test-FAKEKEY-1234567890abcdef"


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth_ok(self):
        h = self.headers
        return FAKE_KEY in (h.get("Authorization", ""), h.get("x-api-key", ""), h.get("x-goog-api-key", "")) or \
            h.get("Authorization") == f"Bearer {FAKE_KEY}"

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def _sse(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for e in events:
            self.wfile.write(f"data: {e}\n\n".encode())

    def do_GET(self):
        if not self._auth_ok():
            # real providers sometimes echo part of the key in errors
            return self._json(401, {"error": {"message": f"Incorrect API key provided: {self.headers.get('Authorization','')}"}})
        p = self.path.split("?")[0]
        if p.endswith("/openai/models"):
            return self._json(200, {"data": [
                {"id": "gpt-9-mini", "created": 3}, {"id": "gpt-9", "created": 2},
                {"id": "gpt-9-realtime", "created": 4}, {"id": "text-embedding-9", "created": 5}]})
        if p.endswith("/anthropic/models"):
            return self._json(200, {"data": [
                {"id": "claude-opus-9", "display_name": "Claude Opus 9"},
                {"id": "claude-sonnet-9", "display_name": "Claude Sonnet 9"}]})
        if p.endswith("/gemini/models"):
            return self._json(200, {"models": [
                {"name": "models/gemini-9-flash", "displayName": "Gemini 9 Flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-9-pro", "displayName": "Gemini 9 Pro", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/text-embedding-9", "supportedGenerationMethods": ["embedContent"]}]})
        self._json(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.last = {"path": self.path, "body": body, "headers": dict(self.headers)}
        if not self._auth_ok():
            return self._json(401, {"error": {"message": "bad key"}})
        if "/openai/chat/completions" in self.path:
            return self._sse([json.dumps({"choices": [{"delta": {"content": t}}]}) for t in ("Hel", "lo")] + ["[DONE]"])
        if "/anthropic/messages" in self.path:
            return self._sse([json.dumps(e) for e in (
                {"type": "message_start"}, {"type": "ping"},
                {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "hmm"}},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}},
                {"type": "message_stop"})])
        if "streamGenerateContent" in self.path:
            return self._sse([json.dumps({"candidates": [{"content": {"parts": p}}]}) for p in (
                [{"text": "thinking...", "thought": True}], [{"text": "Hel"}], [{"text": "lo"}])])
        self._json(404, {})


@pytest.fixture()
def fake(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    from postlens.ai import providers
    monkeypatch.setattr(providers, "BASE", {p: f"{base}/{p}" for p in ("openai", "anthropic", "gemini", "groq")})
    from postlens import keystore
    store = {}
    monkeypatch.setattr(keystore, "get", lambda n: store.get(n, ""))
    monkeypatch.setattr(keystore, "put", lambda n, v: store.__setitem__(n, v))
    monkeypatch.setattr(keystore, "remove", lambda n: store.pop(n, None))
    yield providers, store
    srv.shutdown()


MSGS = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]


@pytest.mark.parametrize("pid,expected_default", [
    ("openai", "gpt-9-mini"), ("anthropic", "claude-sonnet-9"), ("gemini", "gemini-9-flash")])
def test_models_filter_and_default(fake, pid, expected_default):
    providers, _ = fake
    models = providers.list_models(pid, FAKE_KEY)
    ids = [m["id"] for m in models]
    assert "gpt-9-realtime" not in ids and "text-embedding-9" not in ids
    assert providers.default_model(pid, models) == expected_default


@pytest.mark.parametrize("pid", ["openai", "anthropic", "gemini"])
def test_streaming_skips_thinking(fake, pid):
    providers, store = fake
    store[pid] = FAKE_KEY
    ai = {"temperature": 0.3, "ollama_url": ""}
    out = "".join(providers.stream_chat(ai, pid, "m", MSGS, cache_key="ds-1"))
    assert out == "Hello"
    sent = Fake.last
    if pid == "anthropic":  # system prompt is marked cacheable for fast follow-ups
        assert sent["body"]["system"] == [{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]
        assert sent["body"]["max_tokens"] > 0
    if pid == "openai":
        assert sent["body"]["prompt_cache_key"] == "ds-1"
    if pid == "gemini":
        assert sent["body"]["systemInstruction"]["parts"][0]["text"] == "SYS"
        assert FAKE_KEY not in sent["path"]  # key must be in a header, never the URL


def test_bad_key_error_never_contains_key(fake):
    providers, _ = fake
    wrong = "sk-WRONG-abcdefghijklmnop"
    with pytest.raises(providers.AIError) as e:
        providers.list_models("openai", wrong)
    assert "wrong" not in str(e.value).lower() and "abcdefgh" not in str(e.value)
