# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/automation.py  –  Макроси та автоматизація                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Extracted from aivon_sphere.py  (lines 2400–2841 + 5313–5566)              ║
║                                                                              ║
║  Standalone classes:                                                         ║
║    Win32 INPUT structs + helpers  (_send_input, _key_down, _key_up)         ║
║    MacroEngine   – voice-attack-style macro recorder/runner                 ║
║    AutomationEngine – trigger-based UI automation via Win32                 ║
║                                                                              ║
║  Mixin class:                                                                ║
║    SphereAutomationMixin  – automation handler methods for AivonSphere      ║
╚══════════════════════════════════════════════════════════════════════════════╝

NOTE: All self.* accesses in SphereAutomationMixin work via multiple
      inheritance (SphereAutomationMixin + AivonSphere).
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
import uuid as _uuid

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ── Optional psutil ────────────────────────────────────────────────────────────
try:
    import psutil as _psutil
    HAS_PSUTIL = True
except ImportError:
    _psutil = None  # type: ignore
    HAS_PSUTIL = False

# ── Paths ──────────────────────────────────────────────────────────────────────
_appdata = os.environ.get("APPDATA") or str(Path.home())
_USER_DATA_DIR = Path(_appdata) / "AXIS OS"
_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
MACROS_FILE = _USER_DATA_DIR / "macros.json"


# ═══════════════════════════════════════════════════════════
# Win32 Input Simulation — constants, structs, helpers
# ═══════════════════════════════════════════════════════════

INPUT_MOUSE    = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP   = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_MOVE        = 0x0001
MOUSEEVENTF_LEFTDOWN    = 0x0002
MOUSEEVENTF_LEFTUP      = 0x0004
MOUSEEVENTF_RIGHTDOWN   = 0x0008
MOUSEEVENTF_RIGHTUP     = 0x0010
MOUSEEVENTF_MIDDLEDOWN  = 0x0020
MOUSEEVENTF_MIDDLEUP    = 0x0040
MOUSEEVENTF_ABSOLUTE    = 0x8000

# Virtual Key Codes
VK_MAP = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "ctrl": 0xA2, "lctrl": 0xA2, "rctrl": 0xA3,
    "shift": 0xA0, "lshift": 0xA0, "rshift": 0xA1,
    "alt": 0xA4, "lalt": 0xA4, "ralt": 0xA5,
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
    "capslock": 0x14, "numlock": 0x90, "scrolllock": 0x91,
    "printscreen": 0x2C, "pause": 0x13,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46,
    "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
    "m": 0x4D, "n": 0x4E, "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52,
    "s": 0x53, "t": 0x54, "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58,
    "y": 0x59, "z": 0x5A,
    "volumeup": 0xAF, "volumedown": 0xAE, "volumemute": 0xAD,
    "volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD,
    "playpause": 0xB3, "nexttrack": 0xB0, "prevtrack": 0xB1,
    "media_play_pause": 0xB3, "media_next": 0xB0, "media_prev": 0xB1,
    "play_pause": 0xB3, "next_track": 0xB0, "prev_track": 0xB1,
    "print_screen": 0x2C, "prtsc": 0x2C,
    "=": 0xBB, "+": 0xBB, "-": 0xBD, "minus": 0xBD, "equals": 0xBB,
    "`": 0xC0, "~": 0xC0, "tilde": 0xC0, "backtick": 0xC0,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
    "[": 0xDB, "]": 0xDD, "\\": 0xDC,
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


def _send_input(*inputs):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    ctypes.windll.user32.SendInput(n, arr, ctypes.sizeof(INPUT))


def _key_down(vk):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    return inp

def _key_up(vk):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    inp.union.ki.dwFlags = KEYEVENTF_KEYUP
    return inp


# ═══════════════════════════════════════════════════════════
# MACRO ENGINE (Voice Attack style)
# ═══════════════════════════════════════════════════════════

