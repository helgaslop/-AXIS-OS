"""AI, image & video generation handlers + config/key management."""
import json
import os
import threading

from core.secrets import get_all_keys, set_key as _secrets_set, migrate_from_config


def _get_license():
    from core.license import LicenseManager
    from core.paths import USER_DATA_DIR
    return LicenseManager(USER_DATA_DIR)


class AiHandlerMixin:

    def _get_api_keys(self) -> dict:
        """Return API keys merged from Credential Manager + config (nested + flat)."""
        # Start with nested api_keys dict (keyring uses these names)
        base = dict(self._cfg.get("api_keys", {}))
        # Also merge top-level flat keys (openai_key, google_key, etc.)
        _flat = {
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
        for prov, flat in _flat.items():
            if not base.get(prov) and self._cfg.get(flat):
                base[prov] = self._cfg[flat]
        return get_all_keys(base)

    # ── AI chat ───────────────────────────────────────────────────────────────
    def _ai_send(self, p: dict):
        result = _get_license().consume("ai_messages")
        if not result["ok"]:
            req_id = p.get("id", "req")
            self.push_to_js.emit("ai_error", json.dumps({"id": req_id, "error": result["msg"]}))
            return
        self._ai.send(
            p.get("id", "req"), p.get("provider", "openai"),
            p.get("model", "gpt-4o"), p.get("messages", []),
            p.get("system", "Ти корисний AI асистент AXIS OS."),
        )

    def _ai_send_stream(self, p: dict):
        result = _get_license().consume("ai_messages")
        if not result["ok"]:
            req_id = p.get("id", "req")
            self.push_to_js.emit("ai_error", json.dumps({"id": req_id, "error": result["msg"]}))
            return
        self._ai.send_stream(
            p.get("id", "req"), p.get("provider", "openai"),
            p.get("model", "gpt-4o"), p.get("messages", []),
            p.get("system", "Ти корисний AI асистент AXIS OS."),
        )

    def _generate_image(self, p: dict):
        result = _get_license().check("image_gen")
        if not result["ok"]:
            self.push_to_js.emit("ai_error",
                json.dumps({"id": p.get("id", "img_req"), "error": result["msg"]}))
            return
        self._ai.generate_image(
            p.get("id", "img_req"), p.get("provider", "openai"),
            p.get("prompt", ""), p.get("size", "1024x1024"),
            p.get("style", "vivid"), p.get("ref_image", ""),
        )

    def _generate_video(self, p: dict):
        result = _get_license().check("image_gen")
        if not result["ok"]:
            self.push_to_js.emit("ai_error",
                json.dumps({"id": p.get("id", "vid_req"), "error": result["msg"]}))
            return
        self._ai.generate_video(
            p.get("id", "vid_req"), p.get("prompt", ""),
            int(p.get("duration", 9)), p.get("aspect_ratio", "16:9"),
            p.get("ref_image", ""),
        )

    # ── AI signal callbacks ───────────────────────────────────────────────────
    def _on_ai_ready(self, req_id: str, text: str):
        self.push_to_js.emit("ai_response", json.dumps({"id": req_id, "text": text}))

    def _on_ai_error(self, req_id: str, error: str):
        self.push_to_js.emit("ai_error", json.dumps({"id": req_id, "error": error}))

    def _on_ai_token(self, req_id: str, token: str):
        self.push_to_js.emit("ai_token", json.dumps({"id": req_id, "token": token}))

    def _on_ai_done(self, req_id: str):
        self.push_to_js.emit("ai_done", json.dumps({"id": req_id}))

    def _on_image_ready(self, req_id: str, b64: str):
        self.push_to_js.emit("image_ready", json.dumps({"id": req_id, "b64": b64}))
        # Auto-save to Pictures/AXIS OS/
        try:
            import base64 as _b64, pathlib, time as _t
            save_dir = pathlib.Path.home() / "Pictures" / "AXIS OS"
            save_dir.mkdir(parents=True, exist_ok=True)
            fpath = save_dir / f"axis_image_{int(_t.time())}.png"
            fpath.write_bytes(_b64.b64decode(b64))
            self.push_to_js.emit("toast", json.dumps({"msg": f"💾 Збережено: {fpath.name}"}))
        except Exception as e:
            print(f"[AXIS] auto-save image failed: {e}")

    def _on_video_ready(self, req_id: str, url: str):
        # If it's just a filename (from Gemini Veo), convert to local HTTP URL
        if not url.startswith(("http", "data:", "file:")):
            try:
                http_url = self._win.get_media_url(url)
                url = http_url
            except Exception:
                pass
        self.push_to_js.emit("video_ready", json.dumps({"id": req_id, "url": url}))

    # ── Ollama model discovery ────────────────────────────────────────────────
    def _fetch_ollama(self, _):
        threading.Thread(target=self._fetch_ollama_worker, daemon=True).start()

    def _fetch_ollama_worker(self):
        import urllib.request
        base = self._cfg.get("ollama_url", "http://localhost:11434")
        try:
            with urllib.request.urlopen(f"{base}/api/tags", timeout=3) as r:
                data = json.loads(r.read().decode())
            names = [m["name"] for m in data.get("models", [])]
            if names:
                self.push_to_js.emit("ollama_models", json.dumps(names))
        except Exception:
            pass  # Ollama not running — silently skip

    # ── Config / API keys ─────────────────────────────────────────────────────
    def _save_api_key(self, p: dict):
        provider = p.get("provider", "")
        key      = p.get("key", "")
        if provider:
            if _secrets_set(provider, key):
                # Saved in Credential Manager — keep empty placeholder so
                # get_all_keys() still knows to look up this provider in keyring
                self._cfg.setdefault("api_keys", {})[provider] = ""
            else:
                # keyring unavailable — fall back to config file
                self._cfg.setdefault("api_keys", {})[provider] = key
            self._ai.update_key(provider, key)
            self._save_config_file()
            self.push_to_js.emit("toast",
                json.dumps({"msg": f"✓ API ключ «{provider}» збережено"}))
            # Refresh status panel automatically after saving
            threading.Thread(target=self._check_api_status_worker, daemon=True).start()

    def _save_config(self, p: dict):
        self._cfg.update(p)
        if "ollama_url" in p:
            self._ai.ollama_url = p["ollama_url"]
        ai_p = p.get("ai", {})
        if "temperature" in ai_p:
            self._ai.temperature = float(ai_p["temperature"])
        if "max_tokens" in ai_p:
            self._ai.max_tokens = int(ai_p["max_tokens"])
        self._save_config_file()

    def _save_config_file(self):
        try:
            from core.paths import CONFIG_FILE
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[AXIS] config save error: {e}")

    # ── API status check ──────────────────────────────────────────────────────
    def _check_api_status(self, _):
        """Перевіряє які API ключі налаштовані, надсилає результат у JS."""
        threading.Thread(target=self._check_api_status_worker, daemon=True).start()

    def _check_api_status_worker(self):
        keys = self._get_api_keys()
        from core.paths import SPOTIFY_TOKEN_FILE
        results = {}

        simple = [
            "openai", "anthropic", "google", "xai",
            "deepseek", "perplexity", "luma",
            "serper", "tavily", "openweather",
        ]
        for p in simple:
            k = keys.get(p, "")
            results[p] = "set" if k else "missing"

        sp_id  = keys.get("spotify_client_id", "")
        sp_sec = keys.get("spotify_client_secret", "")
        token_file = str(SPOTIFY_TOKEN_FILE)
        if sp_id and sp_sec:
            results["spotify"] = "token" if os.path.exists(token_file) else "set"
        else:
            results["spotify"] = "missing"

        self.push_to_js.emit("api_status", json.dumps(results))

    # ── Live API key tests ────────────────────────────────────────────────────
    def _run_api_tests(self, _):
        threading.Thread(target=self._run_api_tests_worker, daemon=True).start()

    def _run_api_tests_worker(self):
        import requests as _r
        keys = self._get_api_keys()

        def push(id_, name, ico, status, msg):
            self.push_to_js.emit("api_test_result", json.dumps(
                {"id": id_, "name": name, "ico": ico, "status": status, "msg": msg}))

        def test(id_, name, ico, fn):
            k = keys.get(id_, "").strip()
            if not k:
                push(id_, name, ico, "no_key", "Ключ не задано"); return
            push(id_, name, ico, "testing", "Перевіряю...")
            try:
                ok, msg = fn(k)
                push(id_, name, ico, "ok" if ok else "error", msg)
            except Exception as e:
                push(id_, name, ico, "error", str(e)[:70])

        # OpenAI
        def chk_openai(k):
            r = _r.get("https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {k}"}, timeout=8)
            if r.status_code == 200: return True,  "✅ Активний"
            if r.status_code == 401: return False, "❌ Невірний ключ"
            if r.status_code == 429: return True,  "⚠️ Ліміт запитів вичерпано"
            return False, f"❌ HTTP {r.status_code}"

        # Anthropic
        def chk_anthropic(k):
            r = _r.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": k, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-20240307", "max_tokens": 1,
                      "messages": [{"role": "user", "content": "hi"}]}, timeout=10)
            if r.status_code in (200, 400): return True,  "✅ Активний"
            if r.status_code == 401:        return False, "❌ Невірний ключ"
            if r.status_code == 429:        return True,  "⚠️ Ліміт вичерпано"
            return False, f"❌ HTTP {r.status_code}"

        # Google Gemini
        def chk_google(k):
            r = _r.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={k}",
                timeout=8)
            if r.status_code == 200: return True,  "✅ Активний"
            if r.status_code == 400: return False, "❌ Невірний ключ"
            if r.status_code == 403: return False, "❌ Доступ заборонено"
            return False, f"❌ HTTP {r.status_code}"

        # xAI Grok
        def chk_xai(k):
            r = _r.get("https://api.x.ai/v1/models",
                headers={"Authorization": f"Bearer {k}"}, timeout=8)
            if r.status_code == 200: return True,  "✅ Активний"
            if r.status_code == 401: return False, "❌ Невірний ключ"
            return False, f"❌ HTTP {r.status_code}"

        # Perplexity
        def chk_perplexity(k):
            r = _r.post("https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                json={"model": "sonar", "max_tokens": 1,
                      "messages": [{"role": "user", "content": "hi"}]}, timeout=10)
            if r.status_code in (200, 400): return True,  "✅ Активний"
            if r.status_code == 401:        return False, "❌ Невірний ключ"
            if r.status_code == 429:        return True,  "⚠️ Ліміт вичерпано"
            return False, f"❌ HTTP {r.status_code}"

        # Tavily
        def chk_tavily(k):
            r = _r.post("https://api.tavily.com/search",
                headers={"Content-Type": "application/json"},
                json={"api_key": k, "query": "test", "max_results": 1}, timeout=8)
            if r.status_code == 200: return True,  "✅ Активний"
            if r.status_code == 401: return False, "❌ Невірний ключ"
            if r.status_code == 429: return True,  "⚠️ Ліміт вичерпано"
            return False, f"❌ HTTP {r.status_code}"

        # Serper
        def chk_serper(k):
            r = _r.post("https://google.serper.dev/search",
                headers={"X-API-KEY": k, "Content-Type": "application/json"},
                json={"q": "test"}, timeout=8)
            if r.status_code == 200: return True,  "✅ Активний"
            if r.status_code == 401: return False, "❌ Невірний ключ"
            return False, f"❌ HTTP {r.status_code}"

        # OpenWeather
        def chk_weather(k):
            r = _r.get(f"https://api.openweathermap.org/data/2.5/weather?q=Kyiv&appid={k}",
                timeout=8)
            if r.status_code == 200: return True,  "✅ Активний"
            if r.status_code == 401: return False, "❌ Невірний ключ"
            return False, f"❌ HTTP {r.status_code}"

        # Ollama (local)
        def chk_ollama(_k):
            try:
                r = _r.get(self._cfg.get("ollama_url", "http://localhost:11434") + "/api/tags",
                    timeout=3)
                if r.status_code == 200:
                    models = [m["name"] for m in r.json().get("models", [])]
                    return True, f"✅ {len(models)} моделей: {', '.join(models[:3])}"
            except Exception:
                pass
            return False, "❌ Ollama не запущено"

        tests = [
            ("openai",      "OpenAI GPT",         "🤖", chk_openai),
            ("anthropic",   "Anthropic Claude",   "🔵", chk_anthropic),
            ("google",      "Google Gemini",      "✨", chk_google),
            ("xai",         "xAI Grok",           "⚡", chk_xai),
            ("perplexity",  "Perplexity",         "🌐", chk_perplexity),
            ("tavily",      "Tavily Search",      "🔍", chk_tavily),
            ("serper",      "Google Serper",      "🔎", chk_serper),
            ("openweather", "OpenWeather",        "🌤", chk_weather),
            ("ollama",      "Ollama (local)",     "🖥", chk_ollama),
        ]

        # Push initial "no_key" / "testing" states, then run tests
        for id_, name, ico, fn in tests:
            test(id_, name, ico, fn)

        # Final done signal
        self.push_to_js.emit("api_tests_done", "{}")

    # ── Spotify OAuth (з панелі) ──────────────────────────────────────────────
    def _connect_spotify(self, _):
        """Відкриває браузер для авторизації Spotify і запускає сервер-слухача."""
        keys = self._get_api_keys()
        cid  = keys.get("spotify_client_id", "")
        csec = keys.get("spotify_client_secret", "")
        if not cid or not csec:
            self.push_to_js.emit("toast", json.dumps(
                {"msg": "⚠ Спочатку збережи Client ID і Client Secret"}))
            return
        threading.Thread(target=self._spotify_oauth_worker,
                         args=(cid, csec), daemon=True).start()

    def _spotify_oauth_worker(self, client_id: str, client_secret: str):
        from core.paths import SPOTIFY_TOKEN_FILE
        import subprocess, sys, http.server, urllib.parse, os
        REDIRECT_URI = "http://127.0.0.1:8000/callback"
        SCOPE = (
            "user-modify-playback-state user-read-playback-state "
            "user-read-currently-playing user-read-playback-position "
            "user-library-read playlist-read-private"
        )
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
        except ImportError:
            self.push_to_js.emit("toast", json.dumps(
                {"msg": "⚠ Встанови spotipy: pip install spotipy"}))
            return

        try:
            auth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=REDIRECT_URI,
                scope=SCOPE,
                cache_path=str(SPOTIFY_TOKEN_FILE),
                open_browser=False,   # ми відкриємо самі
            )
            auth_url = auth.get_authorize_url()

            # Відкриваємо Chrome вручну (надійніше ніж webbrowser.open)
            opened = False
            for candidate in [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]:
                if os.path.exists(candidate):
                    subprocess.Popen([candidate, auth_url],
                                     creationflags=0x00000008)   # DETACHED_PROCESS
                    opened = True
                    break
            if not opened:
                import webbrowser
                webbrowser.open(auth_url)

            self.push_to_js.emit("toast", json.dumps(
                {"msg": "🎵 Відкрито браузер — авторизуй Spotify, потім поверніться сюди"}))

            # Чекаємо callback на порту 8000 (до 120 с)
            code_holder = [None]

            class _Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    parsed = urllib.parse.urlparse(self.path)
                    params = urllib.parse.parse_qs(parsed.query)
                    code_holder[0] = params.get("code", [None])[0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(
                        b"<h2 style='font-family:sans-serif;text-align:center;margin-top:80px'>"
                        b"&#10003; AXIS OS: Spotify \xd0\xbf\xd1\x96\xd0\xb4\xd0\xba\xd0\xbb\xd1\x8e\xd1\x87\xd0\xb5\xd0\xbd\xd0\xbe!"
                        b"<br><small>\xd0\x9c\xd0\xbe\xd0\xb6\xd0\xb5\xd1\x88 \xd0\xb7\xd0\xb0\xd0\xba\xd1\x80\xd0\xb8\xd1\x82\xd0\xb8 \xd1\x86\xd1\x8e \xd0\xb2\xd0\xba\xd0\xbb\xd0\xb0\xd0\xb4\xd0\xba\xd1\x83</small></h2>"
                    )
                def log_message(self, *a): pass  # тихий режим

            srv = http.server.HTTPServer(("127.0.0.1", 8000), _Handler)
            srv.timeout = 120
            srv.handle_request()   # чекаємо одного запиту
            srv.server_close()

            code = code_holder[0]
            if not code:
                self.push_to_js.emit("toast", json.dumps(
                    {"msg": "⚠ Авторизацію не завершено (timeout)"}))
                return

            token_info = auth.get_access_token(code, as_dict=True)
            if token_info and token_info.get("access_token"):
                self.push_to_js.emit("toast", json.dumps(
                    {"msg": "✅ Spotify підключено! Токен збережено."}))
                # Скидаємо кешований інстанс щоб наступний виклик _get_sp() перечитав токен
                from gui.handlers.spotify import SpotifyHandlerMixin
                SpotifyHandlerMixin._sp_instance = None
                self.push_to_js.emit("api_status", json.dumps(
                    {**{p: ("set" if self._cfg.get("api_keys", {}).get(p) else "missing")
                        for p in ["openai","anthropic","google","xai",
                                  "deepseek","perplexity","luma",
                                  "serper","tavily","openweather"]},
                     "spotify": "token"}))
            else:
                self.push_to_js.emit("toast", json.dumps(
                    {"msg": "⚠ Не вдалося отримати токен"}))
        except Exception as e:
            self.push_to_js.emit("toast", json.dumps(
                {"msg": f"⚠ Spotify: {str(e)[:80]}"}))

