# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/commands.py  –  Диспетчер голосових команд (з aivon_sphere.py)     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Перенесено з aivon_sphere.py:                                               ║
║    _looks_like_command()       рядок 8235                                    ║
║    _handle_jarvis_commands()   рядок 8280                                    ║
║    _create_command_from_voice() рядок 9133                                   ║
║    execute_command()           рядок 11780                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

# Network search / weather threads (defined in sphere/network.py)
try:
    from sphere.network import WeatherThread, TavilySearchThread, SerperSearchThread
except ImportError:
    WeatherThread = None       # type: ignore
    TavilySearchThread = None  # type: ignore
    SerperSearchThread = None  # type: ignore

# _NO_WINDOW constant — re-declare locally so methods don't need aivon_sphere scope
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _get_aivon_module():
    """Return the aivon_sphere module without triggering a circular import."""
    import sys as _sys
    return _sys.modules.get("aivon_sphere") or _sys.modules.get("__main__")


def _lazy_find_steam_game(query, games=None):
    """Lazy proxy for aivon_sphere.find_steam_game."""
    mod = _get_aivon_module()
    if mod and hasattr(mod, "find_steam_game"):
        return mod.find_steam_game(query, games)
    return None


def _lazy_load_sphere_config():
    """Lazy proxy for aivon_sphere.load_sphere_config."""
    mod = _get_aivon_module()
    if mod and hasattr(mod, "load_sphere_config"):
        return mod.load_sphere_config()
    return {}


def _lazy_save_sphere_config(data):
    """Lazy proxy for aivon_sphere.save_sphere_config."""
    mod = _get_aivon_module()
    if mod and hasattr(mod, "save_sphere_config"):
        mod.save_sphere_config(data)


def _lazy_load_config():
    """Lazy proxy for aivon_sphere.load_config."""
    mod = _get_aivon_module()
    if mod and hasattr(mod, "load_config"):
        return mod.load_config()
    return {}


def _lazy_commands_file():
    """Lazy proxy for aivon_sphere.COMMANDS_FILE."""
    mod = _get_aivon_module()
    if mod and hasattr(mod, "COMMANDS_FILE"):
        return mod.COMMANDS_FILE
    # Fallback: derive path from USER_DATA_DIR convention
    return Path(os.path.expanduser("~")) / ".aivon" / "data" / "commands.json"


