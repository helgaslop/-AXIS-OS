# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/media.py  –  Spotify, Steam, серіали, YouTube (з aivon_sphere.py)  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Класи: SpotifyController, SpotifyControlThread, SearchThread               ║
║  Mixin: SphereMediaMixin                                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import re
import subprocess
import webbrowser
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, QTimer

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _get_user_data_dir() -> Path:
    _appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(_appdata) / "AXIS OS"


# ══════════════════════════════════════════════════════════════════════════════
# SpotifyController
# ══════════════════════════════════════════════════════════════════════════════

class SpotifyController:
    """
    Керування Spotify через офіційний Web API (spotipy).
    Fallback на медіа-клавіші якщо spotipy недоступний або ключі не задані.
    """
    SCOPE = (
        "user-modify-playback-state "
        "user-read-playback-state "
        "user-read-currently-playing "
        "user-read-playback-position"
    )
    REDIRECT_URI = "http://127.0.0.1:8000/callback"

    def __init__(self, client_id: str = "", client_secret: str = ""):
        self._sp = None
        self._has_keys = bool(client_id and client_secret)
        if self._has_keys:
            try:
                import os, spotipy
                from spotipy.oauth2 import SpotifyOAuth
                token_path = str(_get_user_data_dir() / ".spotify_token")
                # Only activate Web API if there is already a cached token —
                # never block the thread waiting for a browser OAuth flow.
                if not os.path.exists(token_path):
                    print("[Spotify] немає кешованого токена — використовую URI-fallback")
                else:
                    auth = SpotifyOAuth(
                        client_id=client_id,
                        client_secret=client_secret,
                        redirect_uri=self.REDIRECT_URI,
                        scope=self.SCOPE,
                        cache_path=token_path,
                        open_browser=False,
                    )
                    self._sp = spotipy.Spotify(auth_manager=auth)
                    print("[Spotify] Web API ініціалізовано ✓")
            except ImportError:
                print("[Spotify] spotipy не встановлено: pip install spotipy")
            except Exception as e:
                print(f"[Spotify] Init error: {e}")

    # ── internal helpers ──────────────────────────────────────────────────────
    def _active_device(self):
        try:
            devs = (self._sp.devices() or {}).get("devices", [])
            for d in devs:
                if d.get("is_active"):
                    return d["id"]
            return devs[0]["id"] if devs else None
        except Exception:
            return None

    def _media_key(self, vk: int, msg: str) -> str:
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk, 0, 0x0001, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 0x0001 | 0x0002, 0)
        except Exception:
            pass
        return msg

    def _current_from_window(self) -> str:
        try:
            import ctypes, ctypes.wintypes
            spotify_title = ""
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            def enum_cb(hwnd, lParam):  # NOSONAR — WinAPI callback must always return True
                nonlocal spotify_title
                if not ctypes.windll.user32.IsWindowVisible(hwnd):
                    return True
                cls = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetClassNameW(hwnd, cls, 256)
                if cls.value == "Chrome_WidgetWin_0":
                    ln = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if ln > 0:
                        buf = ctypes.create_unicode_buffer(ln + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, ln + 1)
                        t = buf.value
                        if t and t != "Spotify" and " - " in t:
                            spotify_title = t
                return True
            ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            if spotify_title:
                return f"🎵 Грає: {spotify_title}"
        except Exception:
            pass
        return "🔇 Нічого не грає"

    # ── public API ────────────────────────────────────────────────────────────
    def play_track(self, query: str) -> str:
        if self._sp:
            try:
                res = self._sp.search(q=query, type="track", limit=1)
                items = res["tracks"]["items"]
                if items:
                    track = items[0]
                    uri   = track["uri"]
                    name  = track["name"]
                    artist = track["artists"][0]["name"]
                    self._sp.start_playback(device_id=self._active_device(), uris=[uri])
                    return f"🎵 Граю: {artist} — {name}"
                return f"🔍 Не знайдено: {query}"
            except Exception as e:
                print(f"[Spotify] play_track: {e}")
        # fallback
        from urllib.parse import quote
        try:
            subprocess.Popen(f'start "" "spotify:search:{quote(query)}"', shell=True, creationflags=_NO_WINDOW)
        except Exception:
            webbrowser.open(f"https://open.spotify.com/search/{quote(query)}")
        return f"🎵 Шукаю: {query}"

    def pause(self) -> str:
        if self._sp:
            try:
                self._sp.pause_playback()
                return "⏸️ Пауза"
            except Exception:
                pass
        return self._media_key(0xB3, "⏸️ Пауза")

    def resume(self) -> str:
        if self._sp:
            try:
                self._sp.start_playback(device_id=self._active_device())
                return "▶️ Продовжуємо"
            except Exception:
                pass
        return self._media_key(0xB3, "▶️ Продовжуємо")

    def next_track(self) -> str:
        if self._sp:
            try:
                self._sp.next_track()
                return "⏭️ Наступна пісня"
            except Exception:
                pass
        return self._media_key(0xB0, "⏭️ Наступна пісня")

    def prev_track(self) -> str:
        if self._sp:
            try:
                self._sp.previous_track()
                return "⏮️ Попередня пісня"
            except Exception:
                pass
        return self._media_key(0xB1, "⏮️ Попередня пісня")

    def set_volume(self, pct: int) -> str:
        pct = max(0, min(100, pct))
        if self._sp:
            try:
                self._sp.volume(pct)
                return f"🔊 Гучність: {pct}%"
            except Exception:
                pass
        # fallback — відносна зміна
        steps = max(1, abs(pct - 50) // 10) if pct != 50 else 0
        vk = 0xAF if pct >= 50 else 0xAE
        for _ in range(steps):
            self._media_key(vk, "")
        return f"🔊 Гучність: ~{pct}%"

    def toggle_shuffle(self) -> str:
        if self._sp:
            try:
                state = self._sp.current_playback()
                cur = (state or {}).get("shuffle_state", False)
                self._sp.shuffle(not cur)
                return "🔀 Шафл увімкнено" if not cur else "🔀 Шафл вимкнено"
            except Exception:
                pass
        # hotkey fallback: Ctrl+Shift+R у вікні Spotify
        return self._spotify_hotkey("ctrl+shift+r", "🔀 Шафл")

    def toggle_repeat(self) -> str:
        if self._sp:
            try:
                state = self._sp.current_playback()
                cur = (state or {}).get("repeat_state", "off")
                nxt = {"off": "context", "context": "track", "track": "off"}[cur]
                self._sp.repeat(nxt)
                labels = {"off": "⏭ Повтор вимкнено", "context": "🔁 Повтор плейлисту", "track": "🔂 Повтор треку"}
                return labels[nxt]
            except Exception:
                pass
        return self._spotify_hotkey("ctrl+r", "🔁 Повтор")

    def liked_songs(self) -> str:
        """Запускає Liked Songs (Улюблені треки)."""
        if self._sp:
            try:
                devs = (self._sp.devices() or {}).get("devices", [])
                dev_id = next((d["id"] for d in devs if d.get("is_active")), None) or \
                         (devs[0]["id"] if devs else None)
                self._sp.start_playback(
                    device_id=dev_id,
                    context_uri="spotify:collection",
                )
                return "❤️ Граю улюблені треки"
            except Exception:
                pass
        # URI fallback: відкриваємо колекцію і через 2 с надсилаємо WM_APPCOMMAND Play
        try:
            subprocess.Popen('start "" "spotify:collection"', shell=True,
                             creationflags=_NO_WINDOW)
            import threading as _t
            def _press_play():
                import time, ctypes, ctypes.wintypes
                time.sleep(2.0)
                WNDENUMPROC = ctypes.WINFUNCTYPE(
                    ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                hwnd_box = [0]
                def _cb(hwnd, _):
                    cls = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetClassNameW(hwnd, cls, 256)
                    if "Chrome_WidgetWin" in cls.value or "SpotifyMainWindow" in cls.value:
                        ln  = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                        buf = ctypes.create_unicode_buffer(ln + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, ln + 1)
                        if "Spotify" in buf.value or not buf.value:
                            hwnd_box[0] = hwnd
                    return True
                ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
                if hwnd_box[0]:
                    WM_APPCOMMAND               = 0x0319
                    APPCOMMAND_MEDIA_PLAY_PAUSE = 0x000E0000
                    ctypes.windll.user32.PostMessageW(
                        hwnd_box[0], WM_APPCOMMAND, 0, APPCOMMAND_MEDIA_PLAY_PAUSE)
            _t.Thread(target=_press_play, daemon=True).start()
        except Exception:
            pass
        return "❤️ Улюблені треки"

    def seek_forward(self) -> str:
        return self._spotify_hotkey("ctrl+right", "⏩ +15 сек")

    def seek_back(self) -> str:
        return self._spotify_hotkey("ctrl+left", "⏪ -15 сек")

    def _spotify_hotkey(self, keys: str, label: str) -> str:
        """Посилає гарячу клавішу у вікно Spotify."""
        try:
            import ctypes, ctypes.wintypes, time
            # Знаходимо hwnd вікна Spotify
            target_hwnd = ctypes.c_int(0)
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool,
                                              ctypes.wintypes.HWND,
                                              ctypes.wintypes.LPARAM)
            def _cb(hwnd, _):  # NOSONAR — WinAPI callback must always return True
                ln = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if ln > 0:
                    buf = ctypes.create_unicode_buffer(ln + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, ln + 1)
                    cls = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetClassNameW(hwnd, cls, 256)
                    if cls.value == "Chrome_WidgetWin_0" and "Spotify" in buf.value:
                        target_hwnd.value = hwnd
                return True
            ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)

            hwnd = target_hwnd.value
            if hwnd:
                WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
                key_map = {
                    "ctrl+right": (0x27, True), "ctrl+left": (0x25, True),
                    "ctrl+r":     (0x52, True),  "ctrl+shift+r": (0x52, True, True),
                    "space":      (0x20, False),
                }
                vk, use_ctrl, *extra_shift = key_map.get(keys, (0, False))
                use_shift = bool(extra_shift and extra_shift[0])
                if vk:
                    VK_CTRL  = 0x11
                    VK_SHIFT = 0x10
                    if use_ctrl:
                        ctypes.windll.user32.PostMessageW(hwnd, WM_KEYDOWN, VK_CTRL, 0)
                    if use_shift:
                        ctypes.windll.user32.PostMessageW(hwnd, WM_KEYDOWN, VK_SHIFT, 0)
                    ctypes.windll.user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
                    ctypes.windll.user32.PostMessageW(hwnd, WM_KEYUP,   vk, 0)
                    if use_shift:
                        ctypes.windll.user32.PostMessageW(hwnd, WM_KEYUP, VK_SHIFT, 0)
                    if use_ctrl:
                        ctypes.windll.user32.PostMessageW(hwnd, WM_KEYUP, VK_CTRL, 0)
                    return label
        except Exception:
            pass
        return label

    def current(self) -> str:
        if self._sp:
            try:
                pb = self._sp.current_playback()
                if pb and pb.get("item"):
                    t   = pb["item"]
                    art = t["artists"][0]["name"]
                    return f"🎵 Грає: {art} — {t['name']}"
            except Exception:
                pass
        return self._current_from_window()


