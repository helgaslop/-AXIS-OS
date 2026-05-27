"""AI provider manager — handles OpenAI, Anthropic, Google, xAI, Perplexity, Ollama.

Proxy mode:
  When a paid AXIS OS license is active the manager routes AI requests through
  the AXIS OS proxy server instead of calling providers directly.
  Users on paid plans don't need to configure any API keys.
"""
import threading
import base64
import os
import tempfile
import json

import urllib.request
import urllib.error

from PyQt6.QtCore import QObject, pyqtSignal

OLLAMA_BASE      = "http://localhost:11434"
_DEFAULT_PROXY   = "https://axis-os-production-5220.up.railway.app"
PROXY_URL        = os.environ.get("AXIS_PROXY_URL", _DEFAULT_PROXY)


class AIManager(QObject):
    response_ready = pyqtSignal(str, str)   # (request_id, text)
    response_error = pyqtSignal(str, str)   # (request_id, error)
    response_token = pyqtSignal(str, str)   # (request_id, token) — streaming
    response_done  = pyqtSignal(str)        # (request_id) — streaming complete
    image_ready    = pyqtSignal(str, str)   # (request_id, base64_or_url)
    video_ready    = pyqtSignal(str, str)   # (request_id, video_url)

    PROVIDERS = {
        "openai":    {"label": "OpenAI",    "models": [
            "gpt-5", "gpt-5-mini",
            "gpt-4.5", "gpt-4.5-mini",
            "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "gpt-4o", "gpt-4o-mini",
            "o3", "o4-mini", "o3-mini", "o1", "o1-mini",
        ]},
        "anthropic": {"label": "Anthropic", "models": [
            "claude-opus-4-5", "claude-sonnet-4-5",
            "claude-haiku-4-5", "claude-haiku-4-5-20251001",
        ]},
        "google":    {"label": "Google",    "models": [
            "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
            "gemini-2.0-flash", "gemini-2.0-flash-lite",
            "gemini-1.5-pro", "gemini-1.5-flash",
        ]},
        "xai":       {"label": "xAI",       "models": [
            "grok-3", "grok-3-mini", "grok-3-fast", "grok-2",
        ]},
        "perplexity": {"label": "Perplexity", "models": [
            "sonar-pro", "sonar", "sonar-reasoning-pro", "sonar-reasoning",
            "sonar-deep-research",
        ]},
        "ollama":    {"label": "Ollama",    "models": []},
    }

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        # Merge config keys with Windows Credential Manager (keyring takes priority)
        from core.secrets import get_all_keys as _gak
        _base: dict = dict(config.get("api_keys", {}))
        # Also pull flat keys like "luma_key", "openweather_key", etc.
        _flat_map = {
            "openai":      "openai_key",
            "anthropic":   "anthropic_key",
            "google":      "google_key",
            "xai":         "xai_key",
            "deepseek":    "deepseek_key",
            "perplexity":  "perplexity_key",
            "luma":        "luma_key",
            "serper":      "serper_key",
            "tavily":      "tavily_key",
            "openweather": "openweather_key",
        }
        for prov, flat in _flat_map.items():
            if not _base.get(prov) and config.get(flat):
                _base[prov] = config[flat]
        self.api_keys: dict = _gak(_base)
        self.temperature: float = config.get("ai", {}).get("temperature", 0.7)
        self.max_tokens: int = config.get("ai", {}).get("max_tokens", 4096)
        self.ollama_url: str = config.get("ollama_url", OLLAMA_BASE)
        # Allow config.json to override the proxy URL (set after Railway deploy)
        global PROXY_URL
        if config.get("proxy_url"):
            PROXY_URL = config["proxy_url"]

        # Proxy: load license key once; refresh via reload_license()
        self._license_key: str | None = None
        self._license_tier: str = "trial"
        self.reload_license()

    def reload_license(self):
        """Re-read license from disk. Call after activation."""
        try:
            from core.license import LicenseManager
            from core.paths import USER_DATA_DIR
            lic = LicenseManager(USER_DATA_DIR)
            st = lic.get_status()
            if st.get("active") and st.get("tier") != "trial":
                self._license_key  = st.get("key")
                self._license_tier = st.get("tier", "monthly")
            else:
                self._license_key  = None
                self._license_tier = "trial"
        except Exception as e:
            print(f"[AI] license load error: {e}")
            self._license_key  = None
            self._license_tier = "trial"

    @property
    def proxy_active(self) -> bool:
        """True when a paid license is present → use server proxy."""
        return bool(self._license_key)

    # Default fallback models per provider
    _FALLBACK_MODELS = {
        "openai":    "gpt-4.1",
        "anthropic": "claude-sonnet-4-5",
        "google":    "gemini-2.5-flash",
        "xai":       "grok-3",
        "deepseek":  "deepseek-chat",
        "perplexity":"sonar",
        "ollama":    "llama3",
    }

    # Friendly display names for switch notices
    _PROVIDER_LABELS = {
        "openai":    "OpenAI GPT",
        "anthropic": "Claude",
        "google":    "Gemini",
        "xai":       "Grok",
        "deepseek":  "DeepSeek",
        "perplexity":"Perplexity",
        "ollama":    "Ollama",
    }

    def update_key(self, provider: str, key: str):
        self.api_keys[provider] = key

    # ── Fallback chain builder ────────────────────────────────────────────────
    def _build_chain(self, preferred_provider: str, preferred_model: str) -> list:
        """Return ordered [(provider, key, model)] starting with preferred,
        then any other providers that have keys configured.

        When proxy_active is True, the first entry is a sentinel
        ("_proxy_", license_key, model) that routes through the server.
        """
        chain = []

        # ── Proxy mode (paid license) ──────────────────────────────────────
        if self.proxy_active and preferred_provider != "ollama":
            chain.append(("_proxy_", self._license_key, preferred_model))
            # Keep local keys as fallback in case server is down
            key = self.api_keys.get(preferred_provider, "")
            if key:
                chain.append((preferred_provider, key, preferred_model))
            return chain

        # ── Direct mode (trial / no license) ──────────────────────────────
        key = self.api_keys.get(preferred_provider, "")
        if key or preferred_provider == "ollama":
            chain.append((preferred_provider, key, preferred_model))

        fallback_order = ["openai", "anthropic", "google", "xai",
                          "deepseek", "perplexity"]
        for prov in fallback_order:
            if prov == preferred_provider:
                continue
            k = self.api_keys.get(prov, "")
            if k:
                chain.append((prov, k, self._FALLBACK_MODELS.get(prov, "")))
        return chain

    # ── Text generation (non-streaming) ──────────────────────────────────────
    def send(self, request_id: str, provider: str, model: str,
             messages: list, system_prompt: str = ""):
        t = threading.Thread(
            target=self._worker,
            args=(request_id, provider, model, messages, system_prompt),
            daemon=True,
        )
        t.start()

    def _worker(self, request_id, provider, model, messages, system_prompt):
        chain = self._build_chain(provider, model)
        if not chain:
            self.response_error.emit(request_id,
                "⚠ Немає налаштованих API ключів. Додайте у Налаштування → API Ключі.")
            return

        last_err = ""
        for prov, key, mdl in chain:
            try:
                if prov == "_proxy_":
                    text = self._proxy_call(provider, mdl, messages, system_prompt, key)
                else:
                    text = self._call(prov, mdl, messages, system_prompt)
                if text:
                    if prov not in (provider, "_proxy_"):
                        label = self._PROVIDER_LABELS.get(prov, prov)
                        text = f"⚡ *[Переключився на {label}]*\n\n{text}"
                    self.response_ready.emit(request_id, text)
                    return
            except Exception as e:
                last_err = str(e)
                print(f"[AI] {prov} failed: {e} — trying next…")
                continue

        self.response_error.emit(request_id,
            f"⚠ Всі провайдери не відповіли.\nОстання помилка: {last_err[:120]}")

    # ── Text generation (streaming) ───────────────────────────────────────────
    def send_stream(self, request_id: str, provider: str, model: str,
                    messages: list, system_prompt: str = ""):
        t = threading.Thread(
            target=self._stream_worker,
            args=(request_id, provider, model, messages, system_prompt),
            daemon=True,
        )
        t.start()

    # o-series and newer GPT models don't accept temperature or max_tokens
    _NO_TEMPERATURE = ("o1", "o3", "o4", "gpt-5", "gpt-4.5")
    _USE_COMPLETION_TOKENS = ("o1", "o3", "o4", "gpt-5", "gpt-4.5", "gpt-4.1")

    def _openai_params(self, model: str) -> dict:
        """Return only the parameters supported by this OpenAI model."""
        kw: dict = {}
        if not model.startswith(self._NO_TEMPERATURE):
            kw["temperature"] = self.temperature
        if model.startswith(self._USE_COMPLETION_TOKENS):
            kw["max_completion_tokens"] = self.max_tokens
        else:
            kw["max_tokens"] = self.max_tokens
        return kw

    def _stream_worker(self, request_id, provider, model, messages, system_prompt):
        chain = self._build_chain(provider, model)
        if not chain:
            self.response_error.emit(request_id,
                "⚠ Немає налаштованих API ключів. Додайте у Налаштування → API Ключі.")
            return

        last_err = ""
        for idx, (prov, key, mdl) in enumerate(chain):
            # Notify user we're switching (not on first attempt)
            if idx > 0:
                label = self._PROVIDER_LABELS.get(prov, prov)
                self.response_token.emit(request_id,
                    f"\n\n⚡ *Переключаюсь на {label}…*\n\n")

            try:
                self._run_stream(request_id, prov, key, mdl, messages, system_prompt)
                return   # success — done
            except Exception as e:
                last_err = str(e)
                err_lower = str(e).lower()
                # Decide whether to retry
                retry = any(code in err_lower for code in
                            ("401", "402", "403", "429", "insufficient_quota",
                             "billing", "not active", "invalid_api_key",
                             "rate limit", "exceeded", "no such model",
                             "model_not_found", "connection", "timeout",
                             "nameresolution", "refused"))
                print(f"[AI] stream {prov} failed ({e}) — {'retry' if retry else 'hard error'}")
                if not retry:
                    break   # hard error (bad prompt, etc.) — no point retrying

        self.response_error.emit(request_id,
            f"⚠ Всі провайдери не відповіли.\nОстання помилка: {last_err[:120]}")

    def _run_stream(self, request_id, provider, key, model, messages, system_prompt):
        """Dispatch to the right streaming method. Raises on any error."""
        if provider == "_proxy_":
            # key here is actually the license key
            self._proxy_stream(request_id, self.config.get("ai_provider", "openai"),
                               model, messages, system_prompt, key)
        elif provider == "openai":
            self._openai_stream(request_id, key, model, messages, system_prompt)
        elif provider == "anthropic":
            self._anthropic_stream(request_id, key, model, messages, system_prompt)
        elif provider == "google":
            self._google_stream(request_id, key, model, messages, system_prompt)
        elif provider in ("xai", "deepseek", "perplexity"):
            self._openai_compat_stream(request_id, provider, key, model, messages, system_prompt)
        elif provider == "ollama":
            self._ollama_stream(request_id, model, messages, system_prompt)
        else:
            raise ValueError(f"Провайдер «{provider}» не підтримується.")

    def _openai_stream(self, req_id, key, model, messages, system_prompt):
        if not key:
            raise RuntimeError("no_key: OpenAI API key not set")
        import json as _j
        from openai import OpenAI
        from core.ai_tools import TOOLS, run_tool, build_system_with_profile
        client = OpenAI(api_key=key)
        sys = build_system_with_profile(system_prompt) if system_prompt else ""
        msgs = ([{"role": "system", "content": sys}] if sys else []) + list(messages)

        use_tools = not model.startswith(self._NO_TEMPERATURE)
        kw = self._openai_params(model)
        if use_tools:
            kw["tools"] = TOOLS
            kw["tool_choice"] = "auto"

        # First pass — may return tool calls or text
        resp = client.chat.completions.create(model=model, messages=msgs, **kw)
        msg  = resp.choices[0].message

        # Handle tool calls before streaming the final answer
        for _ in range(3):
            if not getattr(msg, "tool_calls", None):
                break
            msgs.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try: args = _j.loads(tc.function.arguments)
                except Exception: args = {}
                print(f"[Chat stream] 🔧 {tc.function.name}({args})")
                # Emit a subtle "searching..." token so user sees activity
                self.response_token.emit(req_id, f"\n*🔍 {tc.function.name}…*\n\n")
                result = run_tool(tc.function.name, args)
                msgs.append({"role": "tool", "content": result, "tool_call_id": tc.id})
            resp = client.chat.completions.create(model=model, messages=msgs,
                                                   **self._openai_params(model))
            msg = resp.choices[0].message

        # Stream the final text answer — real streaming call
        stream_resp = client.chat.completions.create(
            model=model, messages=msgs, stream=True, **self._openai_params(model))
        for chunk in stream_resp:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                self.response_token.emit(req_id, delta)
        self.response_done.emit(req_id)

    def _anthropic_stream(self, req_id, key, model, messages, system_prompt):
        if not key:
            raise RuntimeError("no_key: Anthropic API key not set")
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        kw = dict(model=model, max_tokens=self.max_tokens,
                  messages=messages, temperature=self.temperature)
        if system_prompt:
            kw["system"] = system_prompt
        with client.messages.stream(**kw) as stream:
            for text in stream.text_stream:
                self.response_token.emit(req_id, text)
        self.response_done.emit(req_id)

    def _google_stream(self, req_id, key, model, messages, system_prompt):
        if not key:
            raise RuntimeError("no_key: Google API key not set")
        import google.genai as genai
        client = genai.Client(api_key=key)
        contents = [
            {"role": "user" if m["role"] == "user" else "model",
             "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        cfg = {"system_instruction": system_prompt} if system_prompt else None
        for chunk in client.models.generate_content_stream(
            model=model, contents=contents, config=cfg
        ):
            if chunk.text:
                self.response_token.emit(req_id, chunk.text)
        self.response_done.emit(req_id)

    def _openai_compat_stream(self, req_id, provider, key, model, messages, system_prompt):
        if not key:
            raise RuntimeError(f"no_key: {provider} API key not set")
        from openai import OpenAI
        bases = {
            "xai":        "https://api.x.ai/v1",
            "deepseek":   "https://api.deepseek.com",
            "perplexity": "https://api.perplexity.ai",
        }
        client = OpenAI(api_key=key, base_url=bases[provider])
        msgs = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages
        stream = client.chat.completions.create(
            model=model, messages=msgs,
            temperature=self.temperature, max_tokens=self.max_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                self.response_token.emit(req_id, delta)
        self.response_done.emit(req_id)

    def _ollama_stream(self, req_id, model, messages, system_prompt):
        import requests
        msgs = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages
        try:
            resp = requests.post(
                f"{self.ollama_url}/v1/chat/completions",
                json={"model": model, "messages": msgs,
                      "temperature": self.temperature, "stream": True},
                stream=True, timeout=120,
            )
            resp.raise_for_status()
            import json as _json
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    break
                try:
                    chunk = _json.loads(line)
                    delta = chunk["choices"][0]["delta"].get("content","")
                    if delta:
                        self.response_token.emit(req_id, delta)
                except Exception:
                    pass
        except Exception as e:
            self.response_error.emit(req_id, f"⚠ Ollama помилка: {e}")
            return
        self.response_done.emit(req_id)

    # ── Image generation ──────────────────────────────────────────────────────
    def generate_image(self, request_id: str, provider: str, prompt: str,
                       size: str = "1024x1024", style: str = "vivid",
                       ref_image_b64: str = ""):
        t = threading.Thread(
            target=self._image_worker,
            args=(request_id, provider, prompt, size, style, ref_image_b64),
            daemon=True,
        )
        t.start()

    def _image_worker(self, req_id, provider, prompt, size, style, ref_image_b64):
        try:
            if provider == "openai":
                b64 = self._dalle(prompt, size, style, ref_image_b64)
            elif provider == "google":
                if self.proxy_active and PROXY_URL and self._license_key:
                    # Proxy mode — NO fallback to direct call (avoids billing user's key)
                    b64 = self._proxy_image(prompt, ref_image_b64)
                else:
                    # Direct mode (trial / no license)
                    b64 = self._gemini_imagen(prompt, size, ref_image_b64)
            else:
                self.response_error.emit(req_id,
                    f"Генерація зображень не підтримується для «{provider}».\n"
                    "Використайте OpenAI (DALL-E 3) або Google (Imagen).")
                return
            self.image_ready.emit(req_id, b64)
        except Exception as e:
            self.response_error.emit(req_id, str(e))

    def _dalle(self, prompt: str, size: str, style: str, ref_b64: str) -> str:
        from openai import OpenAI
        key = self.api_keys.get("openai", "")
        if not key:
            raise RuntimeError("⚠ API ключ OpenAI не налаштовано.")
        client = OpenAI(api_key=key)

        if ref_b64:
            # gpt-image-1 supports image editing (inpainting)
            try:
                from PIL import Image as PILImage
                import io
                img_bytes = base64.b64decode(ref_b64)
                img = PILImage.open(io.BytesIO(img_bytes)).convert("RGBA")
                side = min(img.width, img.height, 1024)
                img = img.resize((side, side), PILImage.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                try:
                    resp = client.images.edit(
                        model="gpt-image-1",
                        image=buf,
                        prompt=prompt,
                        n=1,
                    )
                except Exception:
                    buf.seek(0)
                    edit_size = f"{side}x{side}" if side in (256, 512, 1024) else "1024x1024"
                    resp = client.images.edit(
                        model="dall-e-2",
                        image=buf,
                        prompt=prompt,
                        size=edit_size,
                        n=1,
                        response_format="b64_json",
                    )
            except ImportError:
                raise RuntimeError("Встановіть Pillow для редагування зображень: pip install Pillow")
        else:
            # Try gpt-image-1 first (newer, better quality), fall back to dall-e-3
            try:
                allowed_new = {"1024x1024", "1024x1536", "1536x1024", "auto"}
                gen_size = size if size in allowed_new else "1024x1024"
                resp = client.images.generate(
                    model="gpt-image-1",
                    prompt=prompt,
                    size=gen_size,
                    quality="high",
                    n=1,
                )
            except Exception:
                allowed_old = {"1024x1024", "1024x1792", "1792x1024"}
                gen_size = size if size in allowed_old else "1024x1024"
                resp = client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size=gen_size,
                    quality="standard",
                    style=style if style in ("vivid", "natural") else "vivid",
                    n=1,
                    response_format="b64_json",
                )

        b64 = resp.data[0].b64_json
        if not b64:
            # Some models return URL instead of b64
            import urllib.request as _ur
            with _ur.urlopen(resp.data[0].url) as r:
                b64 = base64.b64encode(r.read()).decode()
        return b64

    def _proxy_image(self, prompt: str, ref_b64: str = "") -> str:
        """Generate image via proxy server (US) using server's own free Google key.
        No user billing key sent — server's GOOGLE_API_KEY env var is used."""
        import urllib.request as _ur
        import json as _j

        payload = _j.dumps({
            "prompt": prompt,
            "ref_image_b64": ref_b64,
        }).encode()
        req = _ur.Request(
            f"{PROXY_URL}/api/v1/image",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._license_key}",
            },
            method="POST",
        )
        with _ur.urlopen(req, timeout=90) as r:
            data = _j.loads(r.read())
        b64 = data.get("b64", "")
        if not b64:
            raise RuntimeError("Proxy: no image in response")
        return b64

    def _proxy_video(self, prompt: str, duration: int) -> str:
        """Generate video via proxy server (US) — bypasses EU/Germany HuggingFace DNS block.
        Returns base64-encoded mp4 bytes."""
        import urllib.request as _ur
        import json as _j
        import pathlib
        import time as _time

        payload = _j.dumps({
            "prompt": prompt,
            "duration": duration,
        }).encode()
        req = _ur.Request(
            f"{PROXY_URL}/api/v1/video",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._license_key}",
            },
            method="POST",
        )
        with _ur.urlopen(req, timeout=200) as r:
            data = _j.loads(r.read())
        b64 = data.get("b64", "")
        if not b64:
            raise RuntimeError("Proxy: no video in response")

        # Decode and save to ~/Pictures/AXIS OS/
        import base64 as _b64
        video_bytes = _b64.b64decode(b64)
        save_dir = pathlib.Path.home() / "Pictures" / "AXIS OS"
        save_dir.mkdir(parents=True, exist_ok=True)
        fname = f"axis_video_{int(_time.time())}.mp4"
        (save_dir / fname).write_bytes(video_bytes)
        return fname

    def _gemini_imagen(self, prompt: str, size: str, ref_b64: str) -> str:
        key = self.api_keys.get("google", "")
        if not key:
            raise RuntimeError("⚠ API ключ Google не налаштовано.")

        from google import genai as _genai
        from google.genai import types as _gtypes

        client = _genai.Client(api_key=key)
        _MODELS = (
            "gemini-2.5-flash-image",
            "gemini-3.1-flash-image-preview",
            "gemini-3-pro-image-preview",
        )
        cfg = _gtypes.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"])

        last_err = ""
        for model in _MODELS:
            try:
                if ref_b64:
                    img_bytes = base64.b64decode(ref_b64)
                    contents = [
                        _gtypes.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                        _gtypes.Part.from_text(text=prompt),
                    ]
                else:
                    contents = prompt

                resp = client.models.generate_content(
                    model=model, contents=contents, config=cfg
                )
                for cand in resp.candidates or []:
                    for part in cand.content.parts or []:
                        if part.inline_data:
                            return base64.b64encode(part.inline_data.data).decode()
                last_err = f"{model} → не повернув зображення"
            except Exception as e:
                last_err = f"{model} → {e}"
                continue

        raise RuntimeError(
            f"⚠ Gemini не зміг згенерувати зображення.\n{last_err}\n\n"
            "Перевірте що ваш Google API ключ дійсний та billing увімкнено\n"
            "на aistudio.google.com"
        )

    # ── Video generation ──────────────────────────────────────────────────────
    def generate_video(self, request_id: str, prompt: str,
                       duration: int = 9, aspect_ratio: str = "16:9",
                       ref_image_b64: str = ""):
        t = threading.Thread(
            target=self._video_worker,
            args=(request_id, prompt, duration, aspect_ratio, ref_image_b64),
            daemon=True,
        )
        t.start()

    def _video_worker(self, req_id, prompt, duration, aspect_ratio, ref_image_b64):
        try:
            # Route through proxy (US + Replicate) — only working option from Germany
            if self.proxy_active and PROXY_URL and self._license_key:
                try:
                    fname = self._proxy_video(prompt, duration)
                    self.video_ready.emit(req_id, fname)
                    return
                except Exception as e:
                    print(f"[AXIS] proxy video failed: {e}")
                    self.response_error.emit(req_id,
                        f"⚠ Генерація відео через проксі не вдалась:\n{str(e)[:200]}")
                    return

            # Fallback: direct HuggingFace (only works outside Germany)
            try:
                fname = self._hf_video(prompt, duration, aspect_ratio)
                self.video_ready.emit(req_id, fname)
            except Exception as e:
                self.response_error.emit(req_id,
                    "⚠ Генерація відео недоступна без активної ліцензії AXIS OS.")
        except Exception as e:
            self.response_error.emit(req_id, str(e))

    def _hf_video(self, prompt: str, duration: int, aspect_ratio: str) -> str:
        """Generate video via HuggingFace Inference API (free).
        Uses zeroscope_v2_576w — no API key required, but optional HF token.
        Returns filename saved to ~/Pictures/AXIS OS/."""
        import time as _time
        import pathlib
        import urllib.request as _ur
        import urllib.error as _ue
        import json as _j

        hf_key = self.api_keys.get("huggingface", "")
        headers = {"Content-Type": "application/json"}
        if hf_key:
            headers["Authorization"] = f"Bearer {hf_key}"

        # zeroscope: fast, free, decent quality 576×320
        _MODELS = [
            "cerspense/zeroscope_v2_576w",
            "damo-vilab/text-to-video-ms-1.7b",
        ]

        num_frames = min(24, max(8, duration * 8))  # ~8 fps
        payload = _j.dumps({
            "inputs": prompt,
            "parameters": {"num_frames": num_frames, "num_inference_steps": 25},
        }).encode()

        last_err = ""
        for model in _MODELS:
            url = f"https://api-inference.huggingface.co/models/{model}"
            try:
                req = _ur.Request(url, data=payload, headers=headers, method="POST")
                # HF may return 503 (model loading) — retry up to 3 min
                for attempt in range(18):
                    try:
                        with _ur.urlopen(req, timeout=120) as r:
                            video_bytes = r.read()
                        if len(video_bytes) < 1000:
                            raise RuntimeError(f"відповідь занадто мала: {len(video_bytes)} байт")
                        # Save to Pictures/AXIS OS/
                        save_dir = pathlib.Path.home() / "Pictures" / "AXIS OS"
                        save_dir.mkdir(parents=True, exist_ok=True)
                        fname = f"axis_video_{int(_time.time())}.mp4"
                        (save_dir / fname).write_bytes(video_bytes)
                        return fname
                    except _ue.HTTPError as e:
                        body = e.read().decode()[:200]
                        if e.code == 503 and attempt < 17:
                            # Model warming up — wait and retry
                            _time.sleep(10)
                            continue
                        last_err = f"{model} HTTP {e.code}: {body}"
                        break
            except Exception as e:
                last_err = f"{model}: {e}"
                continue

        raise RuntimeError(
            f"⚠ HuggingFace не зміг згенерувати відео.\n{last_err}\n\n"
            "Щоб покращити доступність — додайте безкоштовний токен:\n"
            "huggingface.co/settings/tokens → Налаштування → API Ключі → HuggingFace"
        )

    def _luma_video(self, prompt: str, duration: int, aspect_ratio: str,
                    ref_b64: str) -> str:
        """Generate video via Luma AI Dream Machine API.
        Polls until complete (typically 30–120 s). Returns video URL."""
        import requests as req
        import time as _time
        key = self.api_keys.get("luma", "")
        if not key:
            raise RuntimeError("⚠ API ключ Luma AI не налаштовано.\nДодайте у Налаштування → API Ключі → Luma AI.")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body: dict = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "loop": False,
        }
        if ref_b64:
            body["keyframes"] = {
                "frame0": {
                    "type": "image",
                    "url": f"data:image/png;base64,{ref_b64}",
                }
            }

        # Luma API endpoints (try both v1 and v2 in case of changes)
        _LUMA_BASE = "https://api.lumalabs.ai/dream-machine/v1"

        # Submit generation
        try:
            r = req.post(f"{_LUMA_BASE}/generations",
                         headers=headers, json=body, timeout=30)
        except Exception as e:
            err = str(e)
            if "getaddrinfo" in err or "NameResolution" in err or "ConnectionError" in err:
                raise RuntimeError(
                    "⚠ Не вдалось з'єднатись з Luma AI.\n"
                    "Можливі причини:\n"
                    "• Немає доступу до api.lumalabs.ai (заблокований DNS/файрвол)\n"
                    "• Спробуйте підключити VPN"
                )
            raise RuntimeError(f"⚠ Luma мережева помилка: {err[:150]}")

        if r.status_code not in (200, 201):
            raise RuntimeError(f"Luma HTTP {r.status_code}: {r.text[:200]}")
        gen_id = r.json().get("id") or r.json().get("generation_id")
        if not gen_id:
            raise RuntimeError(f"Luma: no generation ID in response: {r.text[:200]}")

        # Poll until done (max 3 min)
        for _ in range(36):   # 36 × 5s = 180s
            _time.sleep(5)
            try:
                poll = req.get(
                    f"{_LUMA_BASE}/generations/{gen_id}",
                    headers=headers, timeout=15)
            except Exception:
                continue
            if poll.status_code != 200:
                continue
            data = poll.json()
            state = data.get("state", "")
            if state == "completed":
                assets = data.get("assets") or {}
                video_url = assets.get("video") or data.get("video_url") or ""
                if video_url:
                    return video_url
                raise RuntimeError("Luma: completed but no video URL")
            if state in ("failed", "error"):
                reason = data.get("failure_reason") or data.get("error") or "failed"
                raise RuntimeError(f"Luma: generation failed — {reason}")
            # dreaming / processing — keep polling

        raise RuntimeError("Luma: timeout after 3 minutes")

    # ── Non-streaming ─────────────────────────────────────────────────────────
    def _call(self, provider, model, messages, system_prompt) -> str:
        """Raises on any error — caller (_worker) handles fallback."""
        if provider == "ollama":
            return self._ollama(model, messages, system_prompt)
        key = self.api_keys.get(provider, "")
        if not key:
            raise RuntimeError(f"no_key: API ключ для «{provider}» не налаштовано")
        if provider == "openai":
            return self._openai(key, model, messages, system_prompt)
        elif provider == "anthropic":
            return self._anthropic(key, model, messages, system_prompt)
        elif provider == "google":
            return self._google(key, model, messages, system_prompt)
        elif provider in ("xai", "deepseek", "perplexity"):
            return self._openai_compat(provider, key, model, messages, system_prompt)
        raise ValueError(f"Провайдер «{provider}» не підтримується.")

    def _ollama(self, model, messages, system_prompt) -> str:
        import requests
        msgs = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages
        try:
            resp = requests.post(
                f"{self.ollama_url}/v1/chat/completions",
                json={"model": model, "messages": msgs,
                      "temperature": self.temperature, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.ConnectionError:
            return "⚠ Ollama не запущено.\nВстановіть: https://ollama.com\nЗапустіть: ollama serve"
        except Exception as e:
            return f"⚠ Ollama помилка: {e}"

    def _openai(self, key, model, messages, system_prompt) -> str:
        import json as _j
        from openai import OpenAI
        from core.ai_tools import TOOLS, run_tool, build_system_with_profile
        client = OpenAI(api_key=key)
        sys = build_system_with_profile(system_prompt) if system_prompt else ""
        msgs = ([{"role": "system", "content": sys}] if sys else []) + list(messages)

        # o-series don't support tools
        use_tools = not model.startswith(self._NO_TEMPERATURE)
        kw = self._openai_params(model)
        if use_tools:
            kw["tools"] = TOOLS
            kw["tool_choice"] = "auto"

        resp = client.chat.completions.create(model=model, messages=msgs, **kw)
        msg  = resp.choices[0].message

        # ── Handle tool calls (up to 3 rounds) ───────────────────────────────
        for _ in range(3):
            if not getattr(msg, "tool_calls", None):
                break
            msgs.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try: args = _j.loads(tc.function.arguments)
                except Exception: args = {}
                print(f"[Chat] 🔧 {tc.function.name}({args})")
                result = run_tool(tc.function.name, args)
                msgs.append({"role": "tool", "content": result, "tool_call_id": tc.id})
            resp = client.chat.completions.create(model=model, messages=msgs,
                                                   **self._openai_params(model))
            msg = resp.choices[0].message

        return msg.content or ""

    def _anthropic(self, key, model, messages, system_prompt) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        kw = dict(model=model, max_tokens=self.max_tokens,
                  messages=messages, temperature=self.temperature)
        if system_prompt:
            kw["system"] = system_prompt
        resp = client.messages.create(**kw)
        return resp.content[0].text if resp.content else ""

    def _google(self, key, model, messages, system_prompt) -> str:
        import google.genai as genai
        client = genai.Client(api_key=key)
        contents = [
            {"role": "user" if m["role"] == "user" else "model",
             "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        cfg = {"system_instruction": system_prompt} if system_prompt else None
        resp = client.models.generate_content(
            model=model, contents=contents, config=cfg,
        )
        return resp.text or ""

    def _openai_compat(self, provider, key, model, messages, system_prompt) -> str:
        from openai import OpenAI
        bases = {
            "xai":        "https://api.x.ai/v1",
            "deepseek":   "https://api.deepseek.com",
            "perplexity": "https://api.perplexity.ai",
        }
        client = OpenAI(api_key=key, base_url=bases[provider])
        msgs = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages
        resp = client.chat.completions.create(
            model=model, messages=msgs,
            temperature=self.temperature, max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content or ""

    # ── AXIS OS Proxy (paid license) ──────────────────────────────────────────
    def _proxy_call(self, provider: str, model: str, messages: list,
                    system_prompt: str, license_key: str) -> str:
        """Send a non-streaming request through the AXIS OS proxy server."""
        body: dict = {
            "provider":      provider,
            "model":         model,
            "messages":      messages,
            "system_prompt": system_prompt,
            "stream":        False,
            "temperature":   self.temperature,
            "max_tokens":    self.max_tokens,
        }
        # Pass user's own key for providers not configured on server (e.g. Google)
        user_key = self.api_keys.get(provider, "")
        if user_key:
            body["user_key"] = user_key
        payload = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{PROXY_URL}/api/v1/chat",
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {license_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data.get("text", "")

    def _proxy_stream(self, request_id: str, provider: str, model: str,
                      messages: list, system_prompt: str, license_key: str):
        """Stream tokens from the AXIS OS proxy server via SSE."""
        body: dict = {
            "provider":      provider,
            "model":         model,
            "messages":      messages,
            "system_prompt": system_prompt,
            "stream":        True,
            "temperature":   self.temperature,
            "max_tokens":    self.max_tokens,
        }
        # Pass user's own key for providers not configured on server (e.g. Google)
        user_key = self.api_keys.get(provider, "")
        if user_key:
            body["user_key"] = user_key
        payload = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{PROXY_URL}/api/v1/chat",
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {license_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                chunk = line[6:]
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                    if "error" in data:
                        raise RuntimeError(data["error"])
                    token = data.get("token", "")
                    if token:
                        self.response_token.emit(request_id, token)
                except json.JSONDecodeError:
                    pass
        self.response_done.emit(request_id)
