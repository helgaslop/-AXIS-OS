# -*- coding: utf-8 -*-
"""sphere/system.py — System control mixin for AivonSphere."""

import os
import sys
import re
import json
import threading
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QTimer

# _NO_WINDOW is defined in aivon_sphere.py, re-declare here for standalone use
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# These are resolved from aivon_sphere.py's module scope at runtime via self.*
# but we import what we can here for clarity.
try:
    import psutil as _psutil
    HAS_PSUTIL = True
except ImportError:
    _psutil = None  # type: ignore
    HAS_PSUTIL = False

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    _requests = None  # type: ignore
    HAS_REQUESTS = False


class SphereSystemMixin:
    """System control methods. Mixed into AivonSphere."""

    # ═══════════════════════════════════════════════════════════
    # СИСТЕМНЕ КЕРУВАННЯ — гучність, завершення, вікна, скріншот
    # ═══════════════════════════════════════════════════════════

    def _handle_system_control(self, lower: str, text: str) -> bool:

        # ── Гучність ──
        vol_patterns = [
            ("зроби гучніше", +20), ("збільш гучність", +20), ("гучніше", +15),
            ("volume up",   +20),   ("louder",          +20),
            ("зроби тихіше", -20),  ("зменш гучність",  -20), ("тихіше", -15),
            ("volume down",  -20),  ("quieter",          -20), ("mute",     0),
            ("вимкни звук",   -1),  ("mute audio",       -1),
        ]
        for phrase, delta in vol_patterns:
            if phrase in lower:
                if delta == -1:
                    self._set_volume_mute()
                    self.respond_silent("🔇 Звук вимкнено")
                elif delta == 0:
                    self._set_volume_mute()
                    self.respond_silent("🔇 Mute")
                else:
                    new_vol = self._adjust_volume(delta)
                    icon = "🔊" if delta > 0 else "🔉"
                    self.respond_silent(f"{icon} Гучність: {new_vol}%")
                return True

        # ── Конкретний відсоток: "встанови гучність 60" ──
        vol_set = re.search(r'(?:гучність|volume|встанови гучність)\s+(\d{1,3})', lower)
        if vol_set:
            val = max(0, min(100, int(vol_set.group(1))))
            self._set_volume_abs(val)
            self.respond_silent(f"🔊 Гучність: {val}%")
            return True

        # ── Вимкнення / сон / перезавантаження ──
        if any(p in lower for p in ["вимкни пк", "вимкни комп", "shutdown pc",
                                     "turn off computer", "вимкни ноутбук"]):
            delay_m = re.search(r'через\s+(\d+)\s*(хвилин|хв|хвилини)', lower)
            secs = int(delay_m.group(1)) * 60 if delay_m else 60
            self.respond(f"🖥️ Вимикаю ПК через {secs//60} хв. Скажи «скасуй вимкнення» щоб відмінити.")
            QTimer.singleShot(secs * 1000, lambda: subprocess.Popen(
                "shutdown /s /t 0", shell=True, creationflags=_NO_WINDOW))
            return True

        if any(p in lower for p in ["скасуй вимкнення", "cancel shutdown", "відміни вимкнення"]):
            subprocess.Popen("shutdown /a", shell=True, creationflags=_NO_WINDOW)
            self.respond_silent("✅ Вимкнення скасовано")
            return True

        if any(p in lower for p in ["сон", "режим сну", "sleep pc", "hibernate"]):
            self.respond_silent("😴 Переходжу в режим сну...")
            QTimer.singleShot(2000, lambda: subprocess.Popen(
                "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                shell=True, creationflags=_NO_WINDOW))
            return True

        if any(p in lower for p in ["перезавантаж", "перезапусти пк", "restart", "reboot"]):
            self.respond_silent("🔄 Перезавантаження...")
            QTimer.singleShot(2000, lambda: subprocess.Popen(
                "shutdown /r /t 0", shell=True, creationflags=_NO_WINDOW))
            return True

        # ── Переключити вікно / додаток ──
        switch_kw = ["переключи на ", "відкрий вікно ", "switch to ", "перейди на "]
        for kw in switch_kw:
            if kw in lower:
                app_name = text[lower.find(kw) + len(kw):].strip()
                if app_name:
                    self._switch_to_window(app_name)
                return True

        # ── Скріншот ──
        if any(p in lower for p in ["зроби скріншот", "screenshot", "скріншот", "знімок екрану"]):
            self._take_screenshot()
            return True

        return False

    def _adjust_volume(self, delta: int) -> int:
        """Змінює гучність Windows на delta%%, повертає нову гучність."""
        try:
            if sys.platform == "win32":
                # Use nircmd if available, else PowerShell SendKeys fallback
                subprocess.Popen(
                    f'nircmd changesysvolume {delta * 655}',
                    shell=True, creationflags=_NO_WINDOW)
                # Fallback via SendKeys
                if delta > 0:
                    for _ in range(abs(delta) // 5):
                        subprocess.Popen('powershell -command "$wsh=New-Object -ComObject WScript.Shell;$wsh.SendKeys([char]175)"',
                            shell=True, creationflags=_NO_WINDOW)
                else:
                    for _ in range(abs(delta) // 5):
                        subprocess.Popen('powershell -command "$wsh=New-Object -ComObject WScript.Shell;$wsh.SendKeys([char]174)"',
                            shell=True, creationflags=_NO_WINDOW)
        except Exception as e:
            print(f"[Volume] {e}")
        # Return estimated volume (we can't easily read it without COM)
        return max(0, min(100, 50 + delta))

    def _set_volume_abs(self, percent: int):
        """Встановлює абсолютну гучність (0-100)."""
        try:
            if sys.platform == "win32":
                val = int(percent * 655.35)
                subprocess.Popen(
                    f'nircmd setsysvolume {val}',
                    shell=True, creationflags=_NO_WINDOW)
        except Exception as e:
            print(f"[Volume set] {e}")

    def _set_volume_mute(self):
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    'powershell -command "$wsh=New-Object -ComObject WScript.Shell;$wsh.SendKeys([char]173)"',
                    shell=True, creationflags=_NO_WINDOW)
        except Exception as e:
            print(f"[Mute] {e}")

    def _switch_to_window(self, app_name: str):
        """Переключає фокус на вікно за назвою."""
        try:
            import ctypes  # noqa: F401
            app_lower = app_name.lower()
            # Map common names → exe names
            APP_MAP = {
                "браузер": "chrome", "хром": "chrome", "firefox": "firefox",
                "code": "code", "vs code": "code", "pycharm": "pycharm",
                "telegram": "telegram", "discord": "discord",
                "блокнот": "notepad", "провідник": "explorer",
                "термінал": "wt", "cmd": "cmd",
            }
            exe = APP_MAP.get(app_lower, app_lower.split()[0])
            if HAS_PSUTIL:
                for p in _psutil.process_iter(['pid', 'name']):
                    try:
                        if exe in (p.info['name'] or '').lower():
                            # Found — bring to front via PowerShell
                            pname = p.info['name']
                            subprocess.Popen(
                                f'powershell -command "(New-Object -ComObject WScript.Shell).AppActivate(\\"{pname}\\")"',
                                shell=True, creationflags=_NO_WINDOW)
                            self.respond_silent(f"⬆ {app_name}")
                            return
                    except Exception:
                        pass
            self.respond_silent(f"Вікно «{app_name}» не знайдено")
        except Exception as e:
            print(f"[Switch window] {e}")

    def _take_screenshot(self):
        """Робить скріншот і зберігає на Робочий стіл."""
        try:
            import mss
            from PIL import Image as _Image
            desktop = Path.home() / "Desktop"
            fname   = desktop / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            with mss.mss() as sct:
                shot = sct.grab(sct.monitors[0])
                _Image.frombytes("RGB", shot.size, shot.rgb).save(str(fname))
            self.respond_silent(f"📸 Скріншот збережено: {fname.name}")
            os.startfile(str(fname))
        except ImportError:
            self.respond_silent("Потрібно: pip install mss Pillow")
        except Exception as e:
            self.respond_silent(f"⚠ Скріншот: {str(e)[:40]}")

    # ═══════════════════════════════════════════════════════════
    # ТАЙМЕРИ ТА НАГАДУВАННЯ З ГОЛОСОМ
    # ═══════════════════════════════════════════════════════════

    def _handle_timer(self, lower: str, text: str) -> bool:
        # ── Таймер: "постав таймер на 5 хвилин" ──
        timer_kw = ["постав таймер", "таймер на", "set timer", "timer for",
                    "відлік", "через"]
        if not any(p in lower for p in timer_kw):
            return False

        # Extract duration
        secs = self._parse_duration(lower)
        if secs is None:
            self.respond("Скільки часу? Наприклад: «таймер на 5 хвилин»")
            return True

        # Extract label
        label = ""
        for kw in ["нагадай про ", "нагадай щодо ", "remind me about ", "про "]:
            if kw in lower:
                label = text[lower.find(kw) + len(kw):].strip()[:40]
                break

        human = self._secs_to_human(secs)
        self.respond_silent(f"⏱ Таймер: {human}" + (f" — {label}" if label else ""))
        QTimer.singleShot(secs * 1000, lambda l=label, h=human:
            self.respond(f"⏰ {h} минуло!" + (f" Нагадування: {l}" if l else " Таймер!")))
        return True

    def _parse_duration(self, lower: str) -> int | None:
        """Парсить тривалість із тексту → секунди."""
        total = 0
        found = False

        patterns = [
            (r'(\d+)\s*(?:год|годин|hour|hours|г)',                 3600),
            (r'(\d+)\s*(?:хвилин|хвилини|хв|min(?:ute)?s?)',        60),
            (r'(\d+)\s*(?:секунд|секунди|сек|sec(?:ond)?s?)',         1),
        ]
        for pat, mult in patterns:
            m = re.search(pat, lower)
            if m:
                total += int(m.group(1)) * mult
                found  = True

        # "через 30" — assume minutes if no unit
        if not found:
            m = re.search(r'через\s+(\d+)', lower)
            if m:
                total = int(m.group(1)) * 60
                found = True

        return total if found else None

    @staticmethod
    def _secs_to_human(secs: int) -> str:
        h, rem = divmod(secs, 3600)
        m, s   = divmod(rem, 60)
        parts  = []
        if h: parts.append(f"{h}год")
        if m: parts.append(f"{m}хв")
        if s: parts.append(f"{s}сек")
        return " ".join(parts) or "0сек"

    # ═══════════════════════════════════════════════════════════
    # БАТАРЕЯ
    # ═══════════════════════════════════════════════════════════

    def _handle_battery(self, text: str, lower: str) -> bool:
        kw = ["заряд батареї", "скільки заряду", "battery",
              "заряд ноутбука", "акумулятор"]
        if not any(k in lower for k in kw):
            return False
        if not HAS_PSUTIL:
            self.respond_silent("🔋 psutil не встановлено: pip install psutil")
            return True
        batt = _psutil.sensors_battery()
        if batt is None:
            self.respond_silent("🖥 ПК не має батареї (стаціонарний)")
            return True
        percent = batt.percent
        plugged = "🔌 підключено до мережі" if batt.power_plugged else "🔋 від батареї"
        secs    = batt.secsleft
        if secs == _psutil.POWER_TIME_UNLIMITED:
            time_str = "необмежено"
        elif secs == _psutil.POWER_TIME_UNKNOWN or secs < 0:
            time_str = "невідомо"
        else:
            h, m = divmod(secs // 60, 60)
            time_str = f"{h}г {m}хв" if h else f"{m}хв"
        icon = "🔋" if percent > 50 else ("⚡" if percent > 20 else "🪫")
        msg = (f"{icon} Батарея: <b>{percent:.0f}%</b> ({plugged})\n"
               f"⏱ Залишилось: {time_str}")
        self.respond_silent(msg)
        return True

    # ═══════════════════════════════════════════════════════════
    # ALARM
    # ═══════════════════════════════════════════════════════════

    def _handle_alarm(self, text: str, lower: str) -> bool:
        set_kw    = ["постав будильник", "будильник на", "alarm",
                     "розбуди мене", "прокинутися", "прокидатися"]
        cancel_kw = ["скасуй будильник", "видали будильник", "cancel alarm",
                     "вимкни будильник"]
        list_kw   = ["мої будильники", "список будильників", "будильники"]

        if any(k in lower for k in cancel_kw):
            self._cancel_all_alarms()
            return True
        if any(k in lower for k in list_kw):
            self._list_alarms()
            return True
        if not any(k in lower for k in set_kw):
            return False

        # Parse time
        alarm_time = self._parse_alarm_time(lower)
        if alarm_time is None:
            self.respond_silent("⏰ Не зрозумів час будильника. Приклад: «будильник на 7:30»")
            return True

        self._add_alarm(alarm_time)
        self.respond_silent(f"⏰ Будильник встановлено на <b>{alarm_time.strftime('%H:%M')}</b>")
        return True

    def _parse_alarm_time(self, lower: str):
        """Parse time from lower-cased text. Returns datetime or None."""
        now = datetime.now()
        # HH:MM or HH.MM
        m = re.search(r'(\d{1,2})[:\.](\d{2})', lower)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                t = now.replace(hour=h, minute=mi, second=0, microsecond=0)
                if t <= now:
                    t = t + timedelta(days=1)
                return t
        # "в 7 ранку" / "о 8 ранку" / "в 22 вечора"
        m2 = re.search(r'(?:в|о)\s+(\d{1,2})\s*(ранку|вечора|дня|ночі)?', lower)
        if m2:
            h = int(m2.group(1))
            period = m2.group(2) or ""
            if period in ("вечора", "дня") and h < 12:
                h += 12
            if period == "ночі" and h >= 12:
                h = h % 12
            if 0 <= h <= 23:
                t = now.replace(hour=h, minute=0, second=0, microsecond=0)
                if t <= now:
                    t = t + timedelta(days=1)
                return t
        return None

    def _add_alarm(self, alarm_dt):
        """Add alarm to file and schedule QTimer."""
        alarms = self._load_alarms_data()
        alarms.append({"ts": alarm_dt.isoformat(), "text": "Час прокидатися!"})
        self._save_alarms_data(alarms)
        self._schedule_alarm_qt(alarm_dt, "Час прокидатися!")

    def _schedule_alarm_qt(self, alarm_dt, alarm_text: str):
        """Schedule a QTimer for alarm."""
        now = datetime.now()
        ms = max(0, int((alarm_dt - now).total_seconds() * 1000))
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._fire_alarm(alarm_text, alarm_dt))
        timer.start(ms)
        self._alarm_timers.append(timer)

    def _fire_alarm(self, text: str, alarm_dt):
        """Called when alarm fires."""
        self.jarvis.play("alarm")
        self.respond(f"⏰ Будильник! {text}")
        self._tg_notify(f"⏰ <b>Будильник</b> ({alarm_dt.strftime('%H:%M')})\n{text}")
        # Remove from file
        alarms = [a for a in self._load_alarms_data()
                  if a.get("ts") != alarm_dt.isoformat()]
        self._save_alarms_data(alarms)

    def _cancel_all_alarms(self):
        for t in self._alarm_timers:
            try:
                t.stop()
            except Exception:
                pass
        self._alarm_timers.clear()
        self._save_alarms_data([])
        self.respond_silent("⏰ Всі будильники скасовано")

    def _list_alarms(self):
        alarms = self._load_alarms_data()
        if not alarms:
            self.respond_silent("⏰ Будильників немає")
            return
        lines = ["⏰ <b>Мої будильники:</b>"]
        for a in alarms:
            try:
                from datetime import datetime as _dt
                t = _dt.fromisoformat(a["ts"]).strftime("%H:%M %d.%m")
                lines.append(f"• {t} — {a.get('text','')}")
            except Exception:
                pass
        self.respond_silent("\n".join(lines))

    def _load_alarms_data(self) -> list:
        try:
            if self._alarms_file.exists():
                return json.loads(self._alarms_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def _save_alarms_data(self, alarms: list):
        try:
            import aivon_sphere as _sphere_mod
            _sphere_mod.USER_DATA_DIR.mkdir(exist_ok=True)
            self._alarms_file.write_text(
                json.dumps(alarms, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[Alarm] save error: {e}")

    def _load_and_schedule_alarms(self):
        """Called at startup — load alarms and schedule pending ones."""
        try:
            alarms = self._load_alarms_data()
            now = datetime.now()
            future = []
            for a in alarms:
                try:
                    from datetime import datetime as _dt
                    dt = _dt.fromisoformat(a["ts"])
                    if dt > now:
                        future.append(a)
                        # Need to schedule after QApplication is running
                        QTimer.singleShot(100, lambda d=dt, t=a.get("text","Будильник!"):
                                          self._schedule_alarm_qt(d, t))
                except Exception:
                    pass
            if len(future) != len(alarms):
                self._save_alarms_data(future)
        except Exception as e:
            print(f"[Alarm] startup load error: {e}")

    # ═══════════════════════════════════════════════════════════
    # SHUTDOWN TIMER
    # ═══════════════════════════════════════════════════════════

    def _handle_shutdown_timer(self, text: str, lower: str) -> bool:
        cancel_kw = ["скасуй вимкнення", "cancel shutdown", "відмінити вимкнення",
                     "shutdown /a", "скасувати вимкнення"]
        set_kw    = ["вимкни через", "shutdown in", "вимкни пк через",
                     "перезавантаж через", "виключи через", "виключи пк через",
                     "вимкни комп через", "виключи комп через",
                     "shutdown after", "вимкни зараз через"]

        if any(k in lower for k in cancel_kw):
            os.system("shutdown /a")
            self.respond_silent("✅ Вимкнення скасовано")
            self._tg_notify("✅ <b>Вимкнення скасовано</b>")
            return True
        if not any(k in lower for k in set_kw):
            return False

        seconds = self._parse_time_duration(lower)
        if seconds is None:
            self.respond_silent(
                "💤 Не зрозумів час.\n"
                "Приклади: «вимкни через 30 секунд» / «вимкни через 2 години» / «вимкни через 10 хвилин»"
            )
            return True

        MAX_SHUTDOWN_DELAY = 86400  # 24 hours max
        seconds = min(int(seconds), MAX_SHUTDOWN_DELAY)
        if seconds < 0:
            seconds = 0

        restart_kw = ["перезавантаж", "restart", "reboot"]
        if any(k in lower for k in restart_kw):
            os.system(f"shutdown /r /t {seconds}")
            action = "перезавантаження"
        else:
            os.system(f"shutdown /s /t {seconds}")
            action = "вимкнення"

        # Build human-readable time string (supports seconds < 60)
        h, rem = divmod(seconds, 3600)
        m, s   = divmod(rem, 60)
        if h and m:
            time_str = f"{h}г {m}хв"
        elif h:
            time_str = f"{h} год"
        elif m and s:
            time_str = f"{m}хв {s}с"
        elif m:
            time_str = f"{m} хвилин"
        else:
            time_str = f"{s} секунд"

        msg = f"💤 {action.capitalize()} через {time_str}\nСкасувати: «скасуй вимкнення»"
        self.respond_silent(msg)
        self._tg_notify(f"💤 <b>{action.capitalize()} через {time_str}</b>\nСкасувати: /cancel_shutdown")
        return True

    def _parse_time_duration(self, lower: str) -> int | None:
        """Parse duration like '2 години', '30 хвилин', '1 годину 30 хвилин'."""
        total = 0
        # Hours
        m = re.search(r'(\d+)\s*(?:годин|год|hour|hours|г(?!\w))', lower)
        if m:
            total += int(m.group(1)) * 3600
        # Minutes
        m = re.search(r'(\d+)\s*(?:хвилин|хв|min|minutes)', lower)
        if m:
            total += int(m.group(1)) * 60
        # Seconds
        m = re.search(r'(\d+)\s*(?:секунд|сек|sec|seconds)', lower)
        if m:
            total += int(m.group(1))
        return total if total > 0 else None

    # ═══════════════════════════════════════════════════════════
    # AUTO-TYPING
    # ═══════════════════════════════════════════════════════════

    def _handle_autotype(self, text: str, lower: str) -> bool:
        kw = ["надрукуй", "введи текст", "напиши у вікно", "type:", "autotype",
              "напиши текст"]
        if not any(k in lower for k in kw):
            return False
        # Extract text after keyword
        type_text = text
        for kw_item in ["надрукуй", "введи текст", "напиши у вікно",
                        "type:", "autotype", "напиши текст"]:
            idx = lower.find(kw_item.lower())
            if idx != -1:
                type_text = text[idx + len(kw_item):].strip()
                break
        if not type_text:
            self.respond_silent("⌨ Після команди вкажіть текст для введення")
            return True

        try:
            import pyautogui  # noqa: F401
        except ImportError:
            self.respond_silent("⌨ pyautogui не встановлено: pip install pyautogui")
            return True

        self.respond_silent(f"⌨ Введу через 1 секунду: «{type_text[:50]}»")

        def _do_type():
            import time as _time
            import pyautogui as _pag
            _pag.PAUSE = 0
            _time.sleep(1)
            try:
                _pag.typewrite(type_text, interval=0.03)
            except Exception as e:
                self._respond_signal.emit(f"⌨ Помилка введення: {str(e)[:40]}")

        threading.Thread(target=_do_type, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # SCREEN OCR
    # ═══════════════════════════════════════════════════════════

    def _handle_screen_ocr(self, text: str, lower: str) -> bool:
        kw = ["що на екрані", "прочитай екран", "screen ocr",
              "що написано на екрані", "аналізуй екран", "розпізнай екран"]
        if not any(k in lower for k in kw):
            return False

        self.respond_silent("📸 Знімаю екран і аналізую...")

        def _ocr_thread():
            import tempfile
            tmp_path = None
            try:
                # Take screenshot
                try:
                    from PIL import ImageGrab
                    img = ImageGrab.grab()
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                        tmp_path = f.name
                    img.save(tmp_path)
                except Exception:
                    try:
                        import mss
                        with mss.mss() as sct:
                            mon = sct.monitors[1]
                            sct_img = sct.grab(mon)
                            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                                tmp_path = f.name
                            mss.tools.to_png(sct_img.rgb, sct_img.size, output=tmp_path)
                    except Exception as ee:
                        self._respond_signal.emit(f"📸 Не вдалось зробити скріншот: {ee}")
                        return

                if tmp_path is None:
                    self._respond_signal.emit("📸 Не вдалось зробити скріншот")
                    return

                # Try Gemini Vision first
                google_key = self.config.get("google_key", "")
                if google_key:
                    try:
                        import google.generativeai as genai
                        from pathlib import Path as _Path
                        import base64 as _b64
                        genai.configure(api_key=google_key)
                        model = genai.GenerativeModel("gemini-1.5-flash")
                        img_data = _Path(tmp_path).read_bytes()
                        response = model.generate_content([
                            {"mime_type": "image/png",
                             "data": _b64.b64encode(img_data).decode()},
                            "Що зображено на цьому екрані? Опиши детально українською."
                        ])
                        result = response.text
                        self._respond_signal.emit(f"📸 <b>Аналіз екрану:</b>\n{result[:500]}")
                        return
                    except Exception:
                        pass

                # Fallback: pytesseract OCR
                try:
                    import pytesseract
                    from PIL import Image as _Img
                    img = _Img.open(tmp_path)
                    ocr_text = pytesseract.image_to_string(img, lang="ukr+eng")
                    if ocr_text.strip():
                        self._respond_signal.emit(
                            f"📸 <b>Текст на екрані:</b>\n{ocr_text[:500]}")
                    else:
                        self._respond_signal.emit("📸 Тексту на екрані не знайдено")
                except ImportError:
                    self._respond_signal.emit(
                        "📸 Встанови pytesseract для OCR або налаштуй Google API")
            finally:
                if tmp_path:
                    try:
                        import os as _os
                        _os.unlink(tmp_path)
                    except Exception:
                        pass

        threading.Thread(target=_ocr_thread, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # INTERNET SPEED TEST
    # ═══════════════════════════════════════════════════════════

    def _handle_speedtest(self, text: str, lower: str) -> bool:
        kw = ["швидкість інтернету", "internet speed", "перевір інтернет",
              "speed test", "speedtest", "швидкість мережі"]
        if not any(k in lower for k in kw):
            return False

        self.respond_silent("🌐 Перевіряю швидкість інтернету...")

        def _speed_thread():
            # Try speedtest-cli
            try:
                import speedtest as _st
                s = _st.Speedtest()
                s.get_best_server()
                down = s.download() / 1e6
                up   = s.upload()   / 1e6
                ping = s.results.ping
                self._respond_signal.emit(
                    f"🌐 <b>Швидкість інтернету:</b>\n"
                    f"⬇ Завантаження: <b>{down:.1f} Мбіт/с</b>\n"
                    f"⬆ Вивантаження: <b>{up:.1f} Мбіт/с</b>\n"
                    f"⚡ Пінг: <b>{ping:.0f} мс</b>")
                return
            except ImportError:
                pass
            except Exception as e:
                print(f"[Speedtest] error: {e}")

            # Fallback: time a Cloudflare download
            if not HAS_REQUESTS:
                self._respond_signal.emit("🌐 pip install speedtest-cli requests")
                return
            try:
                import time as _t
                url = "https://speed.cloudflare.com/__down?bytes=10000000"
                start = _t.time()
                r = _requests.get(url, timeout=30, stream=True)
                total = 0
                for chunk in r.iter_content(65536):
                    total += len(chunk)
                elapsed = _t.time() - start
                mbps = (total * 8 / 1e6) / elapsed if elapsed > 0 else 0
                self._respond_signal.emit(
                    f"🌐 <b>Швидкість завантаження:</b> ~{mbps:.1f} Мбіт/с\n"
                    f"(тест Cloudflare, {total//1024}KB за {elapsed:.1f}с)")
            except Exception as e:
                self._respond_signal.emit(f"🌐 Помилка тесту швидкості: {str(e)[:60]}")

        threading.Thread(target=_speed_thread, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # WHO'S ON WIFI
    # ═══════════════════════════════════════════════════════════

    def _handle_wifi_devices(self, text: str, lower: str) -> bool:
        kw = ["хто в мережі", "хто підключений", "wifi devices",
              "пристрої в мережі", "сусіди по wifi", "хто в wifi"]
        if not any(k in lower for k in kw):
            return False

        self.respond_silent("📡 Сканую мережу...")

        def _arp_thread():
            import subprocess as _sp
            try:
                result = _sp.run(["arp", "-a"], capture_output=True,
                                 text=True, timeout=15)
                lines = result.stdout.strip().split("\n")
                devices = []
                for line in lines:
                    # Match IP and MAC
                    m = re.search(
                        r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+'
                        r'([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}'
                        r'(?:[:-][0-9a-fA-F]{2}){3})',
                        line)
                    if m:
                        ip, mac = m.group(1), m.group(2)
                        if not ip.startswith("224.") and not ip.endswith(".255"):
                            devices.append((ip, mac))
                if devices:
                    lines_out = [f"📡 <b>Пристрої в мережі ({len(devices)}):</b>"]
                    for ip, mac in devices[:20]:
                        lines_out.append(f"• {ip} — <code>{mac}</code>")
                    self._respond_signal.emit("\n".join(lines_out))
                else:
                    self._respond_signal.emit("📡 Пристроїв не знайдено (або немає доступу)")
            except Exception as e:
                self._respond_signal.emit(f"📡 Помилка сканування: {str(e)[:60]}")

        threading.Thread(target=_arp_thread, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # FILE SEARCH
    # ═══════════════════════════════════════════════════════════

    def _handle_file_search(self, text: str, lower: str) -> bool:
        kw = ["знайди файл", "шукай файл", "find file",
              "де файл", "знайди папку", "пошукай файл"]
        if not any(k in lower for k in kw):
            return False

        # Extract filename
        filename = text
        for kw_item in ["знайди файл", "шукай файл", "find file",
                        "де файл", "знайди папку", "пошукай файл"]:
            idx = lower.find(kw_item.lower())
            if idx != -1:
                filename = text[idx + len(kw_item):].strip().strip("\"'")
                break
        if not filename:
            self.respond_silent("🔍 Вкажіть ім'я файлу. Приклад: «знайди файл звіт.docx»")
            return True

        self.respond_silent(f"🔍 Шукаю: «{filename}»...")

        def _search_thread():
            import pathlib as _pl
            home = _pl.Path.home()
            search_dirs = [
                home / "Desktop",
                home / "Documents",
                home / "Downloads",
                home,
            ]
            found = []
            fname_lower = filename.lower()
            for sdir in search_dirs:
                if not sdir.exists():
                    continue
                try:
                    for root, dirs, files in os.walk(str(sdir)):
                        # Limit depth to 4
                        depth = len(_pl.Path(root).relative_to(sdir).parts)
                        if depth > 4:
                            dirs.clear()
                            continue
                        for f in files:
                            if fname_lower in f.lower():
                                found.append(str(_pl.Path(root) / f))
                                if len(found) >= 5:
                                    break
                        if len(found) >= 5:
                            break
                except PermissionError:
                    pass
                if len(found) >= 5:
                    break

            if not found:
                self._respond_signal.emit(
                    f"🔍 Файл «{filename}» не знайдено в Desktop/Documents/Downloads")
                return

            lines = [f"🔍 <b>Знайдено ({len(found)}):</b>"]
            for f in found:
                lines.append(f"• <code>{f}</code>")
            self._respond_signal.emit("\n".join(lines))
            # Open first match
            try:
                os.startfile(found[0])
                self._respond_signal.emit(f"📂 Відкриваю: {_pl.Path(found[0]).name}")
            except Exception:
                pass

        threading.Thread(target=_search_thread, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # DAILY ACTIVITY SUMMARY
    # ═══════════════════════════════════════════════════════════

    def _handle_daily_summary(self, text: str, lower: str) -> bool:
        kw = ["що я робив сьогодні", "підсумок дня", "daily summary",
              "звіт за день", "що зробив сьогодні", "підбий підсумок"]
        if not any(k in lower for k in kw):
            return False

        self.respond_silent("📊 Збираю підсумок дня...")

        def _summary_thread():
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            parts = [f"📊 <b>Підсумок дня — {now.strftime('%d.%m.%Y')}</b>\n"]

            # Notes
            try:
                notes = []
                if self._notes_file.exists():
                    raw = json.loads(self._notes_file.read_text(encoding="utf-8"))
                    notes = [n for n in (raw if isinstance(raw, list) else [])
                             if today_str in n.get("ts", "")
                             or today_str in n.get("date", "")]
                if notes:
                    parts.append(f"📝 Нотатки сьогодні ({len(notes)}): "
                                 + ", ".join(n.get("text", "")[:30] for n in notes[:3]))
            except Exception:
                pass

            # Tasks
            try:
                tasks_today = []
                if self._todo_file.exists():
                    raw = json.loads(self._todo_file.read_text(encoding="utf-8"))
                    for t in (raw if isinstance(raw, list) else []):
                        if today_str in t.get("ts", "") or today_str in t.get("date", ""):
                            tasks_today.append(t)
                if tasks_today:
                    done = [t for t in tasks_today if t.get("done")]
                    parts.append(f"✅ Завдань сьогодні: {len(tasks_today)} "
                                 f"(виконано: {len(done)})")
            except Exception:
                pass

            # Habits
            try:
                if self._habits_file.exists():
                    raw = json.loads(self._habits_file.read_text(encoding="utf-8"))
                    done_habits = [
                        info.get("name", k) for k, info in raw.items()
                        if today_str in info.get("done_dates", [])
                    ]
                    if done_habits:
                        parts.append(f"🏆 Звички виконано: {', '.join(done_habits[:5])}")
            except Exception:
                pass

            # Reminders today
            try:
                fired = [
                    r.get("text", str(r)) if isinstance(r, dict) else str(r)
                    for dt, r in self.reminders
                    if dt.date() == now.date()
                ]
                if fired:
                    parts.append(f"🔔 Нагадування: {', '.join(fired[:3])}")
            except Exception:
                pass

            if len(parts) == 1:
                parts.append("Сьогодні немає записів у нотатках, задачах чи звичках.")

            summary = "\n".join(parts)
            self._respond_signal.emit(summary[:600])
            self._tg_notify(summary[:600])

        threading.Thread(target=_summary_thread, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # FOCUS MODE
    # ═══════════════════════════════════════════════════════════

    def _handle_focus_mode(self, text: str, lower: str) -> bool:
        enable_kw  = ["увімкни фокус", "режим фокусу", "focus mode",
                      "не турбувати", "вимкни відволікання", "фокус на"]
        disable_kw = ["вимкни фокус", "скасуй фокус", "exit focus",
                      "вийти з фокусу", "вимкни режим фокусу"]

        if any(k in lower for k in disable_kw):
            self._stop_focus_mode()
            return True
        if not any(k in lower for k in enable_kw):
            return False

        # Parse duration
        minutes = 25  # default pomodoro
        m = re.search(r'(\d+)\s*(?:хвилин|хв|min)', lower)
        if m:
            minutes = int(m.group(1))
        else:
            m2 = re.search(r'(\d+)\s*(?:годин|год|h(?!\w))', lower)
            if m2:
                minutes = int(m2.group(1)) * 60
            m3 = re.search(r'(\d+)\s*(?:годин|год)[^\d]+(\d+)\s*(?:хвилин|хв)', lower)
            if m3:
                minutes = int(m3.group(1)) * 60 + int(m3.group(2))

        self._start_focus_mode(minutes)
        return True

    def _start_focus_mode(self, minutes: int):
        """Enable focus mode for given minutes."""
        self._focus_mode = True
        # Stop existing timer
        if self._focus_timer:
            self._focus_timer.stop()

        self._focus_timer = QTimer()
        self._focus_timer.setSingleShot(True)
        self._focus_timer.timeout.connect(self._stop_focus_mode_auto)
        self._focus_timer.start(minutes * 60 * 1000)

        msg = f"🎯 Фокус-режим: {minutes} хвилин. Вдалої роботи!"
        self.respond_silent(msg)
        self._tg_notify(f"🎯 <b>Фокус-режим увімкнено</b> на {minutes} хвилин")

    def _stop_focus_mode(self):
        """Manually disable focus mode."""
        self._focus_mode = False
        if self._focus_timer:
            self._focus_timer.stop()
            self._focus_timer = None
        self.respond_silent("✅ Фокус-режим вимкнено")
        self._tg_notify("✅ <b>Фокус-режим вимкнено</b>")

    def _stop_focus_mode_auto(self):
        """Called by timer when focus session ends."""
        self._focus_mode = False
        self._focus_timer = None
        self.jarvis.play("confirm")
        self.respond("🎯 Фокус-сесія завершена! Час відпочити.")
        self._tg_notify("🎯 <b>Фокус-сесія завершена!</b> Час відпочити.")

    # ═══════════════════════════════════════════════════════════
    # SCREENSHOT → TELEGRAM
    # ═══════════════════════════════════════════════════════════

    def _handle_screenshot_tg(self, text: str, lower: str) -> bool:
        kw = ["зроби скрін і відправ", "скріншот в телеграм", "send screenshot",
              "відправ скріншот", "зроби скрін телеграм", "screenshot telegram",
              "надішли скріншот", "скрін в телеграм", "скріншот телеграм"]
        if not any(k in lower for k in kw):
            return False

        target = self._tg_chat_id or self._tg_notify_chat_id
        if not target:
            self.respond_silent(
                "📸 Telegram не підключено.\n"
                "Надішли будь-яке повідомлення боту — і я запам'ятаю куди відправляти."
            )
            return True

        if not (self._telegram_bot and self._telegram_bot.isRunning()):
            self.respond_silent("📸 Telegram бот не запущений")
            return True

        self.respond_silent("📸 Роблю скріншот і відправляю...")

        def _do_shot():
            try:
                import tempfile
                img_path = None

                # Try mss first (fast, no display driver needed)
                try:
                    import mss
                    with mss.mss() as sct:
                        shot = sct.grab(sct.monitors[0])
                        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                        img_path = tmp.name
                        tmp.close()
                        from PIL import Image as _Img
                        _Img.frombytes("RGB", shot.size, shot.rgb).save(img_path)
                except Exception:
                    pass

                # Fallback: PIL ImageGrab
                if not img_path or not os.path.exists(img_path):
                    try:
                        from PIL import ImageGrab
                        img = ImageGrab.grab()
                        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                        img_path = tmp.name
                        tmp.close()
                        img.save(img_path)
                    except Exception:
                        pass

                if not img_path or not os.path.exists(img_path):
                    self._respond_signal.emit(
                        "📸 Не вдалося зробити скріншот.\n"
                        "Встанови: pip install mss Pillow"
                    )
                    return

                # Send photo to Telegram
                try:
                    with open(img_path, "rb") as f:
                        from datetime import datetime as _dt
                        caption = f"📸 Скріншот AXIS OS · {_dt.now().strftime('%H:%M:%S')}"
                        r = self._telegram_bot._sess.post(
                            f"{self._telegram_bot._base}/sendPhoto",
                            data={"chat_id": target, "caption": caption},
                            files={"photo": f},
                            timeout=30,
                        )
                    if r.ok:
                        self._respond_signal.emit("📸 Скріншот відправлено в Telegram!")
                    else:
                        self._respond_signal.emit(
                            f"📸 Помилка відправки: {r.status_code} {r.text[:80]}"
                        )
                finally:
                    try:
                        os.unlink(img_path)
                    except Exception:
                        pass
            except Exception as e:
                self._respond_signal.emit(f"📸 Помилка: {str(e)[:80]}")

        threading.Thread(target=_do_shot, daemon=True).start()
        return True

    # ═══════════════════════════════════════════════════════════
    # DAILY AUTO-BACKUP
    # ═══════════════════════════════════════════════════════════

    def _start_backup_scheduler(self):
        """Start background thread that backs up data files daily at 23:50."""
        def _backup_loop():
            import time as _t
            while True:
                now = datetime.now()
                # Target: 23:50 today (or tomorrow if already past)
                target = now.replace(hour=23, minute=50, second=0, microsecond=0)
                if target <= now:
                    target = target + timedelta(days=1)
                wait_secs = (target - now).total_seconds()
                # Sleep in 1-hour chunks so we don't drift too much
                while wait_secs > 0:
                    _t.sleep(max(0, min(wait_secs, 3600)))
                    wait_secs -= 3600
                    if datetime.now() >= target:
                        break
                self._do_backup()

        threading.Thread(target=_backup_loop, daemon=True).start()

    def _do_backup(self):
        """Zip notes/tasks/habits/memory into backups/YYYY-MM-DD.zip. Keep last 7."""
        try:
            import zipfile
            import aivon_sphere as _sphere_mod
            backup_dir = _sphere_mod.USER_DATA_DIR / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            zip_path = backup_dir / f"{date_str}.zip"

            files_to_backup = [
                getattr(self, "_notes_file",   None),
                getattr(self, "_todo_file",    None),
                getattr(self, "_habits_file",  None),
                getattr(self, "_memory_file",  None),
                getattr(self, "_alarms_file",  None),
            ]

            backed_up = []
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fp in files_to_backup:
                    if fp and isinstance(fp, Path) and fp.exists():
                        zf.write(fp, fp.name)
                        backed_up.append(fp.name)

            # Keep only last 7 backups
            all_zips = sorted(backup_dir.glob("*.zip"))
            while len(all_zips) > 7:
                try:
                    all_zips[0].unlink()
                except Exception:
                    pass
                all_zips = all_zips[1:]

            if backed_up:
                print(f"[Backup] ✅ {zip_path.name}: {', '.join(backed_up)}")
                self._tg_notify(
                    f"💾 <b>Автобекап завершено</b>\n"
                    f"📦 {zip_path.name}\n"
                    f"📄 Файли: {', '.join(backed_up)}"
                )
        except Exception as e:
            print(f"[Backup] ❌ помилка: {e}")

    # ═══════════════════════════════════════════════════════════
    # GOOGLE CALENDAR
    # ═══════════════════════════════════════════════════════════

    def _handle_calendar(self, text: str, lower: str) -> bool:
        kw = ["що сьогодні в календарі", "мої зустрічі", "google calendar",
              "заплановано на сьогодні", "додай подію", "календар",
              "зустрічі сьогодні"]
        if not any(k in lower for k in kw):
            return False

        import aivon_sphere as _sphere_mod
        creds_file = _sphere_mod.USER_DATA_DIR / "google_credentials.json"
        if not creds_file.exists():
            self.respond_silent(
                "📅 Google Calendar не налаштовано.\n"
                "Додай data/google_credentials.json — інструкція:\n"
                "https://developers.google.com/calendar/api/quickstart/python")
            return True

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            self.respond_silent(
                "📅 Встанови бібліотеки: pip install google-auth google-auth-oauthlib "
                "google-auth-httplib2 google-api-python-client")
            return True

        self.respond_silent("📅 Завантажую події з Google Calendar...")

        def _cal_thread():
            try:
                creds_data = json.loads(creds_file.read_text(encoding="utf-8"))
                creds = Credentials.from_authorized_user_info(creds_data)
                service = build("calendar", "v3", credentials=creds)
                now_iso = datetime.utcnow().isoformat() + "Z"
                # End of today
                from datetime import datetime as _dt
                eod = _dt.utcnow().replace(hour=23, minute=59, second=59)
                eod_iso = eod.isoformat() + "Z"
                events_result = service.events().list(
                    calendarId="primary",
                    timeMin=now_iso,
                    timeMax=eod_iso,
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                events = events_result.get("items", [])
                if not events:
                    self._respond_signal.emit("📅 Сьогодні подій немає")
                    return
                lines = ["📅 <b>Сьогодні в календарі:</b>"]
                for ev in events:
                    start = ev["start"].get("dateTime", ev["start"].get("date", ""))
                    try:
                        t = _dt.fromisoformat(start.replace("Z", "+00:00"))
                        t_str = t.strftime("%H:%M")
                    except Exception:
                        t_str = start
                    lines.append(f"• {t_str} — {ev.get('summary', '(без назви)')}")
                self._respond_signal.emit("\n".join(lines))
            except Exception as e:
                self._respond_signal.emit(f"📅 Помилка Calendar: {str(e)[:80]}")

        threading.Thread(target=_cal_thread, daemon=True).start()
        return True
