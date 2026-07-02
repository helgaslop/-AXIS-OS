# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/ai.py  –  AI-провайдери та діалог                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Standalone thread classes (moved from aivon_sphere.py):                     ║
║    _DialogThread   – multi-provider dialog call                              ║
║    AIThread        – full AI with streaming + tool calling                   ║
║                                                                              ║
║  Mixin:                                                                      ║
║    SphereAIMixin   – methods for AivonSphere                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import re
import subprocess
import threading
import time
import webbrowser

from PyQt6.QtCore import QThread, QTimer, pyqtSignal


# ═══════════════════════════════════════════════════════════
# _DialogThread – multi-provider AI call for dialog mode
# ═══════════════════════════════════════════════════════════

class _DialogThread(QThread):
    """Multi-provider AI виклик для діалог режиму з пам'яттю"""
    result   = pyqtSignal(str)
    sentence = pyqtSignal(str)   # streaming: кожне готове речення (тільки openai)
    error    = pyqtSignal(str)

    _SENT_RE = re.compile(r'(?<=[.!?…])\s+')

    def __init__(self, provider, key, messages, config=None):
        super().__init__()
        self.provider = provider
        self.key      = key
        self.messages = messages
        self.config   = config or {}

    def _flush_sentences(self, buf: str) -> str:
        """Емітить завершені речення з буфера, повертає залишок."""
        while True:
            m = self._SENT_RE.search(buf)
            if not m:
                return buf
            s   = buf[:m.end()].strip()
            buf = buf[m.end():]
            if len(s) >= 3:
                self.sentence.emit(s)

    def run(self):
        try:
            import requests
            if self.provider == "gemini":
                self._call_gemini(requests)
            elif self.provider == "anthropic":
                self._call_anthropic(requests)
            elif self.provider == "xai":
                self._call_xai(requests)
            elif self.provider == "perplexity":
                self._call_perplexity(requests)
            else:
                self._call_openai(requests)
        except Exception as e:
            print(f"[Dialog] {self.provider} exception: {e}")
            self.error.emit(str(e)[:50])

    def _call_openai(self, requests):
        """OpenAI зі streaming — речення озвучуються по мірі генерації."""
        import json as _j
        print(f"[Dialog] GPT → {len(self.messages)} msgs (stream)...")
        r = requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "max_tokens": 300,
                  "messages": self.messages, "stream": True},
            timeout=30, stream=True)
        if r.status_code != 200:
            self.error.emit(f"GPT {r.status_code}")
            return
        buf, full = "", ""
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            try:
                delta = (_j.loads(payload)["choices"][0]
                         .get("delta", {}).get("content")) or ""
            except Exception:
                continue
            if delta:
                buf  += delta
                full += delta
                buf   = self._flush_sentences(buf)
        if buf.strip():
            self.sentence.emit(buf.strip())
        if full.strip():
            self.result.emit(full.strip())
        else:
            self.error.emit("GPT: порожня відповідь")

    def _call_anthropic(self, requests):
        print(f"[Dialog] Claude → {len(self.messages)} msgs...")
        system_text = ""
        msgs = []
        for m in self.messages:
            if m["role"] == "system":
                system_text = m["content"]
            else:
                msgs.append(m)
        body = {"model": "claude-sonnet-4-20250514", "max_tokens": 300, "messages": msgs}
        if system_text:
            body["system"] = system_text
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            json=body, timeout=15)
        if r.status_code == 200:
            self.result.emit(r.json()["content"][0]["text"].strip())
        else:
            self.error.emit(f"Claude {r.status_code}")

    def _call_xai(self, requests):
        print(f"[Dialog] Grok → {len(self.messages)} msgs...")
        r = requests.post("https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            json={"model": "grok-4-latest", "max_tokens": 300, "messages": self.messages},
            timeout=15)
        if r.status_code == 200:
            self.result.emit(r.json()["choices"][0]["message"]["content"].strip())
        else:
            self.error.emit(f"Grok {r.status_code}")

    def _call_perplexity(self, requests):
        print(f"[Dialog] Perplexity → {len(self.messages)} msgs...")
        r = requests.post("https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            json={"model": "sonar", "max_tokens": 300, "messages": self.messages},
            timeout=15)
        if r.status_code == 200:
            self.result.emit(r.json()["choices"][0]["message"]["content"].strip())
        else:
            self.error.emit(f"Perplexity {r.status_code}")

    def _call_gemini(self, requests):
        contents = []
        for m in self.messages:
            if m["role"] == "system":
                continue
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        system_text = ""
        for m in self.messages:
            if m["role"] == "system":
                system_text = m["content"]
                break

        body = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 300, "temperature": 0.8},
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        }
        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}

        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-2.5-flash:generateContent?key={self.key}")
        print(f"[Dialog] Gemini → {len(contents)} msgs...")
        r = requests.post(url, json=body, timeout=20)
        print(f"[Dialog] Gemini status={r.status_code}")
        if r.status_code == 200:
            data  = r.json()
            _cands = data.get("candidates") or []
            if not _cands:
                self.error.emit("Gemini: порожня відповідь (можливо SAFETY filter)")
                return
            parts  = _cands[0].get("content", {}).get("parts", [])
            answer = ""
            for p in reversed(parts):
                if p.get("text") and not p.get("thought"):
                    answer = p["text"].strip()
                    break
            if not answer and parts:
                answer = parts[-1].get("text", "").strip()
            if answer:
                self.result.emit(answer)
            else:
                print(f"[Dialog] Gemini empty response: {data}")
                self.error.emit("Gemini: порожня відповідь")
        else:
            print(f"[Dialog] Gemini error: {r.text[:200]}")
            self.error.emit(f"Gemini {r.status_code}")


