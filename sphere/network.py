# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/network.py  –  Мережа: пошук, погода, новини                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Extracted from aivon_sphere.py                                             ║
║                                                                              ║
║  Thread classes:                                                             ║
║    PerplexitySearchThread(QThread)                                           ║
║    WeatherThread(QThread)                                                    ║
║    TavilySearchThread(QThread)                                               ║
║    SerperSearchThread(QThread)                                               ║
║                                                                              ║
║  Mixin class:                                                                ║
║    SphereNetworkMixin  – weather, search, Chrome history, document/URL,     ║
║                          location detection methods for AivonSphere          ║
╚══════════════════════════════════════════════════════════════════════════════╝

NOTE: All self.* accesses work via multiple inheritance (SphereNetworkMixin + AivonSphere).
"""

import os
import re
import threading
import webbrowser

from PyQt6.QtCore import QThread, pyqtSignal


# ═══════════════════════════════════════════════════════════
# PERPLEXITY SEARCH — Пошук з цитатами
# ═══════════════════════════════════════════════════════════

class PerplexitySearchThread(QThread):
    """Пошук через Perplexity sonar з цитатами та посиланнями"""
    response = pyqtSignal(str)
    citations = pyqtSignal(list)  # Список URL цитат
    error = pyqtSignal(str)

    _MAX_QUERY_LEN = 500  # prevent unbounded query strings

    def __init__(self, config, query, search_type="general"):
        super().__init__()
        self.config = config
        self.query = query[:self._MAX_QUERY_LEN]
        self.search_type = search_type  # general, news

    def run(self):
        try:
            import requests
            key = self.config.get("perplexity_key", "")
            if not key:
                self.error.emit("Perplexity ключ не знайдено")
                return

            system_msg = "Відповідай українською мовою, коротко та інформативно."
            if self.search_type == "news":
                system_msg = "Ти — новинний асистент. Дай останні новини по запиту. Відповідай українською, коротко. Обов'язково додай посилання."

            r = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": self.query}
                    ],
                    "max_tokens": 500,
                    "return_citations": True
                },
                timeout=20
            )

            if r.status_code == 200:
                try:
                    data = r.json()
                    text = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, ValueError) as parse_err:
                    self.error.emit(f"Perplexity: unexpected response ({parse_err})")
                    return
                cites = data.get("citations", [])
                self.response.emit(text)
                if cites:
                    self.citations.emit(cites)
            else:
                self.error.emit(f"Perplexity {r.status_code}")
        except Exception as e:
            self.error.emit(str(e)[:50])


# ═══════════════════════════════════════════════════════════
# OPENWEATHER — Погода з деталями
# ═══════════════════════════════════════════════════════════

class WeatherThread(QThread):
    """Погода через OpenWeather API — точні дані з температурою, вітром, вологістю"""
    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, api_key, city="Kyiv"):
        super().__init__()
        self.api_key = api_key
        self.city = city

    def run(self):
        try:
            import requests
            url = f"https://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.api_key}&units=metric&lang=uk"
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                try:
                    d = r.json()
                    temp = d["main"]["temp"]
                    feels = d["main"]["feels_like"]
                    desc = d["weather"][0]["description"]
                    humid = d["main"]["humidity"]
                    wind = d["wind"]["speed"]
                    city = d["name"]
                    text = f"🌤 {city}: {temp:.0f}°C (відчувається {feels:.0f}°C), {desc}, вітер {wind:.0f} м/с, вологість {humid}%"
                    self.result.emit(text)
                except (KeyError, IndexError, ValueError) as parse_err:
                    self.error.emit(f"OpenWeather: unexpected response ({parse_err})")
            else:
                self.error.emit(f"OpenWeather {r.status_code}")
        except Exception as e:
            self.error.emit(str(e)[:50])


# ═══════════════════════════════════════════════════════════
# TAVILY — AI-пошук з контекстом
# ═══════════════════════════════════════════════════════════

class TavilySearchThread(QThread):
    """Пошук через Tavily AI — повертає стислу відповідь + джерела"""
    result = pyqtSignal(str)
    sources = pyqtSignal(list)
    error = pyqtSignal(str)

    _MAX_QUERY_LEN = 500  # prevent unbounded query strings

    def __init__(self, api_key, query, max_results=3):
        super().__init__()
        self.api_key = api_key
        self.query = query[:self._MAX_QUERY_LEN]
        self.max_results = max_results

    def run(self):
        try:
            import requests
            r = requests.post("https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": self.query,
                    "search_depth": "basic",
                    "max_results": self.max_results,
                    "include_answer": True
                },
                timeout=15)
            if r.status_code == 200:
                data = r.json()
                answer = data.get("answer", "")
                results = data.get("results", [])
                if answer:
                    text = f"🔎 {answer}"
                elif results:
                    text = "🔎 " + " | ".join([r.get("title", "") for r in results[:3]])
                else:
                    text = "Нічого не знайдено"
                self.result.emit(text)
                urls = [r.get("url", "") for r in results if r.get("url")]
                if urls:
                    self.sources.emit(urls[:5])
            else:
                self.error.emit(f"Tavily {r.status_code}")
        except Exception as e:
            self.error.emit(str(e)[:50])


# ═══════════════════════════════════════════════════════════
# SERPER — Google Search API
# ═══════════════════════════════════════════════════════════

class SerperSearchThread(QThread):
    """Пошук через Serper (Google Search API) — топ результати"""
    result = pyqtSignal(str)
    sources = pyqtSignal(list)
    error = pyqtSignal(str)

    _MAX_QUERY_LEN = 500  # prevent unbounded query strings

    def __init__(self, api_key, query, num_results=3):
        super().__init__()
        self.api_key = api_key
        self.query = query[:self._MAX_QUERY_LEN]
        self.num_results = num_results

    def run(self):
        try:
            import requests
            r = requests.post("https://google.serper.dev/search",
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": self.query, "num": self.num_results, "hl": "uk"},
                timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Відповідь з knowledge graph або snippet
                kg = data.get("knowledgeGraph", {})
                answer_box = data.get("answerBox", {})
                organic = data.get("organic", [])

                if answer_box.get("answer"):
                    text = f"🌐 {answer_box['answer']}"
                elif answer_box.get("snippet"):
                    text = f"🌐 {answer_box['snippet']}"
                elif kg.get("description"):
                    text = f"🌐 {kg.get('title', '')}: {kg['description']}"
                elif organic:
                    snippets = [f"• {r.get('title','')}: {r.get('snippet','')}" for r in organic[:3]]
                    text = "🌐 " + "\n".join(snippets)
                else:
                    text = "Нічого не знайдено"

                self.result.emit(text)
                urls = [r.get("link", "") for r in organic if r.get("link")]
                if urls:
                    self.sources.emit(urls[:5])
            else:
                self.error.emit(f"Serper {r.status_code}")
        except Exception as e:
            self.error.emit(str(e)[:50])


# ═══════════════════════════════════════════════════════════
# SphereNetworkMixin — network/weather/search methods for AivonSphere
# ═══════════════════════════════════════════════════════════

class SphereNetworkMixin:
    """Network, weather, search and location methods. Mixed into AivonSphere."""

    # ── PERPLEXITY ПОШУК ──
    def _handle_search(self, lower, text):
        """Обробка пошукових запитів через Perplexity"""
        search_triggers = ["знайди інформацію", "пошук", "загугли", "що таке",
                          "розкажи про", "хто такий", "хто така", "що означає",
                          "search for", "look up", "find info"]
        news_triggers = ["новини", "останні новини", "що нового у світі",
                        "news", "останні події", "що відбувається"]

        is_search = any(t in lower for t in search_triggers)
        is_news = any(t in lower for t in news_triggers)

        if not is_search and not is_news:
            return False

        # Витягти запит (до перевірки ключа — потрібен в обох гілках)
        query = text
        for trigger in search_triggers + news_triggers:
            if trigger in lower:
                idx = lower.find(trigger)
                after = text[idx + len(trigger):].strip()
                if after:
                    query = after
                break

        key = self.config.get("perplexity_key", "")
        if not key:
            # Немає Perplexity → DDG без API ключа
            self.state = self.THINKING
            self.response_text = "🌐 Шукаю..."
            self.jarvis.play("loading")
            import threading as _thr
            from aivon_sphere import AIThread
            _q = query
            _thr.Thread(target=lambda: self.respond(AIThread._web_search(_q)[:300]),
                        daemon=True).start()
            return True

        search_type = "news" if is_news else "general"
        self.perplexity_thread = PerplexitySearchThread(self.config, query, search_type)
        self.perplexity_thread.response.connect(self._on_search_result)
        self.perplexity_thread.citations.connect(self._on_search_citations)
        self.perplexity_thread.error.connect(lambda e: self.respond(f"⚠️ Помилка пошуку: {e}"))
        self.perplexity_thread.start()
        return True

    def _on_search_result(self, text):
        """Результат пошуку Perplexity"""
        self.jarvis.play("done")
        self.respond(text[:200])

    def _on_search_citations(self, urls):
        """Відкрити перше посилання з цитат"""
        if urls:
            try:
                webbrowser.open(urls[0])
                print(f"Opened citation: {urls[0]}")
            except Exception:
                pass

    # ── Chrome History reader ─────────────────────────────────────────────────

    @staticmethod
    def _get_chrome_history(limit: int = 15, search: str = "") -> list:
        """Read Chrome browsing history from SQLite DB.

        Chrome locks the file while running → we copy to temp first.
        Returns list of {title, url, visited} sorted by most recent.
        """
        import os, shutil, tempfile, sqlite3
        from datetime import datetime, timedelta

        db_path = os.path.expandvars(
            r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\History")
        if not os.path.exists(db_path):
            return []

        # Copy to temp — Chrome keeps the file locked
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            shutil.copy2(db_path, tmp)
            conn = sqlite3.connect(tmp)
            cur  = conn.cursor()

            # Chrome epoch: microseconds since 1601-01-01
            _epoch = datetime(1601, 1, 1)

            if search:
                cur.execute("""
                    SELECT urls.title, urls.url, urls.last_visit_time
                    FROM urls
                    WHERE (urls.title LIKE ? OR urls.url LIKE ?)
                    ORDER BY urls.last_visit_time DESC
                    LIMIT ?
                """, (f"%{search}%", f"%{search}%", limit))
            else:
                cur.execute("""
                    SELECT title, url, last_visit_time
                    FROM urls
                    ORDER BY last_visit_time DESC
                    LIMIT ?
                """, (limit,))

            rows = cur.fetchall()
            conn.close()

            result = []
            for title, url, ts in rows:
                visited = _epoch + timedelta(microseconds=ts)
                result.append({
                    "title":   title or url,
                    "url":     url,
                    "visited": visited.strftime("%d.%m %H:%M"),
                })
            return result
        except Exception as e:
            print(f"[Chrome History] {e}")
            return []
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    def _handle_chrome_history_query(self, lower: str, text: str) -> bool:
        """Handle voice queries about Chrome history.

        Commands:
          "що я останнє дивився/читав/відкривав"
          "що я дивився вчора/сьогодні"
          "відкрий останній сайт"
          "відкрий останнє відео"
          "знайди в историї Netflix/YouTube/…"
          "розкажи мою историю"
        """
        _TRIGGERS = [
            "що я останнє", "що я дивився", "що я читав", "що я відкривав",
            "що я переглядав", "останні сайти", "останні сторінки",
            "відкрий останній сайт", "відкрий останню сторінку",
            "відкрий останнє відео", "розкажи мою историю",
            "що я дивився вчора", "що я дивився сьогодні",
            "знайди в историї", "пошукай в историї",
            "покажи историю", "моя история", "останні відвідані",
        ]
        if not any(t in lower for t in _TRIGGERS):
            return False

        # Extract search term if present
        search = ""
        for marker in ("знайди в историї", "пошукай в историї"):
            if marker in lower:
                search = lower.split(marker, 1)[-1].strip()
                break

        # Handle "відкрий останній сайт/відео" — open it directly
        if any(k in lower for k in ("відкрий останній", "відкрий останню", "відкрий останнє")):
            items = self._get_chrome_history(limit=5)
            if items:
                top = items[0]
                self._open_chrome_url(top["url"],
                    f"🌐 Відкриваю: {top['title'][:60]}")
            else:
                self.respond("Не вдалось прочитати историю Chrome")
            return True

        # Fetch and speak recent history
        self.state = self.THINKING
        self.response_text = "🔍 Читаю историю..."
        self.update()

        def _fetch():
            items = self._get_chrome_history(limit=8, search=search)
            if not items:
                self._respond_signal.emit("История Chrome порожня або недоступна")
                return

            # Build a short spoken summary
            lines = []
            for i, it in enumerate(items[:5], 1):
                title = it["title"]
                lines.append(f"{i}. {title[:50]} ({it['visited']})")
            summary = "🌐 Останні сайти:\n" + "\n".join(lines)
            self._respond_signal.emit(summary[:300])

        threading.Thread(target=_fetch, daemon=True).start()
        return True

    # ── Геолокація та погода ──────────────────────────────────────────────────

    def _detect_location_device(self):
        """Визначити координати через Windows Location API (GPS/WiFi/мережа)"""
        try:
            import subprocess
            import sys
            _NO_WINDOW = __import__('subprocess').CREATE_NO_WINDOW if sys.platform == "win32" else 0
            ps_script = r"""
