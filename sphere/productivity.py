# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/productivity.py  –  Продуктивність (з aivon_sphere.py)             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Клас (mixin):  SphereProductivityMixin                                      ║
║  ┌──────────────────────────────────────────────────────────────────────┐   ║
║  │ НОТАТКИ                                                               │   ║
║  │   _load_notes()               → список нотаток (notes.json)          │   ║
║  │   _save_notes(notes)          → зберігає                             │   ║
║  │   _handle_notes(lower, text)  → додай/читай/знайди нотатку           │   ║
║  ├──────────────────────────────────────────────────────────────────────┤   ║
║  │ TODO СПИСОК                                                           │   ║
║  │   _load_todo()                → список задач (todo.json)             │   ║
║  │   _save_todo(tasks)           → зберігає                             │   ║
║  │   _handle_todo(lower, text)   → додай/відміть/покажи задачі          │   ║
║  ├──────────────────────────────────────────────────────────────────────┤   ║
║  │ ЗВИЧКИ                                                                │   ║
║  │   _load_habits()              → словник звичок (habits.json)         │   ║
║  │   _save_habits(data)          → зберігає                             │   ║
║  │   _handle_habits(lower, text) → відмітити звичку / показати стрік    │   ║
║  ├──────────────────────────────────────────────────────────────────────┤   ║
║  │ НОВИНИ                                                                │   ║
║  │   _handle_news(lower, text)   → зачитує новини (RSS)                 │   ║
║  ├──────────────────────────────────────────────────────────────────────┤   ║
║  │ АНАЛІЗ ДОКУМЕНТІВ                                                     │   ║
║  │   _handle_document_analysis(lower, text)                             │   ║
║  ├──────────────────────────────────────────────────────────────────────┤   ║
║  │ URL SUMMARIZER                                                        │   ║
║  │   _handle_url_summary(lower, text)                                   │   ║
║  ├──────────────────────────────────────────────────────────────────────┤   ║
║  │ YOUTUBE SEARCH                                                        │   ║
║  │   _handle_youtube_search(lower, text)                                │   ║
║  ├──────────────────────────────────────────────────────────────────────┤   ║
║  │ APP CLOSE                                                             │   ║
║  │   _handle_app_close(lower, text)                                     │   ║
║  ├──────────────────────────────────────────────────────────────────────┤   ║
║  │ TEMPERATURE QUERY                                                     │   ║
║  │   _handle_temperature_query(lower, text)                             │   ║
║  └──────────────────────────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# NOTE: This file uses forward references to the parent class (AivonSphere).
# All self.* accesses work via multiple inheritance (SphereProductivityMixin + AivonSphere).

import os
import re
import sys
import json
import time
import threading
import subprocess
import webbrowser
from datetime import datetime, timedelta

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

try:
    import psutil as _psutil
    HAS_PSUTIL = True
except ImportError:
    _psutil = None  # type: ignore
    HAS_PSUTIL = False