# ══════════════════════════════════════════════════════════════════════════════
# SpotifyControlThread
# ══════════════════════════════════════════════════════════════════════════════

class SpotifyControlThread(QThread):
    """
    Виконує команду управління Spotify в окремому потоці.
    """
    result = pyqtSignal(str)
    error  = pyqtSignal(str)

    # ── ключові слова для кожної команди ─────────────────
    _COMMANDS = {
        "pause":   ["паузу", "пауза", "зупинайся", "зупинись", "стоп музику", "pause"],
        "resume":  ["продовжуй", "продовжай", "віднови", "resume", "продовжуємо"],
        "next":    ["наступну", "наступна", "перемотай вперед", "next", "скип", "скіп", "далі"],
        "prev":    ["попередню", "попередня", "перемотай назад", "previous", "prev", "назад пісню"],
        "shuffle": ["шафл", "шаф", "shuffle", "випадковий порядок", "перемішай"],
        "repeat":  ["повтор", "по колу", "repeat", "повторювати", "зациклити"],
        "liked":   ["улюблені треки", "улюблені пісні", "лайкнуті", "мої треки",
                    "улюблені", "любимые треки", "любимые песни", "избранное",
                    "серце", "серця", "liked songs", "favorites"],
        "seek_fw": ["вперед", "перемотай на", "skip forward", "перемотати вперед"],
        "seek_bk": ["назад", "перемотай назад", "rewind", "перемотати назад"],
        "current": ["що грає", "яка пісня", "хто грає", "what is playing", "яку пісню", "яка музика"],
    }
    # volume окремо, тому що тягнуть число
    _VOLUME_KEYS = ["гучність", "volume", "громче", "тише", "vol", "звук"]

    def __init__(self, controller: SpotifyController, text: str, api_key: str = ""):
        super().__init__()
        self.ctrl     = controller
        self.text     = text.strip().lower()
        self._api_key = api_key

    # ── ключові слова для «грай песню X» через API ──────
    _PLAY_KEYS = [
        "грай песню", "включи песню", "включай песню",
        "грай пісню", "включи пісню", "включай пісню",
        "грай музику", "включи музику", "включай музику",
        "play song", "play music",
        "грай", "включи",
    ]
    # Слова після голих «включи»/«грай», яких НЕ торкаємось
    _PLAY_SKIP_AFTER = ["фільм", "фильм", "movie", "калькулятор", "блокнот"]

    # ── статичний detect ─────────────────────────────────
    @staticmethod
    def detect(text: str) -> bool:
        low = text.strip().lower()
        # play-команди
        for k in SpotifyControlThread._PLAY_KEYS:
            if k in low:
                if k in ("включи", "грай"):
                    after = low[low.find(k) + len(k):].strip()
                    if not after or any(s in after for s in SpotifyControlThread._PLAY_SKIP_AFTER):
                        continue
                return True
        # управление
        for cmd, phrases in SpotifyControlThread._COMMANDS.items():
            for p in phrases:
                if p in low:
                    return True
        for vk in SpotifyControlThread._VOLUME_KEYS:
            if vk in low:
                return True
        return False

    # ── парсер номера з текста ───────────────────────────
    @staticmethod
    def _extract_number(text: str):
        import re
        nums = re.findall(r"\d+", text)
        if nums:
            return int(nums[0])
        # словові числа (часто понадобиться)
        word_map = {
            "нуль": 0, "один": 10, "два": 20, "три": 30,
            "чотири": 40, "п'ять": 50, "шість": 60,
            "сім": 70, "вісім": 80, "дев'ять": 90, "десять": 100,
        }
        for w, v in word_map.items():
            if w in text:
                return v
        return None

    # ── вырезаем запрос для play ────────────────────────
    def _extract_play_query(self) -> str:
        for k in self._PLAY_KEYS:
            idx = self.text.find(k)
            if idx != -1:
                after = self.text[idx + len(k):].strip()
                for stop in ("пожалуйста", "будь ласка", "будь-ласка"):
                    after = after.replace(stop, "").strip()
                return after
        return ""

    # ── main ─────────────────────────────────────────────
    def run(self):
        try:
            low = self.text

            # play — якщо є play-ключ з запитом
            for k in self._PLAY_KEYS:
                if k in low:
                    if k in ("включи", "грай"):
                        after = low[low.find(k) + len(k):].strip()
                        if not after or any(s in after for s in self._PLAY_SKIP_AFTER):
                            continue
                    query = self._extract_play_query()
                    if query:
                        self.result.emit(self.ctrl.play_track(query))
                    else:
                        self.result.emit("Яку песню включити? 🎵")
                    return

            # volume — окремо (через медіа-клавіші)
            for vk in self._VOLUME_KEYS:
                if vk in low:
                    if "громче" in low or "більше" in low:
                        self.result.emit(self.ctrl.set_volume(70))
                        return
                    if "тише" in low or "менше" in low:
                        self.result.emit(self.ctrl.set_volume(30))
                        return
                    n = self._extract_number(low)
                    if n is not None:
                        self.result.emit(self.ctrl.set_volume(n))
                    else:
                        self.result.emit("Скажіть гучність від 0 до 100")
                    return

            # остальные команды
            for cmd, phrases in self._COMMANDS.items():
                for p in phrases:
                    if p in low:
                        if   cmd == "pause":   self.result.emit(self.ctrl.pause())
                        elif cmd == "resume":  self.result.emit(self.ctrl.resume())
                        elif cmd == "next":    self.result.emit(self.ctrl.next_track())
                        elif cmd == "prev":    self.result.emit(self.ctrl.prev_track())
                        elif cmd == "shuffle": self.result.emit(self.ctrl.toggle_shuffle())
                        elif cmd == "repeat":  self.result.emit(self.ctrl.toggle_repeat())
                        elif cmd == "liked":   self.result.emit(self.ctrl.liked_songs())
                        elif cmd == "seek_fw": self.result.emit(self.ctrl.seek_forward())
                        elif cmd == "seek_bk": self.result.emit(self.ctrl.seek_back())
                        elif cmd == "current": self.result.emit(self.ctrl.current())
                        return

            # ── AI fallback: GPT розбирає довільну команду ──────────────────
            cmd = self._ai_parse(self.text)
            if cmd:
                self._execute_ai_cmd(cmd)
            else:
                self.error.emit("Команда Spotify не розпознана")

        except RuntimeError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Spotify: {str(e)[:40]}")

    # ── AI fallback ───────────────────────────────────────────────────────────

    _AI_SYSTEM = """\
Ти — парсер команд Spotify. Отримуєш голосову команду і повертаєш ТІЛЬКИ JSON.

Доступні дії:
  search      — шукати і грати (потрібен "query")
  liked_songs — улюблені треки
  pause       — пауза
  resume      — продовжити
  next        — наступна
  prev        — попередня
  shuffle     — перемішати
  repeat      — повтор
  volume      — гучність (потрібен "value": 0-100)
  current     — що зараз грає

Приклади:
  "зіграй щось весело" → {"action":"search","query":"веселі хіти"}
  "хочу слухати рок"   → {"action":"search","query":"rock"}
  "щось спокійне"      → {"action":"search","query":"спокійна музика"}
  "погромче"           → {"action":"volume","value":75}
  "стоп"               → {"action":"pause"}

Повертай ТІЛЬКИ JSON, без пояснень."""

    def _ai_parse(self, text: str) -> dict | None:
        if not self._api_key:
            return None
        try:
            import json as _json
            from openai import OpenAI
            client = OpenAI(api_key=self._api_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self._AI_SYSTEM},
                    {"role": "user",   "content": text},
                ],
                max_tokens=80,
                temperature=0,
            )
            return _json.loads(resp.choices[0].message.content)
        except Exception as e:
            print(f"[Spotify AI] {e}")
            return None

    def _execute_ai_cmd(self, cmd: dict) -> None:
        action = cmd.get("action", "")
        if   action == "search":
            q = cmd.get("query", self.text)
            self.result.emit(self.ctrl.play_track(q))
        elif action == "liked_songs": self.result.emit(self.ctrl.liked_songs())
        elif action == "pause":       self.result.emit(self.ctrl.pause())
        elif action == "resume":      self.result.emit(self.ctrl.resume())
        elif action == "next":        self.result.emit(self.ctrl.next_track())
        elif action == "prev":        self.result.emit(self.ctrl.prev_track())
        elif action == "shuffle":     self.result.emit(self.ctrl.toggle_shuffle())
        elif action == "repeat":      self.result.emit(self.ctrl.toggle_repeat())
        elif action == "current":     self.result.emit(self.ctrl.current())
        elif action == "volume":
            v = int(cmd.get("value", 50))
            self.result.emit(self.ctrl.set_volume(v))
        else:
            self.error.emit("Команда Spotify не розпознана")


