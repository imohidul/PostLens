"""AI providers: OpenAI, Anthropic (Claude), Google (Gemini), Groq, and
Ollama (runs on the user's own computer).

Every provider exposes the same three operations:
  list_models(key)  -> [{id, label}]   also used to verify an API key
  stream(...)       -> yields text pieces as the model writes them
  default_model()   -> sensible pick from the list when the user hasn't chosen

Model lists are fetched live from each provider, so new models show up
without updating PostLens.

Security: API keys are read from the OS vault (keystore.py) only when a
request is made, are sent only to that provider's official API host, and
are scrubbed from any error text before it reaches the UI.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterator

import httpx

from .. import keystore

TIMEOUT = httpx.Timeout(10, read=300)
MAX_OUTPUT_TOKENS = 4096


class AIError(Exception):
    """Message that is safe to show the user (keys already removed)."""


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    tagline: str
    needs_key: bool
    key_url: str = ""
    key_hint: str = ""  # what a key looks like, shown as placeholder


PROVIDERS: dict[str, ProviderInfo] = {
    "openai": ProviderInfo("openai", "OpenAI", "ChatGPT models", True,
                           "https://platform.openai.com/api-keys", "sk-…"),
    "anthropic": ProviderInfo("anthropic", "Anthropic", "Claude models", True,
                              "https://console.anthropic.com/settings/keys", "sk-ant-…"),
    "gemini": ProviderInfo("gemini", "Google", "Gemini models", True,
                           "https://aistudio.google.com/app/apikey", "AIza…"),
    "groq": ProviderInfo("groq", "Groq", "Fast open models · free tier", True,
                         "https://console.groq.com/keys", "gsk_…"),
    "ollama": ProviderInfo("ollama", "On this computer", "Free & private · via Ollama", False),
}

BASE = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "groq": "https://api.groq.com/openai/v1",
}
ANTHROPIC_VERSION = "2023-06-01"


# ------------------------------------------------------------------ helpers

def _fail(provider: str, r: httpx.Response, key: str) -> AIError:
    try:
        r.read()
    except Exception:
        pass
    try:
        body = r.json()
        err = body.get("error") if isinstance(body, dict) else None
        msg = (err.get("message") if isinstance(err, dict) else err) or r.text
    except ValueError:
        msg = r.text
    msg = keystore.redact(str(msg), key)[:300]
    name = PROVIDERS[provider].name
    if r.status_code in (401, 403):
        return AIError(f"{name} rejected the API key. Check it in Settings → AI.")
    if r.status_code == 404:
        return AIError(f"{name} doesn't offer the selected model to this key. Pick another model in Settings.")
    if r.status_code == 429:
        return AIError(f"{name} rate limit or quota reached. Wait a moment, check your plan, or lower 'Context size'. ({msg})")
    if r.status_code == 413 or "too large" in msg.lower() or "context length" in msg.lower():
        return AIError(f"Too much text for this model. Lower 'Context size' in Settings → AI. ({msg})")
    return AIError(f"{name} error {r.status_code}: {msg}")


def _sse(r: httpx.Response) -> Iterator[dict]:
    """Yield JSON payloads from a Server-Sent Events stream."""
    for line in r.iter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def _net(provider: str, fn: Callable[[], Any]) -> Any:
    name = PROVIDERS[provider].name
    try:
        return fn()
    except httpx.ConnectError as e:
        if provider == "ollama":
            raise AIError("Local AI isn't running. Install Ollama from ollama.com and open it.") from e
        raise AIError(f"Can't reach {name}. Check your internet connection.") from e
    except httpx.TimeoutException as e:
        raise AIError(f"{name} took too long to respond. Try again or pick a faster model.") from e


def _nice(model_id: str) -> str:
    """'gpt-4o-mini' -> 'GPT-4o mini' style label for providers without display names."""
    s = model_id.replace("models/", "")
    s = re.sub(r"^gpt", "GPT", s)
    s = re.sub(r"^o(\d)", r"o\1", s)
    s = s.replace("-", " ")
    s = re.sub(r"^GPT (\S+)", r"GPT-\1", s)
    return s


# ------------------------------------------------------------------ model lists

_OPENAI_SKIP = ("audio", "realtime", "tts", "transcribe", "image", "search", "embedding", "instruct",
                "moderation", "whisper", "dall", "davinci", "babbage", "codex", "computer-use")
_GEMINI_SKIP = ("embedding", "tts", "image", "live", "audio", "aqa", "robotics", "vision", "learnlm")
_GROQ_SKIP = ("whisper", "guard", "tts", "playai", "distil")


def list_models(provider: str, key: str, ollama_url: str = "") -> list[dict[str, str]]:
    if provider == "ollama":
        from . import local
        if not local.supported():
            raise AIError("This computer doesn't meet the requirements for Local AI.")

        def go():
            r = httpx.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=4)
            r.raise_for_status()
            installed = [m["name"] for m in r.json().get("models", [])]
            # Only premium-grade models from the catalog, never whatever else is installed
            return [{"id": t["model"], "label": t["name"]} for t in local.allowed_models()
                    if any(n == t["model"] or n.removesuffix(":latest") == t["model"] for n in installed)]
        return _net("ollama", go)

    if not key:
        raise AIError(f"Add your {PROVIDERS[provider].name} API key in Settings → AI.")

    if provider in ("openai", "groq"):
        def go():
            r = httpx.get(f"{BASE[provider]}/models", headers={"Authorization": f"Bearer {key}"}, timeout=10)
            if r.status_code >= 400:
                raise _fail(provider, r, key)
            data = r.json().get("data", [])
            if provider == "openai":
                data = [m for m in data if re.match(r"^(gpt-|o\d|chatgpt-)", m["id"])
                        and not any(x in m["id"] for x in _OPENAI_SKIP)]
            else:
                data = [m for m in data if m.get("active", True) and not any(x in m["id"] for x in _GROQ_SKIP)]
            data.sort(key=lambda m: m.get("created", 0), reverse=True)
            return [{"id": m["id"], "label": _nice(m["id"]) if provider == "openai" else m["id"]} for m in data]
        return _net(provider, go)

    if provider == "anthropic":
        def go():
            r = httpx.get(f"{BASE['anthropic']}/models", params={"limit": 100},
                          headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}, timeout=10)
            if r.status_code >= 400:
                raise _fail(provider, r, key)
            # API returns newest first
            return [{"id": m["id"], "label": m.get("display_name") or m["id"]} for m in r.json().get("data", [])]
        return _net(provider, go)

    if provider == "gemini":
        def go():
            out, token = [], None
            for _ in range(5):
                params = {"pageSize": 200, **({"pageToken": token} if token else {})}
                r = httpx.get(f"{BASE['gemini']}/models", params=params,
                              headers={"x-goog-api-key": key}, timeout=10)
                if r.status_code >= 400:
                    raise _fail(provider, r, key)
                j = r.json()
                for m in j.get("models", []):
                    mid = m["name"].removeprefix("models/")
                    if ("generateContent" in m.get("supportedGenerationMethods", [])
                            and mid.startswith("gemini") and not any(x in mid for x in _GEMINI_SKIP)):
                        out.append({"id": mid, "label": m.get("displayName") or mid})
                token = j.get("nextPageToken")
                if not token:
                    break
            out.sort(key=lambda m: m["id"], reverse=True)
            return out
        return _net(provider, go)

    raise AIError(f"Unknown provider {provider}")


def default_model(provider: str, models: list[dict[str, str]]) -> str:
    """Pick a good all-round model: capable, not the most expensive."""
    ids = [m["id"] for m in models]
    if not ids:
        return ""
    if provider == "ollama":
        return ids[-1]  # catalog order is smallest -> largest; use the best one installed
    stable = [i for i in ids if not re.search(r"preview|exp|beta|latest$|\d{4}-\d{2}-\d{2}", i)] or ids
    prefs = {
        "openai": [r"^gpt-[\d.]+-mini$", r"^gpt-[\d.]+o?$", r"mini"],
        "anthropic": [r"sonnet", r"haiku"],
        "gemini": [r"flash(?!-lite)", r"pro"],
        "groq": [r"70b", r"versatile"],
        "ollama": [r"."],
    }[provider]
    for pat in prefs:
        for i in stable:
            if re.search(pat, i):
                return i
    return stable[0]


# ------------------------------------------------------------------ streaming

def _openai_like(provider: str, key: str, model: str, messages: list[dict], temperature: float,
                 cache_key: str = "") -> Iterator[str]:
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
    if provider == "groq":
        payload["temperature"] = temperature
    # OpenAI reasoning models reject a custom temperature, so we use the default there.
    # OpenAI caches identical prompt prefixes automatically; a stable key per
    # dataset helps route repeat questions to the same cache.
    if provider == "openai" and cache_key:
        payload["prompt_cache_key"] = cache_key
    for attempt in range(2):
        with httpx.stream("POST", f"{BASE[provider]}/chat/completions", json=payload,
                          headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT) as r:
            if r.status_code == 400 and attempt == 0 and "prompt_cache_key" in payload:
                r.read()
                if "prompt_cache_key" in r.text:
                    payload.pop("prompt_cache_key")
                    continue
                raise _fail(provider, r, key)
            if r.status_code >= 400:
                raise _fail(provider, r, key)
            yield from _openai_chunks(r, key)
            return


def _openai_chunks(r: httpx.Response, key: str) -> Iterator[str]:
    for chunk in _sse(r):
        if chunk.get("error"):
            raise AIError(keystore.redact(str(chunk["error"]), key))
        choices = chunk.get("choices") or []
        if choices:
            piece = (choices[0].get("delta") or {}).get("content")
            if piece:
                yield piece


def _anthropic(key: str, model: str, messages: list[dict], temperature: float) -> Iterator[str]:
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    convo = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    # Mark the (large, unchanging) dataset prompt as cacheable: follow-up
    # questions re-use it instead of re-reading it, which cuts time-to-first-word.
    payload = {"model": model, "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
               "messages": convo, "max_tokens": MAX_OUTPUT_TOKENS, "stream": True, "temperature": temperature}
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
    with httpx.stream("POST", f"{BASE['anthropic']}/messages", json=payload, headers=headers, timeout=TIMEOUT) as r:
        if r.status_code == 400:
            # some newer models may not accept temperature - retry once without it
            r.read()
            if "temperature" in r.text:
                payload.pop("temperature")
                yield from _anthropic_retry(key, payload, headers)
                return
            raise _fail("anthropic", r, key)
        if r.status_code >= 400:
            raise _fail("anthropic", r, key)
        yield from _anthropic_events(r, key)


def _anthropic_retry(key: str, payload: dict, headers: dict) -> Iterator[str]:
    with httpx.stream("POST", f"{BASE['anthropic']}/messages", json=payload, headers=headers, timeout=TIMEOUT) as r:
        if r.status_code >= 400:
            raise _fail("anthropic", r, key)
        yield from _anthropic_events(r, key)


def _anthropic_events(r: httpx.Response, key: str) -> Iterator[str]:
    for ev in _sse(r):
        t = ev.get("type")
        if t == "content_block_delta":
            d = ev.get("delta") or {}
            if d.get("type") == "text_delta" and d.get("text"):
                yield d["text"]
        elif t == "error":
            msg = (ev.get("error") or {}).get("message", "unknown error")
            raise AIError(f"Anthropic: {keystore.redact(msg, key)}")


def _gemini(key: str, model: str, messages: list[dict], temperature: float) -> Iterator[str]:
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in messages if m["role"] != "system"]
    payload = {"contents": contents, "systemInstruction": {"parts": [{"text": system}]},
               "generationConfig": {"temperature": temperature}}
    url = f"{BASE['gemini']}/models/{model}:streamGenerateContent"
    # key goes in a header, not the URL, so it can't end up in any URL log
    with httpx.stream("POST", url, params={"alt": "sse"}, json=payload,
                      headers={"x-goog-api-key": key}, timeout=TIMEOUT) as r:
        if r.status_code >= 400:
            raise _fail("gemini", r, key)
        for chunk in _sse(r):
            if chunk.get("error"):
                raise AIError(f"Gemini: {keystore.redact(str(chunk['error']), key)}")
            for cand in chunk.get("candidates") or []:
                for part in (cand.get("content") or {}).get("parts") or []:
                    if part.get("text") and not part.get("thought"):
                        yield part["text"]
                if cand.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
                    raise AIError("Gemini declined to answer this (safety filter). Try rephrasing.")


def _ollama(url: str, model: str, messages: list[dict], temperature: float) -> Iterator[str]:
    from . import local
    # Fast-reply settings:
    # * num_ctx is FIXED per model: changing it forces Ollama to reload the model.
    # * keep_alive keeps the model in memory between questions (no load delay).
    # * think=False: reasoning models otherwise "think" silently before the
    #   first visible word; analysis answers don't need that.
    # * The system prompt is identical for every question about a dataset, so
    #   Ollama re-uses its cached copy (KV cache) and only reads the new part.
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True, "keep_alive": local.KEEP_ALIVE,
                               "think": False,
                               "options": {"temperature": temperature, "num_ctx": local.num_ctx_for(model)}}
    for attempt in range(2):
        with httpx.stream("POST", f"{url.rstrip('/')}/api/chat", json=payload, timeout=TIMEOUT) as r:
            if r.status_code == 404:
                raise AIError("The local model isn't downloaded yet. Open Settings → AI assistant → Local AI.")
            if r.status_code >= 400:
                r.read()
                if attempt == 0 and "think" in r.text.lower():
                    payload.pop("think")  # model without a thinking switch
                    continue
                raise AIError(f"Local AI error {r.status_code}: {r.text[:300]}")
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise AIError(f"Local AI: {data['error']}")
                piece = (data.get("message") or {}).get("content")
                if piece:
                    yield piece
                if data.get("done"):
                    break
            return


# ------------------------------------------------------------------ facade

def resolve_model(ai: dict[str, Any]) -> tuple[str, str]:
    """(provider, model) - fills in a default model if none was chosen."""
    provider = ai.get("provider") or ""
    if provider not in PROVIDERS:
        raise AIError("Choose an AI assistant in Settings → AI assistant.")
    model = (ai.get("models") or {}).get(provider) or ""
    if provider == "ollama":
        # only accept a catalog model that is actually installed
        installed = [m["id"] for m in list_models("ollama", "", ai.get("ollama_url", ""))]
        if model not in installed:
            model = ""
    if not model:
        model = default_model(provider, list_models(provider, keystore.get(provider), ai.get("ollama_url", "")))
        if not model:
            raise AIError("No local models installed. Open Settings → AI for setup steps."
                          if provider == "ollama" else "No usable models found for this key.")
    return provider, model


def stream_chat(ai: dict[str, Any], provider: str, model: str, messages: list[dict], cache_key: str = "") -> Iterator[str]:
    temp = float(ai.get("temperature", 0.3))
    key = keystore.get(provider) if PROVIDERS[provider].needs_key else ""
    if PROVIDERS[provider].needs_key and not key:
        raise AIError(f"Add your {PROVIDERS[provider].name} API key in Settings → AI.")

    def gen() -> Iterator[str]:
        if provider in ("openai", "groq"):
            yield from _openai_like(provider, key, model, messages, temp, cache_key)
        elif provider == "anthropic":
            yield from _anthropic(key, model, messages, temp)
        elif provider == "gemini":
            yield from _gemini(key, model, messages, temp)
        else:
            yield from _ollama(ai["ollama_url"], model, messages, temp)

    it = gen()
    while True:
        try:
            piece = _net(provider, lambda: next(it))
        except StopIteration:
            return
        except AIError:
            raise
        except Exception as e:  # never let a raw exception (which may echo a URL/header) through
            raise AIError(keystore.redact(f"{PROVIDERS[provider].name}: {e}", key)) from None
        yield piece


def provider_status(ai: dict[str, Any], provider: str) -> dict[str, Any]:
    info = PROVIDERS[provider]
    key = keystore.get(provider) if info.needs_key else ""
    base = {"id": provider, "name": info.name, "tagline": info.tagline, "needs_key": info.needs_key,
            "key_url": info.key_url, "key_placeholder": info.key_hint,
            "key_set": bool(key), "key_ending": keystore.hint(key)}
    if info.needs_key and not key:
        return {**base, "ready": False, "models": [], "model": "", "message": "Add an API key to use this provider."}
    try:
        models = list_models(provider, key, ai.get("ollama_url", ""))
    except AIError as e:
        return {**base, "ready": False, "models": [], "model": "", "message": str(e)}
    chosen = (ai.get("models") or {}).get(provider) or default_model(provider, models)
    ok = bool(chosen) and any(m["id"] == chosen for m in models)
    msg = "Ready" if ok else ("No local models installed yet." if provider == "ollama" and not models
                              else "Selected model isn't available - pick another.")
    return {**base, "ready": ok, "models": models, "model": chosen, "message": msg}


def status(ai: dict[str, Any]) -> dict[str, Any]:
    """Short status of the active provider for the sidebar and chat."""
    p = ai.get("provider") or ""
    if p not in PROVIDERS:
        return {"ok": False, "provider": "", "provider_name": "AI assistant", "model": "", "model_label": "",
                "message": "Choose an AI assistant in Settings."}
    s = provider_status(ai, p)
    label = next((m["label"] for m in s["models"] if m["id"] == s["model"]), s["model"])
    return {"ok": s["ready"], "provider": p, "provider_name": PROVIDERS[p].name if p != "ollama" else "Local AI",
            "model": s["model"], "model_label": label, "message": s["message"]}