class MacroEngine:
    """Движок макросів — як Voice Attack"""

    def __init__(self, app_launcher=None):
        self.macros = []
        self.profiles = ["default"]
        self.active_profile = "default"
        self.app_launcher = app_launcher  # used for safe app/cmd resolution
        self.load()

    # ── Завантаження / Збереження ──

    def load(self):
        if MACROS_FILE.exists():
            try:
                with open(MACROS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.macros = data.get("macros", [])
                self.profiles = data.get("profiles", ["default"])
                self.active_profile = data.get("active_profile", "default")
            except Exception:
                self.macros = []
        self._create_defaults()

    def save(self):
        data = {
            "macros": self.macros,
            "profiles": self.profiles,
            "active_profile": self.active_profile
        }
        with open(MACROS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _create_defaults(self):
        if not self.macros:
            self.macros = [
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Копіювати",
                    "triggers": ["копіюй", "copy", "скопіюй"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "ctrl+c"}]
                },
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Вставити",
                    "triggers": ["встав", "paste", "вставити"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "ctrl+v"}]
                },
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Відмінити",
                    "triggers": ["відміни", "undo", "назад"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "ctrl+z"}]
                },
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Зберегти",
                    "triggers": ["збережи", "save", "зберегти"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "ctrl+s"}]
                },
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Скріншот області",
                    "triggers": ["скрін області", "screenshot area"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "win+shift+s"}]
                },
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Закрити вкладку",
                    "triggers": ["закрий вкладку", "close tab"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "ctrl+w"}]
                },
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Нова вкладка",
                    "triggers": ["нова вкладка", "new tab"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "ctrl+t"}]
                },
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Перемкнути вікно",
                    "triggers": ["наступне вікно", "switch window"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "alt+tab"}]
                },
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Робочий стіл",
                    "triggers": ["покажи робочий стіл", "show desktop"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "win+d"}]
                },
                {
                    "id": str(_uuid.uuid4())[:8],
                    "name": "Закрити програму",
                    "triggers": ["закрий програму", "close app"],
                    "profile": "default",
                    "enabled": True,
                    "steps": [{"type": "hotkey", "value": "alt+f4"}]
                },
            ]
            self.save()

    # ── Пошук макросу по фразі ──

    def find_macro(self, text):
        lower = text.lower()
        for macro in self.macros:
            if not macro.get("enabled", True):
                continue
            profile = macro.get("profile", "default")
            if profile != "default" and profile != self.active_profile:
                continue
            for trigger in macro.get("triggers", []):
                if trigger.lower() in lower:
                    return macro
        return None

    # ── Виконання макросу (в окремому потоці) ──

    def execute(self, macro, callback=None, speak_callback=None):
        """Запускає виконання макросу в фоновому потоці"""
        self._speak_cb = speak_callback
        t = threading.Thread(target=self._run_steps, args=(macro, callback), daemon=True)
        t.start()

    def _run_steps(self, macro, callback=None):
        steps = macro.get("steps", [])
        name = macro.get("name", "?")
        print(f"[Macro] Running '{name}' ({len(steps)} steps)")
        for i, step in enumerate(steps):
            try:
                self._exec_step(step)
            except Exception as e:
                print(f"[Macro] Step {i} error: {e}")
        if callback:
            callback(name)

    def _exec_step(self, step):
        stype = step.get("type", "")
        value = step.get("value", "")

        if stype == "wait":
            ms = int(value) if value else 500
            time.sleep(ms / 1000.0)

        elif stype == "key":
            vk = VK_MAP.get(value.lower())
            if vk:
                _send_input(_key_down(vk), _key_up(vk))
                time.sleep(0.05)

        elif stype == "hotkey":
            keys = [k.strip().lower() for k in value.split("+")]
            vks = [VK_MAP.get(k) for k in keys]
            vks = [v for v in vks if v is not None]
            # Press all down
            for vk in vks:
                _send_input(_key_down(vk))
                time.sleep(0.02)
            # Release all up (reverse)
            for vk in reversed(vks):
                _send_input(_key_up(vk))
                time.sleep(0.02)

        elif stype == "type_text":
            for ch in value:
                inp_down = INPUT()
                inp_down.type = INPUT_KEYBOARD
                inp_down.union.ki.wScan = ord(ch)
                inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE
                inp_up = INPUT()
                inp_up.type = INPUT_KEYBOARD
                inp_up.union.ki.wScan = ord(ch)
                inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                _send_input(inp_down, inp_up)
                time.sleep(0.02)

        elif stype == "url":
            # Security: only allow http/https URLs in macros
            if value.startswith(("http://", "https://")):
                webbrowser.open(value)
            else:
                print(f"[Security] Macro 'url' step blocked — non-http URL: {value!r}")

        elif stype == "app":
            # Security: only run absolute paths to existing files, or resolve via app_launcher
            _resolved_app = None
            if os.path.isabs(value) and os.path.isfile(value):
                _resolved_app = value
            elif self.app_launcher:
                try:
                    _found = self.app_launcher.find_multi(value)
                    if _found:
                        _resolved_app = _found[0][1]
                except Exception:
                    pass
            if _resolved_app:
                try:
                    subprocess.Popen([_resolved_app], creationflags=_NO_WINDOW)
                except Exception:
                    os.startfile(_resolved_app)
            else:
                print(f"[Security] Macro 'app' step blocked — unresolved value: {value!r}")
                if self._speak_cb:
                    self._speak_cb("команда заблокована з міркувань безпеки")

        elif stype == "cmd":
            # Security: only run absolute paths to existing executables, or resolve via app_launcher
            _resolved_cmd = None
            if os.path.isabs(value) and os.path.isfile(value):
                _resolved_cmd = value
            elif self.app_launcher:
                try:
                    _found_cmd_list = self.app_launcher.find_multi(value)
                    if _found_cmd_list:
                        _resolved_cmd = _found_cmd_list[0][1]
                except Exception:
                    pass
            if _resolved_cmd:
                subprocess.Popen([_resolved_cmd], creationflags=_NO_WINDOW)
            else:
                print(f"[Security] Macro 'cmd' step blocked — unresolved value: {value!r}")
                if self._speak_cb:
                    self._speak_cb("команда заблокована з міркувань безпеки")

        elif stype == "mouse_move":
            parts = value.split(",")
            if len(parts) >= 2:
                x, y = int(parts[0].strip()), int(parts[1].strip())
                ctypes.windll.user32.SetCursorPos(x, y)

        elif stype == "mouse_click":
            parts = value.split(",")
            btn = parts[0].strip().lower() if parts else "left"
            if len(parts) >= 3:
                x, y = int(parts[1].strip()), int(parts[2].strip())
                ctypes.windll.user32.SetCursorPos(x, y)
                time.sleep(0.05)
            if btn == "left":
                flags_down, flags_up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
            elif btn == "right":
                flags_down, flags_up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
            else:
                flags_down, flags_up = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
            inp_down = INPUT()
            inp_down.type = INPUT_MOUSE
            inp_down.union.mi.dwFlags = flags_down
            inp_up = INPUT()
            inp_up.type = INPUT_MOUSE
            inp_up.union.mi.dwFlags = flags_up
            _send_input(inp_down, inp_up)

        elif stype == "focus_window":
            hwnd = ctypes.windll.user32.FindWindowW(None, value)
            if not hwnd:
                # Часткове співпадіння
                import ctypes.wintypes
                EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                found = [None]
                def _cb(h, _):
                    buf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetWindowTextW(h, buf, 256)
                    if value.lower() in buf.value.lower():
                        found[0] = h
                        return False
                    return True
                ctypes.windll.user32.EnumWindows(EnumWindowsProc(_cb), 0)
                hwnd = found[0]
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)

        elif stype == "speak":
            print(f"[Macro] speak: {value}")
            if hasattr(self, '_speak_cb') and self._speak_cb:
                try:
                    self._speak_cb(value)
                except Exception:
                    pass

    # ── CRUD операції ──

    def add_macro(self, name, triggers, steps, profile="default"):
        macro = {
            "id": str(_uuid.uuid4())[:8],
            "name": name,
            "triggers": triggers if isinstance(triggers, list) else [triggers],
            "profile": profile,
            "enabled": True,
            "steps": steps
        }
        self.macros.append(macro)
        self.save()
        return macro

    def update_macro(self, macro_id, data):
        for i, m in enumerate(self.macros):
            if m.get("id") == macro_id:
                self.macros[i].update(data)
                self.save()
                return True
        return False

    def delete_macro(self, macro_id):
        self.macros = [m for m in self.macros if m.get("id") != macro_id]
        self.save()

    def get_all(self):
        return {"macros": self.macros, "profiles": self.profiles, "active_profile": self.active_profile}

    def set_profile(self, profile):
        self.active_profile = profile
        if profile not in self.profiles:
            self.profiles.append(profile)
        self.save()

    def add_profile(self, profile):
        if profile not in self.profiles:
            self.profiles.append(profile)
            self.save()

    def delete_profile(self, profile):
        if profile != "default" and profile in self.profiles:
            self.profiles.remove(profile)
            self.macros = [m for m in self.macros if m.get("profile") != profile]
            if self.active_profile == profile:
                self.active_profile = "default"
            self.save()