# ══════════════════════════════════════════════════════════════════════════════
# SearchThread
# ══════════════════════════════════════════════════════════════════════════════

class SearchThread(QThread):
    """
    Розпізнає тип запиту і відкриває:
      music  → Spotify (spotify:// URI, fallback → open.spotify.com)
      movie  → YouTube search + «фільм»
      search → YouTube search (загальний пошук)
    """
    result = pyqtSignal(str)
    error  = pyqtSignal(str)

    # ────────────────────────────────────────────────────
    # Ключові слова (довші фрази стоять вище голих слів)
    # ────────────────────────────────────────────────────
    _MUSIC_KEYS = [
        "найди в спотифай", "грай музику", "включи музику", "включай музику",
        "грай песню",  "включи песню",  "включай песню",
        "грай пісню",  "включи пісню",  "включай пісню",
        "play music",  "play song",     "грай song",
        "грай",        "включи",                          # голі — перевіряємо окремо
    ]

    _MOVIE_KEYS = [
        # explicit movie/series phrases first (more specific → higher priority)
        "включи серіал", "поставь серіал", "знайди серіал", "відкрий серіал",
        "включи сериал", "поставь сериал", "знайди сериал",
        "включи фільм",  "поставь фільм",  "найди фільм",
        "включи фильм",  "поставь фильм",  "найди фильм",
        "play movie",    "play series",    "find movie",
        # bare keywords — checked after specific phrases
        "серіал",  "сериал",
        "фільм",   "фильм",
        "сезон",   "серія",   "серия",
        "episode", "season",
    ]

    _SEARCH_KEYS = [
        "шукай в ютубі", "знайди в ютубі", "найди в ютубі",
        "search", "find", "what is",
        "що таке", "як зробити", "хто це",
    ]

    # Слова після голих «включи»/«грай», яких НЕ торкаємось (→ НЕ музика)
    _NOT_MUSIC_AFTER = [
        "фільм", "фильм", "movie",
        "серіал", "сериал", "series",
        "сезон", "season", "серія", "серия", "episode",
        "калькулятор", "блокнот", "notepad", "calc",
    ]

    _MAX_QUERY_LEN = 500  # prevent unbounded query strings

    def __init__(self, text: str):
        super().__init__()
        self.text = text.strip().lower()[:self._MAX_QUERY_LEN]

    # ────────────────────────────────────────────────────
    # detect()  — статичний, зручний для перевірки снаружі
    # ────────────────────────────────────────────────────
    @staticmethod
    def detect(text: str):
        """Повращає 'music' | 'movie' | 'search' | None"""
        low = text.strip().lower()

        # 1) фільми — самые специфичные
        for k in SearchThread._MOVIE_KEYS:
            if k in low:
                return "movie"

        # 2) музика
        for k in SearchThread._MUSIC_KEYS:
            if k in low:
                if k in ("включи", "грай"):
                    after = low[low.find(k) + len(k):].strip()
                    if not after or any(s in after for s in SearchThread._NOT_MUSIC_AFTER):
                        continue
                return "music"

        # 3) загальний пошук
        for k in SearchThread._SEARCH_KEYS:
            if k in low:
                return "search"

        return None

    # ────────────────────────────────────────────────────
    # _extract_query()  — берём всё после ключевого слова
    # ────────────────────────────────────────────────────
    def _extract_query(self, keys: list) -> str:
        for k in keys:
            idx = self.text.find(k)
            if idx != -1:
                after = self.text[idx + len(k):].strip()
                for stop in ("пожалуйста", "будь ласка", "будь-ласка"):
                    after = after.replace(stop, "").strip()
                return after
        return ""

    @staticmethod
    def _open_spotify(query: str) -> bool:
        from urllib.parse import quote
        encoded = quote(query)
        # URI для пошуку та автоматичного відтворення першого результату
        uri = f"spotify:search:{encoded}"

        try:
            if sys.platform == "win32":
                # Запуск через cmd для Windows
                subprocess.Popen(f'start "" "{uri}"', shell=True, creationflags=_NO_WINDOW)
            else:
                opener = "xdg-open" if sys.platform.startswith("linux") else "open"
                subprocess.Popen([opener, uri])
            return True
        except Exception:
            return False

    @staticmethod
    def _open_youtube(query: str) -> bool:
        from urllib.parse import quote
        url = f"https://www.google.com/search?q={quote(query)}"
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in chrome_paths:
            if os.path.exists(p):
                try:
                    # Pass URL directly — Chrome opens it as new tab in existing window
                    subprocess.Popen([p, url], creationflags=_NO_WINDOW)
                    print(f"[YouTube] Opening: {url}")
                    return True
                except Exception as e:
                    print(f"[YouTube] Chrome launch error: {e}")
        try:
            webbrowser.open(url)
            return True
        except Exception:
            return False

    # ────────────────────────────────────────────────────
    # run()
    # ────────────────────────────────────────────────────
    def run(self):
        """Головна логіка: тільки відкриваємо додатки, не питаючи токени"""
        kind = self.detect(self.text)

        if kind == "music":
            query = self._extract_query(self._MUSIC_KEYS)
            if not query:
                self.result.emit("Яку пісню знайти? 🎵")
                return

            # ЦЕЙ РЯДОК ПРОСТО ВІДКРИВАЄ SPOTIFY
            self._open_spotify(query)
            self.result.emit(f"🎵 Шукаю в Spotify: {query}")

        elif kind == "movie":
            query = self._extract_query(self._MOVIE_KEYS)
            if query:
                # For series (сезон/серія/серіал) keep query as-is; add "фільм" only for bare films
                _series_words = ("сезон", "серія", "серия", "серіал", "сериал",
                                 "season", "episode", "series")
                suffix = "" if any(w in self.text.lower() for w in _series_words) else " фільм"
                self._open_youtube(query + suffix)
                icon = "📺" if suffix == "" else "🎬"
                self.result.emit(f"{icon} Шукаю: {query}")

        elif kind == "search":
            query = self._extract_query(self._SEARCH_KEYS)
            if query:
                self._open_youtube(query)
                self.result.emit(f"🔍 Шукаю: {query}")

        else:
            self.error.emit("Запит не розпізнано")


