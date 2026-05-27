"""
AXIS OS — AI Proxy Server
Validates license keys and proxies AI requests to providers.
Deploy on Railway / Render / any VPS.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

# ── Config ─────────────────────────────────────────────────────────────────
LICENSE_SECRET = os.environ.get("AXIS_LICENSE_SECRET", "AXIS-OS-LICENSE-2024-V1")

# Your provider API keys (set as env vars on Railway/Render — never commit!)
PROVIDER_KEYS = {
    "openai":     os.environ.get("OPENAI_API_KEY", ""),
    "anthropic":  os.environ.get("ANTHROPIC_API_KEY", ""),
    "google":     os.environ.get("GOOGLE_API_KEY", ""),
    "xai":        os.environ.get("XAI_API_KEY", ""),
    "deepseek":   os.environ.get("DEEPSEEK_API_KEY", ""),
    "perplexity": os.environ.get("PERPLEXITY_API_KEY", ""),
}

# Provider base URLs for OpenAI-compatible APIs
COMPAT_BASES = {
    "xai":        "https://api.x.ai/v1",
    "deepseek":   "https://api.deepseek.com/v1",
    "perplexity": "https://api.perplexity.ai",
}

# Admin key for stats endpoint (set ADMIN_KEY env var on Railway)
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")

# Daily message limits per tier (trial never reaches here; -1 = unlimited)
TIER_LIMITS: dict[str, int] = {
    "trial":    50,
    "monthly":  -1,
    "yearly":   -1,
    "lifetime": -1,
}

# Approximate cost per request per provider (USD, based on ~500 avg tokens)
PROVIDER_COST_PER_REQ: dict[str, float] = {
    "openai":     0.002,   # mix of gpt-4o and mini
    "anthropic":  0.001,   # mix of sonnet and haiku
    "google":     0.0003,  # gemini flash mostly
    "xai":        0.0015,  # grok-3
    "deepseek":   0.00015,
    "perplexity": 0.0005,
}

# ── License helpers ─────────────────────────────────────────────────────────
_TIER_CHAR = {"M": "monthly", "Y": "yearly", "L": "lifetime", "T": "trial"}


def validate_license(raw_key: str) -> dict:
    """Returns {ok, tier, expires_ts} or {ok: False, error}."""
    key = raw_key.strip().upper().replace("-", "").replace(" ", "")
    # Strip the human-readable "AXIS" prefix produced by generate_key()
    if key.startswith("AXIS"):
        key = key[4:]
    if len(key) < 16:
        return {"ok": False, "error": "Invalid key format"}

    tier_char  = key[0]
    days_hex   = key[1:4]
    expiry_hex = key[4:12]
    checksum   = key[12:16]

    tier = _TIER_CHAR.get(tier_char)
    if not tier:
        return {"ok": False, "error": "Unknown license tier"}

    payload  = f"{tier_char}{days_hex}{expiry_hex}"
    expected = hmac.new(
        LICENSE_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:4].upper()

    if not hmac.compare_digest(expected, checksum):
        return {"ok": False, "error": "Invalid license key"}

    expiry_ts = int(expiry_hex, 16)
    if expiry_ts > 0 and expiry_ts < int(time.time()):
        return {"ok": False, "error": "License expired"}

    return {"ok": True, "tier": tier, "expires_ts": expiry_ts}


# ── Usage & spending tracking (in-memory) ────────────────────────────────────
# Per-license daily usage
_usage: dict[str, dict] = {}   # key_id → {date, count}

# Global monthly stats per provider  {month: "2026-05", providers: {name: {requests, cost_usd}}}
_monthly: dict = {}


def _this_month() -> str:
    return datetime.now().strftime("%Y-%m")


def _record_provider_request(provider: str):
    """Increment global monthly counter for a provider."""
    month = _this_month()
    if _monthly.get("month") != month:
        _monthly.clear()
        _monthly["month"] = month
        _monthly["providers"] = {}
    provs = _monthly.setdefault("providers", {})
    if provider not in provs:
        provs[provider] = {"requests": 0, "cost_usd": 0.0}
    provs[provider]["requests"] += 1
    provs[provider]["cost_usd"] = round(
        provs[provider]["cost_usd"] + PROVIDER_COST_PER_REQ.get(provider, 0.001), 5
    )


def _key_id(raw_key: str) -> str:
    """Short stable identifier derived from key."""
    return hashlib.md5(raw_key.strip().upper().encode()).hexdigest()[:12]


def check_and_increment(raw_key: str, tier: str) -> tuple[bool, str]:
    """Returns (allowed, message). Increments counter if allowed."""
    limit = TIER_LIMITS.get(tier, -1)
    if limit == -1:
        return True, ""

    kid   = _key_id(raw_key)
    today = datetime.now().strftime("%Y-%m-%d")
    entry = _usage.get(kid, {})

    if entry.get("date") != today:
        entry = {"date": today, "count": 0}

    if entry["count"] >= limit:
        return False, f"Daily limit of {limit} messages reached."

    entry["count"] += 1
    _usage[kid] = entry
    return True, ""


# ── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(title="AXIS OS Proxy", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ─────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    provider: str
    model: str
    messages: list[dict]
    system_prompt: str = ""
    stream: bool = True
    temperature: float = 0.7
    max_tokens: int = 4096
    user_key: str = ""   # optional: client passes own provider key


class ActivateRequest(BaseModel):
    key: str


# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ── License activation ───────────────────────────────────────────────────────
@app.post("/api/v1/activate")
def activate(body: ActivateRequest):
    result = validate_license(body.key)
    if not result["ok"]:
        return JSONResponse({"ok": False, "message": result["error"]}, status_code=400)

    tier = result["tier"]
    tier_names = {"trial": "Пробний", "monthly": "Місячний",
                  "yearly": "Річний", "lifetime": "Назавжди"}
    return {
        "ok": True,
        "tier": tier,
        "message": f"✅ Активовано: {tier_names.get(tier, tier)}!",
        "expires_ts": result["expires_ts"],
    }


# ── Usage stats ───────────────────────────────────────────────────────────────
@app.get("/api/v1/usage")
def usage(authorization: str = Header(None)):
    key = _extract_key(authorization)
    kid = _key_id(key)
    today = datetime.now().strftime("%Y-%m-%d")
    entry = _usage.get(kid, {"date": today, "count": 0})
    if entry.get("date") != today:
        entry = {"date": today, "count": 0}
    return {"date": today, "messages_today": entry["count"]}


# ── Main chat endpoint ────────────────────────────────────────────────────────
@app.post("/api/v1/chat")
async def chat(body: ChatRequest, authorization: str = Header(None)):
    # 1. Validate license
    key = _extract_key(authorization)
    lic = validate_license(key)
    if not lic["ok"]:
        raise HTTPException(status_code=401, detail=lic["error"])

    # 2. Check daily limit
    allowed, msg = check_and_increment(key, lic["tier"])
    if not allowed:
        raise HTTPException(status_code=429, detail=msg)

    # 3. Get provider key — user key has priority, server key as fallback
    provider_key = body.user_key or PROVIDER_KEYS.get(body.provider, "")
    if not provider_key and body.provider != "ollama":
        raise HTTPException(status_code=503,
            detail=f"Provider {body.provider} not configured on server.")

    # 4. Record stats + route to provider
    _record_provider_request(body.provider)
    if body.stream:
        gen = _stream_response(body, provider_key)
        return StreamingResponse(gen, media_type="text/event-stream")
    else:
        text = await _call_provider(body, provider_key)
        return {"text": text}


# ── Image generation (HuggingFace FLUX from US — free, no billing needed) ────
class ImageRequest(BaseModel):
    prompt: str
    google_key: str = ""   # unused, kept for backwards compat
    ref_image_b64: str = ""


@app.post("/api/v1/image")
async def generate_image(body: ImageRequest, authorization: str = Header(None)):
    """Generate image via Pollinations AI (FLUX) — free, no keys, works from any server."""
    key = _extract_key(authorization)
    lic = validate_license(key)
    if not lic["ok"]:
        raise HTTPException(status_code=403, detail=lic["error"])

    import base64 as _b64
    from urllib.parse import quote as _quote

    # Pollinations AI — free FLUX image generation, no API key needed
    # GET https://image.pollinations.ai/prompt/{prompt}?model=flux&width=1024&height=1024
    prompt_enc = _quote(body.prompt)
    _URLS = [
        f"https://image.pollinations.ai/prompt/{prompt_enc}?model=flux&width=1024&height=1024&nologo=true&enhance=false",
        f"https://image.pollinations.ai/prompt/{prompt_enc}?model=flux-schnell&width=1024&height=1024&nologo=true",
        f"https://image.pollinations.ai/prompt/{prompt_enc}?width=1024&height=1024&nologo=true",
    ]

    all_errors: list[str] = []
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        for url in _URLS:
            try:
                r = await client.get(url, headers={"User-Agent": "AXIS-OS/1.0"})
                if r.status_code != 200:
                    all_errors.append(f"Pollinations HTTP {r.status_code}: {r.text[:100]}")
                    continue
                img_bytes = r.content
                if len(img_bytes) < 1000:
                    all_errors.append(f"Pollinations: response too small ({len(img_bytes)} bytes)")
                    continue
                # Detect content type and return
                mime = r.headers.get("content-type", "image/jpeg").split(";")[0]
                b64 = _b64.b64encode(img_bytes).decode()
                return JSONResponse({"b64": b64, "mime": mime})
            except Exception as e:
                all_errors.append(f"Pollinations: {e}")
                continue

    raise HTTPException(status_code=500,
        detail="Image generation failed:\n" + "\n".join(all_errors))


# ── Video generation (HuggingFace from US — bypasses EU DNS block) ───────────
class VideoRequest(BaseModel):
    prompt: str
    duration: int = 5


@app.post("/api/v1/video")
async def generate_video(body: VideoRequest, authorization: str = Header(None)):
    """Generate video via HuggingFace from US (bypasses EU/Germany DNS restrictions).
    Returns base64-encoded mp4."""
    key = _extract_key(authorization)
    lic = validate_license(key)
    if not lic["ok"]:
        raise HTTPException(status_code=403, detail=lic["error"])

    import asyncio
    import base64 as _b64

    REPLICATE_KEY = os.environ.get("REPLICATE_API_KEY", "")
    if not REPLICATE_KEY:
        raise HTTPException(status_code=503,
            detail="NO_REPLICATE_KEY: Додай REPLICATE_API_KEY в Railway Variables. "
                   "Безкоштовно: replicate.com → Sign in → Account → API tokens")

    # Zeroscope v2 XL on Replicate — free credits, good quality
    _VERSION = "9f747673945c62801b13b84701c783929c0ee784e4748ec062204894dda1a351"
    num_frames = min(36, max(12, body.duration * 8))

    async with httpx.AsyncClient(timeout=30) as client:
        # Submit prediction
        r = await client.post(
            "https://api.replicate.com/v1/predictions",
            headers={"Authorization": f"Token {REPLICATE_KEY}",
                     "Content-Type": "application/json"},
            json={"version": _VERSION,
                  "input": {"prompt": body.prompt,
                             "num_frames": num_frames,
                             "num_inference_steps": 25,
                             "fps": 8}},
        )
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500,
                detail=f"Replicate submit failed: {r.status_code} {r.text[:200]}")
        pred = r.json()
        pred_id = pred.get("id")
        if not pred_id:
            raise HTTPException(status_code=500, detail="Replicate: no prediction ID")

    # Poll until complete (max 5 min)
    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(60):
            await asyncio.sleep(5)
            poll = await client.get(
                f"https://api.replicate.com/v1/predictions/{pred_id}",
                headers={"Authorization": f"Token {REPLICATE_KEY}"},
            )
            if poll.status_code != 200:
                continue
            data = poll.json()
            status = data.get("status", "")
            if status == "succeeded":
                output = data.get("output")
                video_url = (output[0] if isinstance(output, list) else output) or ""
                if not video_url:
                    raise HTTPException(status_code=500,
                        detail="Replicate: succeeded but no output URL")
                # Download the video
                async with httpx.AsyncClient(timeout=60) as dl:
                    vr = await dl.get(video_url)
                    video_bytes = vr.content
                b64 = _b64.b64encode(video_bytes).decode()
                return JSONResponse({"b64": b64, "mime": "video/mp4"})
            elif status in ("failed", "canceled"):
                err = data.get("error") or "unknown error"
                raise HTTPException(status_code=500,
                    detail=f"Replicate generation failed: {err}")

    raise HTTPException(status_code=500, detail="Video generation timeout after 5 minutes")


# ── Admin stats endpoint ──────────────────────────────────────────────────────
@app.get("/api/v1/admin/stats")
def admin_stats(authorization: str = Header(None)):
    """Returns monthly spending per provider. Protected by ADMIN_KEY."""
    if ADMIN_KEY:
        provided = (authorization or "").replace("Bearer ", "").strip()
        if not hmac.compare_digest(provided, ADMIN_KEY):
            raise HTTPException(status_code=403, detail="Invalid admin key")

    month = _this_month()
    providers = _monthly.get("providers", {}) if _monthly.get("month") == month else {}

    total_requests = sum(v["requests"] for v in providers.values())
    total_cost     = round(sum(v["cost_usd"] for v in providers.values()), 4)

    breakdown = [
        {
            "provider": prov,
            "requests": data["requests"],
            "cost_usd": round(data["cost_usd"], 4),
        }
        for prov, data in sorted(providers.items(),
                                  key=lambda x: x[1]["cost_usd"], reverse=True)
    ]

    return {
        "month":          month,
        "total_requests": total_requests,
        "total_cost_usd": total_cost,
        "breakdown":      breakdown,
    }


def _extract_key(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="No license key provided.")
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return authorization


# ── Provider calls (non-streaming) ───────────────────────────────────────────
async def _call_provider(body: ChatRequest, key: str) -> str:
    p = body.provider
    if p == "openai":
        return await _openai_call(body, key)
    elif p == "anthropic":
        return await _anthropic_call(body, key)
    elif p == "google":
        return await _google_call(body, key)
    elif p in ("xai", "deepseek", "perplexity"):
        return await _compat_call(body, key)
    raise HTTPException(status_code=400, detail=f"Unknown provider: {p}")


async def _openai_call(body: ChatRequest, key: str) -> str:
    msgs = []
    if body.system_prompt:
        msgs.append({"role": "system", "content": body.system_prompt})
    msgs.extend(body.messages)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": body.model, "messages": msgs,
                  "temperature": body.temperature, "max_tokens": body.max_tokens})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _anthropic_call(body: ChatRequest, key: str) -> str:
    kw: dict = {"model": body.model, "max_tokens": body.max_tokens,
                "messages": body.messages, "temperature": body.temperature}
    if body.system_prompt:
        kw["system"] = body.system_prompt
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json=kw)
        r.raise_for_status()
        return r.json()["content"][0]["text"]


async def _google_call(body: ChatRequest, key: str) -> str:
    contents = [
        {"role": "user" if m["role"] == "user" else "model",
         "parts": [{"text": m["content"]}]}
        for m in body.messages
    ]
    payload: dict = {"contents": contents}
    if body.system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": body.system_prompt}]}
    model = body.model
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": key}, json=payload)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


async def _compat_call(body: ChatRequest, key: str) -> str:
    base = COMPAT_BASES.get(body.provider, "")
    msgs = []
    if body.system_prompt:
        msgs.append({"role": "system", "content": body.system_prompt})
    msgs.extend(body.messages)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": body.model, "messages": msgs,
                  "temperature": body.temperature, "max_tokens": body.max_tokens})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ── Streaming ─────────────────────────────────────────────────────────────────
async def _stream_response(body: ChatRequest, key: str) -> AsyncGenerator[str, None]:
    """Yields SSE chunks: data: {"token": "..."}\n\n   or   data: [DONE]\n\n"""
    try:
        p = body.provider
        if p == "anthropic":
            async for token in _anthropic_stream(body, key):
                yield f"data: {json.dumps({'token': token})}\n\n"
        elif p == "google":
            async for token in _google_stream(body, key):
                yield f"data: {json.dumps({'token': token})}\n\n"
        else:
            # OpenAI-compatible (openai, xai, deepseek, perplexity)
            async for token in _openai_stream(body, key):
                yield f"data: {json.dumps({'token': token})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


_OPENAI_FALLBACK = "gpt-4o"
# Models that don't accept temperature / use max_completion_tokens
_NO_TEMP_MODELS = ("o1", "o3", "o4", "gpt-5", "gpt-4.5")


def _openai_payload(model: str, msgs: list, temperature: float, max_tokens: int) -> dict:
    payload: dict = {"model": model, "messages": msgs, "stream": True}
    if not model.startswith(_NO_TEMP_MODELS):
        payload["temperature"] = temperature
    if model.startswith(("o1", "o3", "o4", "gpt-5", "gpt-4.5", "gpt-4.1")):
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens
    return payload


async def _openai_stream(body: ChatRequest, key: str) -> AsyncGenerator[str, None]:
    base = COMPAT_BASES.get(body.provider, "https://api.openai.com/v1")
    msgs = []
    if body.system_prompt:
        msgs.append({"role": "system", "content": body.system_prompt})
    msgs.extend(body.messages)

    models_to_try = [body.model]
    if body.provider == "openai" and body.model != _OPENAI_FALLBACK:
        models_to_try.append(_OPENAI_FALLBACK)

    last_err = ""
    for model in models_to_try:
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                async with c.stream("POST", f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=_openai_payload(model, msgs, body.temperature, body.max_tokens)
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            return
                        try:
                            data = json.loads(chunk)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            pass
            return  # success
        except httpx.HTTPStatusError as e:
            last_err = str(e)
            if e.response.status_code == 404 and model != _OPENAI_FALLBACK:
                continue  # try fallback model
            raise
        except Exception as e:
            last_err = str(e)
            raise

    raise RuntimeError(f"All models failed. Last error: {last_err}")


async def _anthropic_stream(body: ChatRequest, key: str) -> AsyncGenerator[str, None]:
    kw: dict = {"model": body.model, "max_tokens": body.max_tokens,
                "messages": body.messages, "stream": True,
                "temperature": body.temperature}
    if body.system_prompt:
        kw["system"] = body.system_prompt
    async with httpx.AsyncClient(timeout=120) as c:
        async with c.stream("POST", "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json=kw
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        yield data["delta"].get("text", "")
                except Exception:
                    pass


async def _google_stream(body: ChatRequest, key: str) -> AsyncGenerator[str, None]:
    contents = [
        {"role": "user" if m["role"] == "user" else "model",
         "parts": [{"text": m["content"]}]}
        for m in body.messages
    ]
    payload: dict = {"contents": contents}
    if body.system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": body.system_prompt}]}
    model = body.model
    async with httpx.AsyncClient(timeout=120) as c:
        async with c.stream("POST",
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent",
            params={"key": key, "alt": "sse"}, json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    if text:
                        yield text
                except Exception:
                    pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)),
                reload=False)