# ═══════════════════════════════════════════════════════════
# AUTOMATION ENGINE — trigger-based UI automation
# ═══════════════════════════════════════════════════════════

class AutomationEngine:
    """
    Рушій автоматизацій — відстежує тригери та запускає ланцюги дій.

    Структура автоматизації (з sphere_config.json, ключ "automations"):
    {
        "id": "auto_1",
        "name": "Назва",
        "trigger": {"type": "app_launch"|"app_close"|"time"|"voice_trigger"|"pc_idle",
                    "app": "steam.exe",     # для app_launch/app_close
                    "time": "09:00",        # для time
                    "phrase": "слово",      # для voice_trigger
                    "idle_minutes": 15},    # для pc_idle
        "actions": [
            {"type": "mode",  "value": "game"},
            {"type": "macro", "name": "Назва макросу"},
            {"type": "spotify", "action": "pause"|"play"},
            {"type": "speak", "text": "Текст"},
            {"type": "shell", "command": "notepad"},
            {"type": "notification", "title": "Заголовок", "message": "Текст"},
        ],
        "enabled": true
    }
    """

    CHECK_INTERVAL = 10  # seconds between app/idle checks

    def __init__(self, sphere):
        self._sphere = sphere
        self._running = False
        self._thread: threading.Thread | None = None
        self._running_apps: set = set()
        self._last_time_triggers: dict = {}  # id → last triggered date
        self._last_input_check: float = time.time()

    @property
    def automations(self) -> list:
        return self._sphere.config.get("automations", [])

    def start(self):
        """Запустити фоновий моніторинг тригерів."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print("[AutoEngine] Запущено")

    def stop(self):
        self._running = False

    def _monitor_loop(self):
        while self._running:
            try:
                self._check_app_triggers()
                self._check_time_triggers()
                self._check_idle_triggers()
            except Exception as e:
                print(f"[AutoEngine] Помилка моніторингу: {e}")
            time.sleep(self.CHECK_INTERVAL)

    def _get_running_processes(self) -> set:
        """Повертає set імен запущених процесів (в нижньому регістрі)."""
        names = set()
        if HAS_PSUTIL:
            try:
                for p in _psutil.process_iter(['name']):
                    n = (p.info.get('name') or '').lower()
                    if n:
                        names.add(n)
            except Exception:
                pass
        elif sys.platform == "win32":
            try:
                out = subprocess.check_output(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    creationflags=_NO_WINDOW, timeout=5
                ).decode(errors="replace")
                import csv, io
                for row in csv.reader(io.StringIO(out)):
                    if row:
                        names.add(row[0].strip('"').lower())
            except Exception:
                pass
        return names

    def _check_app_triggers(self):
        current_apps = self._get_running_processes()
        launched = current_apps - self._running_apps
        closed = self._running_apps - current_apps
        self._running_apps = current_apps

        try:
            autos = list(self.automations)
        except Exception:
            autos = []
        for auto in autos:
            if not auto.get("enabled", True):
                continue
            trigger = auto.get("trigger", {})
            t_type = trigger.get("type", "")
            app_name = (trigger.get("app") or "").lower()
            if not app_name:
                continue
            if t_type == "app_launch" and any(app_name in a for a in launched):
                print(f"[AutoEngine] Тригер app_launch: {app_name}")
                self._run_automation(auto)
            elif t_type == "app_close" and any(app_name in a for a in closed):
                print(f"[AutoEngine] Тригер app_close: {app_name}")
                self._run_automation(auto)

    def _check_time_triggers(self):
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.date().isoformat()
        try:
            autos = list(self.automations)
        except Exception:
            autos = []
        for auto in autos:
            if not auto.get("enabled", True):
                continue
            trigger = auto.get("trigger", {})
            if trigger.get("type") != "time":
                continue
            t_time = trigger.get("time", "")
            if t_time == current_time:
                last = self._last_time_triggers.get(auto.get("id", ""))
                if last != today:
                    self._last_time_triggers[auto.get("id", "")] = today
                    print(f"[AutoEngine] Тригер time: {t_time}")
                    self._run_automation(auto)

    def _check_idle_triggers(self):
        """Перевірити idle-тригери (тільки Windows)."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            elapsed_ms = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            idle_min = elapsed_ms / 60000.0
        except Exception:
            return

        try:
            autos = list(self.automations)
        except Exception:
            autos = []
        for auto in autos:
            if not auto.get("enabled", True):
                continue
            trigger = auto.get("trigger", {})
            if trigger.get("type") != "pc_idle":
                continue
            threshold = float(trigger.get("idle_minutes", 15))
            auto_id = auto.get("id", "")
            if idle_min >= threshold:
                # Only trigger once per idle session (reset when user returns)
                if not self._last_time_triggers.get(f"idle_{auto_id}"):
                    self._last_time_triggers[f"idle_{auto_id}"] = True
                    print(f"[AutoEngine] Тригер pc_idle: {idle_min:.1f} хв")
                    self._run_automation(auto)
            else:
                # User is active — reset idle flag
                self._last_time_triggers.pop(f"idle_{auto_id}", None)

    def trigger_voice(self, phrase: str):
        """Перевірити voice_trigger автоматизації. Виклик з on_recognized."""
        phrase_lower = phrase.lower()
        try:
            autos = list(self.automations)
        except Exception:
            autos = []
        for auto in autos:
            if not auto.get("enabled", True):
                continue
            trigger = auto.get("trigger", {})
            if trigger.get("type") != "voice_trigger":
                continue
            t_phrase = (trigger.get("phrase") or "").lower()
            if t_phrase and t_phrase in phrase_lower:
                print(f"[AutoEngine] Тригер voice_trigger: {t_phrase}")
                self._run_automation(auto)
                return True
        return False

    def _run_automation(self, automation: dict):
        """Виконати всі дії автоматизації в фоновому потоці."""
        threading.Thread(
            target=self._execute_actions,
            args=(automation,),
            daemon=True
        ).start()

    def _execute_actions(self, automation: dict):
        """Послідовно виконати дії автоматизації."""
        sphere = self._sphere
        name = automation.get("name", "Автоматизація")
        actions = automation.get("actions", [])
        print(f"[AutoEngine] Запуск '{name}' ({len(actions)} дій)")
        for action in actions:
            try:
                a_type = action.get("type", "")
                if a_type == "mode":
                    mode_val = action.get("value", "normal")
                    # Thread-safe call via Qt signal
                    sphere._respond_signal.emit(f"_AUTO_MODE_{mode_val}")
                    # Actually call directly since we're in daemon thread
                    from PyQt6.QtCore import QTimer as _QT2
                    _QT2.singleShot(0, lambda m=mode_val: sphere._set_mode(m))
                elif a_type == "macro":
                    macro_name = action.get("name", "")
                    if macro_name:
                        # Find macro by name and run it
                        if hasattr(sphere, 'macro_engine'):
                            sphere.macro_engine.run(macro_name)
                elif a_type == "spotify":
                    try:
                        subprocess.Popen(
                            ['powershell', '-Command',
                             '(new-object -com wscript.shell).SendKeys([char]179)'],
                            creationflags=_NO_WINDOW
                        )
                    except Exception:
                        pass
                elif a_type == "speak":
                    speak_text = action.get("text", "")
                    if speak_text:
                        sphere._respond_signal.emit(speak_text)
                elif a_type == "shell":
                    cmd = action.get("command", "")
                    if cmd:
                        subprocess.Popen(cmd, shell=True, creationflags=_NO_WINDOW)
                elif a_type == "notification":
                    title = action.get("title", "AIVON")
                    message = action.get("message", "")
                    try:
                        from plyer import notification as _notif
                        _notif.notify(title=title, message=message, timeout=8)
                    except Exception:
                        pass
                time.sleep(0.3)  # Brief pause between actions
            except Exception as e:
                print(f"[AutoEngine] Помилка дії {action}: {e}")


# ═══════════════════════════════════════════════════════════
# SPHERE AUTOMATION MIXIN
# ═══════════════════════════════════════════════════════════

class SphereAutomationMixin:
    """Automation handler methods. Mixed into AivonSphere."""

    # All macro/automation interaction goes through self.macro_engine and
    # self.automation_engine, which are initialised in AivonSphere.__init__.
    # This mixin is a placeholder that groups the automation-related init
    # logic and any future automation-specific helper methods.

    def _init_automation(self):
        """Called from AivonSphere.__init__ to set up automation subsystems."""
        # macro_engine and automation_engine are already created inline in
        # AivonSphere.__init__; this method exists for future use.
        pass