class SphereProductivityMixin:
    """Productivity methods. Mixed into AivonSphere."""

    # ═══════════════════════════════════════════════════════════
    # VOICE NOTES — нотатки голосом + Telegram
    # ═══════════════════════════════════════════════════════════

    def _load_notes(self) -> list:
        try:
            if self._notes_file.exists():
                return json.loads(self._notes_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def _save_notes(self, notes: list):
        try:
            self._notes_file.write_text(
                json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _handle_notes(self, lower: str, text: str) -> bool:
        """Голосові нотатки: запиши / покажи / видали."""
        save_kw  = ["запиши нотатку", "запиши нотатки", "нотатка", "запам'ятай нотатку",
                    "save note", "add note", "нотатку:", "нотатку "]
        read_kw  = ["мої нотатки", "покажи нотатки", "що я записував",
                    "show notes", "read notes", "список нотаток"]
        clear_kw = ["видали всі нотатки", "очисти нотатки", "clear notes", "delete notes"]

        if any(k in lower for k in clear_kw):
            self._save_notes([])
            self.respond_silent("🗑️ Всі нотатки видалено")
            return True

        if any(k in lower for k in read_kw):
            notes = self._load_notes()
            if not notes:
                self.respond_silent("📝 Нотаток немає")
                return True
            last = notes[-5:]
            msg = "📝 Останні нотатки:\n" + "\n".join(
                f"• [{n['date']}] {n['text']}" for n in reversed(last))
            self.respond_silent(msg[:300])
            self._tg_send(msg)
            return True

        for kw in save_kw:
            if kw in lower:
                idx = lower.find(kw)
                note_text = text[idx + len(kw):].strip().strip(":")
                if not note_text:
                    self.respond("Що записати? Скажіть текст нотатки.")
                    return True
                notes = self._load_notes()
                entry = {
                    "text": note_text,
                    "date": datetime.now().strftime("%d.%m %H:%M"),
                    "ts":   time.time(),
                }
                notes.append(entry)
                self._save_notes(notes)
                self.jarvis.play("confirm")
                self.respond_silent(f"📝 Записано: {note_text[:60]}")
                # Надсилаємо в Telegram (проактивне сповіщення)
                import aivon_sphere as _as
                self._tg_notify(f"📝 <b>Нова нотатка</b> [{entry['date']}]:\n{_as.TelegramBotThread._html_escape(note_text)}")
                return True

        return False

    # ═══════════════════════════════════════════════════════════
    # TO-DO LIST — список завдань голосом
    # ═══════════════════════════════════════════════════════════

    def _load_todo(self) -> list:
        try:
            if self._todo_file.exists():
                return json.loads(self._todo_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def _save_todo(self, tasks: list):
        try:
            self._todo_file.write_text(
                json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _handle_todo(self, lower: str, text: str) -> bool:
        """To-Do список голосом."""
        add_kw  = ["додай завдання", "додай задачу", "add task", "нове завдання",
                   "запиши завдання", "потрібно зробити"]
        list_kw = ["мої завдання", "список завдань", "що потрібно зробити",
                   "show tasks", "my tasks", "todo list", "що у мене"]
        done_kw = ["завдання виконано", "відмітити зроблено", "done task",
                   "task done", "виконав завдання", "зроблено"]
        if any(k in lower for k in list_kw):
            tasks = self._load_todo()
            if not tasks:
                self.respond_silent("✅ Список завдань порожній!")
                return True
            pending   = [t for t in tasks if not t.get("done")]
            completed = [t for t in tasks if t.get("done")]
            lines = [f"📋 Завдань: {len(pending)} активних, {len(completed)} виконано"]
            for t in pending[:5]:
                lines.append(f"◻ {t['text']}")
            msg = "\n".join(lines)
            self.respond_silent(msg[:250])
            self._tg_send(msg)
            return True

        if any(k in lower for k in done_kw):
            tasks = self._load_todo()
            # Позначаємо останнє незавершене
            for t in reversed(tasks):
                if not t.get("done"):
                    t["done"] = True
                    t["done_at"] = datetime.now().strftime("%d.%m %H:%M")
                    break
            self._save_todo(tasks)
            self.jarvis.play("confirm")
            self.respond_silent("✅ Завдання виконано!")
            return True

        for kw in add_kw:
            if kw in lower:
                idx = lower.find(kw)
                task_text = text[idx + len(kw):].strip().strip(":")
                if not task_text:
                    self.respond("Що потрібно зробити?")
                    return True
                tasks = self._load_todo()
                tasks.append({
                    "text": task_text,
                    "done": False,
                    "added": datetime.now().strftime("%d.%m %H:%M"),
                    "ts":   time.time(),
                })
                self._save_todo(tasks)
                self.jarvis.play("confirm")
                self.respond_silent(f"✅ Завдання додано: {task_text[:60]}")
                import aivon_sphere as _as
                self._tg_notify(f"📋 <b>Нове завдання додано:</b>\n◻ {_as.TelegramBotThread._html_escape(task_text)}")
                return True

        return False

    # ═══════════════════════════════════════════════════════════
    # HABITS TRACKER — трекер звичок
    # ═══════════════════════════════════════════════════════════

    def _load_habits(self) -> dict:
        try:
            if self._habits_file.exists():
                return json.loads(self._habits_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_habits(self, data: dict):
        try:
            self._habits_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _handle_habits(self, lower: str, text: str) -> bool:
        """Трекер звичок — стрік та статистика."""
        mark_kw  = ["відмітити звичку", "зробив звичку", "виконав звичку",
                    "mark habit", "habit done", "зробив "]
        stats_kw = ["мої звички", "статистика звичок", "стрік", "streak",
                    "habit stats", "my habits", "show habits"]
        add_kw   = ["додай звичку", "нова звичка", "add habit"]

        if any(k in lower for k in stats_kw):
            data = self._load_habits()
            if not data:
                self.respond_silent("🏆 Звичок ще немає. Скажіть «додай звичку: [назва]»")
                return True
            today = datetime.now().strftime("%Y-%m-%d")
            lines = ["🏆 Звички:"]
            for name, info in data.items():
                streak = info.get("streak", 0)
                done_today = today in info.get("done_dates", [])
                icon = "✅" if done_today else "◻"
                lines.append(f"{icon} {name}: 🔥{streak} днів підряд")
            self.respond_silent("\n".join(lines)[:250])
            return True

        for kw in add_kw:
            if kw in lower:
                idx = lower.find(kw)
                habit_name = text[idx + len(kw):].strip().strip(":").strip()
                if not habit_name:
                    self.respond("Назвіть звичку яку хочете відстежувати.")
                    return True
                data = self._load_habits()
                key = habit_name.lower()
                if key not in data:
                    data[key] = {"name": habit_name, "streak": 0, "done_dates": []}
                    self._save_habits(data)
                self.jarvis.play("confirm")
                self.respond_silent(f"🏆 Звичку «{habit_name}» додано!")
                return True

        for kw in mark_kw:
            if kw in lower:
                idx = lower.find(kw)
                habit_query = text[idx + len(kw):].strip().strip(":").strip()
                data = self._load_habits()
                today = datetime.now().strftime("%Y-%m-%d")
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                matched = None
                if habit_query:
                    for key in data:
                        if habit_query.lower() in key:
                            matched = key
                            break
                else:
                    # Перша звичка яка ще не відмічена сьогодні
                    for key, info in data.items():
                        if today not in info.get("done_dates", []):
                            matched = key
                            break
                if not matched:
                    if data:
                        matched = next(iter(data))
                    else:
                        self.respond("Спочатку додайте звичку: «додай звичку: [назва]»")
                        return True
                info = data[matched]
                done_dates = info.get("done_dates", [])
                if today not in done_dates:
                    done_dates.append(today)
                    # Перевіряємо стрік
                    if yesterday and yesterday in done_dates:
                        info["streak"] = info.get("streak", 0) + 1
                    elif not yesterday:
                        info["streak"] = info.get("streak", 0) + 1
                    else:
                        info["streak"] = 1
                    info["done_dates"] = done_dates[-90:]  # Зберігаємо 90 днів
                    data[matched] = info
                    self._save_habits(data)
                streak = info.get("streak", 1)
                self.jarvis.play("confirm")
                self.respond_silent(
                    f"🔥 «{info.get('name', matched)}» виконано! Стрік: {streak} {'день' if streak == 1 else 'дні' if streak < 5 else 'днів'}")
                return True

        return False

    # ═══════════════════════════════════════════════════════════
    # NEWS RSS — новини дня
    # ═══════════════════════════════════════════════════════════

    # │  Новини, документи, URL                                                │
    def _handle_news(self, lower: str, text: str) -> bool:
        """Новини через RSS (без API-ключа)."""
        kw = ["новини", "що нового", "останні новини", "news", "what's new",
              "технологічні новини", "tech news", "світові новини"]
        if not any(k in lower for k in kw):
            return False

        # Вибір RSS-стрічки
        if any(w in lower for w in ["технолог", "tech", "it"]):
            feed_url = "https://feeds.feedburner.com/TechCrunch"
            label = "Tech"
        elif any(w in lower for w in ["україн", "ukraine"]):
            feed_url = "https://www.pravda.com.ua/rss/view_news/"
            label = "Україна"
        else:
            feed_url = "https://rss.cnn.com/rss/edition.rss"
            label = "Світ"

        self.state = self.THINKING
        self.respond_silent(f"📰 Завантажую новини ({label})…")

        def _fetch():
            try:
                import urllib.request
                import xml.etree.ElementTree as ET
                req = urllib.request.Request(
                    feed_url,
                    headers={"User-Agent": "AXIS-OS/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    xml_data = r.read()
                root = ET.fromstring(xml_data)
                items = root.findall(".//item")[:5]
                if not items:
                    self._respond_signal.emit("📰 Новини недоступні")
                    return
                lines = [f"📰 <b>Новини ({label}):</b>"]
                spoken = []
                for item in items:
                    title = (item.findtext("title") or "").strip()
                    if title:
                        lines.append(f"• {title}")
                        spoken.append(title)
                msg = "\n".join(lines)
                self._tg_notify(msg)
                # Зачитуємо перші 2 заголовки
                short = ". ".join(spoken[:2])
                self._respond_signal.emit(f"📰 {short[:200]}")
            except Exception as e:
                self._respond_signal.emit(f"📰 Помилка новин: {str(e)[:40]}")

        threading.Thread(target=_fetch, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # DOCUMENT ANALYSIS — аналіз документів через Gemini
    # ═══════════════════════════════════════════════════════════

    def _handle_document_analysis(self, lower: str, text: str) -> bool:
        """Аналіз документів (txt/pdf/docx) через Gemini."""
        kw = ["проаналізуй документ", "аналіз документу", "прочитай файл",
              "analyze document", "read file", "analyze file",
              "підсумуй файл", "що у файлі", "розбери документ",
              "відкрий документ для аналізу", "аналізуй"]
        if not any(k in lower for k in kw):
            return False

        # Витягуємо шлях або назву файлу
        file_path = None
        for kw_item in kw:
            if kw_item in lower:
                idx = lower.find(kw_item)
                candidate = text[idx + len(kw_item):].strip().strip(":")
                if candidate:
                    file_path = candidate
                break

        if not file_path:
            self.respond("Вкажіть шлях до файлу, наприклад: «проаналізуй документ C:/звіт.pdf»")
            return True

        # Якщо шлях відносний — шукаємо на десктопі та в документах
        if not os.path.isabs(file_path):
            search_dirs = [
                os.path.expanduser("~/Desktop"),
                os.path.expanduser("~/Documents"),
                os.path.expanduser("~/Downloads"),
            ]
            for d in search_dirs:
                candidate = os.path.join(d, file_path)
                if os.path.exists(candidate):
                    file_path = candidate
                    break

        if not os.path.exists(file_path):
            self.respond(f"Файл не знайдено: {file_path}")
            return True

        # Security: block path traversal outside allowed directories
        import pathlib as _pathlib
        try:
            resolved = _pathlib.Path(file_path).resolve()
            allowed_roots = [
                _pathlib.Path.home(),
                _pathlib.Path.home() / 'Documents',
                _pathlib.Path.home() / 'Desktop',
                _pathlib.Path.home() / 'Downloads',
            ]
            if not any(str(resolved).startswith(str(r)) for r in allowed_roots):
                self.respond(f"⚠️ Доступ до файлу заборонений: {file_path}")
                return True
        except Exception:
            self.respond("⚠️ Невірний шлях файлу")
            return True

        self.state = self.THINKING
        self.respond_silent(f"📄 Читаю «{os.path.basename(file_path)}»…")

        def _analyze():
            try:
                ext = os.path.splitext(file_path)[1].lower()
                content = ""

                if ext == ".txt":
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(20000)

                elif ext == ".pdf":
                    try:
                        import pdfplumber
                        with pdfplumber.open(file_path) as pdf:
                            pages = pdf.pages[:15]
                            content = "\n".join(
                                p.extract_text() or "" for p in pages)[:20000]
                    except ImportError:
                        # Fallback: PyPDF2
                        try:
                            import PyPDF2
                            with open(file_path, "rb") as f:
                                reader = PyPDF2.PdfReader(f)
                                content = "\n".join(
                                    page.extract_text() or ""
                                    for page in reader.pages[:15])[:20000]
                        except ImportError:
                            self._respond_signal.emit(
                                "⚠️ Встановіть pdfplumber: pip install pdfplumber")
                            return

                elif ext in (".docx", ".doc"):
                    try:
                        import docx
                        doc = docx.Document(file_path)
                        content = "\n".join(p.text for p in doc.paragraphs)[:20000]
                    except ImportError:
                        self._respond_signal.emit(
                            "⚠️ Встановіть python-docx: pip install python-docx")
                        return

                else:
                    # Спробуємо прочитати як текст
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(10000)

                if not content.strip():
                    self._respond_signal.emit("📄 Файл порожній або не вдалося прочитати")
                    return

                # Завжди через Gemini якщо є ключ
                import aivon_sphere as _as
                cfg   = _as.load_config()
                fname = os.path.basename(file_path)
                prompt = (
                    f"Ти аналізуєш документ «{fname}».\n"
                    f"Зроби стислий аналіз: основна тема, ключові пункти (3-5), "
                    f"висновок. Відповідай українською.\n\n"
                    f"ДОКУМЕНТ:\n{content[:15000]}"
                )

                # Пробуємо Gemini (найкращий для документів)
                import queue as _q
                _rq = _q.Queue()
                gemini_cfg = dict(cfg)
                gemini_cfg["_force_provider"] = "gemini"
                t = _as.AIThread(cfg, prompt)
                t.response.connect(lambda r: _rq.put(r))
                t.error.connect(lambda e: _rq.put(f"ERR:{e}"))
                t.start()
                t.wait(60000)
                try:
                    result = _rq.get_nowait()
                except Exception:
                    result = ""
                if not result or result.startswith("ERR:"):
                    # Ollama fallback
                    try:
                        result = self._call_ollama([{"role": "user", "content": prompt}])
                    except Exception:
                        result = ""

                if result:
                    summary = result.strip()[:600]
                    self._respond_signal.emit(f"📄 {summary}")
                    self._tg_notify(
                        f"📄 <b>Аналіз документа: {_as.TelegramBotThread._html_escape(fname)}</b>\n\n"
                        f"{_as.TelegramBotThread._html_escape(summary)}")
                else:
                    self._respond_signal.emit("📄 Не вдалося проаналізувати документ")
            except Exception as e:
                self._respond_signal.emit(f"📄 Помилка: {str(e)[:60]}")

        threading.Thread(target=_analyze, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # URL SUMMARIZER — підсумок веб-сторінки
    # ═══════════════════════════════════════════════════════════

    def _handle_url_summary(self, lower: str, text: str) -> bool:
        """Підсумовує веб-сторінку за URL."""
        kw = ["підсумуй сторінку", "підсумуй сайт", "summarize url",
              "про що ця сторінка", "що на сайті", "summarize site",
              "підсумуй посилання", "читай url", "прочитай сайт"]
        url_found = re.search(r'https?://\S+', text)
        has_kw = any(k in lower for k in kw)
        if not url_found and not has_kw:
            return False
        if not url_found:
            self.respond("Скажіть URL після команди, наприклад: «підсумуй сторінку https://…»")
            return True
        url = url_found.group(0).rstrip(".,;")
        self.state = self.THINKING
        self.respond_silent(f"🌐 Завантажую {url[:50]}…")

        def _fetch_and_summarize():
            try:
                import urllib.request
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0 AXIS-OS/1.0"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    raw = r.read(300_000).decode("utf-8", errors="ignore")
                # Strip HTML tags
                clean = re.sub(r'<[^>]+>', ' ', raw)
                clean = re.sub(r'\s+', ' ', clean).strip()[:12000]
                if len(clean) < 100:
                    self._respond_signal.emit("🌐 Не вдалося прочитати вміст сторінки")
                    return
                prompt = (
                    f"Підсумуй вміст цієї веб-сторінки коротко (3-5 речень) українською:\n\n{clean}"
                )
                import queue as _q
                import aivon_sphere as _as
                _rq = _q.Queue()
                t = _as.AIThread(self.config, prompt)
                t.response.connect(lambda r: _rq.put(r))
                t.error.connect(lambda e: _rq.put(f"ERR:{e}"))
                t.start()
                t.wait(30000)
                try:
                    result = _rq.get_nowait()
                except Exception:
                    result = ""
                if result and not result.startswith("ERR:"):
                    self._respond_signal.emit(f"🌐 {result.strip()[:300]}")
                else:
                    self._respond_signal.emit("🌐 Не вдалося підсумувати")
            except Exception as e:
                self._respond_signal.emit(f"🌐 Помилка: {str(e)[:50]}")

        threading.Thread(target=_fetch_and_summarize, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # YOUTUBE SEARCH — пошук та запуск YouTube
    # ═══════════════════════════════════════════════════════════

    def _handle_youtube_search(self, lower: str, text: str) -> bool:
        """Пошук на YouTube або відкриття відео."""
        kw = ["знайди на ютубі", "відкрий ютуб", "шукай на ютубі",
              "youtube search", "find on youtube", "пошук ютуб",
              "включи ютуб", "відкрий відео", "знайди відео"]
        if not any(k in lower for k in kw):
            return False
        query = text
        for k in kw:
            if k in lower:
                idx = lower.find(k)
                q = text[idx + len(k):].strip()
                if q:
                    query = q
                break
        import urllib.parse
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        webbrowser.open(search_url)
        self.jarvis.play("confirm")
        self.respond_silent(f"▶️ YouTube: «{query[:50]}»")
        return True

    # ═══════════════════════════════════════════════════════════
    # APP CLOSE — закрити програму голосом
    # ═══════════════════════════════════════════════════════════

    def _handle_app_close(self, lower: str, text: str) -> bool:
        """Закрити програму голосом через psutil."""
        kw = ["закрий", "вбий процес", "kill", "зупини програму",
              "close app", "виключи", "заверши"]
        if not any(k in lower for k in kw):
            return False
        # Не заважаємо командам типу "закрий діалог", "закрий сферу"
        skip = ["діалог", "сферу", "панель", "вікно", "вкладку", "ютуб"]
        if any(s in lower for s in skip):
            return False
        if not HAS_PSUTIL:
            return False

        app_name = text
        for k in kw:
            if k in lower:
                idx = lower.find(k)
                cand = text[idx + len(k):].strip()
                if cand:
                    app_name = cand
                    break

        app_name_l = app_name.lower().strip()
        killed = []
        try:
            for proc in _psutil.process_iter(["pid", "name"]):
                pname = proc.info["name"].lower()
                if app_name_l in pname or pname.startswith(app_name_l[:4]):
                    # Не вбиваємо системні процеси
                    if pname not in ("explorer.exe", "svchost.exe",
                                     "system", "csrss.exe", "winlogon.exe"):
                        proc.terminate()
                        killed.append(proc.info["name"])
        except Exception:
            pass

        if killed:
            self.jarvis.play("confirm")
            self.respond_silent(f"💀 Закрито: {', '.join(set(killed))}")
        else:
            self.respond_silent(f"🔍 «{app_name[:30]}» не знайдено серед запущених")
        return True

    # ═══════════════════════════════════════════════════════════
    # TEMPERATURE — CPU / GPU температура
    # ═══════════════════════════════════════════════════════════

    def _handle_temperature_query(self, lower: str, text: str) -> bool:
        """Температура CPU та GPU."""
        kw = ["температура", "перегрів", "температуру пк",
              "cpu temperature", "gpu temperature", "скільки градусів",
              "гаряче пк", "нагрів процесора"]
        if not any(k in lower for k in kw):
            return False

        lines = ["🌡️ Температури:"]
        got_any = False

        if HAS_PSUTIL:
            try:
                temps = _psutil.sensors_temperatures()
                if temps:
                    for chip, entries in temps.items():
                        for entry in entries[:2]:
                            if entry.current and entry.current > 0:
                                icon = "🔥" if entry.current > 80 else "✅"
                                lines.append(f"{icon} {chip}/{entry.label or 'CPU'}: {entry.current:.0f}°C")
                                got_any = True
            except (AttributeError, Exception):
                pass

        # NVIDIA GPU через pynvml (якщо встановлено)
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
                icon = "🔥" if temp > 85 else "✅"
                lines.append(f"{icon} GPU ({name}): {temp}°C")
                got_any = True
        except Exception:
            pass

        if not got_any:
            # Fallback через WMI на Windows
            try:
                result = subprocess.run(
                    ["powershell", "-Command",
                     "Get-WmiObject MSAcpi_ThermalZoneTemperature "
                     "-Namespace root/wmi | "
                     "Select-Object -First 1 -ExpandProperty CurrentTemperature"],
                    capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW)
                if result.stdout.strip():
                    kelvin = int(result.stdout.strip()) / 10
                    celsius = kelvin - 273.15
                    icon = "🔥" if celsius > 80 else "✅"
                    lines.append(f"{icon} Thermal Zone: {celsius:.0f}°C")
                    got_any = True
            except Exception:
                pass

        if not got_any:
            self.respond_silent("🌡️ Не вдалося зчитати температуру (можливо потрібен pynvml)")
        else:
            msg = "\n".join(lines)
            self.respond_silent(msg[:200])
            self._tg_send(msg)
        return True
