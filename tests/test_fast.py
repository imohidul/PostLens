"""Fast-reply pipeline and Local AI hardware gate."""
import json
from pathlib import Path

import numpy as np
import pytest

from postlens import hardware

CATALOG = json.loads((Path(__file__).resolve().parents[1] / "postlens" / "data" / "models.json").read_text())


def hw(**kw):
    base = {"os": "Windows", "arch": "amd64", "ram_gb": 32, "free_disk_gb": 200, "apple_silicon": False,
            "unified_gb": None, "gpus": []}
    base.update(kw)
    return base


@pytest.mark.parametrize("info,tier", [
    (hw(gpus=[]), None),                                                                   # CPU only
    (hw(gpus=[{"vendor": "NVIDIA", "name": "RTX 3050", "vram_gb": 6}]), None),              # too little VRAM
    (hw(gpus=[{"vendor": "Intel", "name": "Arc", "vram_gb": 16}]), None),                   # not accelerated
    (hw(ram_gb=8, gpus=[{"vendor": "NVIDIA", "name": "RTX 4060", "vram_gb": 8}]), None),    # too little RAM
    (hw(gpus=[{"vendor": "NVIDIA", "name": "RTX 4060", "vram_gb": 8}]), "standard"),
    (hw(gpus=[{"vendor": "AMD", "name": "RX 7700 XT", "vram_gb": 12}]), "plus"),
    (hw(gpus=[{"vendor": "NVIDIA", "name": "RTX 4090", "vram_gb": 24}]), "pro"),
    (hw(os="Darwin", apple_silicon=True, ram_gb=8, unified_gb=8), None),
    (hw(os="Darwin", apple_silicon=True, ram_gb=16, unified_gb=16), "standard"),
    (hw(os="Darwin", apple_silicon=True, ram_gb=48, unified_gb=48), "pro"),
    (hw(free_disk_gb=5, gpus=[{"vendor": "NVIDIA", "name": "RTX 4090", "vram_gb": 24}]), None),
])
def test_hardware_tiers(info, tier):
    a = hardware.assess(info, CATALOG)
    assert (a["tier"]["id"] if a["tier"] else None) == tier
    if tier is None:
        assert a["reasons"], "unsupported machines must get a plain-language reason"


def test_local_ai_hidden_when_unsupported(monkeypatch):
    from fastapi.testclient import TestClient

    from postlens import server
    from postlens.ai import local
    monkeypatch.setattr(local, "supported", lambda: False)
    with TestClient(server.app) as c:
        ids = [p["id"] for p in c.get("/api/ai/providers").json()["providers"]]
    assert "ollama" not in ids and "openai" in ids


def test_hybrid_rank_fuses_semantic_and_keyword(monkeypatch):
    from postlens.ai import index
    chunks = [{"text": "[Page #1]\nOur prices and shipping costs"},
              {"text": "[Page #2]\nডেলিভারি সময় তিন দিন"},          # Bangla: "delivery takes three days"
              {"text": "[Page #3]\nMeet the team"}]
    vecs = np.eye(3, dtype=np.float32)
    for c, v in zip(chunks, vecs):
        c["embedding"] = v.tobytes()
    # Fake embedder: the English question is semantically closest to the Bangla chunk
    monkeypatch.setattr(index, "embed", lambda texts: np.array([[0.1, 0.99, 0.0]], dtype=np.float32))
    order = index.hybrid_rank("how long does delivery take", chunks)
    assert order[0] == 1  # found despite zero shared keywords


def test_prompt_prefix_is_stable_and_answers_are_cached(monkeypatch):
    """The system prompt must be identical for every question (so providers
    can cache it) and a repeated opening question must come from the cache."""
    from postlens import db
    from postlens.ai import assistant, index, providers
    from postlens.demo import create_demo
    db.init()
    monkeypatch.setattr(index, "embed", lambda texts: None)
    ds_id = create_demo()
    ds = db.get_dataset(ds_id)
    s1, _, complete = assistant.build_prompt(ds, 24000)
    s2, _, _ = assistant.build_prompt(ds, 24000)
    assert s1 == s2 and complete

    calls = []

    def fake_stream(ai, provider, model, messages, cache_key=""):
        calls.append(messages)
        yield "Answer"

    monkeypatch.setattr(assistant, "resolve_model", lambda ai: ("openai", "gpt-test"))
    monkeypatch.setattr(assistant, "stream_chat", fake_stream)
    chat1, chat2 = db.create_chat(ds_id), db.create_chat(ds_id)
    ev1 = list(assistant.answer(chat1, ds_id, "What do people complain about?"))
    ev2 = list(assistant.answer(chat2, ds_id, "what do people complain about"))
    assert len(calls) == 1                                  # second one never hit the AI
    assert ev2[-1]["meta"]["cached"] is True
    assert calls[0][0]["content"] == s1                     # prefix unchanged by the question
    assert "".join(e["text"] for e in ev2 if e["type"] == "token") == "Answer"