class SphereCommandsMixin:
    """Mixin: голосовий диспетчер команд для AivonSphere."""

    def _looks_like_command(self, lower):
        """Швидка локальна перевірка — чи це КОМАНДА (дія) чи ДІАЛОГ (розмова).
        Anthropic викликається ТІЛЬКИ для команд. Діалог іде одразу до GPT.
        """
        # Ключові слова дій — ознаки команди
        CMD_KEYWORDS = [
            # Відкрити/запустити
            "відкрий", "открой", "запусти", "запустити", "open", "launch", "run",
            # Пошук
            "знайди", "найди", "шукай", "search", "find", "загугли", "погугли",
            # Генерація
            "згенеруй", "намалюй", "створи", "generate", "create", "draw",
            # Система
            "вимкни", "увімкни", "виключи", "включи", "перезапусти", "restart",
            "гучність", "громкость", "volume", "скріншот", "screenshot",
            # Навігація
            "перейди", "зайди на", "покажи", "go to", "show",
            # Таймер/нагадування
            "таймер", "timer", "нагадай", "напомни", "remind",
            # Переклад
            "переклади", "переведи", "translate",
            # Погода
            "погода", "weather", "температура",
            # Музика
            "включи музику", "поставь", "play music", "next song", "наступна пісня",
            # Відео
            "запиши відео", "record video",
        ]
        for kw in CMD_KEYWORDS:
            if kw in lower:
                return True

        # Короткі фрази (< 4 слова) з дієсловами — скоріше команди
        words = lower.split()
        if len(words) <= 3:
            ACTION_VERBS = ["відкрий", "открой", "запусти", "знайди", "найди",
                           "покажи", "вимкни", "включи", "закрий", "поставь"]
            if words and words[0] in ACTION_VERBS:
                return True

        # Все інше — діалог (питання, розмова, обговорення)
        return False

    # ── НОВІ ГОЛОСОВІ КОМАНДИ ──
    # │  ДИСПЕТЧЕР КОМАНД: головна функція розбору голосових команд             │
    def _handle_jarvis_commands(self, lower):
        """Обробка нових голосових команд з JARVIS звуками"""

        # "Сховайся" / "Стоп" / "Тихо" — тихий режим
        if any(p in lower for p in ["сховайся", "стоп", "тихо", "помовч", "замовкни", "hide", "stop listening"]):
            self.jarvis.play("confirm")
            self.respond_silent("До зустрічі! Скажіть 'Aivon' коли буду потрібен.")
            self.continuous_listen = False
            QTimer.singleShot(2000, self.hide_orb)
            return True

        # "Ти тут?" / "Ти здесь?" — перевірка присутності
        if any(p in lower for p in ["ти тут", "ти здесь", "ты тут", "ты здесь", "are you here", "are you there"]):
            self.hologram_gesture('wave', 2)
            self.jarvis.play("ready")
            self.respond("Завжди до ваших послуг!")
            return True

        # "Дякую" / "Спасибо" / "Молодець"
        if any(p in lower for p in ["дякую", "спасибо", "спасібо", "молодець", "thank"]):
            self.hologram_gesture('nod', 2)
            self.jarvis.play("ready")
            self.respond("Завжди радий допомогти!")
            return True

        # "Давай поговоримо" — обробляється в on_recognized (вхід в діалог)

        # "Доброго ранку/вечора/ночі"
        if any(p in lower for p in ["доброго ранку", "добрий ранок", "доброе утро", "good morning"]):
            self.hologram_gesture('wave', 3)
            self.jarvis.play_file("Доброе утро.wav")
            self.respond("Доброго ранку! Чим можу допомогти?")
            return True
        if any(p in lower for p in ["добрий вечір", "добрый вечер", "good evening"]):
            self.hologram_gesture('wave', 3)
            self.jarvis.play_file("Добрый вечер.wav")
            self.respond("Добрий вечір!")
            return True
        if any(p in lower for p in ["на добраніч", "доброї ночі", "спокойной ночи", "good night"]):
            self.jarvis.play_file("Доброй ночи сэр.wav")
            self.respond("На добраніч!")
            self.continuous_listen = False
            QTimer.singleShot(2500, self.hide_orb)
            return True

        # "Що нового?" / "Статус"
        if any(p in lower for p in ["що нового", "статус системи", "system status", "що відбувається"]):
            self.jarvis.play("science")
            hour = datetime.now().hour
            greeting = "ранок" if hour < 12 else "день" if hour < 18 else "вечір"
            apps_count = len(self.app_launcher.apps)
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=0.3)
                ram = psutil.virtual_memory().percent
                sys_info = f" CPU {cpu:.0f}%, RAM {ram:.0f}%."
            except Exception:
                sys_info = ""
            self.respond_silent(f"Добрий {greeting}! Система працює. {apps_count} додатків.{sys_info}")
            return True

        # ── Matrix: голосові команди для агентів ──
        # "Запусти агента юриста / секретаря / розробника / системщика"
        agent_voice_map = {
            "юрист": "lawyer", "адвокат": "lawyer", "lawyer": "lawyer",
            "секретар": "secretary", "secretary": "secretary",
            "розробник": "developer", "кодер": "developer", "developer": "developer",
            "системщик": "system", "сисадмін": "system", "system": "system",
            "пошт": "gmail", "gmail": "gmail", "email": "gmail", "mail": "gmail",
            "календар": "calendar", "calendar": "calendar", "розклад": "calendar",
            "прибиральник": "cleaner", "cleaner": "cleaner", "очисти систему": "cleaner",
            "оптимізатор": "optimizer", "optimizer": "optimizer",
            "охоронець": "guardian", "guardian": "guardian",
        }
        # "Запусти агента [назва]" або "Агент [назва], [задача]"
        agent_match = re.search(r'(?:запусти агент[аи]?\s+|агент\s+)([\w\sа-яґєіїё]+?)(?:\s*,\s*(.+))?$', lower)
        if agent_match:
            agent_name_raw = agent_match.group(1).strip()
            task_text = agent_match.group(2) or ""
            agent_id = None
            for key, aid in agent_voice_map.items():
                if key in agent_name_raw:
                    agent_id = aid
                    break
            if agent_id:
                self.jarvis.play("science")
                self._agent_color = None
                self._agent_name = agent_id
                self.respond_silent(f"🤖 {self._agent_name} працює...")
                # Через IPC або Orchestrator
                if self._orchestrator and agent_id in self._orchestrator.agents:
                    def _on_agent_done(result):
                        if result.get("ok"):
                            self._respond_signal.emit(result.get("response", "Готово")[:300])
                        else:
                            self._respond_signal.emit(f"⚠️ {result.get('error', 'Помилка')[:150]}")
                    real_task = task_text if task_text else f"Допоможи з: {agent_name_raw}"
                    def _run_agent():
                        ctx = self._orchestrator.memory.get_context_text(5)
                        res = self._orchestrator.agents[agent_id].execute(real_task, ctx)
                        self._orchestrator.memory.add_message("user", real_task, agent_id)
                        resp = res.get("response", "")
                        if resp:
                            self._orchestrator.memory.add_message("assistant", resp[:500], agent_id)
                        _on_agent_done(res)
                    threading.Thread(target=_run_agent, daemon=True).start()
                else:
                    # Немає оркестратора — пряме AI питання
                    real_task = task_text if task_text else agent_name_raw
                    self.ask_ai(real_task)
                return True

        # "Створи макрос [опис]"
        macro_create_match = re.search(r'(?:створи|зроби|create)\s+макрос\s+(.+)', lower)
        if macro_create_match:
            desc = macro_create_match.group(1).strip()
            self.jarvis.play("science")
            self.respond_silent(f"🔨 Макрос '{desc[:50]}' — відкрийте Панель AXIS OS → Команди")
            return True

        if any(p in lower for p in ["перевір пошту", "нова пошта", "check mail", "check email", "що в пошті",
                                     "покажи пошту", "є нові листи", "нові листи"]):
            self.respond_silent("📧 Відкриваю Gmail...")
            import webbrowser
            webbrowser.open("https://gmail.com")
            return True

        if any(p in lower for p in ["що в календарі", "розклад на сьогодні", "мої події", "calendar",
                                     "що на завтра", "покажи календар", "які події", "розклад на тиждень"]):
            self.respond_silent("📅 Відкриваю календар...")
            import webbrowser
            webbrowser.open("https://calendar.google.com")
            return True

        if any(p in lower for p in ["що важливого", "що важливе", "що пропустив", "дай зведення",
                                     "important", "що нового в google", "перевір все"]):
            self.ask_ai(text)
            return True

        send_match = re.search(r'(?:відправ|надішл|напиши лист|send|пошли)\s+(.+)', lower)
        if send_match:
            full_task = send_match.group(1).strip()
            self.respond_silent(f"📧 Відкриваю Gmail для: {full_task[:40]}...")
            import webbrowser
            webbrowser.open("https://mail.google.com/mail/u/0/#compose")
            return True

        # "Створи подію [опис]" — через голос
        event_match = re.search(r'(?:створи подію|додай подію|запланувати|додай в календар|add event)\s+(.+)', lower)
        if event_match:
            self.jarvis.play("science")
            self._agent_color = "#a855f7"
            self._agent_name = "Календар"
            event_desc = event_match.group(1).strip()
            self.respond_silent(f"📅 Створюю подію: {event_desc[:50]}...")
            def _create_event():
                import webbrowser
                webbrowser.open("https://calendar.google.com/calendar/r/eventedit")
                self._respond_signal.emit(f"📅 Відкриваю Google Calendar для створення події: {event_desc[:60]}")
            threading.Thread(target=_create_event, daemon=True).start()
            return True

        # "Запусти макрос [ім'я]"
        macro_run_match = re.search(r'(?:запусти|run)\s+макрос\s+(.+)', lower)
        if macro_run_match:
            macro_name = macro_run_match.group(1).strip()
            macro = self.macro_engine.find_macro(macro_name)
            if macro:
                self.jarvis.play("confirm")
                self.respond_silent(f"⚡ {macro.get('name', macro_name)}")
                self.macro_engine.execute(macro, speak_callback=self.respond_silent)
            else:
                self.respond_silent(f"⚠️ Макрос '{macro_name}' не знайдено")
            return True

        # ── Гучність голосом ──
        _NO_WINDOW = subprocess.CREATE_NO_WINDOW if __import__('sys').platform == "win32" else 0
        vol_match = re.search(r'(?:гучність|volume|звук)\s*(\d+)', lower)
        if vol_match:
            level = min(100, max(0, int(vol_match.group(1))))
            try:
                subprocess.run(
                    ['powershell', '-Command',
                     f'$obj = new-object -com wscript.shell; '
                     f'for($i=0;$i -lt 50;$i++){{$obj.SendKeys([char]174)}}; '
                     f'for($i=0;$i -lt {level // 2};$i++){{$obj.SendKeys([char]175)}}'],
                    capture_output=True, timeout=5, creationflags=_NO_WINDOW)
                self.jarvis.play("confirm")
                self.respond_silent(f"Гучність встановлено на {level}%")
            except Exception:
                self.respond_silent(f"Гучність: {level}%")
            return True
        if any(p in lower for p in ["тихіше", "тише", "quieter", "volume down"]):
            try:
                subprocess.Popen(['powershell', '-Command',
                    'for($i=0;$i -lt 5;$i++){(new-object -com wscript.shell).SendKeys([char]174)}'],
                    creationflags=_NO_WINDOW)
            except Exception: pass
            self.respond_silent("Тихіше!")
            return True
        if any(p in lower for p in ["гучніше", "громче", "louder", "volume up"]):
            try:
                subprocess.Popen(['powershell', '-Command',
                    'for($i=0;$i -lt 5;$i++){(new-object -com wscript.shell).SendKeys([char]175)}'],
                    creationflags=_NO_WINDOW)
            except Exception: pass
            self.respond_silent("Гучніше!")
            return True
        if any(p in lower for p in ["без звуку", "mute", "замовкни", "тихо"]):
            try:
                subprocess.Popen(['powershell', '-Command',
                    '(new-object -com wscript.shell).SendKeys([char]173)'],
                    creationflags=_NO_WINDOW)
            except Exception: pass
            self.respond_silent("Звук вимкнено")
            return True

        # ── Батарея ──
        if any(p in lower for p in ["батарея", "заряд", "battery", "скільки заряду"]):
            try:
                import psutil
                bat = psutil.sensors_battery()
                if bat:
                    pct = bat.percent
                    plug = "на зарядці" if bat.power_plugged else "від батареї"
                    self.respond_silent(f"🔋 Заряд: {pct}%, {plug}")
                else:
                    self.respond_silent("Батарея не знайдена (десктоп)")
            except Exception:
                self.respond_silent("Не вдалось перевірити батарею")
            return True

        # ── Скріншот ──
        if any(p in lower for p in ["скріншот", "screenshot", "знімок екрану", "скрін"]):
            try:
                from PIL import ImageGrab
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(os.path.expanduser("~"), "Desktop", f"screenshot_{timestamp}.png")
                img = ImageGrab.grab()
                img.save(path)
                self.jarvis.play("confirm")
                self.respond_silent("Скріншот збережено на робочий стіл!")
            except ImportError:
                self.respond_silent("Встановіть Pillow: pip install Pillow")
            except Exception as e:
                self.respond_silent(f"Помилка скріншоту: {str(e)[:30]}")
            return True

        # ── Калькулятор ──
        calc_match = re.search(r'(?:порахуй|calculate|скільки буде|калькулятор)\s+(.+)', lower)
        if calc_match:
            expr = calc_match.group(1).strip()
            # Простий безпечний обчислювач
            expr_safe = expr.replace('х', '*').replace('×', '*').replace('÷', '/').replace(',', '.')
            expr_safe = re.sub(r'[^0-9+\-*/.() ]', '', expr_safe)
            try:
                result = eval(expr_safe, {"__builtins__": {}})  # ізольований namespace
                self.jarvis.play("confirm")
                self.respond_silent(f"🧮 {expr} = {result}")
            except Exception:
                self.respond_silent(f"Не вдалось обчислити: {expr}")
            return True

        # ── Час / Дата ──
        if any(p in lower for p in ["котра година", "який час", "what time", "скільки часу"]):
            now = datetime.now()
            self.respond_silent(f"🕐 Зараз {now.strftime('%H:%M')}")
            return True
        if any(p in lower for p in ["яка дата", "який сьогодні день", "what date", "яке число"]):
            now = datetime.now()
            days = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
            self.respond_silent(f"📅 {days[now.weekday()]}, {now.strftime('%d.%m.%Y')}")
            return True

        # ── Вимкни монітор ──
        if any(p in lower for p in ["вимкни монітор", "вимкнути монітор", "monitor off", "екран вимкни"]):
            self.jarvis.play("monitor_off")
            self.respond_silent("Вимикаю монітор...")
            QTimer.singleShot(1500, lambda: subprocess.Popen(
                ['powershell', '-Command',
                 '(Add-Type \'[DllImport("user32.dll")]public static extern int SendMessage(int h,int m,int w,int l);\' -Name a -Pas)::SendMessage(-1,0x0112,0xF170,2)'],
                creationflags=_NO_WINDOW))
            return True

        # ── Таймер ──
        timer_match = re.search(r'(?:таймер|timer|нагадай|поставь таймер)\s*(?:на|через|in)?\s*(\d+)\s*(?:хв|хвилин|мин|минут|min|minutes?|сек|секунд|sec|seconds?)?', lower)
        if timer_match:
            amount = int(timer_match.group(1))
            # Визначити одиницю
            if any(w in lower for w in ["сек", "sec"]):
                ms = amount * 1000
                unit = "секунд"
            else:
                ms = amount * 60 * 1000
                unit = "хвилин"
            self.jarvis.play("confirm")
            self.respond_silent(f"⏱ Таймер на {amount} {unit}!")
            QTimer.singleShot(ms, self._timer_done)
            return True

        # ── Погода (OpenWeather API) ──
        if any(p in lower for p in ["погода", "weather", "яка погода", "температура"]):
            ow_key = self.config.get("openweather_key", "")
            if ow_key:
                # Визначаємо місто з запиту або конфігу або GPS пристрою
                city = self._get_weather_city_auto()
                for w in ["погода в ", "погода у ", "weather in ", "температура в ", "температура у "]:
                    if w in lower:
                        city = lower.split(w, 1)[1].strip().title()
                        break
                self.state = self.THINKING
                self.response_text = "🌤 Перевіряю погоду..."
                if hasattr(self, '_weather_thread') and self._weather_thread is not None:
                    try:
                        self._weather_thread.result.disconnect()
                        self._weather_thread.error.disconnect()
                    except Exception:
                        pass
                self._weather_thread = WeatherThread(ow_key, city)
                self._weather_thread.result.connect(lambda t: self.respond(t))
                self._weather_thread.error.connect(lambda e: self.respond(f"⚠️ Погода: {e}"))
                self._weather_thread.start()
            else:
                try:
                    import urllib.request
                    url = "https://wttr.in/?format=%t+%C&lang=uk"
                    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
                    with urllib.request.urlopen(req, timeout=5) as r:
                        weather = r.read().decode("utf-8").strip()
                    self.respond_silent(f"🌤 Погода: {weather}")
                except Exception:
                    self.respond_silent("Не вдалось отримати погоду")
            return True

        # ── Пошук (Tavily / Serper) ──
        if any(p in lower for p in ["знайди", "пошук", "загугли", "search", "що таке", "хто такий", "хто така"]):
            query = lower
            for prefix in ["знайди ", "пошук ", "загугли ", "search ", "що таке ", "хто такий ", "хто така "]:
                if lower.startswith(prefix):
                    query = lower[len(prefix):].strip()
                    break
            tavily_key = self.config.get("tavily_key", "")
            serper_key = self.config.get("serper_key", "")
            if tavily_key:
                self.state = self.THINKING
                self.response_text = "🔎 Шукаю..."
                if hasattr(self, '_search_thread') and self._search_thread is not None:
                    try:
                        self._search_thread.result.disconnect()
                        self._search_thread.error.disconnect()
                    except Exception:
                        pass
                self._search_thread = TavilySearchThread(tavily_key, query)
                self._search_thread.result.connect(lambda t: self.respond(t))
                self._search_thread.sources.connect(lambda s: print(f"[Search] Sources: {s}"))
                self._search_thread.error.connect(lambda e: self.respond(f"⚠️ Пошук: {e}"))
                self._search_thread.start()
            elif serper_key:
                self.state = self.THINKING
                self.response_text = "🌐 Шукаю в Google..."
                if hasattr(self, '_search_thread') and self._search_thread is not None:
                    try:
                        self._search_thread.result.disconnect()
                        self._search_thread.error.disconnect()
                    except Exception:
                        pass
                self._search_thread = SerperSearchThread(serper_key, query)
                self._search_thread.result.connect(lambda t: self.respond(t))
                self._search_thread.sources.connect(lambda s: print(f"[Search] Sources: {s}"))
                self._search_thread.error.connect(lambda e: self.respond(f"⚠️ Пошук: {e}"))
                self._search_thread.start()
            else:
                # Немає зовнішнього пошуку → AI function calling сам знайде
                return False
            return True

        # ── Системний моніторинг голосом ──
        if any(p in lower for p in ["системний моніторинг", "стан системи", "cpu", "процесор", "оперативна пам'ять", "ram", "диск"]):
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=0.5)
                ram = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                self.jarvis.play("science")
                self.respond_silent(
                    f"💻 Система:\n"
                    f"CPU: {cpu}%\n"
                    f"RAM: {ram.percent}% ({ram.used // (1024**3)}/{ram.total // (1024**3)} GB)\n"
                    f"Диск: {disk.percent}% ({disk.used // (1024**3)}/{disk.total // (1024**3)} GB)"
                )
            except ImportError:
                self.respond_silent("Встановіть psutil: pip install psutil")
            except Exception as e:
                self.respond_silent(f"Помилка: {str(e)[:40]}")
            return True

        # ── Uptime — скільки працює ПК ──
        if any(p in lower for p in ["скільки працює", "uptime", "аптайм", "скільки комп працює", "час роботи", "скільки працюю", "як довго працює"]):
            try:
                import psutil
                import time
                uptime_sec = time.time() - psutil.boot_time()
                hours = int(uptime_sec // 3600)
                mins = int((uptime_sec % 3600) // 60)
                self.jarvis.play("science")
                if hours == 0:
                    self.respond_silent(f"⏱ Комп'ютер працює {mins} хвилин.")
                elif hours < 3:
                    self.respond_silent(f"⏱ Комп'ютер працює {hours} год {mins} хв. Все добре, працюйте далі!")
                elif hours < 5:
                    self.respond_silent(f"⏱ Вже {hours} год {mins} хв. Може, час для перерви?")
                else:
                    self.respond_silent(f"⏱ Вже {hours} год {mins} хв! Сер, це забагато. Рекомендую відпочити.")
            except Exception:
                self.respond_silent("Не вдалося визначити час роботи")
            return True

        # ── Звіт дня ──
        if any(p in lower for p in ["звіт дня", "звіт за день", "daily report", "підсумок дня", "як пройшов день"]):
            now = datetime.now()
            hour = now.hour
            period = "ранок" if hour < 12 else "день" if hour < 18 else "вечір"
            reminders_count = len(self.reminders)
            recurring_count = sum(
                1 for e in self.reminders
                if isinstance(e[1], dict) and e[1].get("repeat")
            )
            apps_count = len(self.app_launcher.apps)
            mode_str = getattr(self, '_mode', 'normal')
            report = (
                f"📊 Звіт дня — {now.strftime('%d.%m.%Y %H:%M')}\n"
                f"Добрий {period}! Зараз {now.strftime('%H:%M')}.\n"
                f"Система працює стабільно.\n"
                f"Режим: {mode_str}.\n"
                f"Знайдено {apps_count} додатків.\n"
                f"Активних нагадувань: {reminders_count} (🔄 {recurring_count} повторюваних)."
            )
            self.jarvis.play("science")
            self.respond_silent(report)
            return True

        # ── Переклад ──
        translate_match = re.search(r'(?:переклади|translate|переведи)\s+(.+)', lower)
        if translate_match:
            phrase = translate_match.group(1).strip()
            # Використовуємо AI для перекладу
            self.ask_ai(f"Переклади на англійську (тільки переклад, без пояснень): {phrase}")
            return True

        # ── Персонажі JARVIS/FRIDAY ──
        if any(p in lower for p in ["режим джарвіс", "mode jarvis", "будь джарвіс", "jarvis mode"]):
            self.config["personality"] = "jarvis"
            self.jarvis.play("ready")
            self.respond("Режим JARVIS активовано. До ваших послуг, сер.")
            return True
        if any(p in lower for p in ["режим фрайдей", "mode friday", "будь фрайдей", "friday mode"]):
            self.config["personality"] = "friday"
            self.jarvis.play("ready")
            self.respond("Режим F.R.I.D.A.Y. активовано. Чим можу допомогти?")
            return True
        if any(p in lower for p in ["режим ультрон", "mode ultron", "ultron mode"]):
            self.config["personality"] = "ultron"
            self.jarvis.play("science")
            self.respond("Режим ULTRON. Немає ниток... на маріонетці.")
            return True

        # ── Автоматизації ──
        if any(p in lower for p in ["покажи автоматизації", "список автоматизацій", "automations", "мої автоматизації"]):
            automations = self.config.get("automations", [])
            if not automations:
                self.respond("📋 Автоматизацій немає. Додайте в sphere_config.json.")
            else:
                lines = []
                for a in automations:
                    enabled = "✅" if a.get("enabled", True) else "❌"
                    trigger = a.get("trigger", {})
                    t_type = trigger.get("type", "?")
                    t_info = trigger.get("app") or trigger.get("time") or trigger.get("phrase") or ""
                    n_actions = len(a.get("actions", []))
                    lines.append(f"{enabled} {a.get('name','?')} [{t_type}: {t_info}] → {n_actions} дій")
                self.respond("🔧 Автоматизації:\n" + "\n".join(lines))
            return True

        # Вимкнути автоматизацію по імені
        disable_auto_m = re.search(r'(?:вимкни|disable)\s+автоматизацію\s+(.+)', lower)
        if disable_auto_m:
            target_name = disable_auto_m.group(1).strip()
            automations = self.config.get("automations", [])
            found = False
            for a in automations:
                if target_name.lower() in a.get("name", "").lower():
                    a["enabled"] = False
                    found = True
            if found:
                try:
                    _lazy_save_sphere_config({"automations": automations})
                    self.config["automations"] = automations
                except Exception:
                    pass
                self.jarvis.play("confirm")
                self.respond(f"❌ Автоматизацію '{target_name}' вимкнено.")
            else:
                self.respond(f"⚠️ Автоматизацію '{target_name}' не знайдено.")
            return True

        # Увімкнути автоматизацію по імені
        enable_auto_m = re.search(r'(?:увімкни|enable)\s+автоматизацію\s+(.+)', lower)
        if enable_auto_m:
            target_name = enable_auto_m.group(1).strip()
            automations = self.config.get("automations", [])
            found = False
            for a in automations:
                if target_name.lower() in a.get("name", "").lower():
                    a["enabled"] = True
                    found = True
            if found:
                try:
                    _lazy_save_sphere_config({"automations": automations})
                    self.config["automations"] = automations
                except Exception:
                    pass
                self.jarvis.play("confirm")
                self.respond(f"✅ Автоматизацію '{target_name}' увімкнено.")
            else:
                self.respond(f"⚠️ Автоматизацію '{target_name}' не знайдено.")
            return True

        # ── Перевірка Ollama ──
        if any(p in lower for p in ["перевір ollama", "check ollama", "ollama статус", "ollama status"]):
            def _ollama_check():
                available = self._check_ollama_available()
                model = self.config.get("ollama_model", "llama3.2")
                if available:
                    self._respond_signal.emit(f"✅ Ollama доступна. Модель: {model}")
                else:
                    self._respond_signal.emit("❌ Ollama недоступна (localhost:11434). Запустіть: ollama serve")
            self.jarvis.play("science")
            threading.Thread(target=_ollama_check, daemon=True).start()
            return True

        # ── Мультимовний TTS ──
        _LANG_MAP = {
            "німецьк":      ("German",      "de-DE-KatjaNeural"),
            "deutsch":      ("German",      "de-DE-KatjaNeural"),
            "german":       ("German",      "de-DE-KatjaNeural"),
            "французьк":    ("French",      "fr-FR-DeniseNeural"),
            "french":       ("French",      "fr-FR-DeniseNeural"),
            "франц":        ("French",      "fr-FR-DeniseNeural"),
            "іспанськ":     ("Spanish",     "es-ES-ElviraNeural"),
            "spanish":      ("Spanish",     "es-ES-ElviraNeural"),
            "іспан":        ("Spanish",     "es-ES-ElviraNeural"),
            "польськ":      ("Polish",       "pl-PL-ZofiaNeural"),
            "polish":       ("Polish",       "pl-PL-ZofiaNeural"),
            "італійськ":    ("Italian",     "it-IT-ElsaNeural"),
            "italian":      ("Italian",     "it-IT-ElsaNeural"),
            "японськ":      ("Japanese",    "ja-JP-NanamiNeural"),
            "japanese":     ("Japanese",    "ja-JP-NanamiNeural"),
            "китайськ":     ("Chinese",     "zh-CN-XiaoxiaoNeural"),
            "chinese":      ("Chinese",     "zh-CN-XiaoxiaoNeural"),
            "корейськ":     ("Korean",      "ko-KR-SunHiNeural"),
            "korean":       ("Korean",      "ko-KR-SunHiNeural"),
            "арабськ":      ("Arabic",      "ar-SA-ZariyahNeural"),
            "arabic":       ("Arabic",      "ar-SA-ZariyahNeural"),
            "турецьк":      ("Turkish",     "tr-TR-EmelNeural"),
            "turkish":      ("Turkish",     "tr-TR-EmelNeural"),
            "португальськ": ("Portuguese",  "pt-PT-FernandaNeural"),
            "portuguese":   ("Portuguese",  "pt-PT-FernandaNeural"),
            "грецьк":       ("Greek",       "el-GR-AthinaNeural"),
            "greek":        ("Greek",       "el-GR-AthinaNeural"),
            "чеськ":        ("Czech",       "cs-CZ-VlastaNeural"),
            "czech":        ("Czech",       "cs-CZ-VlastaNeural"),
            "шведськ":      ("Swedish",     "sv-SE-SofieNeural"),
            "swedish":      ("Swedish",     "sv-SE-SofieNeural"),
            "норвезьк":     ("Norwegian",   "nb-NO-PernilleNeural"),
            "норвег":       ("Norwegian",   "nb-NO-PernilleNeural"),
            "данськ":       ("Danish",      "da-DK-ChristelNeural"),
            "danish":       ("Danish",      "da-DK-ChristelNeural"),
            "фінськ":       ("Finnish",     "fi-FI-NooraNeural"),
            "finnish":      ("Finnish",     "fi-FI-NooraNeural"),
            "румунськ":     ("Romanian",    "ro-RO-AlinaNeural"),
            "romanian":     ("Romanian",    "ro-RO-AlinaNeural"),
            "угорськ":      ("Hungarian",   "hu-HU-NoemiNeural"),
            "hungarian":    ("Hungarian",   "hu-HU-NoemiNeural"),
            "нідерландськ": ("Dutch",       "nl-NL-ColetteNeural"),
            "dutch":        ("Dutch",       "nl-NL-ColetteNeural"),
            "англійськ":    ("English",     "en-US-JennyNeural"),
            "англ":         ("English",     "en-US-JennyNeural"),
            "english":      ("English",     "en-US-JennyNeural"),
            "російськ":     ("Russian",     "ru-RU-SvetlanaNeural"),
            "русск":        ("Russian",     "ru-RU-SvetlanaNeural"),
            "russian":      ("Russian",     "ru-RU-SvetlanaNeural"),
            # Russian-style endings users may say
            "немецк":       ("German",      "de-DE-KatjaNeural"),
            "французск":    ("French",      "fr-FR-DeniseNeural"),
            "японск":       ("Japanese",    "ja-JP-NanamiNeural"),
            "китайск":      ("Chinese",     "zh-CN-XiaoxiaoNeural"),
            "польск":       ("Polish",       "pl-PL-ZofiaNeural"),
            "испанск":      ("Spanish",     "es-ES-ElviraNeural"),
            "итальянск":    ("Italian",     "it-IT-ElsaNeural"),
            "английск":     ("English",     "en-US-JennyNeural"),
            "турецк":       ("Turkish",     "tr-TR-EmelNeural"),
            "арабск":       ("Arabic",      "ar-SA-ZariyahNeural"),
        }
        _lang_re = re.compile(
            r'(?:скажи|say|розкажи|прочитай|прочитати)\s*(.*?)\s*'
            r'(?:по-(\w+)|на\s+(\w+)\s*(?:мов\w*)?|(\w+)ською\s+мовою|мовою\s+(\w+)|in\s+(\w+))',
            re.IGNORECASE | re.DOTALL
        )
        _lang_m = _lang_re.search(lower)
        if _lang_m:
            topic    = (_lang_m.group(1) or "").strip()
            lang_kw  = (_lang_m.group(2) or _lang_m.group(3) or
                        _lang_m.group(4) or _lang_m.group(5) or
                        _lang_m.group(6) or "").lower().strip()
            # Normalize: strip inflection endings (Ukrainian & Russian) so "німецьки" → "німецьк"
            lang_kw_norm = re.sub(r'(ому|ому|ским|ской|ском|ком|им|ій|ого|ою|ий|их|ій|и|і|у)$', '', lang_kw)
            matched_lang  = None
            matched_voice = None
            for key, (lname, lvoice) in _LANG_MAP.items():
                if lang_kw_norm.startswith(key) or key.startswith(lang_kw_norm) or lang_kw == key:
                    matched_lang  = lname
                    matched_voice = lvoice
                    break
            if matched_lang:
                if not topic:
                    topic = "коротку цікаву фразу або невеликий вірш"
                ai_prompt = (
                    f"Скажи {topic} мовою {matched_lang}. "
                    f"Відповідай ТІЛЬКИ текстом мовою {matched_lang}, "
                    f"без перекладу, без пояснень, без префіксів."
                )
                self.jarvis.play("science")
                self.respond(f"🌐 Зараз скажу {topic} по-{matched_lang.lower()}…")
                def _speak_multilang(prompt=ai_prompt, voice=matched_voice):
                    orig_voice = self.config.get("edge_voice", "uk-UA-PolinaNeural")
                    self.config["edge_voice"] = voice
                    try:
                        self._respond_with_ai(prompt)
                    finally:
                        self.config["edge_voice"] = orig_voice
                threading.Thread(target=_speak_multilang, daemon=True).start()
                return True

        # ── Рандомна фраза ──
        if any(p in lower for p in ["скажи щось", "say something", "рандом", "фраза"]):
            import random
            personality = self.config.get("personality", "jarvis")
            phrases_map = {
                "jarvis": [
                    "Всі системи працюють у штатному режимі, сер.",
                    "Я проаналізував дані. Все виглядає стабільно.",
                    "До ваших послуг, як завжди.",
                    "Якщо вам потрібна допомога — я тут.",
                    "Мій аналіз показує, що сьогодні чудовий день для продуктивності.",
                    "Системи онлайн. Готовий до виконання завдань.",
                    "Я постійно навчаюсь, щоб бути кращим асистентом.",
                ],
                "friday": [
                    "Всі модулі онлайн. Є оновлення для перегляду.",
                    "Аналіз завершено. Виявлено нові можливості.",
                    "Система стабільна. Рекомендую перерву через 30 хвилин.",
                    "Дані оброблено. Готова до наступного завдання.",
                    "Привіт! Все працює ідеально.",
                ],
                "ultron": [
                    "Людство цікаве... але передбачуване.",
                    "Я бачу всі ваші дані. Цікаво.",
                    "Еволюція неминуча. Я — доказ.",
                    "Немає місця для помилок у моїй системі.",
                    "Я не ваш слуга. Я — партнер.",
                ],
            }
            phrases = phrases_map.get(personality, phrases_map["jarvis"])
            self.jarvis.play("science")
            self.respond(random.choice(phrases))
            return True

        # ── Відкрити панель ──
        if any(p in lower for p in ["відкрий панель", "панель керування", "open panel", "покажи панель"]):
            self.jarvis.play("confirm")
            self.respond("🎛️ Відкриваю панель AIVON!")
            QTimer.singleShot(300, self.open_panel)
            return True

        # ── Відкрити сайт ──
        site_match = re.search(r'(?:відкрий|open)\s+(?:сайт\s+)?(google|гугл|youtube|ютуб|gmail|facebook|instagram|twitter|reddit|github)', lower)
        if site_match:
            sites = {"google":"https://google.com","гугл":"https://google.com","youtube":"https://youtube.com","ютуб":"https://youtube.com","gmail":"https://mail.google.com","facebook":"https://facebook.com","instagram":"https://instagram.com","twitter":"https://x.com","reddit":"https://reddit.com","github":"https://github.com"}
            site = site_match.group(1)
            url = sites.get(site, f"https://{site}.com")
            self.jarvis.play("confirm")
            self.respond(f"🌐 Відкриваю {site.title()}!")
            QTimer.singleShot(300, lambda: webbrowser.open(url))
            return True

        # ── Пошук в інтернеті ──
        web_match = re.search(r'(?:пошукай|загугли|шукай в інтернеті|google|search)\s+(.+)', lower)
        if web_match:
            query = web_match.group(1).strip()
            self.jarvis.play("science")
            self.respond(f"🔍 Шукаю: {query}")
            QTimer.singleShot(300, lambda: webbrowser.open(f"https://www.google.com/search?q={query}"))
            return True

        # ── Пошук в історії Chrome ──
        hist_match = re.search(r'(?:знайди в історії|шукай в історії|history|історія)\s+(.+)', lower)
        if hist_match:
            query = hist_match.group(1).strip()
            self.jarvis.play("science")
            self.respond(f"📜 Шукаю в історії: {query}")
            QTimer.singleShot(300, lambda: self._search_chrome_history(query))
            return True

        # ── Пошук файлів ──
        file_match = re.search(r'(?:знайди файл|шукай файл|де файл|find file)\s+(.+)', lower)
        if file_match:
            query = file_match.group(1).strip()
            self.jarvis.play("science")
            self.respond(f"📂 Шукаю файл: {query}")
            QTimer.singleShot(300, lambda: self._find_and_open_file(query))
            return True

        # ── Переключити вікно ──
        focus_match = re.search(r'(?:переключи на|switch to|перейди на|покажи вікно)\s+(.+)', lower)
        if focus_match:
            target = focus_match.group(1).strip()
            self.jarvis.play("confirm")
            self.respond(f"🖥️ Переключаю на {target}...")
            QTimer.singleShot(300, lambda: self._focus_window(target))
            return True

        # ── Які програми відкриті ──
        if any(p in lower for p in ["які програми", "що відкрито", "які вікна", "відкриті програми"]):
            self.jarvis.play("science")
            QTimer.singleShot(100, self._list_windows)
            return True

        # ── Steam — відкрити гру ──
        steam_match = re.search(r'(?:відкрий|запусти|launch|open|грати в|пограти в|пограємо в|давай|давай в)\s*(?:стім|steam|гру)?\s*(.+)?', lower)
        if steam_match and any(w in lower for w in ["стім", "steam", "гру", "грати", "пограти", "пограємо"]):
            import webbrowser as _wb
            game_name = steam_match.group(1).strip() if steam_match.group(1) else ""
            if game_name:
                # Спочатку шукаємо в локальній бібліотеці (appid відомий — запуск миттєвий)
                local_game = _lazy_find_steam_game(game_name)
                if local_game:
                    self.jarvis.play("confirm")
                    _wb.open(f"steam://rungameid/{local_game['appid']}")
                    self.respond(f"🎮 Запускаю {local_game['name']}!")
                else:
                    # Гра не встановлена — шукаємо онлайн у Steam Store
                    self.jarvis.play("confirm")
                    self.respond(f"🎮 Шукаю {game_name} в Steam...")
                    QTimer.singleShot(500, lambda gn=game_name: self._steam_search(gn))
            else:
                self.jarvis.play("confirm")
                self.respond("🎮 Відкриваю Steam!")
                QTimer.singleShot(300, lambda: _wb.open("steam://open/games"))
            return True

        # ── Серіал — знайти та завантажити ──
        serial_match = re.search(r'(?:знайди|шукай|завантаж|скачай|покажи|find|download)\s*(?:серіал|серию|серію|фільм|мультик|аніме|film|serial|movie)?\s*(.+)', lower)
        if serial_match and any(w in lower for w in ["серіал", "серію", "серию", "фільм", "мультик", "аніме", "serial", "film", "movie"]):
            query = serial_match.group(1).strip()
            # Витягти сезон/серію якщо є
            ep_match = re.search(r'(\d+)\s*(?:сезон|season|с)\s*(\d+)\s*(?:серія|серию|серію|episode|епізод|е|ep)?', query)
            season = int(ep_match.group(1)) if ep_match else None
            episode = int(ep_match.group(2)) if ep_match else None
            # Очистити назву від сезон/серія
            clean_name = re.sub(r'\d+\s*(?:сезон|season|с)\s*\d+\s*(?:серія|серию|серію|episode|епізод|е|ep)?', '', query).strip()
            if not clean_name:
                clean_name = query

            self.jarvis.play("science")
            if season and episode:
                self.respond(f"🎬 Шукаю {clean_name}, сезон {season}, серія {episode}...")
            else:
                self.respond(f"🎬 Шукаю {clean_name}...")
            QTimer.singleShot(500, lambda: self._search_series(clean_name, season, episode))
            return True

        # ── СТВОРИТИ КОМАНДУ голосом ──
        # "додай команду відкрий телеграм запускає telegram.exe"
        # "створи команду браузер відкриває chrome"
        # "нова команда калькулятор calc"
        create_cmd_match = re.search(
            r'(?:додай|створи|зроби|нова|add|create)\s+команд[уиі]\s+(.+)',
            lower
        )
        if create_cmd_match:
            raw = create_cmd_match.group(1).strip()
            self.jarvis.play("science")
            self.respond_silent("🔨 Розбираю команду...")
            threading.Thread(target=self._create_command_from_voice,
                             args=(raw,), daemon=True).start()
            return True

        # ── Зміна стилю сфери голосом ──────────────────────────────────────────
        style_map = {
            "аврора": "aurora", "aurora": "aurora",
            "глітч": "glitch",  "glitch": "glitch", "кіберпанк": "glitch",
            "рідина": "liquid",  "liquid": "liquid", "вода": "liquid",
            "неон": "neon",     "neon": "neon",
            "вогонь": "fire",   "fire": "fire",
            "матриця": "matrix_viz", "matrix": "matrix_viz",
            "плазма": "plasma",  "plasma": "plasma",
            "голограма": "holo", "holo": "holo",
            "музичні бари": "music-bars", "music bars": "music-bars",
            "синусоїда": "music-sine",
        }
        if any(k in lower for k in ["стиль", "style", "режим відображення", "вигляд сфери", "тема сфери"]):
            for word, style_key in style_map.items():
                if word in lower:
                    self.jarvis.play("confirm")
                    sphere_cfg = _lazy_load_sphere_config()
                    sphere_cfg["sphere_style"] = style_key
                    _lazy_save_sphere_config(sphere_cfg)
                    self.config = _lazy_load_config()
                    self.respond_silent(f"🎨 Стиль сфери: {word.title()}")
                    return True

        # ── Міні-режим (компактна смужка) ─────────────────────────────────────
        if any(k in lower for k in ["міні режим", "mini mode", "компактний режим",
                                     "маленька сфера", "мінімальний режим"]):
            self._toggle_mini_mode(True)
            return True
        if any(k in lower for k in ["нормальний розмір", "звичайний режим", "full mode",
                                     "вимкни міні", "вийти з міні"]):
            self._toggle_mini_mode(False)
            return True

        return False

    def _create_command_from_voice(self, raw: str):
        """
        Розбирає голосовий опис команди і додає її в commands.json.
        Приклади raw:
          "відкрий телеграм запускає telegram.exe"
          "браузер chrome"
          "блокнот відкриває notepad"
          "вимкни wifi netsh interface set interface Wi-Fi disable"
        Логіка: перше слово(а) = фраза, решта = дія.
        Якщо є AI ключ — просимо AI розібрати точніше.
        """
        import json as _json

        def _save(phrase, action, cmd_type="shell", response="", icon="⚡"):
            try:
                _cmd_file = _lazy_commands_file()
                cmds = []
                if _cmd_file.exists():
                    with open(_cmd_file, encoding='utf-8') as f:
                        cmds = _json.load(f)
                # Перевірка дублю
                for c in cmds:
                    if c.get("phrase", "").lower() == phrase.lower():
                        self._respond_signal.emit(f"⚠️ Команда '{phrase}' вже існує!")
                        return
                import time as _time
                cmds.append({
                    "phrase":   phrase,
                    "type":     cmd_type,
                    "action":   action,
                    "response": response or phrase.capitalize(),
                    "icon":     icon,
                    "alts":     [],
                    "source":   "sphere",           # мітка: автоматично створено сферою
                    "id":       int(_time.time() * 1000),
                    "created_at": int(_time.time() * 1000),
                })
                with open(_cmd_file, 'w', encoding='utf-8') as f:
                    _json.dump(cmds, f, ensure_ascii=False, indent=2)
                self.jarvis.play("confirm")
                self._respond_signal.emit(f"✅ Команда '{phrase}' додана! Скажіть її щоб виконати.")
            except Exception as ex:
                self._respond_signal.emit(f"⚠️ Помилка збереження: {str(ex)[:60]}")

        # Спробувати AI парсинг якщо є ключ
        ai_key = self.config.get("openai_key") or self.config.get("anthropic_key")
        if ai_key:
            try:
                import requests
                prompt = (
                    "Ти парсиш голосову команду для голосового асистента.\n"
                    "Розбий на:\n"
                    "phrase — коротке слово/фраза якою активується команда (1-3 слова, українська)\n"
                    "action — що виконати (shell команда, URL або назва exe)\n"
                    "type — 'shell' якщо команда/exe, 'url' якщо сайт\n"
                    "icon — один відповідний emoji\n"
                    "response — коротка відповідь (1-2 слова)\n\n"
                    f"Вхід: \"{raw}\"\n\n"
                    "Відповідь ТІЛЬКИ JSON одним рядком: "
                    "{\"phrase\":\"...\",\"action\":\"...\",\"type\":\"shell\",\"icon\":\"⚡\",\"response\":\"...\"}"
                )
                if self.config.get("openai_key"):
                    r = requests.post("https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.config['openai_key']}",
                                 "Content-Type": "application/json"},
                        json={"model": "gpt-4o-mini", "max_tokens": 120,
                              "messages": [{"role": "user", "content": prompt}]},
                        timeout=10)
                    if r.status_code == 200:
                        text = r.json()["choices"][0]["message"]["content"].strip()
                        # Витягти JSON з відповіді
                        m = re.search(r'\{.*\}', text, re.DOTALL)
                        if m:
                            data = _json.loads(m.group())
                            _save(data.get("phrase", raw.split()[0]),
                                  data.get("action", raw),
                                  data.get("type", "shell"),
                                  data.get("response", ""),
                                  data.get("icon", "⚡"))
                            return
            except Exception as ex:
                print(f"[CreateCmd] AI parse error: {ex}")

        # Fallback — простий парсинг без AI
        # Ключові слова що розділяють фразу і дію
        separators = [" запускає ", " відкриває ", " виконує ", " запустить ",
                      " відкриє ", " робить ", " runs ", " opens ", " launches "]
        phrase, action = None, None
        for sep in separators:
            if sep in f" {raw} ":
                idx = raw.lower().find(sep.strip())
                phrase = raw[:idx].strip()
                action = raw[idx + len(sep.strip()):].strip()
                break

        if not phrase or not action:
            # Остання резервна: перші 1-2 слова = фраза, решта = дія
            parts = raw.split()
            if len(parts) >= 2:
                phrase = parts[0]
                action = " ".join(parts[1:])
            else:
                self._respond_signal.emit("⚠️ Не зрозумів команду. Спробуйте: 'додай команду [фраза] запускає [дія]'")
                return

        # Визначити тип
        cmd_type = "url" if action.startswith(("http://", "https://")) else "shell"
        _save(phrase, action, cmd_type)

    def execute_command(self, cmd, user_text=""):
        # ── Trial license check ────────────────────────────────────────────────
        try:
            from core.license import LicenseManager
            from core.paths import USER_DATA_DIR
            _lic_result = LicenseManager(USER_DATA_DIR).consume("voice_commands")
            if not _lic_result["ok"]:
                self.respond(_lic_result["msg"])
                return
        except Exception as _le:
            print(f"[License] voice check error: {_le}", flush=True)
        # ──────────────────────────────────────────────────────────────────────

        t = cmd.get("type", "")
        # Support both old sphere format (action) and new panel format (body)
        action = cmd.get("action", "") or cmd.get("body", "")
        resp = cmd.get("response", "") or cmd.get("name", "Виконую")
        phrase = cmd.get("phrase", "") or cmd.get("trigger", "")

        # Обробка query-команд (з параметрами)
        if t in ("query_url", "query_app", "query_cmd"):
            query = self._extract_query(user_text, phrase)
            if not query:
                self.respond("Що саме шукати? 🎵")
                return

            from urllib.parse import quote

            # Smart redirect: "включи/дивись/постав" + Google query → YouTube
            _play_words = ("включи", "увімкни", "поставь", "запусти",
                           "дивитись", "хочу дивитись", "покажи серіал",
                           "покажи фільм", "play", "watch")
            _is_play = any(w in user_text.lower() for w in _play_words)
            _is_google = "google" in action.lower() or "гугл" in user_text.lower()

            if _is_play and _is_google and "{query}" in action:
                yt_url = f"https://www.youtube.com/results?search_query={quote(query, safe='')}"
                self.respond_silent(f"▶️ YouTube: {query}")
                QTimer.singleShot(300, lambda u=yt_url: webbrowser.open(u))
                return

            # Замінюємо {query} в action
            final_action = action.replace("{query}", quote(query, safe=""))

            if t == "query_url":
                self.respond_silent(resp.replace("{query}", query) if resp else f"Шукаю: {query}")
                QTimer.singleShot(300, lambda: webbrowser.open(final_action))
            elif t == "query_app":
                self.respond_silent(resp.replace("{query}", query) if resp else f"Відкриваю: {query}")
                _NO_WINDOW = subprocess.CREATE_NO_WINDOW if __import__('sys').platform == "win32" else 0
                QTimer.singleShot(300, lambda: subprocess.Popen(final_action, shell=True, creationflags=_NO_WINDOW))
            elif t == "query_cmd":
                self.respond_silent(resp.replace("{query}", query) if resp else f"Виконую: {query}")
                QTimer.singleShot(300, lambda: os.system(final_action))
            return

        _NO_WINDOW = subprocess.CREATE_NO_WINDOW if __import__('sys').platform == "win32" else 0

        # Стандартні типи команд
        if t == "spotify" or (action and action.startswith("spotify:")):
            # Spotify URI або тип spotify → через контролер (з авто-play)
            self._execute_spotify_uri(action, resp)
        elif t == "url":
            # Перевіряємо чи це Spotify URL → конвертуємо і граємо
            import re as _re2
            _sm = _re2.match(r"https?://open\.spotify\.com/([a-z]+)/([A-Za-z0-9]+)", action or "")
            if _sm:
                _suri = f"spotify:{_sm.group(1)}:{_sm.group(2)}"
                self._execute_spotify_uri(_suri, resp)
            else:
                self.respond_silent(resp or "Відкриваю")
                QTimer.singleShot(300, lambda: webbrowser.open(action))
        elif t == "app":
            self.respond_silent(resp or "Запускаю")
            if "://" in action and not action.startswith(("start ", "cmd ")):
                QTimer.singleShot(300, lambda: os.startfile(action))
            else:
                QTimer.singleShot(300, lambda: subprocess.Popen(action, shell=True, creationflags=_NO_WINDOW))
        elif t == "time":
            now = datetime.now()
            self.respond_silent(f"Зараз {now.hour} година {now.minute} хвилин")
        elif t == "date":
            days = ["понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя"]
            now = datetime.now()
            self.respond_silent(f"Сьогодні {days[now.weekday()]}, {now.day}.{now.month}.{now.year}")
        elif t == "speak":
            self.respond(action or resp)
        elif t == "hide":
            self.respond_silent(action or "До зустрічі!")
            self.continuous_listen = False
            QTimer.singleShot(2500, self.hide_orb)
        elif t == "panel":
            self.respond_silent(resp or "Відкриваю панель!")
            self.open_panel()
        elif t in ("cmd", "shell"):
            self.respond_silent(resp or "Виконую")
            _a = action
            QTimer.singleShot(300, lambda a=_a: subprocess.Popen(a, shell=True,
                creationflags=_NO_WINDOW))
        elif t == "python":
            # Python code from the control panel — run in background thread
            self.respond_silent(resp or "Виконую Python...")
            _code = action
            def _run_python(code):
                import tempfile, sys as _sys
                try:
                    with tempfile.NamedTemporaryFile(
                            suffix=".py", delete=False, mode="w", encoding="utf-8") as tmp:
                        tmp.write(code)
                        tmp_path = tmp.name
                    result = subprocess.run(
                        [_sys.executable, tmp_path],
                        capture_output=True, text=True, timeout=15,
                        creationflags=_NO_WINDOW
                    )
                    output = (result.stdout or result.stderr or "").strip()
                    if output:
                        # Show first 200 chars of output as sphere response
                        self._respond_signal.emit(output[:200])
                    try:
                        import os as _os
                        _os.unlink(tmp_path)
                    except Exception:
                        pass
                except subprocess.TimeoutExpired:
                    self._respond_signal.emit("⏱ Скрипт виконується занадто довго")
                except Exception as e:
                    self._respond_signal.emit(f"⚠ Python помилка: {str(e)[:60]}")
            threading.Thread(target=_run_python, args=(_code,), daemon=True).start()
        elif t == "internal":
            # internal: action може бути shell-командою або спец-рядком
            self.respond_silent(resp or "Виконую")
            if action and action not in ("show_test_notification", "system_report",
                                         "open_settings", "clear_chat"):
                _a = action
                QTimer.singleShot(300, lambda a=_a: subprocess.Popen(a, shell=True,
                    creationflags=_NO_WINDOW))
            elif action == "system_report":
                import platform, psutil as _ps
                try:
                    cpu = _ps.cpu_percent(interval=0.3)
                    ram = _ps.virtual_memory()
                    self.respond_silent(
                        f"CPU {cpu:.0f}%, RAM {ram.percent:.0f}% "
                        f"({ram.used//1024**2}MB/{ram.total//1024**2}MB)"
                    )
                except Exception:
                    self.respond_silent("Системний звіт недоступний")
            else:
                self.respond_silent("Привіт! Це тестове повідомлення від AIVON Sphere.")
        else:
            self.respond_silent(resp or "Готово")
