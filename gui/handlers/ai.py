"""AI, image & video generation handlers + config/key management."""
import json
import os
import threading


class AiHandlerMixin:
    # ── AI chat ───────────────────────────────────────────────────────────────
    def _ai_send(self, p: dict):
        self._ai.send(
            p.get("id", "req"), p.get("provider", "openai"),
            p.get("model", "gpt-4o"), p.get("messages", []),
            p.get("system", "Ти корисний AI асистент AXIS OS."),
        )

    def _ai_send_stream(self, p: dict):
        self._ai.send_stream(
            p.get("id", "req"), p.get("provider", "openai"),
            p.get("model", "gpt-4o"), p.get("messages", []),
            p.get("system", "Ти корисний AI асистент AXIS OS."),
        )

    def _generate_image(self, p: dict):
        self._ai.generate_image(
            p.get("id", "img_req"), p.get("provider", "openai"),
            p.get("prompt", ""), p.get("size", "1024x1024"),
            p.get("style", "vivid"), p.get("ref_image", ""),
        )

    def _generate_video(self, p: dict):
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

    def _on_video_ready(self, req_id: str, url: str):
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
            self._cfg.setdefault("api_keys", {})[provider] = key
            self._ai.update_key(provider, key)
            self._save_config_file()
            self.push_to_js.emit("toast",
                json.dumps({"msg": f"✓ API ключ «{provider}» збережено"}))

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
        keys = self._cfg.get("api_keys", {})
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

    # ── Spotify OAuth (з панелі) ──────────────────────────────────────────────
    def _connect_spotify(self, _):
        """Запускає OAuth авторизацію Spotify прямо з панелі."""
        keys = self._cfg.get("api_keys", {})
        cid  = keys.get("spotify_client_id", "")
        csec = keys.get("spotify_client_secret", "")
        if not cid or not csec:
            self.push_to_js.emit("toast", json.dumps(
                {"msg": "⚠ Спочатку збережи Client ID і Client Secret"}))
            return
        self.push_to_js.emit("toast", json.dumps(
            {"msg": "🎵 Відкриваю браузер для авторизації Spotify..."}))
        threading.Thread(target=self._spotify_oauth_worker,
                         args=(cid, csec), daemon=True).start()

    def _spotify_oauth_worker(self, client_id: str, client_secret: str):
        from core.paths import SPOTIFY_TOKEN_FILE
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            scope = (
                "user-modify-playback-state "
                "user-read-playback-state "
                "user-read-currently-playing "
                "user-read-playback-position"
            )
            auth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri="http://127.0.0.1:8888/callback",
                scope=scope,
                cache_path=str(SPOTIFY_TOKEN_FILE),
                open_browser=True,
            )
            # Це відкриє браузер і зачекає на токен
            token = auth.get_access_token(as_dict=False)
            if token:
                self.push_to_js.emit("toast", json.dumps(
                    {"msg": "✅ Spotify підключено! Токен збережено."}))
                self.push_to_js.emit("api_status", json.dumps(
                    {**{p: ("set" if self._cfg.get("api_keys", {}).get(p) else "missing")
                        for p in ["openai","anthropic","google","xai",
                                  "deepseek","perplexity","luma",
                                  "serper","tavily","openweather"]},
                     "spotify": "token"}))
            else:
                self.push_to_js.emit("toast", json.dumps(
                    {"msg": "⚠ Авторизацію Spotify не завершено"}))
        except ImportError:
            self.push_to_js.emit("toast", json.dumps(
                {"msg": "⚠ Встанови spotipy: pip install spotipy"}))
        except Exception as e:
            self.push_to_js.emit("toast", json.dumps(
                {"msg": f"⚠ Spotify помилка: {str(e)[:60]}"}))