# ══════════════════════════════════════════════════════════════════════════════
# SphereMediaMixin — AivonSphere methods for media control
# ══════════════════════════════════════════════════════════════════════════════

class SphereMediaMixin:
    """Methods mixed into AivonSphere for Spotify/Steam/media control."""

    def _handle_music(self, lower):
        """Голосове керування музикою через медіа-клавіші"""
        if any(p in lower for p in ["грай музику", "play music", "включи музику", "відтворюй"]):
            try:
                subprocess.Popen(['powershell', '-Command',
                    '(new-object -com wscript.shell).SendKeys([char]179)'],
                    creationflags=_NO_WINDOW)
            except Exception: pass
            self.respond_silent("▶️ Відтворення!")
            return True
        if any(p in lower for p in ["пауза", "pause", "стоп музику", "зупини музику"]):
            try:
                subprocess.Popen(['powershell', '-Command',
                    '(new-object -com wscript.shell).SendKeys([char]179)'],
                    creationflags=_NO_WINDOW)
            except Exception: pass
            self.respond_silent("⏸ Пауза!")
            return True
        if any(p in lower for p in ["наступна пісня", "next song", "наступний трек", "next track", "далі"]):
            try:
                subprocess.Popen(['powershell', '-Command',
                    '(new-object -com wscript.shell).SendKeys([char]176)'],
                    creationflags=_NO_WINDOW)
            except Exception: pass
            self.respond_silent("⏭ Наступний трек!")
            return True
        if any(p in lower for p in ["попередня пісня", "previous song", "попередній трек", "назад"]):
            try:
                subprocess.Popen(['powershell', '-Command',
                    '(new-object -com wscript.shell).SendKeys([char]177)'],
                    creationflags=_NO_WINDOW)
            except Exception: pass
            self.respond_silent("⏮ Попередній трек!")
            return True
        return False

    def _handle_steam(self, lower: str, text: str) -> bool:
        """Обробка Steam-команд: запуск ігор, список, рекомендація."""
        try:
            from sphere.utils import get_steam_games, find_steam_game
        except ImportError:
            return False

        # ── Список ігор ──
        if any(p in lower for p in [
            "які ігри", "список ігор", "мої ігри", "що є в стімі",
            "що є в steam", "покажи ігри", "show games",
        ]):
            games = get_steam_games(max_games=100)
            if not games:
                self.respond("Steam не знайдено або ігор немає 🎮")
            else:
                names = [g["name"] for g in games[:6]]
                extra = f" і ще {len(games)-6}" if len(games) > 6 else ""
                self.respond(f"Ігор у Steam: {len(games)}. Останні: " +
                             ", ".join(names) + extra)
            return True

        # ── Що пограти / відпочинь ──
        if any(p in lower for p in [
            "що пограти", "порекомендуй гру", "яку гру", "відпочинь",
            "може пограти", "час відпочити", "зроби перерву",
            "suggest game", "what to play",
        ]):
            games = get_steam_games(max_games=50)
            if not games:
                self.respond("Steam не знайдено 🎮 Встановіть Steam або запустіть його.")
                return True
            # Prefer recently played
            recent = [g for g in games if g["last_played"] > 0]
            picks  = recent[:5] if recent else games[:5]
            import random as _rnd
            pick = _rnd.choice(picks)
            self.respond(
                f"Рекомендую пограти в «{pick['name']}» 🎮 "
                f"({pick['playtime_h']}год зіграно). Запустити?"
            )
            self._last_steam_suggestion = pick
            return True

        # ── Так (підтвердження після рекомендації) ──
        if hasattr(self, "_last_steam_suggestion") and self._last_steam_suggestion:
            if any(p in lower for p in ["так", "запусти", "давай", "yes", "ок", "окей"]):
                pick = self._last_steam_suggestion
                self._last_steam_suggestion = None
                self.respond_silent(f"🎮 Запускаю {pick['name']}!")
                QTimer.singleShot(500, lambda aid=pick["appid"]: subprocess.Popen(
                    f'steam://rungameid/{aid}', shell=True, creationflags=_NO_WINDOW))
                return True

        # ── Запуск конкретної гри ──
        launch_kw = [
            "зіграй в ", "запусти гру ", "відкрий гру ",
            "play game ", "launch game ", "run game ",
            "запусти в стімі ", "відкрий в стімі ",
        ]
        for kw in launch_kw:
            if kw in lower:
                game_name = text[lower.find(kw) + len(kw):].strip()
                game_name = re.sub(r'\s*(будь ласка|пожалуйста|please)\s*', '', game_name).strip()
                if not game_name:
                    self.respond("Яку гру запустити? Назвіть назву.")
                    return True
                game = find_steam_game(game_name)
                if game:
                    self.respond_silent(f"🎮 Запускаю {game['name']}!")
                    QTimer.singleShot(500, lambda aid=game["appid"]: subprocess.Popen(
                        f'steam://rungameid/{aid}', shell=True, creationflags=_NO_WINDOW))
                else:
                    self.respond(f"Гру «{game_name}» не знайдено в Steam. "
                                 "Перевірте назву або скажіть «які ігри».")
                return True

        return False

    def _handle_media(self, lower: str, text: str) -> bool:
        """Обробка команд перегляду фільмів і серіалів."""
        try:
            from sphere.utils import (load_watch_history, save_watch_entry,
                                      get_vlc_recent, _open_video_fullscreen,
                                      _VIDEO_EXTENSIONS)
        except ImportError:
            return False

        # ── Включи серіал / фільм (останній переглянутий) ──
        open_last = any(p in lower for p in [
            "включи серіал", "включи фільм", "відкрий серіал", "відкрий фільм",
            "поставь серіал", "поставь фільм", "дивитись", "запусти серіал",
            "play movie", "open movie", "watch movie",
        ])

        # ── Конкретна назва після команди ──
        media_keywords = [
            "включи серіал ", "включи фільм ", "відкрий серіал ", "відкрий фільм ",
            "поставь ", "запусти фільм ", "запусти серіал ", "дивитись ",
        ]
        title_query = ""
        for kw in media_keywords:
            if kw in lower:
                title_query = text[lower.find(kw) + len(kw):].strip()
                title_query = re.sub(r'\s*(будь ласка|пожалуйста)\s*', '', title_query).strip()
                break

        if not open_last and not title_query:
            return False

        # Якщо є назва — шукаємо в history і VLC recent
        if title_query:
            history = load_watch_history()
            vlc     = get_vlc_recent()
            all_media = history + [v for v in vlc if v not in history]
            q = title_query.lower()
            for entry in all_media:
                if q in entry.get("title", "").lower():
                    self.respond_silent(f"📺 Відкриваю «{entry['title']}» на весь екран!")
                    save_watch_entry(entry["title"], entry.get("path", ""),
                                     entry.get("source", ""))
                    QTimer.singleShot(500, lambda p=entry.get("path",""):
                        _open_video_fullscreen(p) if p else None)
                    return True
            # Не знайшли — шукаємо файл
            self.respond_silent(f"🔍 Шукаю «{title_query}»...")
            from sphere.network import PCFileSearchThread
            self._pc_search_thread = PCFileSearchThread(title_query)
            def _on_found(result: str, tq=title_query):
                # Якщо знайшли конкретний файл
                if result.startswith("Знайшов:"):
                    p = result.replace("Знайшов:", "").strip()
                    if Path(p).suffix.lower() in _VIDEO_EXTENSIONS:
                        self.respond_silent(f"📺 Відкриваю {Path(p).name}!")
                        save_watch_entry(Path(p).stem, p, "pc")
                        QTimer.singleShot(300, lambda: _open_video_fullscreen(p))
                        return
                self.respond(f"Не знайшов «{tq}» 😕 Скажіть точнішу назву або додайте в список перегляду.")
            self._pc_search_thread.result.connect(_on_found)
            self._pc_search_thread.start()
            return True

        # Відкрити останній переглянутий
        history = load_watch_history()
        vlc     = get_vlc_recent()

        # Пріоритет: watch history → VLC recent
        if history:
            entry = history[0]
            path  = entry.get("path", "")
            title = entry.get("title", "?")
            self.respond_silent(f"📺 Відкриваю «{title}» — продовжуємо!")
            save_watch_entry(title, path, entry.get("source", ""))
            if path:
                QTimer.singleShot(500, lambda p=path: _open_video_fullscreen(p))
            return True

        if vlc:
            entry = vlc[0]
            path  = entry.get("path", "")
            title = entry.get("title", "?")
            self.respond_silent(f"📺 Відкриваю «{title}» з VLC!")
            save_watch_entry(title, path, "vlc")
            QTimer.singleShot(500, lambda p=path: _open_video_fullscreen(p))
            return True

        # Нічого немає — пропонуємо додати
        self.respond("Немає збережених фільмів 📺 Скажіть «включи фільм [назва]» — "
                     "я знайду і запам'ятаю. Або скажіть «додай фільм [шлях]».")
        return True

    def _handle_add_media(self, lower: str, text: str) -> bool:
        """'Додай фільм X' — ручне додавання в список перегляду."""
        try:
            from sphere.utils import save_watch_entry
        except ImportError:
            return False
        for kw in ["додай фільм ", "додай серіал ", "add movie ", "запам'ятай фільм "]:
            if kw in lower:
                title = text[lower.find(kw) + len(kw):].strip()
                if title:
                    save_watch_entry(title, "", "manual")
                    self.respond_silent(f"✅ Запам'ятав: «{title}»")
                return True
        return False

    def _on_work_started(self, app_name: str):
        """Виклик коли з'явився робочий застосунок."""
        if not self.config.get("work_mode_notify", True):
            return
        self.respond(f"💻 Бачу, ти відкрив {app_name}. Починаємо роботу? "
                     "Скажи «відкрий робочий процес» якщо потрібен контекст.")

    def _on_work_stopped(self):
        """Виклик коли всі робочі застосунки закрито."""
        if not self.config.get("work_mode_notify", True):
            return
        # Пропонуємо відпочити
        import random as _rnd
        suggestions = [
            "Робочі застосунки закрито. Може зробити перерву? 😊",
            "Гарна робота! Відпочинь — скажи «що пограти» або «включи серіал» 🎮",
            "Схоже, робота завершена. Кажи «відпочинь» — підберу гру!",
        ]
        self.respond(_rnd.choice(suggestions))

    def _execute_spotify_uri(self, uri: str, resp: str = ""):
        """Виконує Spotify URI через контролер — з авто-play."""
        self._ensure_spotify_ctrl()
        ctrl = self.spotify_ctrl

        def _do():
            if uri == "spotify:collection":
                msg = ctrl.liked_songs() if ctrl else "❤️ Відкриваю улюблені треки"
            elif uri.startswith("spotify:track:"):
                if ctrl and ctrl._sp:
                    try:
                        devs = (ctrl._sp.devices() or {}).get("devices", [])
                        dev_id = next((d["id"] for d in devs if d.get("is_active")), None) or \
                                 (devs[0]["id"] if devs else None)
                        ctrl._sp.start_playback(device_id=dev_id, uris=[uri])
                        msg = resp or "🎵 Граю"
                    except Exception:
                        subprocess.Popen(f'start "" "{uri}"', shell=True,
                                         creationflags=_NO_WINDOW)
                        msg = resp or "🎵 Відкриваю Spotify"
                else:
                    subprocess.Popen(f'start "" "{uri}"', shell=True,
                                     creationflags=_NO_WINDOW)
                    msg = resp or "🎵 Відкриваю Spotify"
            elif uri.startswith("spotify:playlist:") or uri.startswith("spotify:album:") or \
                 uri.startswith("spotify:artist:"):
                if ctrl and ctrl._sp:
                    try:
                        devs = (ctrl._sp.devices() or {}).get("devices", [])
                        dev_id = next((d["id"] for d in devs if d.get("is_active")), None) or \
                                 (devs[0]["id"] if devs else None)
                        ctrl._sp.start_playback(device_id=dev_id, context_uri=uri)
                        msg = resp or "🎵 Граю"
                    except Exception:
                        subprocess.Popen(f'start "" "{uri}"', shell=True,
                                         creationflags=_NO_WINDOW)
                        msg = resp or "🎵 Відкриваю Spotify"
                else:
                    subprocess.Popen(f'start "" "{uri}"', shell=True,
                                     creationflags=_NO_WINDOW)
                    msg = resp or "🎵 Відкриваю Spotify"
            else:
                subprocess.Popen(f'start "" "{uri}"', shell=True,
                                 creationflags=_NO_WINDOW)
                msg = resp or "🎵 Spotify"
            self.respond_silent(msg)

        import threading as _t
        _t.Thread(target=_do, daemon=True).start()

    def _ensure_spotify_ctrl(self):
        """Lazy-init SpotifyController з конфіга."""
        if self.spotify_ctrl:
            return
        cid  = self.config.get("spotify_client_id", "")
        csec = self.config.get("spotify_client_secret", "")
        self.spotify_ctrl = SpotifyController(cid, csec)
        if cid and csec:
            print("Spotify controller ready (Web API)")
        else:
            print("Spotify controller ready (URI fallback, no API keys)")