Add-Type -AssemblyName System.Device
$w = New-Object System.Device.Location.GeoCoordinateWatcher('High')
$w.Start()
$t = 0
while (($w.Status -ne 'Ready') -and ($t -lt 40)) {
    Start-Sleep -Milliseconds 500
    $t++
}
$c = $w.Position.Location
if (!$c.IsUnknown) {
    Write-Output "$($c.Latitude),$($c.Longitude)"
} else {
    Write-Output "UNKNOWN"
}
$w.Stop()
"""
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=25,
                creationflags=_NO_WINDOW
            )
            out = result.stdout.strip()
            if out and out != "UNKNOWN" and "," in out:
                parts = out.split(",")
                return (float(parts[0]), float(parts[1]))
        except Exception:
            pass
        return (None, None)

    def _reverse_geocode(self, lat, lon):
        """Отримати назву міста по координатах через OpenWeather"""
        try:
            import requests
            ow_key = self.config.get("openweather_key", "")
            if ow_key:
                url = f"https://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={lon}&limit=1&appid={ow_key}"
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    if data and len(data) > 0:
                        return data[0].get("name", "")
        except Exception:
            pass
        return ""

    def _detect_city_by_ip(self):
        """Fallback: визначити місто по IP (ip-api.com → ipinfo.io)"""
        try:
            import requests
            r = requests.get("https://ip-api.com/json/?fields=city,country,lat,lon", timeout=4)
            if r.status_code == 200:
                d = r.json()
                if d.get("city"):
                    return d["city"]
        except Exception:
            pass
        try:
            import requests
            r = requests.get("https://ipinfo.io/json", timeout=4)
            if r.status_code == 200:
                d = r.json()
                if d.get("city"):
                    return d["city"]
        except Exception:
            pass
        return ""

    def _get_weather_city_auto(self):
        """Отримати місто: конфіг → GPS пристрою → IP → Kyiv"""
        from aivon_sphere import save_config
        city = self.config.get("weather_city", "")
        if city:
            return city
        lat, lon = self._detect_location_device()
        if lat is not None and lon is not None:
            self.config["weather_lat"] = lat
            self.config["weather_lon"] = lon
            city = self._reverse_geocode(lat, lon)
            if city:
                self.config["weather_city"] = city
                save_config(self.config)
                return city
        detected = self._detect_city_by_ip()
        if detected:
            self.config["weather_city"] = detected
            save_config(self.config)
            return detected
        return "Kyiv"

    # ── DOCUMENT ANALYSIS ──────────────────────────────────────────────────────

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
                from aivon_sphere import AIThread, load_config, TelegramBotThread
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
                cfg   = load_config()
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
                t = AIThread(cfg, prompt)
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
                        f"📄 <b>Аналіз документа: {TelegramBotThread._html_escape(fname)}</b>\n\n"
                        f"{TelegramBotThread._html_escape(summary)}")
                else:
                    self._respond_signal.emit("📄 Не вдалося проаналізувати документ")
            except Exception as e:
                self._respond_signal.emit(f"📄 Помилка: {str(e)[:60]}")

        threading.Thread(target=_analyze, daemon=True).start()
        return True

    # ── URL SUMMARIZER ────────────────────────────────────────────────────────

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
                from aivon_sphere import AIThread
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
                _rq = _q.Queue()
                t = AIThread(self.config, prompt)
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