# ═══════════════════════════════════════════════════════════
# AIThread – full AI with streaming, tool calling, history
# ═══════════════════════════════════════════════════════════

# Grok prefix (declared here so AIThread._xai() can reference it)
_GROK_PREFIX = (
    "Ти Aivon — голосовий AI асистент. Відповідай українською, "
    "лаконічно і природно. "
)


class AIThread(QThread):
    """Multi-provider AI з підтримкою діалогу (conversation history).

    Task 1: Streaming support.
      - `sentence_ready` fires for each sentence as it arrives.
      - `response` fires with the full text when generation is done.
      - Call `abort()` to cancel in-flight generation (interrupt handling).
    """
    response       = pyqtSignal(str)   # full text when done (for history / display)
    sentence_ready = pyqtSignal(str)   # Task 1: each sentence as it streams
    error          = pyqtSignal(str)

    SYSTEM = (
        "Ти Aivon — природний голосовий AI асистент для ПК. "
        "Відповідай українською мовою природно, як людина. "
        "Адаптуй довжину відповіді до запиту: "
        "на коротку команду — 1-2 речення, "
        "на питання — по суті без зайвого, "
        "на 'розкажи' / 'поясни' / 'напиши' — повністю і детально. "
        "Пам'ятаєш контекст всієї розмови."
    )

    # Спільна історія діалогу (зберігається між викликами)
    _history      = []
    _history_lock = threading.Lock()
    MAX_HISTORY   = 8   # 8 пар = 16 повідомлень

    _SMART_KEYWORDS = [
        "проаналізуй", "порівняй", "яка різниця між",
        "напиши код", "напиши програму", "склади звіт", "склади план",
        "детально розбери", "докладно поясни",
        "analyze", "compare the difference", "write code", "write a program",
    ]

    @classmethod
    def pick_model(cls, msg: str, config: dict) -> str:
        lower  = msg.lower()
        words  = lower.split()
        forced = config.get("openai_model", "")
        if forced:
            return forced
        if len(words) > 25 and any(k in lower for k in cls._SMART_KEYWORDS):
            return "gpt-4o"
        return "gpt-4o-mini"

    _MAX_INPUT_CHARS = 50_000

    def __init__(self, config: dict, msg: str, system_override: str = ""):
        super().__init__()
        self.config           = config
        self.msg              = msg[:self._MAX_INPUT_CHARS] if len(msg) > self._MAX_INPUT_CHARS else msg
        self.model            = self.pick_model(msg, config)
        self._system_override = system_override
        self._abort_event     = threading.Event()

    def abort(self) -> None:
        """Task 1: Cancel in-flight streaming generation."""
        self._abort_event.set()

    @classmethod
    def clear_history(cls):
        with cls._history_lock:
            cls._history.clear()

    @staticmethod
    def _load_owner_context() -> str:
        try:
            from core.profile import ProfileManager
            from core.paths import USER_DATA_DIR
            return ProfileManager(USER_DATA_DIR).build_ai_context()
        except Exception:
            return ""

    _LONG_KEYWORDS = [
        "розкажи", "розкажіть", "казку", "казочку", "казка", "казки",
        "анекдот", "жарт", "жартівливу", "смішну", "вірш", "поему",
        "поясни", "поясніть", "детально", "докладно", "розгорни",
        "напиши", "склади", "придумай", "вигадай", "розповідь",
        "историю", "расскажи", "подробно", "объясни",
        "tell me a story", "write a story", "joke", "poem",
        "fairy tale", "explain in detail",
    ]

    @classmethod
    def _needs_long_response(cls, msg: str) -> bool:
        lower = msg.lower()
        return any(k in lower for k in cls._LONG_KEYWORDS)

    def run(self):
        # Lazy import to avoid circular dependency
        try:
            from aivon_sphere import load_memory, get_pc_context  # type: ignore
        except ImportError:
            def get_pc_context(): return ""       # type: ignore[misc]
            def load_memory(): return {}          # type: ignore[misc]

        # Inject live PC context + owner profile + long-term memory
        try:
            pc_ctx = get_pc_context()
            extra  = "\n\n[Поточний стан ПК]\n" + pc_ctx
            # Owner profile
            owner = AIThread._load_owner_context()
            if owner:
                extra += f"\n\n[Профіль власника]\n{owner}"
            # Add memory facts if any
            mem = load_memory()
            if mem:
                facts = "; ".join(v["value"][:40] for v in list(mem.values())[:6])
                extra += f"\n\n[Що я знаю про користувача]\n{facts}"
            # Add relevant conversation memories
            try:
                from core.convo_memory import build_recall_context
                convo_ctx = build_recall_context(self.msg)
                if convo_ctx:
                    extra += f"\n\n{convo_ctx}"
            except Exception:
                pass
            # Inject response style
            try:
                from core.ai_tools import build_system_with_profile as _bswp
                _style_sys = _bswp("")
                if _style_sys:
                    extra += _style_sys
            except Exception:
                pass
            # Task 6: dynamic response length exception
            if AIThread._needs_long_response(self.msg):
                extra += (
                    "\n\nУВАГА: Для цього запиту НЕ обмежуй довжину відповіді — "
                    "відповідай повністю і розгорнуто, без будь-яких скорочень."
                )
                self._long_response = True
            else:
                self._long_response = False
            # system_override замінює базовий SYSTEM (персона/recall),
            # але динамічний контекст (ПК, профіль, пам'ять) додаємо завжди
            if getattr(self, '_system_override', ''):
                self.SYSTEM = self._system_override + extra
            else:
                self.SYSTEM = AIThread.SYSTEM + extra
        except Exception:
            self.SYSTEM         = AIThread.SYSTEM
            self._long_response = False

        # Додаємо повідомлення користувача в історію
        with AIThread._history_lock:
            AIThread._history.append({"role": "user", "content": self.msg})
            if len(AIThread._history) > AIThread.MAX_HISTORY * 2:
                AIThread._history = AIThread._history[-(AIThread.MAX_HISTORY * 2):]

        preferred = self.config.get("ai_provider", "openai")
        print(f"[Dialog] Provider: {preferred}")

        PROVIDER_MAP = {
            "openai":     ("openai_key",     self._openai),
            "anthropic":  ("anthropic_key",  self._anthropic),
            "google":     ("google_key",     self._google),
            "xai":        ("xai_key",        self._xai),
            "perplexity": ("perplexity_key", self._perplexity),
        }

        self._sentences_emitted = False

        def _emit_result(result: str):
            with AIThread._history_lock:
                AIThread._history.append({"role": "assistant", "content": result})
            if not self._sentences_emitted:
                self.sentence_ready.emit(result)
            self.response.emit(result)

        tried = set()
        if preferred in PROVIDER_MAP:
            key_name, fn = PROVIDER_MAP[preferred]
            key = self.config.get(key_name, "")
            if key:
                tried.add(preferred)
                try:
                    result = fn(key)
                    if result:
                        _emit_result(result)
                        return
                except Exception as e:
                    _safe_err = str(e)
                    if key and len(key) > 8:
                        _safe_err = _safe_err.replace(key, key[:4] + "****")
                    print(f"[Dialog] {preferred} error: {_safe_err}")

        # Fallback — інші провайдери
        fallback_order = ["openai", "anthropic", "google", "xai", "perplexity"]
        for prov in fallback_order:
            if prov in tried:
                continue
            if prov not in PROVIDER_MAP:
                continue
            key_name, fn = PROVIDER_MAP[prov]
            key = self.config.get(key_name, "")
            if key:
                try:
                    result = fn(key)
                    if result:
                        _emit_result(result)
                        return
                except Exception as e:
                    _safe_err = str(e)
                    if key and len(key) > 8:
                        _safe_err = _safe_err.replace(key, key[:4] + "****")
                    print(f"[Dialog] {prov} fallback error: {_safe_err}")
                    continue
        self.error.emit("Немає API ключів. Додайте у панелі → API Ключі.")

    # ── Task 1: sentence splitting helper ────────────────────────────────────
    _SENT_RE = re.compile(r'(?<=[.!?…])\s+|(?<=[.!?…])$|\n{2,}')

    def _flush_sentences(self, buf: str) -> str:
        """Emit complete sentences from buf via sentence_ready; return remainder."""
        while not self._abort_event.is_set():
            m = self._SENT_RE.search(buf)
            if not m:
                break
            sentence = buf[:m.end()].strip()
            buf      = buf[m.end():]
            if len(sentence) >= 3:
                self._sentences_emitted = True
                self.sentence_ready.emit(sentence)
        return buf

    def _anthropic(self, key):
        """Anthropic with streaming (Task 1)."""
        import anthropic
        client    = anthropic.Anthropic(api_key=key)
        buf       = ""
        full_text = ""
        max_tok   = 4000 if getattr(self, '_long_response', False) else 500
        with AIThread._history_lock:
            _history_snapshot = list(AIThread._history)
        try:
            with client.messages.stream(
                model="claude-sonnet-4-20250514", max_tokens=max_tok,
                system=self.SYSTEM,
                messages=_history_snapshot,
            ) as stream:
                for token in stream.text_stream:
                    if self._abort_event.is_set():
                        break
                    buf       += token
                    full_text += token
                    buf = self._flush_sentences(buf)
        except anthropic.RateLimitError:
            self.error.emit("Anthropic Claude: ліміт запитів (429). Спробуйте через хвилину.")
            return None
        except Exception:
            # Fallback: non-streaming
            try:
                res = anthropic.Anthropic(api_key=key).messages.create(
                    model="claude-sonnet-4-20250514", max_tokens=max_tok,
                    system=self.SYSTEM, messages=_history_snapshot)
                full_text = res.content[0].text
                buf       = full_text
            except anthropic.RateLimitError:
                self.error.emit("Anthropic Claude: ліміт запитів (429). Спробуйте через хвилину.")
                return None

        # flush remainder
        if buf.strip() and not self._abort_event.is_set():
            self._sentences_emitted = True
            self.sentence_ready.emit(buf.strip())
        return full_text or None

    # ── Tool schemas for Function Calling ────────────────────────────────────
    TOOLS = [
        {"type": "function", "function": {
            "name": "web_search",
            "description": "Шукати актуальну інформацію в інтернеті: новини, погода, ціни, факти.",
            "parameters": {"type": "object",
                "properties": {"query": {"type": "string", "description": "Пошуковий запит"}},
                "required": ["query"]}}},
        {"type": "function", "function": {
            "name": "get_datetime",
            "description": "Отримати поточну дату і час.",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "open_app",
            "description": "Відкрити програму на ПК (Telegram, Chrome, Калькулятор тощо).",
            "parameters": {"type": "object",
                "properties": {"name": {"type": "string", "description": "Назва програми"}},
                "required": ["name"]}}},
        {"type": "function", "function": {
            "name": "open_url",
            "description": "Відкрити сайт у браузері.",
            "parameters": {"type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]}}},
        {"type": "function", "function": {
            "name": "system_action",
            "description": "Дія над системою: вимкнути, перезавантажити, режим сну, гучність.",
            "parameters": {"type": "object",
                "properties": {"action": {"type": "string",
                    "enum": ["shutdown", "restart", "sleep",
                             "volume_up", "volume_down", "mute"]}},
                "required": ["action"]}}},
        {"type": "function", "function": {
            "name": "save_note",
            "description": "Зберегти нотатку або нагадування.",
            "parameters": {"type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Заголовок"},
                    "text":  {"type": "string", "description": "Текст нотатки"}},
                "required": ["text"]}}},
        {"type": "function", "function": {
            "name": "clarify",
            "description": (
                "Запитати уточнення коли бракує обов'язкових деталей для виконання команди "
                "(назва програми, пісні, фільму, час нагадування, тощо). "
                "НЕ вигадуй значення — завжди питай якщо не вистачає."
            ),
            "parameters": {"type": "object",
                "properties": {"question": {"type": "string",
                    "description": "Питання для уточнення"}},
                "required": ["question"]}}},
    ]

    # ── Tool execution ────────────────────────────────────────────────────────
    @staticmethod
    def _run_tool(name: str, args: dict) -> str:
        import json as _j
        from datetime import datetime

        if name == "get_datetime":
            return datetime.now().strftime("Зараз: %A, %d %B %Y, %H:%M")

        elif name == "web_search":
            return AIThread._web_search(args.get("query", ""))

        elif name == "open_app":
            app = args.get("name", "")
            APP_MAP = {
                "telegram": "Telegram.exe", "хром": "chrome", "chrome": "chrome",
                "firefox": "firefox", "блокнот": "notepad", "notepad": "notepad",
                "калькулятор": "calc", "calculator": "calc",
                "провідник": "explorer", "explorer": "explorer",
                "discord": "Discord.exe", "spotify": "Spotify.exe",
                "vscode": "code", "vs code": "code", "ворд": "winword",
                "word": "winword", "excel": "excel", "ексель": "excel",
            }
            exe = APP_MAP.get(app.lower(), app)
            try:
                subprocess.Popen(exe, shell=True)
                return f"Відкрив {app}"
            except Exception as e:
                return f"Не вдалось відкрити {app}: {e}"

        elif name == "open_url":
            url = args.get("url", "")
            if not url.startswith("http"):
                url = "https://" + url
            webbrowser.open(url)
            return f"Відкрив {url}"

        elif name == "system_action":
            action = args.get("action", "")
            if action == "shutdown":
                subprocess.Popen("shutdown /s /t 30", shell=True)
                return "Вимикаю ПК через 30 секунд"
            elif action == "restart":
                subprocess.Popen("shutdown /r /t 30", shell=True)
                return "Перезавантажую через 30 секунд"
            elif action == "sleep":
                subprocess.Popen(
                    "rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
                return "Перехожу в режим сну"
            elif action in ("volume_up", "volume_down", "mute"):
                try:
                    from ctypes import cast, POINTER
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    dev = AudioUtilities.GetSpeakers()
                    vol = cast(dev.Activate(IAudioEndpointVolume._iid_,
                                            CLSCTX_ALL, None),
                               POINTER(IAudioEndpointVolume))
                    if action == "mute":
                        m = vol.GetMute(); vol.SetMute(not m, None)
                        return "Звук вимкнено" if not m else "Звук увімкнено"
                    cur = vol.GetMasterVolumeLevelScalar()
                    nw  = (min(1.0, cur + 0.1) if action == "volume_up"
                           else max(0.0, cur - 0.1))
                    vol.SetMasterVolumeLevelScalar(nw, None)
                    return f"Гучність: {int(nw * 100)}%"
                except Exception:
                    return "Гучність змінено"
            return "Дія виконана"

        elif name == "save_note":
            import json as _j
            title = args.get("title", "Нотатка від Aivon")
            text  = args.get("text", "")
            print(f"__AXIS_PUSH__:save_note_request:{_j.dumps({'title': title, 'text': text})}",
                  flush=True)
            return f"Нотатку «{title}» збережено"

        elif name == "clarify":
            return f"__CLARIFY__:{args.get('question', 'Уточніть будь ласка')}"

        return "Виконано"

    @staticmethod
    def _web_search(query: str) -> str:
        """Пошук в інтернеті."""
        import requests as _req

        # ── 1. duckduckgo_search ─────────────────────────────────────────────
        try:
            from duckduckgo_search import DDGS
            with DDGS(timeout=8) as ddgs:
                results = list(ddgs.text(query, max_results=4))
            if results:
                lines = []
                for r in results[:3]:
                    title = r.get("title", "")
                    body  = r.get("body", "")[:200]
                    href  = r.get("href", "")
                    lines.append(f"• {title}: {body}" + (f" [{href}]" if href else ""))
                return "\n".join(lines)
        except ImportError:
            pass
        except Exception as e:
            print(f"[Search] DDGS error: {e}")

        # ── 2. DuckDuckGo Instant Answer API ─────────────────────────────────
        try:
            r = _req.get("https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1,
                        "skip_disambig": 1, "kl": "ua-uk"},
                timeout=8, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0)"})
            d = r.json()
            if d.get("AbstractText"):
                src = d.get("AbstractSource", "")
                return d["AbstractText"][:500] + (f" (Джерело: {src})" if src else "")
            topics = [t for t in d.get("RelatedTopics", []) if t.get("Text")]
            if topics:
                return "\n".join(f"• {t['Text'][:200]}" for t in topics[:3])
        except Exception as e:
            print(f"[Search] DDG API error: {e}")

        # ── 3. DuckDuckGo HTML scrape fallback ───────────────────────────────
        try:
            import re as _re
            r = _req.get(
                f"https://html.duckduckgo.com/html/?q={_req.utils.quote(query)}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0)"}, timeout=8)
            snippets = _re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', r.text, _re.S)
            if snippets:
                clean = [_re.sub(r'<[^>]+>', '', s).strip() for s in snippets[:3]]
                return "\n".join(f"• {s[:200]}" for s in clean if s)
        except Exception as e:
            print(f"[Search] HTML scrape error: {e}")

        return f"Пошук '{query}': результатів не знайдено"

    def _openai(self, key):
        """OpenAI with streaming (Task 1). Handles tool calls + clarify (Tasks 4, 5)."""
        import json as _j
        from openai import OpenAI
        try:
            from openai import RateLimitError as _OAIRateLimit
        except ImportError:
            _OAIRateLimit = Exception
        client = OpenAI(api_key=key)
        with AIThread._history_lock:
            msgs = [{"role": "system", "content": self.SYSTEM}] + list(AIThread._history)

        if getattr(self, '_long_response', False):
            max_tok = 4000
        elif "5.5" in self.model:
            max_tok = 1500
        else:
            max_tok = 800
        print(f"[AI] model={self.model} max_tokens={max_tok} "
              f"long={getattr(self,'_long_response',False)}")

        # ── Phase 1: streaming with tool-call accumulation ────────────────────
        try:
            stream = client.chat.completions.create(
                model=self.model, max_tokens=max_tok, messages=msgs,
                tools=AIThread.TOOLS, tool_choice="auto", stream=True,
            )
        except _OAIRateLimit:
            self.error.emit("OpenAI: ліміт запитів (429). Спробуйте через хвилину.")
            return None

        buf       = ""
        full_text = ""
        tool_acc: dict[int, dict] = {}

        for chunk in stream:
            if self._abort_event.is_set():
                try: stream.close()
                except Exception: pass
                return full_text or None

            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue
            delta = choice.delta

            if delta.tool_calls:
                for tc_d in delta.tool_calls:
                    idx = tc_d.index
                    if idx not in tool_acc:
                        tool_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_d.id:
                        tool_acc[idx]["id"] = tc_d.id
                    if tc_d.function:
                        if tc_d.function.name:
                            tool_acc[idx]["name"] += tc_d.function.name
                        if tc_d.function.arguments:
                            tool_acc[idx]["arguments"] += tc_d.function.arguments

            if delta.content:
                buf       += delta.content
                full_text += delta.content
                buf = self._flush_sentences(buf)

        if buf.strip() and not self._abort_event.is_set() and not tool_acc:
            self.sentence_ready.emit(buf.strip())

        if not tool_acc:
            return full_text or None

        # ── Phase 2: execute tool calls, stream final response ────────────────
        msgs.append({
            "role": "assistant", "content": "",
            "tool_calls": [{"id": tc["id"], "type": "function",
                            "function": {"name": tc["name"],
                                         "arguments": tc["arguments"]}}
                           for tc in tool_acc.values()],
        })

        clarify_q = None
        for tc in tool_acc.values():
            try:
                args = _j.loads(tc["arguments"])
            except Exception:
                args = {}
            print(f"[AI] 🔧 {tc['name']}({args})")
            result = AIThread._run_tool(tc["name"], args)
            print(f"[AI] ✅ {result[:80]}")

            if result.startswith("__CLARIFY__:"):
                clarify_q = result[len("__CLARIFY__:"):]
                msgs.append({"role": "tool", "content": clarify_q,
                             "tool_call_id": tc["id"]})
            else:
                msgs.append({"role": "tool", "content": result,
                             "tool_call_id": tc["id"]})

        if clarify_q:
            self.sentence_ready.emit(clarify_q)
            return clarify_q

        if self._abort_event.is_set():
            return full_text or None

        buf2 = ""
        try:
            stream2 = client.chat.completions.create(
                model=self.model, max_tokens=max_tok, messages=msgs, stream=True,
            )
        except _OAIRateLimit:
            self.error.emit("OpenAI: ліміт запитів (429). Спробуйте через хвилину.")
            return full_text or None
        for chunk in stream2:
            if self._abort_event.is_set():
                try: stream2.close()
                except Exception: pass
                break
            delta2 = chunk.choices[0].delta if chunk.choices else None
            if delta2 and delta2.content:
                buf2      += delta2.content
                full_text += delta2.content
                buf2 = self._flush_sentences(buf2)
        if buf2.strip() and not self._abort_event.is_set():
            self.sentence_ready.emit(buf2.strip())

        return full_text or None

    def _google(self, key):
        import requests
        contents = []
        with AIThread._history_lock:
            _history_snapshot = list(AIThread._history)
        for m in _history_snapshot:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={key}",
            json={"systemInstruction": {"parts": [{"text": self.SYSTEM}]},
                  "contents": contents,
                  "generationConfig": {"maxOutputTokens": 500},
                  "safetySettings": [
                      {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
                      {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
                      {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                      {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                  ]}, timeout=15)
        if r.status_code == 429:
            self.error.emit("Google Gemini: ліміт запитів (429). Спробуйте через хвилину.")
            return None
        if r.status_code == 200:
            parts = (r.json().get("candidates", [{}])[0]
                     .get("content", {}).get("parts", []))
            return parts[0]["text"] if parts else None
        return None

    def _xai(self, key):
        from openai import OpenAI
        try:
            from openai import RateLimitError as _RateLimitError
        except ImportError:
            _RateLimitError = Exception
        client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
        with AIThread._history_lock:
            msgs = ([{"role": "system", "content": _GROK_PREFIX + self.SYSTEM}]
                    + list(AIThread._history))
        try:
            res = client.chat.completions.create(
                model="grok-2-latest", max_tokens=500, messages=msgs)
            return res.choices[0].message.content
        except _RateLimitError:
            self.error.emit("xAI Grok: ліміт запитів (429). Спробуйте через хвилину.")
            return None

    def _perplexity(self, key):
        import requests
        with AIThread._history_lock:
            msgs = ([{"role": "system", "content": self.SYSTEM}]
                    + list(AIThread._history))
        r = requests.post("https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "sonar", "max_tokens": 500, "messages": msgs}, timeout=15)
        if r.status_code == 429:
            self.error.emit("Perplexity: ліміт запитів (429). Спробуйте через хвилину.")
            return None
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return None


# ═══════════════════════════════════════════════════════════
# SphereAIMixin – methods added to AivonSphere
# ═══════════════════════════════════════════════════════════

class SphereAIMixin:
    """Mixin that provides all AI/dialog methods for AivonSphere.

    Requires the host class to have:
        self.config, self.state, self.response_text,
        self.update(), self.respond(), self.respond_silent(),
        self._respond_signal, self._respond_error_signal,
        self.dialog_history, self.dialog_provider, self.sphere_mode,
        self.start_listening(), self.memory_enabled,
        THINKING / SPEAKING / IDLE constants.
    """

    # ── Core AI send ──────────────────────────────────────────────────────────
    def _respond_with_ai(self, prompt: str, extra_system: str = ""):
        """Send a prompt to AI; stream sentences to TTS as they arrive (Task 1)."""
        self.state         = self.THINKING
        self.response_text = "🧠 Думаю..."
        self.update()

        system_override = ""
        if extra_system:
            system_override = extra_system + "\n\n" + AIThread.SYSTEM

        t = AIThread(self.config, prompt, system_override=system_override)
        t.sentence_ready.connect(self._respond_signal)
        t.response.connect(lambda full: setattr(self, 'response_text', full[:120]))
        t.error.connect(self._on_ai_error_signal)
        self._current_ai_thread = t
        t.finished.connect(lambda: setattr(self, '_current_ai_thread', None))
        t.start()

    def _on_ai_error_signal(self, msg: str):
        """Route AIThread error safely to the main-thread error handler."""
        self._respond_error_signal.emit(msg)

    # ── Dialog mode ───────────────────────────────────────────────────────────
    def _dialog_ask(self, text: str):
        """Multi-provider AI виклик для діалогу — з пам'яттю та роллю"""
        self.state         = self.THINKING
        self.response_text = "🧠 ..."

        # Lazy import to avoid circular at module load
        from aivon_sphere import load_config, VOICE_PROVIDER_NAMES, DIALOG_ROLE_PROMPTS  # type: ignore

        _fresh_cfg = load_config()
        provider   = self.dialog_provider

        KEY_MAP = {
            "gemini":     "google_key",
            "openai":     "openai_key",
            "anthropic":  "anthropic_key",
            "xai":        "xai_key",
            "perplexity": "perplexity_key",
        }
        key = _fresh_cfg.get(KEY_MAP.get(provider, ""), "")
        if not key:
            prov_name = VOICE_PROVIDER_NAMES.get(provider, provider)
            self.respond(f"Додайте ключ для {prov_name} в налаштуваннях")
            return

        _MAX_DIALOG_TURNS = 50
        if len(self.dialog_history) >= _MAX_DIALOG_TURNS * 2:
            self.dialog_history = self.dialog_history[-_MAX_DIALOG_TURNS:]

        self.dialog_history.append({"role": "user", "content": text})

        role          = getattr(self, 'dialog_role', 'assistant')
        system_prompt = DIALOG_ROLE_PROMPTS.get(role, DIALOG_ROLE_PROMPTS["assistant"])

        mem_size = _fresh_cfg.get("dialog_memory_size", 20)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.dialog_history[-mem_size:])

        print(f"[Dialog] provider={provider}, role={role}, "
              f"history={len(self.dialog_history)} msgs")
        if hasattr(self, '_dialog_thread') and self._dialog_thread is not None:
            try:
                self._dialog_thread.result.disconnect()
                self._dialog_thread.sentence.disconnect()
                self._dialog_thread.error.disconnect()
            except Exception:
                pass
        self._dialog_streamed = False
        self._stream_generating = True
        self._dialog_thread = _DialogThread(provider, key, messages, _fresh_cfg)
        self._dialog_thread.sentence.connect(self._on_dialog_sentence)
        self._dialog_thread.result.connect(
            lambda answer: self._on_dialog_response(answer, provider))
        self._dialog_thread.error.connect(self._on_dialog_error)
        self._dialog_thread.finished.connect(self._on_stream_finished)
        self._dialog_thread.start()

    def _on_dialog_sentence(self, sentence: str):
        """Streaming діалог: озвучуємо речення одразу, не чекаючи повної відповіді.
        Черга TTS грає їх послідовно; _on_all_tts_done продовжить слухання."""
        self._dialog_streamed = True
        self.state = self.SPEAKING
        self.respond(sentence)

    def _on_dialog_response(self, answer: str, provider=None):
        """AI відповів — одразу голос (OpenAI TTS), слухаємо далі."""
        from aivon_sphere import _DialogTTSThread  # type: ignore

        self.dialog_history.append({"role": "assistant", "content": answer})
        mem_size = self.config.get("dialog_memory_size", 20)
        if len(self.dialog_history) > mem_size:
            self.dialog_history = self.dialog_history[-(mem_size // 2):]
        print(f"[Dialog] → '{answer[:60]}...'")

        # Streaming: речення вже озвучені по мірі генерації —
        # черга TTS сама продовжить слухання після останнього речення
        if getattr(self, '_dialog_streamed', False):
            self._dialog_streamed = False
            return

        self.response_text = "🔊"
        self.state         = self.SPEAKING

        prov = provider or self.dialog_provider
        PROVIDER_VOICE_KEYS = {
            "openai": "voice_openai", "anthropic": "voice_anthropic",
            "gemini": "voice_gemini", "xai": "voice_xai",
            "perplexity": "voice_perplexity",
        }
        PROVIDER_VOICE_DEFAULTS = {
            "openai": "onyx", "anthropic": "echo",
            "gemini": "nova", "xai": "alloy",
            "perplexity": "fable",
        }
        voice_key = PROVIDER_VOICE_KEYS.get(prov, "voice_openai")
        voice     = self.config.get(voice_key, PROVIDER_VOICE_DEFAULTS.get(prov, "onyx"))
        print(f"[Dialog TTS] provider={prov}, voice={voice}")

        oai_key = self.config.get("openai_key", "")
        if oai_key:
            self._dialog_tts = _DialogTTSThread(
                oai_key, answer, self.config, voice_override=voice)
            self._dialog_tts.done.connect(self._dialog_listen_next)
            self._dialog_tts.start()
        else:
            QTimer.singleShot(500, self._dialog_listen_next)

    def _dialog_listen_next(self):
        """Після озвучки в діалозі — одразу слухаємо."""
        self.state = self.IDLE
        if self.sphere_mode == "dialog":
            QTimer.singleShot(300, self.start_listening)

    def _on_dialog_error(self, err: str):
        """GPT помилка — текст і далі слухаємо."""
        print(f"[Dialog] error: {err}")
        self.response_text = f"⚠️ {err[:30]}"
        self.state         = self.IDLE
        if self.sphere_mode == "dialog":
            QTimer.singleShot(500, self.start_listening)

    # ── Ollama offline fallback ───────────────────────────────────────────────
    def _check_ollama_available(self) -> bool:
        """Перевірити чи Ollama запущена на localhost:11434."""
        try:
            import urllib.request
            req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            return req.status == 200
        except Exception:
            return False

    def _start_ollama_server(self) -> bool:
        """Спробувати запустити Ollama і зачекати 3 секунди."""
        import subprocess as _sp
        try:
            _NO_WINDOW = _sp.CREATE_NO_WINDOW if hasattr(_sp, 'CREATE_NO_WINDOW') else 0
            _sp.Popen(
                ["ollama", "serve"],
                stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                creationflags=_NO_WINDOW,
            )
            time.sleep(3)
            return self._check_ollama_available()
        except Exception as e:
            print(f"[Ollama] Не вдалося запустити: {e}")
            return False

    def _call_ollama(self, messages: list, model: str | None = None) -> str:
        """Надіслати запит до Ollama (POST /api/chat)."""
        import urllib.request
        import json as _json

        if model is None:
            model = self.config.get("ollama_model", "llama3.2")

        if not self._check_ollama_available():
            print("[Ollama] Не запущена — спробую запустити...")
            if not self._start_ollama_server():
                raise RuntimeError("Ollama недоступна")

        payload = _json.dumps({
            "model":    model,
            "messages": messages,
            "stream":   False,
        }).encode("utf-8")

        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        return data.get("message", {}).get("content", "").strip()

    def _ollama_ask_thread(self, q: str):
        """Фоновий потік для запиту до Ollama."""
        try:
            messages = [{"role": "user", "content": q}]
            if getattr(self, '_mode', 'normal') == 'focus' and self.dialog_history:
                messages = self.dialog_history[-10:] + messages
            answer = self._call_ollama(messages)
            if answer:
                self._respond_signal.emit(f"🔌 Офлайн (Ollama): {answer}")
            else:
                self._respond_signal.emit("🔌 Ollama відповіла порожньо.")
        except Exception as e:
            self._respond_signal.emit(f"🔌 Ollama помилка: {str(e)[:60]}")

    # ── Public ask_ai + fallbacks ─────────────────────────────────────────────
    def ask_ai(self, q: str):
        """AI-відповідь зі streaming: перше речення озвучується одразу,
        не чекаючи повної генерації (як Gemini на телефоні)."""
        from sphere.memory import MemoryThread

        has_key = any(self.config.get(k) for k in
                      ["anthropic_key", "openai_key", "google_key",
                       "xai_key", "perplexity_key"])

        if not has_key:
            if self.config.get("ollama_fallback", True):
                self.state         = self.THINKING
                self.response_text = "🔌 Ollama..."
                threading.Thread(target=self._ollama_ask_thread,
                                 args=(q,), daemon=True).start()
                return
            self.respond(f"Почув: '{q[:20]}'. Додайте API ключ у панелі.")
            return

        self.state         = self.THINKING
        self.response_text = "🧠 Думаю..."
        self.update()

        # Персона JARVIS (як раніше в MemoryThread), історія і tools — в AIThread
        persona = MemoryThread.ASSISTANT_INSTRUCTIONS if self.memory_enabled else ""

        # Telegram: речення не шлемо окремо — повний текст один раз наприкінці
        self._tg_stream_suppress = True
        # Поки триває генерація — _on_all_tts_done не вмикає мікрофон
        self._stream_generating = True

        t = AIThread(self.config, q, system_override=persona)
        t.sentence_ready.connect(self._respond_signal)
        t.response.connect(self._on_ai_stream_done)
        t.error.connect(lambda e: self._on_ai_stream_error(q, e))
        self._current_ai_thread = t
        t.finished.connect(self._on_stream_finished)
        self.ai_thread = t
        t.start()

    def _on_stream_finished(self):
        """Streaming-генерація завершилась (успіх, помилка чи abort)."""
        self._current_ai_thread  = None
        self._stream_generating  = False
        # Якщо TTS вже все проговорив поки ми генерували — продовжуємо слухання
        with self._tts_lock:
            _idle = not self._tts_busy and not self._tts_queue
        _dlg_tts = getattr(self, '_dialog_tts', None)
        if _dlg_tts is not None and _dlg_tts.isRunning():
            _idle = False   # діалоговий TTS ще говорить — він сам продовжить
        if _idle:
            self._on_all_tts_done()

    def _on_ai_stream_done(self, full: str):
        """Streaming завершено — показуємо повний текст і шлемо в Telegram раз."""
        self._tg_stream_suppress = False
        self.response_text = full[:120]
        try:
            self._tg_send(full)
        except Exception:
            pass

    def _on_ai_stream_error(self, q: str, error: str):
        self._tg_stream_suppress = False
        self._ai_fallback_with_ollama(q, error)

    def _ai_fallback(self, q: str, error: str):
        """Fallback до звичайного AI якщо Assistants не працює."""
        print(f"Memory fallback: {error}")
        self.ai_thread = AIThread(self.config, q)
        self.ai_thread.response.connect(self.respond)
        self.ai_thread.error.connect(
            lambda e: self._ai_fallback_with_ollama(q, e))
        self.ai_thread.start()

    def _ai_fallback_with_ollama(self, q: str, error: str):
        """Якщо всі AI провайдери недоступні — пробуємо Ollama."""
        print(f"[AI] Всі провайдери недоступні: {error}")
        if self.config.get("ollama_fallback", True):
            self.state         = self.THINKING
            self.response_text = "🔌 Ollama..."
            threading.Thread(target=self._ollama_ask_thread,
                             args=(q,), daemon=True).start()
        else:
            self.respond_silent(f"Помилка AI: {error[:40]}")
