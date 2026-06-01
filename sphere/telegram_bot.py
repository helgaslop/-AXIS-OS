# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/telegram_bot.py  –  Telegram інтеграція (з aivon_sphere.py)        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Клас:  TelegramBotThread(QThread)  (рядки 1229–2226)                       ║
║  Mixin: SphereTelegramMixin — методи AivonSphere для Telegram               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import re
import time
import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, QTimer

# ── Optional imports ─────────────────────────────────────────────────────────
try:
    import requests as _requests
    import urllib3 as _urllib3
    _urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import psutil as _psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _load_commands_safe():
    """Load custom commands without circular imports."""
    try:
        from sphere.config import load_commands
        return load_commands()
    except Exception:
        return []


def _get_steam_games_safe(max_games=24):
    """Load Steam games without circular imports."""
    try:
        from sphere.utils import get_steam_games
        return get_steam_games(max_games=max_games)
    except Exception:
        return []


def _get_most_watched_safe():
    try:
        from sphere.utils import get_most_watched
        return get_most_watched()
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# TelegramBotThread
# ══════════════════════════════════════════════════════════════════════════════

class TelegramBotThread(QThread):
    """Telegram бот — слухає повідомлення і передає їх сфері як команди.
    Використовує long-polling (не потрібен webhook/публічний IP).
    """
    message_received = pyqtSignal(str, str)   # text, chat_id
    status_changed   = pyqtSignal(str)         # "online" / "offline" / "error:..."

    _POLL_TIMEOUT = 25  # секунди long-poll

    # ── Тематичні смарт-меню ─────────────────────────────────────────────────
    # Кожна тема → inline keyboard. "__wait__:key" = чекаємо текстовий ввід.
    TOPIC_MENUS: dict = {
        "notes": {
            "title": "📝  <b>Нотатки</b>",
            "rows": [
                [("📋 Мої нотатки",     "мої нотатки"),
                 ("🗑 Очистити всі",    "видали всі нотатки")],
                [("✏️ Записати нотатку","__wait__:add_note")],
            ],
        },
        "music": {
            "title": "🎵  <b>Музика / Spotify</b>",
            "rows": [
                [("▶️ Грати",           "включи музику"),
                 ("⏸ Пауза",           "пауза")],
                [("⏭ Наступний",       "наступний трек"),
                 ("⏮ Попередній",      "попередній трек")],
                [("❤️ Улюблені треки", "улюблені треки"),
                 ("🔀 Перемішати",     "перемішати spotify")],
                [("🎵 Зараз грає",     "що зараз грає"),
                 ("🔍 Знайти пісню",   "__wait__:spotify_search")],
                [("📋 Мої плейлісти", "__submenu__:spotify_playlists"),
                 ("🕐 Нещодавні",      "__submenu__:spotify_recent")],
            ],
        },
        "tasks": {
            "title": "✅  <b>Завдання / To-Do</b>",
            "rows": [
                [("📋 Мої задачі",      "мої задачі"),
                 ("✅ Виконати",        "завдання виконано")],
                [("➕ Нове завдання",   "__wait__:add_task")],
            ],
        },
        "habits": {
            "title": "🏆  <b>Звички</b>",
            "rows": [
                [("📊 Прогрес",         "мій прогрес звичок"),
                 ("📋 Список",          "мої звички")],
                [("✅ Відмітити",       "__wait__:mark_habit")],
            ],
        },
        "news": {
            "title": "📰  <b>Новини</b>",
            "rows": [
                [("🖥 Технології",      "новини tech"),
                 ("🌍 Світ",           "новини світу")],
                [("🇺🇦 Україна",       "новини україна")],
            ],
        },
        "reminders": {
            "title": "⏰  <b>Нагадування</b>",
            "rows": [
                [("📋 Мої нагадування", "/reminders"),
                 ("❌ Видалити",        "видали нагадування")],
                [("⏰ Нагадати о...",   "__wait__:add_reminder")],
            ],
        },
        "weather": {
            "title": "🌤  <b>Погода</b>",
            "rows": [
                [("🌤 Зараз",           "яка погода"),
                 ("📅 На тиждень",      "прогноз погоди на тиждень")],
                [("🌆 Змінити місто",   "__wait__:set_city")],
            ],
        },
        "alarms": {
            "title": "⏰  <b>Будильники</b>",
            "rows": [
                [("📋 Мої будильники", "мої будильники"),
                 ("❌ Скасувати",      "скасуй будильник")],
                [("⏰ Новий будильник", "__wait__:add_alarm")],
            ],
        },
        "focus": {
            "title": "🎯  <b>Фокус-режим</b>",
            "rows": [
                [("🎯 25 хвилин",  "увімкни фокус на 25 хвилин"),
                 ("⏱ 50 хвилин",  "увімкни фокус на 50 хвилин")],
                [("🔥 90 хвилин",  "увімкни фокус на 90 хвилин"),
                 ("❌ Вимкнути",   "вимкни фокус")],
            ],
        },
        "system2": {
            "title": "🖥  <b>Система+</b>",
            "rows": [
                [("🔋 Заряд",       "скільки заряду"),
                 ("🌐 Інтернет",    "швидкість інтернету")],
                [("📡 WiFi",        "хто в мережі"),
                 ("💤 Вимкнути",    "__wait__:shutdown_timer")],
                [("📸 Скрін в TG",  "зроби скрін і відправ")],
            ],
        },
        "pomodoro": {
            "title": "🍅  <b>Помодоро</b>",
            "rows": [
                [("▶️ Старт",        "старт помодоро"),
                 ("⏸ Пауза",        "пауза помодоро")],
                [("🔄 Скинути",      "скинь помодоро"),
                 ("☕ Перерва",      "перерва помодоро")],
                [("📊 Статус",       "скільки помодоро"),
                 ("🎯 Фокус 25хв",  "увімкни фокус на 25 хвилин")],
            ],
        },
    }

    # Підказки для стану "очікування тексту"
    _WAIT_PROMPTS: dict = {
        "add_note":       "✏️  Напиши текст нотатки — збережу одразу:",
        "add_task":       "✅  Напиши завдання — додам до списку:",
        "add_reminder":   "⏰  Напиши нагадування:\n<i>Напр: о 15:00 зателефонувати Олені</i>",
        "spotify_search": "🔍  Що шукати в Spotify?\n<i>Напр: Imagine Dragons Believer</i>",
        "mark_habit":     "🏆  Яку звичку відмітити? Напиши назву:",
        "set_city":       "🌆  Напиши місто для погоди (укр або англ):",
        "add_alarm":      "⏰  Введи час будильника (напр: 7:30 або 08:00):",
        "shutdown_timer": "💤  Через скільки вимкнути ПК?\n<i>Напр: 30 секунд / 10 хвилин / 2 години</i>",
    }
    # Префікси для перетворення тексту у голосову команду
    _WAIT_PREFIXES: dict = {
        "add_note":       "запиши нотатку",
        "add_task":       "додай завдання",
        "add_reminder":   "нагадай",
        "spotify_search": "spotify знайди",
        "mark_habit":     "відмітити звичку",
        "set_city":       "змінити місто погоди на",
        "add_alarm":      "постав будильник на",
        "shutdown_timer": "вимкни через",
    }

    def __init__(self, token: str, allowed_ids=None, custom_commands=None, parent=None):
        super().__init__(parent)
        self.token            = token.strip()
        self.allowed_ids      = [str(x).strip() for x in (allowed_ids or [])] if allowed_ids else []
        self._custom_commands = list(custom_commands or [])
        self._running         = True
        # chat_id → pending wait key (очікуємо текстовий ввід від користувача)
        self._tg_pending: dict[str, str] = {}
        self._offset          = 0
        self._sess            = None
        # Callback map: short_id → action_text (для inline кнопок)
        self._cb_map: dict[str, str] = {}
        self._cb_counter = 0
        # Offline message queue: list of (chat_id, text) tuples
        self._msg_queue: list = []

    def update_commands(self, custom_commands: list):
        """Оновити список кастомних команд (live, без рестарту)."""
        self._custom_commands = list(custom_commands or [])

    # ── Callback helpers ──────────────────────────────────────────────────────
    def _cb(self, action: str) -> str:
        """Повертає короткий ID для callback_data (≤64 байти)."""
        for k, v in self._cb_map.items():
            if v == action:
                return k
        key = f"x{self._cb_counter}"
        self._cb_counter += 1
        self._cb_map[key] = action
        return key

    def _answer_cb(self, cb_id: str, text: str = ""):
        try:
            self._sess.post(f"{self._base}/answerCallbackQuery",
                json={"callback_query_id": cb_id, "text": text[:200]}, timeout=5)
        except Exception:
            pass

    def _edit_message(self, chat_id: str, msg_id: int, text: str,
                      reply_markup: dict | None = None):
        """Редагувати вже надіслане повідомлення."""
        try:
            payload = {"chat_id": chat_id, "message_id": msg_id,
                       "text": text[:4096], "parse_mode": "HTML"}
            if reply_markup:
                payload["reply_markup"] = reply_markup
            self._sess.post(f"{self._base}/editMessageText", json=payload, timeout=10)
        except Exception:
            pass

    @property
    def _base(self) -> str:
        return f"https://api.telegram.org/bot{self.token}"

    def run(self):
        if not HAS_REQUESTS:
            self.status_changed.emit("error: pip install requests")
            return
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            self._sess = _requests.Session()
            self._sess.headers.update({"User-Agent": "AXIS-OS/1.0"})
            self._sess.verify = False   # антивірус може підміняти SSL-сертифікат
        except Exception as e:
            self.status_changed.emit(f"error: {e}")
            return

        # Verify token
        try:
            r = self._sess.get(f"{self._base}/getMe", timeout=10)
            if not r.ok:
                self.status_changed.emit(f"error: invalid token ({r.status_code})")
                return
            bot_name = r.json().get("result", {}).get("username", "")
            self.status_changed.emit(f"online (@{bot_name})")
        except Exception as e:
            self.status_changed.emit(f"error: {e}")
            return

        # Реєструємо команди в меню '/' бота
        self._register_bot_menu()

        _backoff = 5          # current wait seconds after network error
        _backoff_max = 60     # cap at 60 s
        _was_offline = False  # track state so we only log once per outage

        while self._running:
            try:
                resp = self._sess.get(
                    f"{self._base}/getUpdates",
                    params={"offset": self._offset, "timeout": self._POLL_TIMEOUT},
                    timeout=self._POLL_TIMEOUT + 5
                )
                # ── successful response → reset backoff + drain queued msgs ──
                if _was_offline:
                    print("[Telegram] ✅ з'єднання відновлено")
                    self.status_changed.emit("online")
                    _was_offline = False
                    # Send any messages that were queued while offline
                    if self._msg_queue:
                        queued = self._msg_queue[:]
                        self._msg_queue.clear()
                        for q_cid, q_txt, q_mkp in queued:
                            self.send_message(q_cid, q_txt, reply_markup=q_mkp)
                        print(f"[Telegram] 📬 черга відправлена: {len(queued)} повідом.")
                _backoff = 5

                if not resp.ok:
                    time.sleep(3)
                    continue
                for upd in resp.json().get("result", []):
                    self._offset = upd["update_id"] + 1
                    try:
                        self._process_update(upd)
                    except Exception as e:
                        print(f"[Telegram] ❌ _process_update error: {e}")
                        import traceback; traceback.print_exc()

            except Exception as e:
                if not self._running:
                    break
                err_str = str(e)
                # Detect network / DNS failures
                _net_keywords = ("getaddrinfo", "NameResolution", "ConnectionError",
                                 "ConnectTimeout", "ReadTimeout", "Max retries",
                                 "RemoteDisconnected", "ConnectionReset")
                is_net_err = any(k in err_str for k in _net_keywords)

                if is_net_err:
                    if not _was_offline:
                        # First failure → log the full error once
                        print(f"[Telegram] ⚠️ мережа недоступна: {e}")
                        self.status_changed.emit("offline (no network)")
                        _was_offline = True
                    else:
                        # Subsequent failures → silent (no log spam)
                        pass
                else:
                    # Non-network error → always log
                    print(f"[Telegram] ❌ polling error: {e}")

                # Exponential backoff: 5 → 10 → 20 → 40 → 60 → 60 …
                time.sleep(_backoff)
                _backoff = min(_backoff * 2, _backoff_max)

        self.status_changed.emit("offline")

    # ── Дизайн / брендинг ────────────────────────────────────────────────────
    _HEADER = (
        "╔══════════════════════════╗\n"
        "║  🔮  <b>AXIS OS</b>  ·  <b>AIVON</b>  🔮  ║\n"
        "║   <i>AI Operating System</i>    ║\n"
        "╚══════════════════════════╝"
    )
    _DIVIDER  = "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"
    _DIVIDER2 = "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰"

    def _fmt_welcome(self, first: str, chat_id: str) -> str:
        now = datetime.now().strftime("%H:%M  %d.%m.%Y")
        name_line = f"👤  Привіт, <b>{first}</b>!" if first else "👤  Привіт!"
        return (
            f"{self._HEADER}\n\n"
            f"{name_line}\n"
            f"🟢  Асистент <b>онлайн</b> та готовий\n"
            f"🕐  <code>{now}</code>\n\n"
            f"{self._DIVIDER}\n"
            f"⌨️  <b>Обери дію кнопкою нижче</b>\n"
            f"    або напиши <i>природньою мовою</i>\n"
            f"{self._DIVIDER}\n\n"
            f"💡 <b>Приклади:</b>\n"
            f"   <code>відкрий гта</code>  →  Steam\n"
            f"   <code>гучність 50</code>  →  гучність\n"
            f"   <code>виключи пк</code>   →  вимкнення\n\n"
            f"🔑  ID: <code>{chat_id}</code>"
        )

    def _fmt_status(self) -> str:
        """Красиво форматований стан ПК."""
        try:
            now = datetime.now().strftime("%H:%M:%S  %d.%m.%Y")
            lines = [
                f"{self._HEADER}\n",
                "🖥️  <b>МОНІТОРИНГ СИСТЕМИ</b>",
                f"🕐  <code>{now}</code>",
                f"{self._DIVIDER}",
            ]
            if HAS_PSUTIL:
                cpu  = _psutil.cpu_percent(interval=0.3)
                ram  = _psutil.virtual_memory()
                disk = _psutil.disk_usage("/")
                # CPU bar
                cpu_bar  = self._bar(cpu,  20)
                ram_pct  = ram.percent
                ram_bar  = self._bar(ram_pct, 20)
                disk_pct = disk.percent
                disk_bar = self._bar(disk_pct, 20)
                ram_used = ram.used  / (1024**3)
                ram_tot  = ram.total / (1024**3)
                disk_used= disk.used / (1024**3)
                disk_tot = disk.total/ (1024**3)
                cpu_icon  = "🔴" if cpu  > 85 else ("🟡" if cpu  > 60 else "🟢")
                ram_icon  = "🔴" if ram_pct  > 85 else ("🟡" if ram_pct  > 60 else "🟢")
                disk_icon = "🔴" if disk_pct > 85 else ("🟡" if disk_pct > 70 else "🟢")
                lines += [
                    f"\n{cpu_icon}  <b>CPU</b>    {cpu_bar}  <code>{cpu:.0f}%</code>",
                    f"{ram_icon}  <b>RAM</b>    {ram_bar}  <code>{ram_pct:.0f}%</code>  ({ram_used:.1f}/{ram_tot:.1f} GB)",
                    f"{disk_icon}  <b>Диск</b>   {disk_bar}  <code>{disk_pct:.0f}%</code>  ({disk_used:.0f}/{disk_tot:.0f} GB)",
                ]
                # Топ процеси по CPU
                try:
                    procs = sorted(
                        _psutil.process_iter(['name','cpu_percent']),
                        key=lambda p: p.info.get('cpu_percent',0) or 0,
                        reverse=True
                    )[:4]
                    if any((p.info.get('cpu_percent') or 0) > 0.5 for p in procs):
                        lines.append(f"\n{self._DIVIDER}")
                        lines.append("⚡  <b>Топ процеси:</b>")
                        for p in procs:
                            c = p.info.get('cpu_percent') or 0
                            if c > 0.3:
                                n = (p.info.get('name') or '?')[:22]
                                lines.append(f"   <code>{n:<22}</code> {c:.1f}%")
                except Exception:
                    pass
            else:
                lines.append("\n⚠️  psutil не встановлено")
            lines.append(f"\n{self._DIVIDER}")
            lines.append("📟  <i>AXIS OS v1.0  ·  AIVON Sphere</i>")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ Помилка збору статистики: {e}"

    @staticmethod
    def _bar(pct: float, width: int = 15) -> str:
        """Текстовий прогрес-бар: ████░░░░"""
        filled = int(width * pct / 100)
        return "█" * filled + "░" * (width - filled)

    def _fmt_blocked(self, chat_id: str) -> str:
        return (
            f"⛔  <b>ДОСТУП ЗАБОРОНЕНО</b>\n\n"
            f"{self._DIVIDER}\n"
            f"🔑  Твій Chat ID:\n"
            f"    <code>{chat_id}</code>\n\n"
            f"👆  Додай його в:\n"
            f"    AXIS OS → Sphere → Telegram\n"
            f"    → <b>Дозволені Chat ID</b>\n"
            f"{self._DIVIDER}\n"
            f"📟  <i>AXIS OS Security Gate</i>"
        )

    @staticmethod
    def _html_escape(s: str) -> str:
        """Escape characters that break Telegram HTML parse mode."""
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _fmt_response(self, text: str) -> str:
        """Обгортаємо відповідь сфери в красивий контейнер.
        HTML-спецсимволи в тілі відповіді екрануємо, щоб Telegram не відхиляв.
        """
        now = datetime.now().strftime("%H:%M")
        # Скорочуємо якщо дуже довге
        raw = text[:800] + ("…" if len(text) > 800 else "")
        # Якщо текст вже містить HTML-теги (<b>, <i>, <code>…) — не екрануємо,
        # інакше екрануємо небезпечні символи.
        if re.search(r"<(b|i|code|pre|a)\b", raw, re.I):
            body = raw   # вже розмічений HTML — залишаємо як є
        else:
            body = self._html_escape(raw)
        return (
            f"🔮  <b>AIVON</b>  ·  <code>{now}</code>\n"
            f"{self._DIVIDER}\n"
            f"{body}\n"
            f"{self._DIVIDER}"
        )

    # ── Обробка оновлень ─────────────────────────────────────────────────────
    def _process_update(self, upd: dict):
        # ── Inline callback query (натискання inline кнопки) ──────────────────
        cq = upd.get("callback_query")
        if cq:
            cq_id   = cq["id"]
            cq_data = cq.get("data", "")
            chat_id = str(cq["message"]["chat"]["id"])
            msg_id  = cq["message"].get("message_id")
            # Validate callback_data: must either be a known short ID in _cb_map
            # or start with a known action prefix. Unknown raw values are rejected.
            _VALID_CB_PREFIXES = ("__menu__", "__wait__:", "__submenu__:",
                                  "__spotify_uri__:", "__topic__:", "/status",
                                  "/start", "/menu", "/help")
            if cq_data not in self._cb_map and not any(cq_data.startswith(p) for p in _VALID_CB_PREFIXES):
                print(f"[Telegram] ⚠ Unknown callback_data ignored: {cq_data!r}")
                self._answer_cb(cq_id, "")
                return
            action  = self._cb_map.get(cq_data, cq_data)

            # Спеціальна дія — повернутись до головного меню
            if action == "__menu__":
                self._answer_cb(cq_id, "🏠 Головне меню")
                first = cq.get("from", {}).get("first_name", "") or ""
                welcome = self._fmt_welcome(first, chat_id)
                # Прибираємо inline кнопки з поточного повідомлення
                self._edit_message(chat_id, msg_id, welcome,
                    reply_markup={"inline_keyboard": []})
                return

            # /status через inline
            if action == "/status":
                self._answer_cb(cq_id, "🖥️ Збираю дані...")
                status_text = self._fmt_status()
                self.send_message(chat_id, status_text)
                return

            # Перевірка дозволів
            if self.allowed_ids and chat_id not in self.allowed_ids:
                self._answer_cb(cq_id, "⛔ Немає доступу")
                return

            # Кнопка "очікування тексту" — запитуємо ввід
            if action.startswith("__wait__:"):
                wait_key = action[9:]
                self._tg_pending[chat_id] = wait_key
                prompt = self._WAIT_PROMPTS.get(wait_key, "Введи текст наступним повідомленням:")
                self._answer_cb(cq_id, "✏️ Введи текст")
                self.send_message(chat_id, prompt)
                return

            # Inline підменю Spotify (плейлісти, нещодавні)
            if action.startswith("__submenu__:"):
                sub = action[12:]
                self._answer_cb(cq_id, "⏳ Завантажую...")
                self._show_spotify_submenu(chat_id, sub)
                return

            # Пряме відтворення Spotify URI з кнопки
            if action.startswith("__spotify_uri__:"):
                uri = action[16:]
                self._answer_cb(cq_id, "🎵 Запускаю...")
                self._execute_spotify_uri(uri)
                return

            # Показати тематичне меню через callback
            if action.startswith("__topic__:"):
                topic = action[10:]
                self._answer_cb(cq_id, "📋 Меню")
                self._show_topic_menu(chat_id, topic)
                return

            self._answer_cb(cq_id, "⚙️ Виконую...")
            if action:
                self.message_received.emit(action, chat_id)
            return

        # ── Звичайне текстове повідомлення ────────────────────────────────────
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            return
        chat_id  = str(msg["chat"]["id"])
        raw_text = (msg.get("text") or "").strip()
        cmd = raw_text.split("@")[0].lower() if raw_text.startswith("/") else raw_text.lower()

        # ── /start | /menu — відповідаємо ВСІМ ───────────────────────────────
        if cmd in ("/start", "/menu", "/help", "start"):
            first = msg.get("from", {}).get("first_name", "") or ""
            tg_cmds = self._custom_commands
            welcome = self._fmt_welcome(first, chat_id)
            if tg_cmds:
                rows = self.build_keyboard_rows(tg_cmds, cols=2)
                self.send_with_keyboard(chat_id, welcome, rows)
            else:
                # Дефолтна клавіатура якщо кастомних немає
                default_rows = [
                    ["🖥️ Стан ПК",    "⚡ Процеси"],
                    ["🎮 Ігри",        "🎬 Серіал"],
                    ["🔊 Гучніше",     "🔇 Тихіше"],
                    ["💻 Робота",      "📷 Скріншот"],
                    ["😴 Режим сну",   "❌ Вимкнути ПК"],
                ]
                self.send_with_keyboard(chat_id, welcome, default_rows)
            print(f"[Telegram] /start від {chat_id} ({first})")
            return

        # ── /status — красивий моніторинг ────────────────────────────────────
        if cmd == "/status" or raw_text in ("🖥️ Стан ПК",):
            if self.allowed_ids and chat_id not in self.allowed_ids:
                self.send_message(chat_id, self._fmt_blocked(chat_id))
                return
            status_text = self._fmt_status()
            self.send_message(chat_id, status_text)
            return

        # ── Перевірка дозволів ────────────────────────────────────────────────
        if self.allowed_ids and chat_id not in self.allowed_ids:
            self.send_message(chat_id, self._fmt_blocked(chat_id))
            print(f"[Telegram] BLOCKED: {chat_id}")
            return

        # ── Rate limit: max 30 commands per minute per user ───────────────────
        _now = time.time()
        if not hasattr(self, '_cmd_rate'):
            self._cmd_rate = {}
        user_times = self._cmd_rate.get(chat_id, [])
        user_times = [t for t in user_times if _now - t < 60]  # keep last 60s
        if len(user_times) >= 30:
            self.send_message(chat_id, "⚠️ Забагато команд. Зачекайте хвилину.")
            return
        user_times.append(_now)
        self._cmd_rate[chat_id] = user_times

        # ── Фото-повідомлення → Gemini Vision ────────────────────────────────
        photos = msg.get("photo")
        if photos and not raw_text:
            file_id = photos[-1]["file_id"]
            caption = msg.get("caption") or "Що на цьому фото? Опиши детально українською."
            self.send_message(chat_id, "🖼 Аналізую фото...")
            self.message_received.emit(f"__photo__:{file_id}:{caption}", chat_id)
            return

        # ── Голосове повідомлення → транскрипція ──────────────────────────────
        voice = msg.get("voice")
        if voice:
            file_id = voice["file_id"]
            self.send_message(chat_id, "🎤 Розпізнаю голосове...")
            self.message_received.emit(f"__voice__:{file_id}", chat_id)
            return

        # ── Очікування тексту (після натискання __wait__ кнопки) ────────────
        if chat_id in self._tg_pending and raw_text:
            wait_key = self._tg_pending.pop(chat_id)
            prefix = self._WAIT_PREFIXES.get(wait_key, "")
            if prefix:
                raw_text = f"{prefix} {raw_text}"
                print(f"[Telegram] pending '{wait_key}' → '{raw_text[:60]}'")

        # ── Кастомна кнопка або звичайний текст ──────────────────────────────
        if raw_text:
            print(f"[Telegram] текстова кнопка: {raw_text!r} | cmds_count={len(self._custom_commands)}")
            cmd_cfg = self._resolve_custom_cmd(raw_text)
            if cmd_cfg:
                ctype = cmd_cfg.get("type", "command")
                print(f"[Telegram] матч: type={ctype!r}")
                if ctype.startswith("submenu"):
                    # Показуємо підменю (inline keyboard) з динамічним вмістом
                    self._show_submenu(chat_id, cmd_cfg)
                    return
                elif ctype.startswith("topic_"):
                    # Тематичне смарт-меню (notes, music, tasks, …)
                    topic = ctype[6:]
                    print(f"[Telegram] topic menu: {topic!r}")
                    self._show_topic_menu(chat_id, topic)
                    return
                else:
                    action = cmd_cfg.get("action", raw_text)
                    print(f"[Telegram] '{raw_text[:30]}' → '{action[:40]}'")
                    self.message_received.emit(action, chat_id)
                    return
            # Звичайний текст — як голосова команда
            print(f"[Telegram] текст: '{raw_text[:50]}'")
            self.message_received.emit(raw_text, chat_id)

    def _resolve_custom_cmd(self, text: str) -> dict | None:
        """Якщо text збігається з label кастомної команди — повертає весь конфіг."""
        tl = text.strip().lower()
        _emoji_re = re.compile(
            r'^[\U00010000-\U0010ffff☀-➿⬀-⯿ἰ0-ᾟF]+\s*',
            re.UNICODE)
        for c in self._custom_commands:
            lbl = c.get("label", "").strip()
            if not lbl:
                continue
            lbl_l = lbl.lower()
            lbl_clean = _emoji_re.sub("", lbl_l).strip()
            if tl == lbl_l or (lbl_clean and tl == lbl_clean):
                return c
            slug = re.sub(r"[^a-z0-9_]", "", lbl_l.replace(" ", "_"))
            if slug and tl == "/" + slug:
                return c
        return None

    def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML",
                     reply_markup: dict | None = None):
        """Надіслати повідомлення в Telegram.
        Якщо HTML-парсинг Telegram відхиляє — повторюємо без parse_mode.
        """
        if not HAS_REQUESTS or not self._sess:
            return
        try:
            payload = {"chat_id": chat_id, "text": text[:4096], "parse_mode": parse_mode}
            if reply_markup:
                payload["reply_markup"] = reply_markup
            r = self._sess.post(f"{self._base}/sendMessage", json=payload, timeout=10)
            if not r.ok:
                err_body = r.text[:200] if hasattr(r, 'text') else str(r.status_code)
                print(f"[Telegram] sendMessage {r.status_code}: {err_body}")
                # HTML parse error → retry as plain text
                if r.status_code == 400 and parse_mode == "HTML":
                    payload2 = {"chat_id": chat_id, "text": text[:4096]}
                    if reply_markup:
                        payload2["reply_markup"] = reply_markup
                    r2 = self._sess.post(f"{self._base}/sendMessage", json=payload2, timeout=10)
                    if not r2.ok:
                        _preview = (text[:100] + "…") if len(text) > 100 else text
                        print(f"[Telegram] sendMessage plain fallback {r2.status_code}: {r2.text[:100]} | msg={_preview!r}")
        except Exception as e:
            err_str = str(e)
            _net_kw = ("getaddrinfo", "NameResolution", "ConnectionError",
                       "ConnectTimeout", "ReadTimeout", "Max retries",
                       "RemoteDisconnected", "ConnectionReset")
            if any(k in err_str for k in _net_kw):
                # Queue the message for later delivery when network comes back
                self._msg_queue.append((chat_id, text, reply_markup))
                print(f"[Telegram] 📪 повідомлення в чергу ({len(self._msg_queue)} ч.)")
            else:
                print(f"[Telegram] sendMessage exception: {e}")

    def send_with_keyboard(self, chat_id: str, text: str,
                           buttons: list[list[str]], parse_mode: str = "HTML"):
        """Надіслати повідомлення з Reply Keyboard (постійні кнопки знизу)."""
        keyboard = [[{"text": btn} for btn in row] for row in buttons]
        markup = {
            "keyboard": keyboard,
            "resize_keyboard": True,
            "persistent": True,        # кнопки завжди видно
            "input_field_placeholder": "Виберіть команду або напишіть...",
        }
        self.send_message(chat_id, text, parse_mode, reply_markup=markup)

    def remove_keyboard(self, chat_id: str, text: str = "⌨️"):
        """Прибрати Reply Keyboard."""
        self.send_message(chat_id, text, reply_markup={"remove_keyboard": True})

    def send_inline_keyboard(self, chat_id: str, text: str,
                             rows: list) -> int | None:
        """Надіслати повідомлення з inline-кнопками всередині.
        rows = [[(label, cb_data), ...], ...]
        Повертає message_id (для подальшого редагування).
        """
        keyboard = [[{"text": lbl, "callback_data": cb} for lbl, cb in row]
                    for row in rows]
        if not HAS_REQUESTS or not self._sess:
            print(f"[Telegram] send_inline_keyboard: немає сесії (HAS_REQUESTS={HAS_REQUESTS})")
            return None
        try:
            r = self._sess.post(f"{self._base}/sendMessage", json={
                "chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": keyboard}
            }, timeout=10)
            if r.ok:
                return r.json().get("result", {}).get("message_id")
            else:
                print(f"[Telegram] send_inline_keyboard error: {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"[Telegram] send_inline_keyboard exception: {e}")
        return None

    # ── Підменю (inline keyboard) ─────────────────────────────────────────────
    def _show_submenu(self, chat_id: str, config: dict):
        """Показати inline підменю залежно від типу кнопки."""
        ctype = config.get("type", "command")
        label = config.get("label", "Меню")
        print(f"[Telegram] _show_submenu: type={ctype!r} label={label!r} chat={chat_id}")

        if ctype == "submenu_steam":
            items = self._items_steam()
            title = "🎮  <b>Steam — Ігри</b>"
            empty = "⚠️ Steam ігри не знайдено.\nПереконайся що Steam встановлено."
        elif ctype == "submenu_watch":
            items = self._items_watch()
            title = "🎬  <b>Відео / Серіали</b>"
            empty = "⚠️ Немає збережених переглядів.\nСкажи сфері «включи фільм [назва]»."
        elif ctype == "submenu_volume":
            items = self._items_volume()
            title = "🔊  <b>Гучність</b>"
            empty = ""
        elif ctype == "submenu_system":
            items = self._items_system()
            title = "🖥️  <b>Система</b>"
            empty = ""
        elif ctype == "submenu_apps":
            items = self._items_apps()
            title = "📂  <b>Програми</b>"
            empty = "⚠️ Немає додатків у списку."
        elif ctype == "submenu_commands":
            items = self._items_user_commands()
            title = "📋  <b>Всі команди</b>"
            empty = "⚠️ Немає збережених команд. Додай в панелі AXIS OS → Команди."
        else:  # submenu_custom
            raw = config.get("children", [])
            items = [(c.get("label","?"), c.get("action","")) for c in raw if c.get("label")]
            title = f"📋  <b>{label}</b>"
            empty = "⚠️ Підменю порожнє — додай команди в панелі AXIS OS."

        print(f"[Telegram] _show_submenu items: {len(items)}")
        if not items:
            self.send_message(chat_id, f"{title}\n\n{empty}")
            return

        rows = self._build_item_rows(items)
        rows.append([("🏠  Головне меню", self._cb("__menu__"))])

        header = (
            f"{self._HEADER}\n\n"
            f"{title}\n"
            f"{self._DIVIDER}\n"
            f"Натисни на кнопку:"
        )
        msg_id = self.send_inline_keyboard(chat_id, header, rows)
        print(f"[Telegram] send_inline_keyboard → msg_id={msg_id}")

    # ── Контент підменю ───────────────────────────────────────────────────────
    def _items_steam(self) -> list:
        try:
            games = _get_steam_games_safe(max_games=24)
            result = [(f"🎮 {g['name'][:28]}", f"запусти гру {g['name']}") for g in games]
            print(f"[Telegram] _items_steam: знайдено {len(result)} ігор")
            return result
        except Exception as e:
            print(f"[Telegram] _items_steam error: {e}")
            return []

    def _items_watch(self) -> list:
        try:
            hist = _get_most_watched_safe()[:16]
            return [(f"🎬 {h['title'][:28]}", f"включи {h['title']}") for h in hist]
        except Exception:
            return []

    def _items_volume(self) -> list:
        return [
            ("🔇 Без звуку",  "без звуку"),
            ("🔈 20%",        "гучність 20"),
            ("🔉 40%",        "гучність 40"),
            ("🔉 60%",        "гучність 60"),
            ("🔊 80%",        "гучність 80"),
            ("🔊 100%",       "гучність 100"),
            ("➕ Гучніше +10","гучність вище"),
            ("➖ Тихіше −10", "гучність нижче"),
        ]

    def _items_system(self) -> list:
        return [
            ("🖥️ Стан ПК",    "/status"),
            ("⚡ Процеси",    "що зараз запущено"),
            ("📷 Скріншот",   "зроби скріншот"),
            ("📋 Буфер",      "проаналізуй буфер"),
            ("😴 Сон",        "сплячий режим"),
            ("🔄 Рестарт",    "перезавантаж пк"),
            ("❌ Вимкнути",   "виключи пк"),
        ]

    def _items_apps(self) -> list:
        """Список з кастомних дочірніх команд типу apps."""
        return []

    def _items_user_commands(self) -> list:
        """Всі кастомні команди з commands.json — для Telegram підменю."""
        try:
            cmds = _load_commands_safe()
            result = []
            for c in cmds:
                phrase = c.get("phrase") or c.get("trigger") or ""
                name   = c.get("name") or c.get("response") or phrase
                icon   = c.get("icon") or c.get("ico") or "⚡"
                if phrase:
                    label = f"{icon} {name[:25]}" if icon not in name else name[:28]
                    result.append((label, phrase))
            return result[:48]   # Telegram обмеження — не більше ~48 кнопок
        except Exception as e:
            print(f"[Telegram] _items_user_commands error: {e}")
            return []

    # ── Тематичне смарт-меню ─────────────────────────────────────────────────
    def _show_topic_menu(self, chat_id: str, topic: str):
        """Показати смарт-меню для теми (notes, music, tasks, …)."""
        cfg = self.TOPIC_MENUS.get(topic)
        if not cfg:
            self.send_message(chat_id, f"⚠️ Невідома тема: {topic}")
            return
        title_text = (
            f"{self._HEADER}\n\n"
            f"{cfg['title']}\n"
            f"{self._DIVIDER}\n"
            f"Обери дію:"
        )
        inline_rows = []
        for row in cfg["rows"]:
            inline_row = []
            for label, action in row:
                cb_id = self._cb(action)
                inline_row.append({"text": label, "callback_data": cb_id})
            inline_rows.append(inline_row)
        inline_rows.append([{"text": "🏠 Головне меню", "callback_data": self._cb("__menu__")}])
        if not HAS_REQUESTS or not self._sess:
            return
        try:
            self._sess.post(f"{self._base}/sendMessage", json={
                "chat_id": chat_id,
                "text": title_text,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": inline_rows},
            }, timeout=10)
        except Exception as e:
            print(f"[Telegram] _show_topic_menu error: {e}")

    # ── Shared row-builder: pairs items into 2-column inline rows ────────────
    def _build_item_rows(self, items: list) -> list:
        rows = []
        for i in range(0, len(items), 2):
            chunk = items[i:i+2]
            rows.append([(lbl, self._cb(act)) for lbl, act in chunk])
        return rows

    # ── Spotify підменю (плейлісти / нещодавні) ──────────────────────────────
    def _show_spotify_submenu(self, chat_id: str, sub: str):
        """Показує inline-клавіатуру з плейлістами або нещодавніми треками Spotify."""
        if sub == "spotify_playlists":
            title  = "📋  <b>Мої плейлісти</b>"
            items  = self._items_spotify_playlists()
            empty  = "⚠️ Плейлісти не знайдено.\nПереконайся що Spotify підключено в панелі."
        elif sub == "spotify_recent":
            title  = "🕐  <b>Нещодавно слухав</b>"
            items  = self._items_spotify_recent()
            empty  = "⚠️ Немає нещодавніх треків."
        else:
            return

        header = (
            f"{self._HEADER}\n\n"
            f"{title}\n"
            f"{self._DIVIDER}\n"
            f"Натисни — одразу заграє:"
        )
        if not items:
            self.send_message(chat_id, f"{header}\n\n{empty}")
            return

        rows = self._build_item_rows(items)
        rows.append([
            ("🎵 Керування",    self._cb("__topic__:music")),
            ("🏠 Головне меню", self._cb("__menu__")),
        ])
        self.send_inline_keyboard(chat_id, header, rows)

    def _items_spotify_playlists(self) -> list:
        """Плейлісти користувача через Spotify API."""
        try:
            # spotify_ctrl may be injected from outside (e.g. AivonSphere)
            ctrl = getattr(self, 'spotify_ctrl', None)
            sp = getattr(ctrl, "_sp", None) if ctrl else None
            if not sp:
                return []
            result = [("❤️ Улюблені треки", "улюблені треки")]
            playlists = sp.current_user_playlists(limit=24).get("items", [])
            for pl in playlists:
                name = pl.get("name", "")[:28]
                uri  = pl.get("uri", "")
                if name and uri:
                    result.append((f"🎵 {name}", f"__spotify_uri__:{uri}"))
            return result
        except Exception as e:
            print(f"[Telegram] _items_spotify_playlists error: {e}")
            return [("❤️ Улюблені треки", "улюблені треки")]

    def _items_spotify_recent(self) -> list:
        """Нещодавно прослухані треки через Spotify API."""
        result = []
        try:
            ctrl = getattr(self, 'spotify_ctrl', None)
            sp = getattr(ctrl, "_sp", None) if ctrl else None
            if not sp:
                return result
            recent = sp.current_user_recently_played(limit=16).get("items", [])
            seen = set()
            for item in recent:
                track  = item.get("track", {})
                name   = track.get("name", "")
                artist = (track.get("artists") or [{}])[0].get("name", "")
                uri    = track.get("uri", "")
                if uri and uri not in seen:
                    seen.add(uri)
                    label = f"🎵 {artist[:12]} — {name[:16]}"
                    result.append((label, f"__spotify_uri__:{uri}"))
        except Exception as e:
            print(f"[Telegram] _items_spotify_recent error: {e}")
        return result

    def _execute_spotify_uri(self, uri: str):
        """Execute a Spotify URI — handled by AivonSphere via message signal."""
        self.message_received.emit(f"__spotify_uri__:{uri}", "")

    def set_bot_commands(self, commands: list[dict]):
        """Зареєструвати команди в меню '/' бота (з'являються при натисканні /).
        commands = [{"command": "status", "description": "Стан ПК"}, ...]
        """
        if not HAS_REQUESTS or not self._sess:
            return
        try:
            self._sess.post(
                f"{self._base}/setMyCommands",
                json={"commands": commands[:100]},
                timeout=10
            )
        except Exception:
            pass

    def _register_bot_menu(self):
        """Реєструє команди в меню '/' бота та встановлює опис."""
        static = [
            {"command": "start",  "description": "🏠 Головне меню + клавіатура"},
            {"command": "menu",   "description": "⌨️  Показати кнопки керування"},
            {"command": "status", "description": "🖥️  Моніторинг CPU · RAM · Диск"},
            {"command": "help",   "description": "❓  Список команд і підказки"},
        ]
        # Додаємо кастомні команди як /slug
        import re as _re
        for i, c in enumerate(self._custom_commands[:16], 1):
            lbl  = c.get("label", f"cmd{i}")
            act  = c.get("action", "")[:60]
            slug = _re.sub(r"[^a-z0-9_]", "", lbl.lower().replace(" ", "_"))[:32] or f"cmd{i}"
            static.append({"command": slug, "description": f"{lbl}  →  {act}"})
        self.set_bot_commands(static)

        # Встановлюємо опис бота (видно на сторінці бота)
        if HAS_REQUESTS and self._sess:
            desc = (
                "🔮 AXIS OS — AI Operating System\n\n"
                "Керуй своїм ПК голосом і текстом:\n"
                "• Відкривай ігри, фільми, програми\n"
                "• Контролюй гучність і живлення\n"
                "• Отримуй стан системи в реальному часі\n"
                "• Спілкуйся з AI природньою мовою\n\n"
                "Розроблено для Windows 10/11"
            )
            short_desc = "🔮 Керуй ПК голосом і текстом через AXIS OS AI-асистент"
            try:
                self._sess.post(f"{self._base}/setMyDescription",
                    json={"description": desc}, timeout=5)
                self._sess.post(f"{self._base}/setMyShortDescription",
                    json={"short_description": short_desc}, timeout=5)
            except Exception:
                pass

    def build_keyboard_rows(self, tg_commands: list[dict],
                            cols: int = 2) -> list[list[str]]:
        """Перетворює список команд у рядки кнопок (по cols штук у рядку)."""
        labels = [c.get("label", c.get("text", "?")) for c in tg_commands if c.get("label") or c.get("text")]
        rows = []
        for i in range(0, len(labels), cols):
            rows.append(labels[i:i + cols])
        return rows

    def stop(self):
        self._running = False
        # Interrupt long-poll with a quick getUpdates
        if HAS_REQUESTS:
            try:
                _requests.get(f"{self._base}/getUpdates",
                               params={"offset": self._offset, "timeout": 0},
                               timeout=2)
            except Exception:
                pass
        self.quit()


# ══════════════════════════════════════════════════════════════════════════════
# SphereTelegramMixin — AivonSphere methods for Telegram
# ══════════════════════════════════════════════════════════════════════════════

class SphereTelegramMixin:
    """Methods mixed into AivonSphere for Telegram bot integration."""

    def _start_telegram_bot(self, cfg: dict | None = None):
        """Запускає Telegram бот потік.
        cfg — якщо передано, використовує ці налаштування замість self.config
        (потрібно коли викликається з _apply_sphere_config де self.config ще не оновлено).
        """
        if not HAS_REQUESTS:
            self.respond_silent("⚠️ Потрібно: pip install requests")
            return
        src = cfg if cfg is not None else self.config
        token = src.get("telegram_token", "").strip()
        if not token:
            return
        allowed_raw = src.get("telegram_allowed_ids", "")
        allowed = [x.strip() for x in str(allowed_raw).split(",") if x.strip()]
        custom_cmds = src.get("telegram_commands", [])
        print(f"[Telegram] _start_telegram_bot: {len(custom_cmds)} команд, {len(allowed)} ID")
        # Зупинити попередній якщо є
        if self._telegram_bot:
            self._telegram_bot.stop()
            self._telegram_bot.wait(2000)
            self._telegram_bot = None
        self._telegram_bot = TelegramBotThread(token, allowed, custom_cmds)
        self._telegram_bot.message_received.connect(self._on_telegram_message)
        self._telegram_bot.status_changed.connect(self._on_telegram_status)
        self._telegram_bot.start()

    def _stop_telegram_bot(self):
        """Зупиняє Telegram бот потік."""
        if self._telegram_bot:
            self._telegram_bot.stop()
            self._telegram_bot.wait(2000)
            self._telegram_bot = None

    def _on_telegram_status(self, status: str):
        print(f"[Telegram] {status}")
        if status.startswith("online"):
            self.respond_silent(f"📱 Telegram бот підключено! {status}")
            # Надсилаємо привітальне повідомлення в Telegram при запуску
            QTimer.singleShot(1500, self._tg_send_startup_greeting)
        elif status.startswith("error"):
            self.respond_silent(f"⚠️ Telegram: {status}")

    def _tg_send_startup_greeting(self):
        """Надсилає привітання в Telegram при старті Sphere."""
        if not (self._telegram_bot and self._telegram_bot.isRunning()):
            return
        target = self._tg_notify_chat_id
        if not target:
            return   # Нема збереженого chat_id — чекаємо поки хтось напише /start
        from datetime import datetime as _dt
        now = _dt.now()
        hour = now.hour
        if hour < 6:
            greeting = "🌙 Доброї ночі"
        elif hour < 12:
            greeting = "🌅 Доброго ранку"
        elif hour < 18:
            greeting = "☀️ Доброго дня"
        else:
            greeting = "🌆 Доброго вечора"
        time_str = now.strftime("%H:%M  %d.%m.%Y")
        msg = (
            f"🔮  <b>AIVON Sphere запущена</b>\n"
            f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"{greeting}! Я онлайн та готова до роботи.\n"
            f"🕐  <code>{time_str}</code>\n"
            f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"💬 Говоріть команди голосом або пишіть сюди."
        )
        self._telegram_bot.send_message(target, msg)

    def _on_telegram_message(self, text: str, chat_id: str):
        """Повідомлення з Telegram → обробляємо як голосову команду."""
        import subprocess as _sp
        print(f"[Telegram] обробка від {chat_id}: '{text[:60]}'")

        # /status — показуємо стан ПК напряму
        if text.strip().lower() in ("/status", "status"):
            if self._telegram_bot:
                try:
                    from sphere.utils import get_pc_context
                    ctx = get_pc_context()
                except Exception:
                    ctx = "Стан недоступний"
                self._telegram_bot.send_message(chat_id, f"🖥️ <b>Стан ПК:</b>\n{ctx[:1000]}")
            return

        # /automations — список автоматизацій
        if text.strip().lower() in ("/automations", "/автоматизації"):
            if self._telegram_bot:
                automations = self.config.get("automations", [])
                if not automations:
                    msg = "📋 <b>Автоматизацій немає.</b>"
                else:
                    lines = ["📋 <b>Автоматизації:</b>"]
                    for a in automations:
                        enabled = "✅" if a.get("enabled", True) else "❌"
                        trigger = a.get("trigger", {})
                        t_type = trigger.get("type", "?")
                        t_info = trigger.get("app") or trigger.get("time") or trigger.get("phrase") or ""
                        n_actions = len(a.get("actions", []))
                        a_id = a.get("id", "?")
                        lines.append(f"{enabled} <b>{a.get('name','?')}</b> [<code>{t_type}: {t_info}</code>] → {n_actions} дій (id: {a_id})")
                    msg = "\n".join(lines)
                self._telegram_bot.send_message(chat_id, msg)
            return

        # /mode — поточний режим
        if text.strip().lower() in ("/mode", "/режим"):
            if self._telegram_bot:
                mode = getattr(self, '_mode', 'normal')
                cfg = getattr(type(self), '_MODE_CONFIGS', {}).get(mode, {})
                icon = cfg.get('icon', '⚪')
                label = cfg.get('label', mode)
                self._telegram_bot.send_message(chat_id, f"{icon} <b>Поточний режим:</b> {label}")
            return

        # /reminders — список нагадувань
        if text.strip().lower() in ("/reminders", "/нагадування"):
            if self._telegram_bot:
                reminders = getattr(self, 'reminders', [])
                if not reminders:
                    msg = "📋 <b>Нагадувань немає.</b>"
                else:
                    lines = ["📋 <b>Нагадування:</b>"]
                    for dt, rdata in reminders:
                        if isinstance(rdata, dict):
                            t = rdata.get("text", "?")
                            repeat = rdata.get("repeat")
                            icon = "🔄" if repeat else "🔔"
                            repeat_str = f" [{repeat}]" if repeat else ""
                        else:
                            t = str(rdata)
                            icon = "🔔"
                            repeat_str = ""
                        lines.append(f"{icon} {dt.strftime('%d.%m %H:%M')} — {t}{repeat_str}")
                    msg = "\n".join(lines)
                self._telegram_bot.send_message(chat_id, msg)
            return

        # ── Фото-аналіз через Gemini Vision ──────────────────────────────────
        if text.startswith("__photo__:"):
            parts = text[len("__photo__:"):].split(":", 1)
            file_id = parts[0]
            caption = parts[1] if len(parts) > 1 else "Що на цьому фото? Опиши детально."
            self._tg_chat_id = chat_id
            import threading as _thr
            _thr.Thread(
                target=self._tg_analyze_photo,
                args=(chat_id, file_id, caption),
                daemon=True
            ).start()
            return

        # ── Транскрипція голосового повідомлення ─────────────────────────────
        if text.startswith("__voice__:"):
            file_id = text[len("__voice__:"):]
            self._tg_chat_id = chat_id
            import threading as _thr
            _thr.Thread(
                target=self._tg_transcribe_voice,
                args=(chat_id, file_id),
                daemon=True
            ).start()
            return

        # ── Spotify URI з inline кнопки ───────────────────────────────────────
        if text.startswith("__spotify_uri__:"):
            uri = text[len("__spotify_uri__:"):]
            self._tg_chat_id = chat_id
            self._execute_spotify_uri(uri)
            return

        # Всі інші — обробляємо як голосову команду
        self._tg_chat_id = chat_id
        # Зберігаємо як постійний chat_id для проактивних сповіщень
        if not self._tg_notify_chat_id or self._tg_notify_chat_id != chat_id:
            self._tg_notify_chat_id = chat_id
            self.config["telegram_notify_chat_id"] = chat_id
            try:
                from sphere.config import save_config
                save_config(self.config)
            except Exception:
                pass
        # Скинути chat_id через 30с щоб не надсилати зайве
        QTimer.singleShot(30000, self._clear_tg_chat_id)
        # Показуємо сферу при команді з Telegram
        if self.is_hidden:
            self.show_orb()
        # Показуємо текст команди на сфері
        self.user_text = f"📱 {text[:40]}"
        self.update()

        # "музика" / "спотіфай" з Telegram → показуємо inline меню одразу
        _TG_MUSIC_KW = frozenset((
            "музика", "спотіфай", "spotify", "музику", "плейлист",
            "плейлісти", "включи музику", "відкрий музику",
        ))
        _tl = text.lower().strip()
        if any(_tl == kw or _tl.startswith(kw) for kw in _TG_MUSIC_KW):
            if self._telegram_bot and chat_id:
                self._telegram_bot._show_topic_menu(chat_id, "music")
                return

        # Обробляємо як команду
        self.on_recognized(text)

    def _clear_tg_chat_id(self):
        self._tg_chat_id = None

    # ── Telegram photo analysis ───────────────────────────────────────────────
    _TG_MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

    def _tg_download_file(self, file_id: str) -> bytes | None:
        """Download a file from Telegram by file_id. Returns bytes or None.
        Rejects files larger than _TG_MAX_DOWNLOAD_BYTES (10 MB).
        """
        if not (self._telegram_bot and HAS_REQUESTS):
            return None
        try:
            token = self._telegram_bot.token
            r = _requests.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": file_id}, timeout=10)
            r.raise_for_status()
            result = r.json().get("result", {})
            file_size = result.get("file_size", 0)
            if file_size and file_size > self._TG_MAX_DOWNLOAD_BYTES:
                print(f"[TG] download rejected — file too large: {file_size} bytes (max {self._TG_MAX_DOWNLOAD_BYTES})")
                return None
            file_path = result["file_path"]
            r2 = _requests.get(
                f"https://api.telegram.org/file/bot{token}/{file_path}",
                timeout=30)
            r2.raise_for_status()
            # Double-check actual content length
            if len(r2.content) > self._TG_MAX_DOWNLOAD_BYTES:
                print(f"[TG] download rejected — content too large: {len(r2.content)} bytes")
                return None
            return r2.content
        except Exception as e:
            print(f"[TG] download file error: {e}")
            return None

    def _tg_analyze_photo(self, chat_id: str, file_id: str, caption: str):
        """Download Telegram photo and analyze with Gemini Vision."""
        data = self._tg_download_file(file_id)
        if not data:
            self._respond_signal.emit("🖼 Не вдалось завантажити фото")
            return

        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(data)
            tmp_path = f.name

        try:
            google_key = self.config.get("google_key", "")
            if google_key:
                try:
                    import google.generativeai as genai
                    import base64 as _b64
                    genai.configure(api_key=google_key)
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    img_b64 = _b64.b64encode(data).decode()
                    # Detect image type
                    mime = "image/jpeg"
                    if data[:8] == b"\x89PNG\r\n\x1a\n":
                        mime = "image/png"
                    response = model.generate_content([
                        {"mime_type": mime, "data": img_b64},
                        caption
                    ])
                    result_text = response.text
                    self._respond_signal.emit(
                        f"🖼 <b>Аналіз фото:</b>\n{result_text[:800]}")
                    if self._telegram_bot and chat_id:
                        self._telegram_bot.send_message(
                            chat_id, f"🖼 <b>Аналіз фото:</b>\n{result_text[:800]}")
                    return
                except Exception as e:
                    print(f"[TG Photo] Gemini error: {e}")

            # Fallback: OpenAI vision
            openai_key = self.config.get("openai_key", "")
            if openai_key:
                try:
                    import base64 as _b64
                    img_b64 = _b64.b64encode(data).decode()
                    headers = {"Authorization": f"Bearer {openai_key}",
                               "Content-Type": "application/json"}
                    payload = {
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": [
                            {"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                            {"type": "text", "text": caption}
                        ]}],
                        "max_tokens": 600
                    }
                    r = _requests.post("https://api.openai.com/v1/chat/completions",
                                       json=payload, headers=headers, timeout=30)
                    result_text = r.json()["choices"][0]["message"]["content"]
                    self._respond_signal.emit(
                        f"🖼 <b>Аналіз фото:</b>\n{result_text[:800]}")
                    if self._telegram_bot and chat_id:
                        self._telegram_bot.send_message(
                            chat_id, f"🖼 <b>Аналіз фото:</b>\n{result_text[:800]}")
                    return
                except Exception as e:
                    print(f"[TG Photo] OpenAI error: {e}")

            self._respond_signal.emit(
                "🖼 Налаштуй Google API або OpenAI для аналізу фото")
            if self._telegram_bot and chat_id:
                self._telegram_bot.send_message(
                    chat_id, "🖼 Для аналізу фото потрібен Google API або OpenAI ключ")
        finally:
            try:
                _os.unlink(tmp_path)
            except Exception:
                pass

    def _tg_transcribe_voice(self, chat_id: str, file_id: str):
        """Download Telegram voice message and transcribe."""
        data = self._tg_download_file(file_id)
        if not data:
            self._respond_signal.emit("🎤 Не вдалось завантажити аудіо")
            return

        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(data)
            tmp_path = f.name

        transcribed = None
        try:
            # Try Whisper
            try:
                import whisper as _whisper
                model = _whisper.load_model("base")
                result = model.transcribe(tmp_path)
                transcribed = result.get("text", "").strip()
            except ImportError:
                pass
            except Exception as e:
                print(f"[TG Voice] Whisper error: {e}")

            # Try OpenAI Whisper API
            if not transcribed:
                openai_key = self.config.get("openai_key", "")
                if openai_key and HAS_REQUESTS:
                    try:
                        with open(tmp_path, "rb") as audio_f:
                            r = _requests.post(
                                "https://api.openai.com/v1/audio/transcriptions",
                                headers={"Authorization": f"Bearer {openai_key}"},
                                files={"file": ("voice.ogg", audio_f, "audio/ogg")},
                                data={"model": "whisper-1", "language": "uk"},
                                timeout=30)
                        if r.status_code == 200:
                            transcribed = r.json().get("text", "").strip()
                        else:
                            err = r.json().get("error", {}).get("message", r.status_code)
                            print(f"[TG Voice] Whisper HTTP {r.status_code}: {err}")
                    except Exception as e:
                        print(f"[TG Voice] OpenAI Whisper error: {e}")

            if transcribed:
                if self._telegram_bot and chat_id:
                    self._telegram_bot.send_message(
                        chat_id, f"🎤 <i>Розпізнано:</i> «{transcribed}»\n⚙️ Виконую...")
                # Process as command
                QTimer.singleShot(0, lambda t=transcribed: self.on_recognized(t))
            else:
                msg = "🎤 Не вдалось розпізнати голосове. Встанови: pip install openai-whisper"
                if self._telegram_bot and chat_id:
                    self._telegram_bot.send_message(chat_id, msg)
                self._respond_signal.emit(msg)
        finally:
            try:
                _os.unlink(tmp_path)
            except Exception:
                pass

    def _tg_send(self, text: str):
        """Відповідь у Telegram на поточну команду (reply context).
        Якщо команда прийшла з Telegram — відповідаємо туди.
        Якщо голосова команда — використовуємо збережений notify chat_id.
        """
        if not (self._telegram_bot and self._telegram_bot.isRunning()):
            return
        target = self._tg_chat_id or self._tg_notify_chat_id
        if target:
            formatted = self._telegram_bot._fmt_response(text)
            self._telegram_bot.send_message(target, formatted)
            if self._tg_chat_id:
                self._tg_chat_id = None   # відповідаємо один раз на команду

    def _tg_notify(self, text: str):
        """Проактивне сповіщення в Telegram (нотатки, задачі, нагадування тощо).
        Завжди надсилає до збереженого notify chat_id (незалежно від поточної команди).
        """
        if not (self._telegram_bot and self._telegram_bot.isRunning()):
            return
        target = self._tg_notify_chat_id or self._tg_chat_id
        if target:
            self._telegram_bot.send_message(target, text)

    def _on_telegram_btn_click(self):
        """Обробник натискання кнопки Telegram в UI сфери."""
        if self._telegram_bot and self._telegram_bot.isRunning():
            self.respond_silent("📱 Telegram бот активний")
        else:
            # Start if configured
            if self.config.get("telegram_token"):
                self._start_telegram_bot()
            else:
                self.respond_silent("📱 Telegram не налаштований. Відкрий панель → Telegram")
