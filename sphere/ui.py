# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/ui.py  –  SphereUIMixin: UI drawing, animations, tray, gestures     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Mixin: SphereUIMixin                                                        ║
║  HandGestureThread (MediaPipe gesture recognition)                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import math
import os
import sys
import subprocess
import threading
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMenu, QSystemTrayIcon, QLineEdit,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QFileSystemWatcher
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QRadialGradient, QPen, QFont, QIcon, QPixmap,
)

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

try:
    import cv2
    import mediapipe as _mp
    HAS_GESTURE = True
except ImportError:
    HAS_GESTURE = False


# ══════════════════════════════════════════════════════════════════════════════
# HandGestureThread — MediaPipe Tasks API 0.10+
# ══════════════════════════════════════════════════════════════════════════════

class HandGestureThread(QThread):
    """Розпізнавання жестів руки через MediaPipe Tasks API 0.10+.
    Автоматично завантажує модель hand_landmarker.task при першому запуску.
    Жести:
      open_palm  — відкрита долоня  → зупинити TTS
      fist       — кулак            → замовкни + сховатись
      thumbs_up  — великий палець ↑ → підтвердити
      point_right— вказівний →      → наступний трек
      point_left — вказівний ←      → попередній трек
    """
    gesture = pyqtSignal(str)

    OPEN_PALM   = "open_palm"
    FIST        = "fist"
    THUMBS_UP   = "thumbs_up"
    POINT_RIGHT = "point_right"
    POINT_LEFT  = "point_left"

    _COOLDOWN    = 2.0   # секунди між однаковими жестами
    _MODEL_URL   = ("https://storage.googleapis.com/mediapipe-models/"
                    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task")
    _MODEL_NAME  = "hand_landmarker.task"

    def __init__(self):
        super().__init__()
        self._running  = False
        self._last_time: dict = {}

    def stop(self):
        self._running = False

    def _cooldown_ok(self, g: str) -> bool:
        now = time.time()
        if now - self._last_time.get(g, 0) < self._COOLDOWN:
            return False
        self._last_time[g] = now
        return True

    def _get_model_path(self) -> "str | None":
        """Повертає шлях до моделі, завантажує якщо відсутня."""
        from pathlib import Path as _Path
        try:
            _app_dir = _Path(sys.executable).parent if getattr(sys, 'frozen', False) else _Path(__file__).parent.parent
        except Exception:
            _app_dir = _Path(".")
        candidates = [
            _app_dir / "data" / self._MODEL_NAME,
        ]
        try:
            appdata = os.environ.get("APPDATA") or str(_Path.home())
            candidates.append(_Path(appdata) / "AXIS OS" / self._MODEL_NAME)
        except Exception:
            pass

        for p in candidates:
            if p.exists():
                return str(p)

        save_to = candidates[-1]
        print(f"[Gesture] Завантажую модель ({self._MODEL_URL}) → {save_to}")
        try:
            import urllib.request
            save_to.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(self._MODEL_URL, str(save_to))
            print(f"[Gesture] Модель завантажена: {save_to}")
            return str(save_to)
        except Exception as e:
            print(f"[Gesture] Помилка завантаження моделі: {e}")
            return None

    def _classify(self, lm) -> str:
        """lm — список NormalizedLandmark з Tasks API."""
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        fingers_up = sum(1 for t, p in zip(tips, pips) if lm[t].y < lm[p].y)
        thumb_up   = lm[4].y < lm[3].y

        if fingers_up == 4:
            return self.OPEN_PALM
        if fingers_up == 0 and not thumb_up:
            return self.FIST
        if thumb_up and fingers_up == 0:
            return self.THUMBS_UP
        if lm[8].y < lm[6].y and lm[12].y > lm[10].y:
            dx = lm[8].x - lm[5].x
            if   dx >  0.08: return self.POINT_RIGHT
            elif dx < -0.08: return self.POINT_LEFT
        return ""

    def run(self):
        if not HAS_GESTURE:
            print("[Gesture] opencv-python/mediapipe не встановлено")
            return

        model_path = self._get_model_path()
        if not model_path:
            print("[Gesture] Модель недоступна — жести вимкнено")
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[Gesture] Камера недоступна")
            return

        from mediapipe.tasks import python as _mp_python
        from mediapipe.tasks.python import vision as _mp_vision

        base_opts = _mp_python.BaseOptions(model_asset_path=model_path)
        opts = _mp_vision.HandLandmarkerOptions(
            base_options=base_opts,
            running_mode=_mp_vision.RunningMode.IMAGE,
            num_hands=1,
            min_hand_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )

        self._running = True
        print("[Gesture] ✋ Жести рукою активовано (MediaPipe 0.10+)")

        with _mp_vision.HandLandmarker.create_from_options(opts) as landmarker:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = _mp.Image(
                    image_format=_mp.ImageFormat.SRGB,
                    data=rgb
                )
                result = landmarker.detect(mp_image)
                if result.hand_landmarks:
                    lm = result.hand_landmarks[0]
                    g  = self._classify(lm)
                    if g and self._cooldown_ok(g):
                        print(f"[Gesture] 👋 {g}")
                        self.gesture.emit(g)
                time.sleep(0.05)

        cap.release()
        print("[Gesture] Камера закрита")


# ══════════════════════════════════════════════════════════════════════════════
# SphereUIMixin — UI methods mixed into AivonSphere
# ══════════════════════════════════════════════════════════════════════════════

class SphereUIMixin:
    """
    UI methods for AivonSphere: hologram, tray, config watching,
    paintEvent, all _viz_* painters, mouse/key events, gestures,
    show_orb / hide_orb / animate, text-input popup.
    """

    # ── Hologram ──────────────────────────────────────────────────────────────

    def _start_holo_server(self):
        """Запустити локальний HTTP сервер для голограми (потрібно для FBX/GLB)"""
        import http.server, socketserver, functools
        from pathlib import Path as _P
        _app_dir = _P(sys.executable).parent if getattr(sys, 'frozen', False) else _P(__file__).parent.parent
        self._holo_port = 8090
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(_app_dir))
        def try_port(port):
            try:
                httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
                httpd.timeout = 0.5
                t = threading.Thread(target=httpd.serve_forever, daemon=True)
                t.start()
                self._holo_port = port
                self._holo_httpd = httpd
                print(f"[Hologram] HTTP server on port {port} → {_app_dir}")
                return True
            except OSError:
                return False
        if not try_port(8090):
            for port in range(8091, 8100):
                if try_port(port):
                    break

    def _init_hologram(self):
        """Ініціалізація 3D голограми через QWebEngineView"""
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        from PyQt6.QtGui import QColor as _QC
        from pathlib import Path as _P
        _app_dir = _P(sys.executable).parent if getattr(sys, 'frozen', False) else _P(__file__).parent.parent
        self._start_holo_server()
        self._holo_view = QWebEngineView(self)
        self._holo_view.setFixedSize(self.width(), self.height())
        self._holo_view.move(0, 0)
        self._holo_view.page().setBackgroundColor(_QC(0, 0, 0, 0))
        self._holo_view.setStyleSheet("background:transparent;")
        settings = self._holo_view.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        holo_path = _app_dir / "sphere_hologram.html"
        if holo_path.exists():
            self._holo_view.setUrl(QUrl(f"http://127.0.0.1:{self._holo_port}/sphere_hologram.html"))
            print(f"[Hologram] Loaded via http://127.0.0.1:{self._holo_port}")
            self.jarvis.set_hologram(self._holo_view, self._holo_port)
        else:
            print("[Hologram] sphere_hologram.html not found!")
            self.hologram_mode = False
        self._holo_view.show()

    def _sync_hologram_state(self):
        """Синхронізація стану сфери з 3D голограмою"""
        if not self.hologram_mode or not self._holo_view:
            return
        state_map = {self.IDLE: 'idle', self.LISTENING: 'listening',
                     self.THINKING: 'thinking', self.SPEAKING: 'speaking'}
        new_state = state_map.get(self.state, 'idle')
        if new_state != self._holo_state:
            self._holo_state = new_state
            self._holo_view.page().runJavaScript(f"window.setState('{new_state}')")

    def hologram_gesture(self, name, duration=2.5):
        """Програти жест на голограмі: wave, no, nod, point, shrug, bow, excited, sad, explain, laugh"""
        if not self.hologram_mode or not self._holo_view:
            return
        self._holo_view.page().runJavaScript(f"window.playGesture('{name}',{duration})")

    def hologram_auto_gesture(self, text):
        """Автоматичний вибір жесту за контекстом тексту відповіді"""
        if not self.hologram_mode or not self._holo_view:
            return
        lower = text.lower() if text else ""
        if any(w in lower for w in ["привіт", "привет", "hello", "вітаю", "доброго", "добрий"]):
            self.hologram_gesture('wave', 3)
            return
        if any(w in lower for w in ["не можу", "не вмію", "не знаю як", "на жаль", "вибач",
                                      "не вдалось", "помилка", "неможливо", "нет", "ні,", "ні "]):
            self.hologram_gesture('no', 2)
            return
        if any(w in lower for w in ["звичайно", "так,", "так!", "зроблено", "готово", "виконано",
                                      "будь ласка", "добре", "окей", "зрозуміло"]):
            self.hologram_gesture('nod', 2)
            return
        if any(w in lower for w in ["не знаю", "можливо", "мабуть", "важко сказати", "не впевнен"]):
            self.hologram_gesture('shrug', 2.5)
            return
        if any(w in lower for w in ["чудово", "відмінно", "супер", "класно", "вітаю",
                                      "молодець", "прекрасно", "ура", "🎉", "🎊"]):
            self.hologram_gesture('excited', 2.5)
            return
        if any(w in lower for w in ["шкода", "сумно", "жаль", "проблема", "погано",
                                      "невдача", "сумую", "😢", "😞"]):
            self.hologram_gesture('sad', 2.5)
            return
        if any(w in lower for w in ["ха-ха", "хаха", "😂", "🤣", "жарт", "смішно",
                                      "кумедно", "лол", "😄"]):
            self.hologram_gesture('laugh', 2)
            return
        if len(lower) > 80 or any(w in lower for w in ["пояснюю", "розповім", "ось як",
                                                          "по-перше", "тому що", "справа в"]):
            self.hologram_gesture('explain', 3)
            return
        if any(w in lower for w in ["дякую", "до зустрічі", "бувай", "на добраніч"]):
            self.hologram_gesture('bow', 2)
            return
        if any(w in lower for w in ["подивись", "відкриваю", "ось", "запускаю", "шукаю"]):
            self.hologram_gesture('point', 2)
            return
        if currentState := getattr(self, 'state', None):
            if currentState == self.SPEAKING:
                self.hologram_gesture('explain', 2)

    # ── Tray ──────────────────────────────────────────────────────────────────

    def setup_tray(self):
        """Системний трей"""
        from PyQt6.QtWidgets import QMenu as _QMenu
        from pathlib import Path as _P
        _app_dir = _P(sys.executable).parent if getattr(sys, 'frozen', False) else _P(__file__).parent.parent
        self.tray = QSystemTrayIcon(self)
        icon_path = _app_dir / "data" / "icon_sphere.ico"
        if icon_path.exists():
            self.tray.setIcon(QIcon(str(icon_path)))
        else:
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(0, 212, 255))
            self.tray.setIcon(QIcon(pixmap))
        self.tray.setToolTip("AIVON - Voice Assistant")
        tray_menu = _QMenu()
        tray_menu.setStyleSheet("""
            QMenu { background: #1a1a2e; color: white; border: 1px solid #333; }
            QMenu::item:selected { background: #00d4ff; color: black; }
        """)
        tray_menu.addAction("🔮 Показати", self.show_orb)
        tray_menu.addAction("🔇 Сховати", self.hide_orb)
        tray_menu.addSeparator()
        tray_menu.addAction("🎛️ Панель керування", self.open_panel)
        tray_menu.addSeparator()
        mode_menu = tray_menu.addMenu("🎭 Режим")
        mode_menu.setStyleSheet("""
            QMenu { background: #1a1a2e; color: white; border: 1px solid #333; }
            QMenu::item:selected { background: #00d4ff; color: black; }
        """)
        for _m_key, _m_cfg in self._MODE_CONFIGS.items():
            _m_label = f"{_m_cfg['icon']} {_m_cfg['label']}"
            _action = mode_menu.addAction(_m_label)
            _action.setCheckable(True)
            _action.setChecked(getattr(self, '_mode', 'normal') == _m_key)
            _action.triggered.connect(lambda checked, mk=_m_key: self._set_mode(mk))
        tray_menu.addSeparator()
        self.autostart_action = tray_menu.addAction("🚀 Автозапуск з Windows")
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self._is_autostart_enabled())
        self.autostart_action.triggered.connect(self._toggle_autostart)
        tray_menu.addSeparator()
        tray_menu.addAction("❌ Вийти", self.quit_app)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self.on_tray_click)
        self.tray.show()

    def on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.is_hidden:
                self.show_orb()
            else:
                self.hide_orb()

    def _is_autostart_enabled(self):
        """Перевірити чи Sphere в автозапуску Windows"""
        try:
            startup_dir = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            shortcut = os.path.join(startup_dir, "AIVON Sphere.lnk")
            return os.path.exists(shortcut)
        except Exception:
            return False

    def _toggle_autostart(self, checked):
        """Увімкнути/вимкнути автозапуск з Windows"""
        from pathlib import Path as _P
        _app_dir = _P(sys.executable).parent if getattr(sys, 'frozen', False) else _P(__file__).parent.parent
        try:
            startup_dir = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            shortcut = os.path.join(startup_dir, "AIVON Sphere.lnk")
            if checked:
                if getattr(sys, 'frozen', False):
                    target_path = str(sys.executable)
                    arguments   = ""
                else:
                    pythonw = sys.executable.replace('python.exe', 'pythonw.exe')
                    if not os.path.exists(pythonw):
                        pythonw = sys.executable
                    target_path = pythonw
                    arguments   = f'"{_app_dir / "aivon_sphere.py"}"'
                ps = f'''
                $ws = New-Object -ComObject WScript.Shell
                $s = $ws.CreateShortcut("{shortcut}")
                $s.TargetPath = "{target_path}"
                $s.Arguments = '{arguments}'
                $s.WorkingDirectory = "{_app_dir}"
                $s.Description = "AIVON Voice Assistant"
                $s.Save()
                '''
                subprocess.run(['powershell', '-Command', ps],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=_NO_WINDOW)
                self.respond("🚀 Автозапуск увімкнено! Sphere запускатиметься з Windows.")
            else:
                if os.path.exists(shortcut):
                    os.remove(shortcut)
                self.respond("⏹ Автозапуск вимкнено.")
        except Exception as e:
            self.respond(f"Помилка: {str(e)[:30]}")

    def open_panel(self):
        """Відкрити панель AXIS OS"""
        from pathlib import Path as _P
        _app_dir = _P(sys.executable).parent if getattr(sys, 'frozen', False) else _P(__file__).parent.parent
        if getattr(sys, 'frozen', False):
            panel_exe = _app_dir / "AXIS_OS.exe"
            if not panel_exe.exists():
                panel_exe = _app_dir.parent / "AXIS_OS.exe"
            if not panel_exe.exists():
                self.respond("Панель AXIS OS не знайдена (AXIS_OS.exe)")
                return
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] == 'AXIS_OS.exe':
                            self.respond("Панель AXIS OS вже відкрита!")
                            return
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except ImportError:
                pass
            try:
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
                subprocess.Popen([str(panel_exe)], cwd=str(_app_dir), creationflags=flags)
                self.respond("Відкриваю AXIS OS!")
            except Exception as e:
                self.respond(f"Помилка запуску: {str(e)[:40]}")
        else:
            panel_py = _app_dir / "main.py"
            if not panel_py.exists():
                panel_py = _app_dir / "axis_ide.py"
            if not panel_py.exists():
                self.respond("Панель AXIS OS не знайдена (main.py)")
                return
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'cmdline']):
                    try:
                        cmdline = ' '.join(proc.info.get('cmdline') or [])
                        if panel_py.name in cmdline:
                            self.respond("Панель AXIS OS вже відкрита!")
                            return
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except ImportError:
                pass
            try:
                pythonw = sys.executable.replace('python.exe', 'pythonw.exe')
                if not os.path.exists(pythonw):
                    pythonw = sys.executable
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
                subprocess.Popen([pythonw, str(panel_py)], cwd=str(_app_dir),
                                 creationflags=flags, close_fds=True)
                self.respond("Відкриваю AXIS OS!")
            except Exception as e:
                self.respond(f"Помилка запуску: {str(e)[:40]}")

    # ── Wake / Gesture helpers ────────────────────────────────────────────────

    def start_wake_listener(self):
        """Запуск фонового прослуховування"""
        from sphere.audio import WakeWordThread as _WWT
        from sphere.config import load_config as _lc
        _cfg = getattr(self, 'config', _lc())
        _default_name = _cfg.get("sphere_name", "Aivon")
        self.wake_thread = _WWT(
            _cfg.get("language", "uk-UA"),
            _default_name,
        )
        self.wake_thread.wake_detected.connect(self.on_wake_word)
        self.wake_thread.start()

    def _start_gesture_listener(self):
        """Запуск розпізнавання жестів руки (потребує MediaPipe + OpenCV)."""
        if not HAS_GESTURE:
            print("[Gesture] Бібліотеки недоступні — pip install opencv-python mediapipe")
            return
        self.gesture_thread = HandGestureThread()
        self.gesture_thread.gesture.connect(self._on_gesture)
        self.gesture_thread.start()
        print("[Gesture] ✋ Жести рукою увімкнено")

    def on_wake_word(self, mode='greeting'):
        """Wake word виявлено"""
        print(f"[Wake] ✅ Activation! mode={mode}")
        self.show_orb()
        self.continuous_listen = True
        if mode == 'greeting':
            self.hologram_gesture('wave', 3)
            self.jarvis.play_greeting()
            self.state = self.SPEAKING
            self.response_text = "Слухаю! 🎤"
            self.update()
            QTimer.singleShot(1500, self._force_listen)
        else:
            if self.config.get("bhv_recog_sound", True):
                self.jarvis.play("activate")
            self.state = self.LISTENING
            self.response_text = "🎤"
            self.update()
            QTimer.singleShot(300, self._force_listen)

    def _force_listen(self):
        """Примусове слухання — ігнорує _tts_busy (для wake word)"""
        print("[Wake] → _force_listen()")
        self._tts_busy = False
        self._tts_queue.clear()
        if self.wake_thread:
            self.wake_thread.pause()
        self._do_listen()

    # ── Gesture handlers ──────────────────────────────────────────────────────

    def _on_gesture(self, gesture: str):
        """Обробник жесту від HandGestureThread."""
        _GESTURE_MAP = {
            HandGestureThread.OPEN_PALM:   "stop_tts",
            HandGestureThread.FIST:        "hide",
            HandGestureThread.THUMBS_UP:   "confirm",
            HandGestureThread.POINT_RIGHT: "next_track",
            HandGestureThread.POINT_LEFT:  "prev_track",
        }
        action = _GESTURE_MAP.get(gesture, "none")
        print(f"[Gesture] {gesture} → action={action}")
        self.jarvis.play("confirm")
        self._execute_gesture_action(action)

    def _execute_gesture_action(self, action: str):
        """Виконує дію жесту за назвою."""
        if action == "stop_tts":
            self.respond_silent("✋ Стоп")
            self._stop_tts()
        elif action == "hide":
            self.respond_silent("🤫")
            self.continuous_listen = False
            QTimer.singleShot(1500, self.hide_orb)
        elif action == "confirm":
            self.respond_silent("👍 Добре!")
        elif action == "next_track":
            self.respond_silent("⏭ Наступна")
            self._handle_music("наступна пісня")
        elif action == "prev_track":
            self.respond_silent("⏮ Попередня")
            self._handle_music("попередня пісня")
        elif action == "volume_up":
            self._adjust_volume(+20)
            self.respond_silent("🔊 Гучніше")
        elif action == "volume_down":
            self._adjust_volume(-20)
            self.respond_silent("🔉 Тихіше")
        elif action == "screenshot":
            self._take_screenshot()
        elif action == "show_panel":
            self.open_panel()
            self.respond_silent("📋 Панель")
        elif action == "none":
            pass

    # ── show / hide / quit / animate ─────────────────────────────────────────

    def showEvent(self, event):
        """Вимкнути Windows 11 Mica/Acrylic та rounded corners через DWM."""
        super().showEvent(event)
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 38,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int)
            )
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass

    def show_orb(self):
        """Показати сферу"""
        self.is_hidden = False
        self.show()
        self.raise_()
        self.activateWindow()
        if self.wake_thread:
            self.wake_thread.pause()

    def hide_orb(self):
        """Сховати в тихий режим"""
        self.is_hidden = True
        self.continuous_listen = False
        self.hide()
        self.state = self.IDLE
        self.user_text = ""
        self.response_text = ""
        if self.wake_thread:
            self.wake_thread.resume()
        print("Silent mode. Say 'Privet Aivon'...")

    def quit_app(self):
        """Вихід"""
        if self.wake_thread:
            self.wake_thread.stop()
            self.wake_thread.wait(1000)
        if self.gesture_thread:
            self.gesture_thread.stop()
            self.gesture_thread.wait(1500)
        if self.work_monitor:
            self.work_monitor.stop()
            self.work_monitor.wait(1000)
        if self._telegram_bot:
            self._telegram_bot.stop()
            self._telegram_bot.wait(2000)
        QApplication.quit()

    def animate(self):
        import random
        self._sync_hologram_state()
        self.phase += 0.06
        speeds = [0.018, 0.013, 0.022, 0.009, 0.016]
        for i in range(5):
            self.rings[i] = (self.rings[i] + speeds[i]) % (2 * math.pi)
        for i in range(6):
            self.inner_phase[i] += 0.03 + i * 0.008
        if self.state == self.LISTENING:
            self.waves = [random.randint(18, 50) for _ in range(9)]
        elif self.state == self.SPEAKING:
            self.waves = [abs(math.sin(self.phase * 2.5 + i * 0.8)) * 40 + 8 for i in range(9)]
        elif self.state == self.THINKING:
            self.waves = [abs(math.sin(self.phase * 3 + i * 0.5)) * 25 for i in range(9)]
        else:
            self.waves = [max(0, w - 2) for w in self.waves]
        new_p = []
        for (a, d, sp, life) in self.particles:
            life -= 0.008
            if life <= 0:
                a = random.uniform(0, 2 * math.pi)
                d = random.uniform(0.6, 1.0)
                sp = random.uniform(0.005, 0.02)
                life = random.uniform(0.5, 1.0)
            else:
                a += sp
                d += 0.001
            new_p.append((a, d, sp, life))
        self.particles = new_p
        self.update()

    # ── Config watching ───────────────────────────────────────────────────────

    def _on_config_file_changed(self, path: str):
        """Спрацьовує МИТТЄВО коли sphere_config.json змінено (QFileSystemWatcher)"""
        QTimer.singleShot(50, self._reload_sphere_config)
        if not self._cfg_watcher.files():
            from sphere.config import SPHERE_CONFIG_FILE as _SCF
            if _SCF.exists():
                self._cfg_watcher.addPath(str(_SCF))

    def _reload_sphere_config(self):
        """Зчитує і застосовує нові налаштування сфери"""
        from sphere.config import SPHERE_CONFIG_FILE as _SCF, load_sphere_config as _lsc
        try:
            if not _SCF.exists():
                return
            mtime = _SCF.stat().st_mtime
            self._config_mtime = mtime
            new_sphere_cfg = _lsc()
            new_cfg = dict(self.config)
            new_cfg.update(new_sphere_cfg)
            self._apply_sphere_config(new_cfg)
            self.config = new_cfg
            print("[SphereConfig] ✅ Миттєво оновлено з sphere_config.json")
        except Exception as e:
            print(f"[SphereConfig] ⚠️ Помилка миттєвого оновлення: {e}")

    def _check_config_reload(self):
        """Fallback-перевірка кожні 10 сек (якщо watcher не спрацював)"""
        from sphere.config import SPHERE_CONFIG_FILE as _SCF
        try:
            if not _SCF.exists():
                return
            mtime = _SCF.stat().st_mtime
            if mtime <= self._config_mtime:
                return
            self._reload_sphere_config()
            if not self._cfg_watcher.files():
                self._cfg_watcher.addPath(str(_SCF))
        except Exception as e:
            print(f"[SphereConfig] ⚠️ Fallback помилка: {e}")

    def _apply_sphere_config(self, new_cfg):
        """Живе застосування змін налаштувань сфери"""
        from sphere.audio import WhisperSTT as _WSTT, HAS_WHISPER as _HW
        old = self.config

        new_op = new_cfg.get("sphere_opacity", 90)
        if new_op != old.get("sphere_opacity", 90):
            self.setWindowOpacity(max(0.3, min(1.0, new_op / 100.0)))

        new_size = new_cfg.get("sphere_size", "medium")
        if new_size != old.get("sphere_size", "medium") and not self.hologram_mode:
            sizes = {"small": (280, 320), "medium": (320, 380), "large": (380, 440)}
            w, h = sizes.get(new_size, sizes["medium"])
            self.setFixedSize(w, h)
            self._reposition(new_cfg.get("sphere_position", "bottom-right"), w, h)

        new_pos = new_cfg.get("sphere_position", "bottom-right")
        if new_pos != old.get("sphere_position", "bottom-right") and not self.hologram_mode:
            sizes = {"small": (280, 320), "medium": (320, 380), "large": (380, 440)}
            w, h = sizes.get(new_cfg.get("sphere_size", "medium"), sizes["medium"])
            self._reposition(new_pos, w, h)

        new_particles = new_cfg.get("sphere_particles", True)
        new_count = new_cfg.get("sphere_particle_count", 20)
        if not new_particles:
            self.particles = []
        elif new_count != old.get("sphere_particle_count", 20):
            import random
            while len(self.particles) < new_count:
                self.particles.append((random.uniform(0, 6.28), random.uniform(0.6, 1.0),
                                       random.uniform(0.005, 0.02), random.uniform(0.5, 1.0)))
            self.particles = self.particles[:new_count]

        _default_name = "Aivon"
        new_name = new_cfg.get("sphere_name", _default_name).strip()
        old_name = old.get("sphere_name", _default_name).strip()
        if new_name != old_name and self.wake_thread:
            self.wake_thread.update_name(new_name)
            print(f"[Config] Ім'я асистента → '{new_name}'")
        new_wake = new_cfg.get("sphere_wake", "").strip().lower()
        old_wake = old.get("sphere_wake", "").strip().lower()
        if new_wake != old_wake and self.wake_thread:
            self.wake_thread.update_name(new_wake)
            print(f"[Config] Wake word → '{new_wake}'")

        new_tg_enabled = bool(new_cfg.get("telegram_enabled", False))
        old_tg_enabled = bool(old.get("telegram_enabled", False))
        new_tg_token   = new_cfg.get("telegram_token", "")
        old_tg_token   = old.get("telegram_token", "")
        if new_tg_enabled != old_tg_enabled or new_tg_token != old_tg_token:
            if new_tg_enabled and new_tg_token:
                self._start_telegram_bot(cfg=new_cfg)
            elif self._telegram_bot:
                self._telegram_bot.stop()
                self._telegram_bot = None
                self.respond_silent("📱 Telegram бот вимкнено")
        elif self._telegram_bot and self._telegram_bot.isRunning():
            new_cmds = new_cfg.get("telegram_commands", [])
            old_cmds = old.get("telegram_commands", [])
            if new_cmds != old_cmds:
                self._telegram_bot.update_commands(new_cmds)
                self._telegram_bot._register_bot_menu()
                self.respond_silent(f"📱 Telegram: оновлено {len(new_cmds)} команд")

        new_gestures = bool(new_cfg.get("hand_gestures", False))
        old_gestures = bool(old.get("hand_gestures", False))
        if new_gestures != old_gestures:
            if new_gestures:
                self._start_gesture_listener()
            else:
                if self.gesture_thread:
                    self.gesture_thread.stop()
                    self.gesture_thread = None

        new_stt = new_cfg.get("stt_provider", "google")
        old_stt = old.get("stt_provider", "google")
        if new_stt != old_stt:
            if new_stt == "whisper" and _HW:
                self._load_whisper_model()
            elif new_stt == "google":
                _WSTT._instance = None
                import gc; gc.collect()
                self.respond_silent("🔄 Перемкнено на Google STT")

    def _reposition(self, position, w, h):
        """Перемістити сферу на нову позицію"""
        screen = QApplication.primaryScreen().geometry()
        positions = {
            "bottom-right": (screen.width() - w - 20, screen.height() - h - 20),
            "bottom-left":  (20, screen.height() - h - 20),
            "center":       ((screen.width() - w) // 2, (screen.height() - h) // 2),
            "top-right":    (screen.width() - w - 20, 20),
        }
        x, y = positions.get(position, positions["bottom-right"])
        self.move(x, y)

    # ── paintEvent ────────────────────────────────────────────────────────────

    def paintEvent(self, e):
        if self.hologram_mode:
            p = QPainter(self)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(self.rect(), QColor(0, 0, 0, 0))
            p.end()
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        w, h = self.width(), self.height()
        cx, cy = w // 2, 130

        base1 = self.config.get("sphere_color",  "#ff1493" if self.sphere_mode == "dialog" else "#00d4ff")
        base2 = self.config.get("sphere_color2", "#8a2be2" if self.sphere_mode == "dialog" else "#7b2cbf")
        state_colors = {
            self.IDLE:      (QColor(base1), QColor(base2)),
            self.LISTENING: (QColor(base1).lighter(125), QColor(base2).lighter(125)),
            self.THINKING:  (QColor(255, 200, 60), QColor(220, 120, 0)),
            self.SPEAKING:  (QColor(base1).darker(110), QColor(base2).darker(110)),
        }
        c1, c2 = state_colors.get(self.state, state_colors[self.IDLE])
        if getattr(self, '_agent_color', None):
            try:
                ac = QColor(self._agent_color)
                c1 = QColor(ac.red(), ac.green(), ac.blue(), 255)
                c2 = QColor(max(0, ac.red()-60), max(0, ac.green()-60), max(0, ac.blue()-60), 255)
            except Exception:
                pass

        pulse = 1 + 0.08 * math.sin(self.phase)
        R = int(65 * pulse)
        viz = self.config.get("sphere_visual", "plasma")

        if viz == "neon":
            self._viz_neon(p, cx, cy, R, c1, c2, pulse)
        elif viz in ("fire", "wave-sunset"):
            self._viz_fire(p, cx, cy, R, c1, c2, pulse)
        elif viz == "matrix_viz":
            self._viz_matrix(p, cx, cy, R, c1, c2, pulse)
        elif viz == "holo":
            self._viz_holo(p, w, h, cx, cy, R, c1, c2, pulse)
        elif viz == "music-bars":
            self._viz_music_bars(p, cx, cy, R, c1, c2)
        elif viz == "music-sine":
            self._viz_music_sine(p, w, cx, cy, R, c1, c2)
        elif viz == "music-spectrum":
            self._viz_music_spectrum(p, cx, cy, R, c1, c2)
        elif viz == "music-pulse":
            self._viz_music_pulse(p, cx, cy, R, c1, c2, pulse)
        elif viz == "aurora":
            self._viz_aurora(p, cx, cy, R, c1, c2, pulse)
        elif viz == "glitch":
            self._viz_glitch(p, cx, cy, R, c1, c2, pulse)
        elif viz == "liquid":
            self._viz_liquid(p, cx, cy, R, c1, c2, pulse)
        else:
            self._viz_plasma(p, cx, cy, R, c1, c2, pulse)

        if viz not in ("music-bars", "music-sine", "music-spectrum", "music-pulse"):
            if any(wv > 3 for wv in self.waves):
                p.save()
                p.translate(cx, cy)
                n = len(self.waves)
                for i, amp in enumerate(self.waves):
                    if amp > 3:
                        bar_a = min(220, int(amp * 4.5))
                        bar_g = QRadialGradient((i - n // 2) * 8, 0, int(amp * 0.8))
                        bar_g.setColorAt(0, QColor(255, 255, 255, bar_a))
                        bar_g.setColorAt(1, QColor(c1.red(), c1.green(), c1.blue(), bar_a // 3))
                        p.setBrush(QBrush(bar_g))
                        p.setPen(Qt.PenStyle.NoPen)
                        p.drawRoundedRect((i - n // 2) * 8 - 2, int(-amp / 2), 4, int(amp), 2, 2)
                p.restore()

        ty = cy + R + 22
        if self.user_text:
            p.setFont(QFont("Segoe UI", 10))
            txt = self.user_text[:38] + "..." if len(self.user_text) > 40 else self.user_text
            p.setBrush(QBrush(QColor(8, 10, 22, 190)))
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), 35), 1))
            p.drawRoundedRect(16, ty, w - 32, 30, 10, 10)
            p.setPen(QColor(210, 220, 235, 230))
            p.drawText(22, ty, w - 44, 30, Qt.AlignmentFlag.AlignCenter, f'"{txt}"')
            ty += 36

        if self.response_text:
            p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            txt = self.response_text[:38] + "..." if len(self.response_text) > 40 else self.response_text
            p.setBrush(QBrush(QColor(c1.red(), c1.green(), c1.blue(), 20)))
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), 60), 1))
            p.drawRoundedRect(16, ty, w - 32, 36, 10, 10)
            p.setPen(QColor(c1.red(), c1.green(), c1.blue(), 245))
            p.drawText(22, ty, w - 44, 36, Qt.AlignmentFlag.AlignCenter, txt)
            ty += 42

        status = ["", "🎤 Слухаю...", "🧠 Думаю...", "💬 Говорю..."][self.state]
        if status:
            p.setFont(QFont("Segoe UI", 9))
            p.setPen(QColor(190, 200, 210, 130))
            p.drawText(0, ty, w, 20, Qt.AlignmentFlag.AlignCenter, status)
            ty += 22

        if self.sphere_mode == "dialog":
            try:
                from sphere.tts import VOICE_ROLE_NAMES, VOICE_PROVIDER_NAMES
            except ImportError:
                VOICE_ROLE_NAMES = {}
                VOICE_PROVIDER_NAMES = {}
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            role_name = VOICE_ROLE_NAMES.get(getattr(self, 'dialog_role', 'assistant'), 'Асистент')
            prov_name = VOICE_PROVIDER_NAMES.get(getattr(self, 'dialog_provider', 'gemini'), 'AI')
            badge_text = f"🗣️ {role_name} • {prov_name}"
            badge_w = max(120, len(badge_text) * 8)
            p.setBrush(QBrush(QColor(120, 80, 255, 40)))
            p.setPen(QPen(QColor(180, 100, 255, 100), 1))
            p.drawRoundedRect(w // 2 - badge_w // 2, ty, badge_w, 20, 8, 8)
            p.setPen(QColor(200, 140, 255, 220))
            p.drawText(0, ty, w, 20, Qt.AlignmentFlag.AlignCenter, badge_text)

        _btn_sz = 28
        self._gesture_btn_rect = (w - _btn_sz - 6,  6,          _btn_sz, _btn_sz)
        self._stt_btn_rect     = (6,                  6,          _btn_sz, _btn_sz)
        self._tg_btn_rect      = (6,                  h - _btn_sz - 6, _btn_sz, _btn_sz)
        self._ti_btn_rect      = (w - _btn_sz - 6,  h - _btn_sz - 6, _btn_sz, _btn_sz)

        gesture_on  = bool(self.config.get("hand_gestures", False)) and self.gesture_thread is not None
        _tg_running = bool(self._telegram_bot and self._telegram_bot.isRunning())
        _stt_active = self.config.get("stt_provider", "google") == "whisper"
        _ti_on      = bool(self._text_input and self._text_input.isVisible())
        _vf_on      = False
        try:
            from core.voice_filter import get_voice_filter
            _vf_on = get_voice_filter().enabled
        except Exception:
            pass

        def _draw_dot(px, py, color, label=''):
            p.setBrush(QBrush(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(px, py, 8, 8)
            if label:
                p.setFont(QFont("Segoe UI", 6))
                p.setPen(QColor(200, 200, 220, 110))
                p.drawText(px - 8, py + 10, 24, 10, Qt.AlignmentFlag.AlignCenter, label)

        if gesture_on:
            _draw_dot(w - 12, 8, QColor(0, 220, 130, 200), "✋")
        if _stt_active:
            from sphere.audio import WhisperSTT as _W
            if _W._instance:
                _draw_dot(6, 8, QColor(140, 80, 255, 200), "W")
        if _tg_running:
            _draw_dot(6, h - 14, QColor(0, 150, 220, 200), "TG")
        if _vf_on:
            p.setFont(QFont("Segoe UI Emoji", 8))
            p.setPen(QColor(100, 220, 120, 180))
            p.drawText(cx - 10, h - 16, 20, 14, Qt.AlignmentFlag.AlignCenter, "🔒")
        if _ti_on:
            _draw_dot(w - 12, h - 14, QColor(160, 100, 255, 200), "✏")

        conf = getattr(self, '_last_stt_confidence', 1.0)
        if conf < 0.9 and self.state in (self.IDLE, self.THINKING):
            bar_w = int(w * conf)
            _conf_alpha = 120 if conf < 0.6 else 70
            _conf_color = QColor(255, 80, 80, _conf_alpha) if conf < 0.5 else QColor(255, 200, 0, _conf_alpha)
            p.setBrush(QBrush(_conf_color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(0, h - 4, bar_w, 4, 2, 2)

    # ══════════════════════════════════════════════════════════
    # VIZ HELPERS
    # ══════════════════════════════════════════════════════════

    def _viz_plasma(self, p, cx, cy, R, c1, c2, pulse):
        """Стандартна плазмена сфера"""
        for i in range(10, 0, -1):
            glow = QColor(c1)
            glow.setAlpha(max(1, int(18 / (i * 0.7))))
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            gr = int(R * pulse + i * 14)
            p.drawEllipse(cx - gr, cy - gr, gr * 2, gr * 2)
        p.setPen(Qt.PenStyle.NoPen)
        for (angle, dist, sp, life) in self.particles:
            if life <= 0:
                continue
            pr = int(R * 1.1 + dist * R * 0.6)
            px_ = cx + int(pr * math.cos(angle))
            py_ = cy + int(pr * math.sin(angle))
            sz = max(1, int(2.5 * life))
            alpha = int(180 * life)
            pg = QRadialGradient(px_, py_, sz + 3)
            pg.setColorAt(0, QColor(c1.red(), c1.green(), c1.blue(), alpha))
            pg.setColorAt(1, QColor(c1.red(), c1.green(), c1.blue(), 0))
            p.setBrush(QBrush(pg))
            p.drawEllipse(px_ - sz - 3, py_ - sz - 3, (sz + 3) * 2, (sz + 3) * 2)
        for i, angle in enumerate(self.rings):
            ring_r = int(R + 12 + i * 10)
            alpha = 40 + int(35 * abs(math.sin(self.phase * 0.7 + i * 1.2)))
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), alpha), 1.2 if i % 2 == 0 else 0.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.save()
            p.translate(cx, cy)
            p.rotate(math.degrees(angle) + i * 36)
            span = (80 + int(40 * math.sin(self.phase + i))) * 16
            p.drawArc(-ring_r, -ring_r, ring_r * 2, ring_r * 2, 0, span)
            p.restore()
        base_g = QRadialGradient(cx, cy, R * 1.8)
        base_g.setColorAt(0, QColor(c2.red(), c2.green(), c2.blue(), 200))
        base_g.setColorAt(0.5, QColor(c2.red() // 3, c2.green() // 3, c2.blue() // 3, 220))
        base_g.setColorAt(1, QColor(4, 6, 18, 250))
        p.setBrush(QBrush(base_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        for i in range(6):
            ph = self.inner_phase[i]
            nx = cx + int(18 * math.sin(ph * 0.9 + i * 1.1))
            ny = cy + int(14 * math.cos(ph * 0.7 + i * 0.8))
            nr = int(R * (0.5 + 0.2 * math.sin(ph + i)))
            na = int(25 + 20 * abs(math.sin(ph * 0.5 + i * 0.6)))
            rs = int(c1.red() * (0.5 + 0.5 * math.sin(ph + i * 0.3)))
            gs = int(c1.green() * (0.5 + 0.5 * math.sin(ph + i * 0.5 + 1)))
            bs = int(c1.blue() * (0.5 + 0.5 * math.sin(ph + i * 0.7 + 2)))
            neb_g = QRadialGradient(nx, ny, nr)
            neb_g.setColorAt(0, QColor(min(255, rs), min(255, gs), min(255, bs), na))
            neb_g.setColorAt(1, QColor(rs // 3, gs // 3, bs // 3, 0))
            p.setBrush(QBrush(neb_g))
            p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        core_x = cx + int(5 * math.sin(self.phase * 0.4))
        core_y = cy + int(3 * math.cos(self.phase * 0.3))
        core_r = int(R * 0.35)
        ca = int(60 + 30 * math.sin(self.phase * 1.5))
        core_g = QRadialGradient(core_x, core_y, core_r)
        core_g.setColorAt(0, QColor(255, 255, 255, ca))
        core_g.setColorAt(0.3, QColor(c1.red(), c1.green(), c1.blue(), ca // 2))
        core_g.setColorAt(1, QColor(c1.red(), c1.green(), c1.blue(), 0))
        p.setBrush(QBrush(core_g))
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        for k in range(3):
            rim_a = int(30 + 15 * math.sin(self.phase + k))
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), rim_a), 2.0 - k * 0.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rk = R + k
            p.drawEllipse(cx - rk, cy - rk, rk * 2, rk * 2)
        hl_x, hl_y = cx - int(R * 0.28), cy - int(R * 0.35)
        hl_g = QRadialGradient(hl_x, hl_y, int(R * 0.45))
        hl_g.setColorAt(0, QColor(255, 255, 255, 130))
        hl_g.setColorAt(0.35, QColor(255, 255, 255, 50))
        hl_g.setColorAt(0.7, QColor(255, 255, 255, 10))
        hl_g.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(hl_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(hl_x - int(R * 0.38), hl_y - int(R * 0.28), int(R * 0.76), int(R * 0.5))
        for i in range(12):
            sa = self.phase * 0.8 + i * math.pi / 6
            sd = R * 0.6 * abs(math.sin(self.phase * 0.5 + i * 0.9))
            sx = cx + int(sd * math.cos(sa))
            sy = cy + int(sd * math.sin(sa) * 0.7)
            dx, dy = sx - cx, sy - cy
            if dx * dx + dy * dy < R * R:
                s_a = int(100 + 100 * abs(math.sin(self.phase * 2 + i * 1.3)))
                s_s = 1 + int(abs(math.sin(self.phase + i)) * 2)
                sg = QRadialGradient(sx, sy, s_s + 2)
                sg.setColorAt(0, QColor(255, 255, 255, s_a))
                sg.setColorAt(1, QColor(c1.red(), c1.green(), c1.blue(), 0))
                p.setBrush(QBrush(sg))
                p.drawEllipse(sx - s_s - 2, sy - s_s - 2, (s_s + 2) * 2, (s_s + 2) * 2)

    def _viz_neon(self, p, cx, cy, R, c1, c2, pulse):
        """Неон: порожня куля з яскравими кільцями"""
        p.setPen(Qt.PenStyle.NoPen)
        inner_g = QRadialGradient(cx, cy, R)
        inner_g.setColorAt(0, QColor(c2.red() // 5, c2.green() // 5, c2.blue() // 5, 50))
        inner_g.setColorAt(0.75, QColor(c2.red() // 4, c2.green() // 4, c2.blue() // 4, 90))
        inner_g.setColorAt(1, QColor(c1.red(), c1.green(), c1.blue(), 170))
        p.setBrush(QBrush(inner_g))
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        for i in range(5, 0, -1):
            halo_r = int(R * 1.5 + i * 8 + 4 * math.sin(self.phase * 1.5 + i))
            halo_a = max(0, int(28 - i * 4))
            halo_g = QRadialGradient(cx, cy, halo_r)
            halo_g.setColorAt(0.78, QColor(c1.red(), c1.green(), c1.blue(), 0))
            halo_g.setColorAt(0.92, QColor(c1.red(), c1.green(), c1.blue(), halo_a))
            halo_g.setColorAt(1.0, QColor(c1.red(), c1.green(), c1.blue(), 0))
            p.setBrush(QBrush(halo_g))
            p.drawEllipse(cx - halo_r, cy - halo_r, halo_r * 2, halo_r * 2)
        for k in range(5):
            neon_a = max(0, int(255 - k * 42))
            neon_w = max(0.3, 4.0 - k * 0.65)
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), neon_a), neon_w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            nr = R + k * 2
            p.drawEllipse(cx - nr, cy - nr, nr * 2, nr * 2)
        p.save()
        p.translate(cx, cy)
        p.rotate(math.degrees(self.phase * 1.5))
        arc_a = int(200 + 55 * math.sin(self.phase * 3))
        p.setPen(QPen(QColor(255, 255, 255, arc_a), 2.5))
        p.drawArc(-R, -R, R * 2, R * 2, 0, 120 * 16)
        p.restore()
        core_a = int(80 + 60 * abs(math.sin(self.phase * 2)))
        cr = int(R * 0.38)
        core_g = QRadialGradient(cx, cy, cr)
        core_g.setColorAt(0, QColor(c1.red(), c1.green(), c1.blue(), core_a))
        core_g.setColorAt(1, QColor(c1.red(), c1.green(), c1.blue(), 0))
        p.setBrush(QBrush(core_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - cr, cy - cr, cr * 2, cr * 2)

    def _viz_fire(self, p, cx, cy, R, c1, c2, pulse):
        """Вогонь: теплий градієнт + частинки летять вгору"""
        for i in range(8, 0, -1):
            gr = int(R * pulse + i * 12)
            alpha = max(1, int(22 / (i * 0.8)))
            p.setBrush(QBrush(QColor(c1.red(), max(0, c1.green() - 30), 0, alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - gr, cy - gr, gr * 2, gr * 2)
        fire_g = QRadialGradient(cx, cy + int(R * 0.3), R * 1.6)
        fire_g.setColorAt(0, QColor(255, 220, 80, 230))
        fire_g.setColorAt(0.3, QColor(c1.red(), max(0, c1.green() - 20), 0, 210))
        fire_g.setColorAt(0.7, QColor(c2.red(), max(0, c2.green() // 2), 0, 200))
        fire_g.setColorAt(1, QColor(20, 5, 0, 240))
        p.setBrush(QBrush(fire_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        for (angle, dist, sp, life) in self.particles:
            if life <= 0:
                continue
            t = (self.phase * sp * 12 + dist * 6.28) % 1.0
            px_ = cx + int((dist - 0.5) * R * 0.9 * math.sin(angle * 3 + self.phase))
            py_ = cy + R - int(t * R * 2.8)
            sz = max(1, int(3.5 * life * (1 - t * 0.6)))
            alpha = int(210 * life * (1 - t))
            if alpha < 8:
                continue
            g_v = max(0, int(200 * (1 - t * 0.9)))
            fg = QRadialGradient(px_, py_, sz + 2)
            fg.setColorAt(0, QColor(255, g_v, 0, alpha))
            fg.setColorAt(1, QColor(200, g_v // 2, 0, 0))
            p.setBrush(QBrush(fg))
            p.drawEllipse(px_ - sz - 2, py_ - sz - 2, (sz + 2) * 2, (sz + 2) * 2)
        core_a = int(130 + 90 * abs(math.sin(self.phase * 2.5)))
        cr = int(R * 0.5)
        core_g = QRadialGradient(cx, cy, cr)
        core_g.setColorAt(0, QColor(255, 255, 200, core_a))
        core_g.setColorAt(0.5, QColor(255, 160, 0, core_a // 2))
        core_g.setColorAt(1, QColor(200, 60, 0, 0))
        p.setBrush(QBrush(core_g))
        p.drawEllipse(cx - cr, cy - cr, cr * 2, cr * 2)
        rim_a = int(90 + 90 * abs(math.sin(self.phase * 3 + 0.5)))
        p.setPen(QPen(QColor(255, 150, 0, rim_a), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)

    def _viz_matrix(self, p, cx, cy, R, c1, c2, pulse):
        """Matrix: темна куля з кодовим дощем"""
        mat_g = QRadialGradient(cx, cy, R * 1.5)
        mat_g.setColorAt(0, QColor(0, max(8, c1.green() // 6), 0, 220))
        mat_g.setColorAt(0.6, QColor(0, max(5, c1.green() // 10), 0, 230))
        mat_g.setColorAt(1, QColor(0, 5, 0, 245))
        p.setBrush(QBrush(mat_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        num_cols = 7
        col_step = max(1, int(R * 1.8 / num_cols))
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for col in range(num_cols):
            col_x = cx - R + col * col_step + col_step // 2
            offset = (self.phase * 38 + col * 19) % (R * 2)
            for row in range(7):
                dot_y = cy - R + int((offset + row * 13) % (R * 2))
                dx, dy = col_x - cx, dot_y - cy
                if dx * dx + dy * dy >= (R - 4) * (R - 4):
                    continue
                fade = max(0.0, 1.0 - row / 7.0)
                dot_a = int(230 * fade)
                g_v = min(255, int(c1.green() * fade))
                r_v = int(c1.red() * fade * 0.25)
                b_v = int(c1.blue() * fade * 0.15)
                p.setPen(QColor(r_v, g_v, b_v, dot_a))
                char_idx = int(self.phase * 9 + col * 8 + row * 4) % len(chars)
                p.drawText(col_x - 5, dot_y, chars[char_idx])
        ring_a = int(130 + 70 * abs(math.sin(self.phase)))
        p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), ring_a), 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        p.save()
        p.translate(cx, cy)
        p.rotate(math.degrees(self.phase * 0.8))
        scan_a = int(55 + 35 * math.sin(self.phase * 2))
        p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), scan_a), 1))
        p.drawLine(0, -R, 0, R)
        p.restore()

    def _viz_holo(self, p, w, h, cx, cy, R, c1, c2, pulse):
        """Голограма: прозора куля зі скан-лініями та сіткою"""
        holo_g = QRadialGradient(cx, cy, R * 1.4)
        holo_g.setColorAt(0, QColor(c1.red() // 4, c1.green() // 4, c1.blue() // 4, 35))
        holo_g.setColorAt(0.7, QColor(c1.red() // 4, c1.green() // 4, c1.blue() // 4, 55))
        holo_g.setColorAt(0.92, QColor(c1.red(), c1.green(), c1.blue(), 130))
        holo_g.setColorAt(1, QColor(c1.red(), c1.green(), c1.blue(), 25))
        p.setBrush(QBrush(holo_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        scan_step = 6
        scan_offset = int(self.phase * 28) % scan_step
        for sy in range(cy - R + scan_offset, cy + R, scan_step):
            ddx = R * R - (sy - cy) * (sy - cy)
            if ddx < 4:
                continue
            dx = math.sqrt(ddx)
            scan_a = int(22 + 12 * abs(math.sin(self.phase * 0.5 + (sy - cy) * 0.05)))
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), scan_a), 1))
            p.drawLine(int(cx - dx), sy, int(cx + dx), sy)
        beam_t = (self.phase * 0.4) % 1.0
        beam_y = cy - R + int(R * 2 * beam_t)
        bdy = beam_y - cy
        bdx2 = R * R - bdy * bdy
        if bdx2 > 4:
            bdx = math.sqrt(bdx2)
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), 120), 2))
            p.drawLine(int(cx - bdx), beam_y, int(cx + bdx), beam_y)
        v_step = 14
        for vx_off in range(-R + v_step, R, v_step):
            top_dy2 = R * R - vx_off * vx_off
            if top_dy2 < 4:
                continue
            top_dy = math.sqrt(top_dy2)
            vy1 = int(cy - top_dy)
            vy2 = int(cy + top_dy)
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), 16), 1))
            p.drawLine(cx + vx_off, vy1, cx + vx_off, vy2)
        outer_a = int(190 + 65 * math.sin(self.phase * 1.5))
        p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), outer_a), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        ir = int(R * 0.62)
        p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), 50), 1))
        p.drawEllipse(cx - ir, cy - ir, ir * 2, ir * 2)
        p.save()
        p.translate(cx, cy)
        p.rotate(math.degrees(self.phase * 0.6))
        arc_a = int(170 + 85 * math.sin(self.phase * 2))
        p.setPen(QPen(QColor(255, 255, 255, arc_a), 1.5))
        p.drawArc(-R, -R, R * 2, R * 2, 45 * 16, 90 * 16)
        p.restore()

    def _viz_music_bars(self, p, cx, cy, R, c1, c2):
        """Еквалайзер: вертикальні bars"""
        base_g = QRadialGradient(cx, cy, R * 1.2)
        base_g.setColorAt(0, QColor(c2.red() // 4, c2.green() // 4, c2.blue() // 4, 200))
        base_g.setColorAt(1, QColor(4, 6, 18, 240))
        p.setBrush(QBrush(base_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        n = len(self.waves)
        bar_w = max(3, int(R * 1.6 / n) - 2)
        step_x = max(1, int(R * 1.6 / n))
        p.save()
        p.translate(cx - int(R * 0.8), cy)
        for i, amp in enumerate(self.waves):
            h_bar = max(4, int(amp * 1.9))
            t = i / max(1, n - 1)
            r_v = int(c1.red() * (1 - t) + c2.red() * t)
            g_v = int(c1.green() * (1 - t) + c2.green() * t)
            b_v = int(c1.blue() * (1 - t) + c2.blue() * t)
            bar_a = min(240, 120 + int(h_bar * 2))
            bar_g = QRadialGradient(i * step_x + bar_w // 2, -h_bar // 2, h_bar)
            bar_g.setColorAt(0, QColor(min(255, r_v + 70), min(255, g_v + 70), min(255, b_v + 70), bar_a))
            bar_g.setColorAt(1, QColor(r_v, g_v, b_v, bar_a // 2))
            p.setBrush(QBrush(bar_g))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(i * step_x, -h_bar, bar_w, h_bar, 2, 2)
            p.setBrush(QBrush(QColor(255, 255, 255, min(200, bar_a))))
            p.drawEllipse(i * step_x + bar_w // 2 - 2, -h_bar - 2, 4, 4)
        p.restore()
        ring_a = int(100 + 60 * abs(math.sin(self.phase)))
        p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), ring_a), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)

    def _viz_music_sine(self, p, w, cx, cy, R, c1, c2):
        """Синусоїда: хвилі всередині кола"""
        base_g = QRadialGradient(cx, cy, R * 1.2)
        base_g.setColorAt(0, QColor(c2.red() // 5, c2.green() // 5, c2.blue() // 5, 210))
        base_g.setColorAt(1, QColor(4, 6, 18, 245))
        p.setBrush(QBrush(base_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        for harmonic in range(3):
            freq = 1.0 + harmonic * 0.7
            ampl = int(R * (0.55 - harmonic * 0.15))
            alpha = int(200 - harmonic * 55)
            speed_off = self.phase * (1.8 + harmonic * 0.4)
            prev_x, prev_y = None, None
            for x_off in range(-R, R + 1, 2):
                t = x_off / R
                y_off = int(ampl * math.sin(t * math.pi * 2.5 * freq + speed_off))
                sx_ = cx + x_off
                sy_ = cy + y_off
                if x_off * x_off + y_off * y_off > R * R * 0.95:
                    prev_x = prev_y = None
                    continue
                if prev_x is not None:
                    r_v = int(c1.red() * (1 - harmonic * 0.3))
                    g_v = int(c1.green() * (1 - harmonic * 0.2))
                    b_v = min(255, int(c1.blue() * (1 + harmonic * 0.3)))
                    p.setPen(QPen(QColor(r_v, g_v, b_v, alpha), max(0.5, 2 - harmonic * 0.5)))
                    p.drawLine(prev_x, prev_y, sx_, sy_)
                prev_x, prev_y = sx_, sy_
        p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), 100), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)

    def _viz_music_spectrum(self, p, cx, cy, R, c1, c2):
        """Спектр: кругові bars з веселкою"""
        base_g = QRadialGradient(cx, cy, R * 1.2)
        base_g.setColorAt(0, QColor(8, 8, 20, 200))
        base_g.setColorAt(1, QColor(2, 4, 12, 245))
        p.setBrush(QBrush(base_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        n = 32
        p.save()
        p.translate(cx, cy)
        for i in range(n):
            ang = i * 2 * math.pi / n
            wave_i = self.waves[i % len(self.waves)] if self.waves else 20
            bar_len = int(10 + wave_i * 0.85)
            hue = int(i * 360 / n)
            c_bar = QColor.fromHsv(hue, 240, 255, 200)
            p.setPen(QPen(c_bar, 3))
            x1 = int(R * 0.45 * math.cos(ang))
            y1 = int(R * 0.45 * math.sin(ang))
            x2 = int((R * 0.45 + bar_len) * math.cos(ang))
            y2 = int((R * 0.45 + bar_len) * math.sin(ang))
            p.drawLine(x1, y1, x2, y2)
        p.restore()
        p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), 120), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)

    def _viz_music_pulse(self, p, cx, cy, R, c1, c2, pulse):
        """Пульс: концентричні кільця"""
        base_g = QRadialGradient(cx, cy, R * 1.2)
        base_g.setColorAt(0, QColor(c2.red() // 4, c2.green() // 4, c2.blue() // 4, 200))
        base_g.setColorAt(1, QColor(4, 6, 18, 240))
        p.setBrush(QBrush(base_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        n_rings = 6
        for k in range(n_rings):
            t = (self.phase * 0.4 + k / n_rings) % 1.0
            ring_r = int(R * 0.08 + R * 0.92 * t)
            ring_a = max(0, int(210 * (1 - t)))
            ring_w = max(0.3, 2.8 * (1 - t))
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), ring_a), ring_w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
        core_a = int(160 + 95 * abs(math.sin(self.phase * 2)))
        cr = int(R * 0.28)
        core_g = QRadialGradient(cx, cy, cr)
        core_g.setColorAt(0, QColor(255, 255, 255, core_a))
        core_g.setColorAt(0.5, QColor(c1.red(), c1.green(), c1.blue(), core_a // 2))
        core_g.setColorAt(1, QColor(c1.red(), c1.green(), c1.blue(), 0))
        p.setBrush(QBrush(core_g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - cr, cy - cr, cr * 2, cr * 2)
        p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), 150), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)

    def _viz_aurora(self, p, cx, cy, R, c1, c2, pulse):
        """Aurora — північне сяйво"""
        ph = self.phase
        aurora_colors = [
            QColor(0, 255, 150),
            QColor(100, 200, 255),
            QColor(180, 100, 255),
            QColor(0, 255, 200),
        ]
        n_bands = 5
        for band in range(n_bands):
            col = aurora_colors[band % len(aurora_colors)]
            alpha = int(80 + 70 * abs(math.sin(ph * 0.7 + band * 1.3)))
            col.setAlpha(alpha)
            offset_y = int(math.sin(ph * 1.2 + band * 0.8) * R * 0.3)
            p.setPen(Qt.PenStyle.NoPen)
            g = QRadialGradient(cx, cy + offset_y, R)
            transparent = QColor(col)
            transparent.setAlpha(0)
            g.setColorAt(0.5 - 0.15, transparent)
            g.setColorAt(0.5, col)
            g.setColorAt(0.5 + 0.15, transparent)
            p.setBrush(QBrush(g))
            p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        cr = int(R * 0.3)
        glow = QRadialGradient(cx, cy, cr)
        glow.setColorAt(0, QColor(200, 255, 220, int(180 * pulse)))
        glow.setColorAt(1, QColor(0, 255, 150, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - cr, cy - cr, cr * 2, cr * 2)

    def _viz_glitch(self, p, cx, cy, R, c1, c2, pulse):
        """Glitch — кіберпанк"""
        import random as _rnd
        ph = self.phase
        g = QRadialGradient(cx, cy, R)
        g.setColorAt(0.0, QColor(255, 0, 200, int(180 * pulse)))
        g.setColorAt(0.5, QColor(0, 255, 255, 120))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        _rnd.seed(int(ph * 8))
        for _ in range(6):
            if _rnd.random() > 0.35:
                continue
            gx = cx - R + _rnd.randint(0, int(R * 1.8))
            gy = cy - R + _rnd.randint(0, int(R * 1.8))
            gw = _rnd.randint(int(R * 0.1), int(R * 0.6))
            gh = _rnd.randint(2, int(R * 0.06))
            gcol = _rnd.choice([
                QColor(255, 0, 200, 180),
                QColor(0, 255, 255, 160),
                QColor(255, 255, 255, 200),
            ])
            p.setBrush(QBrush(gcol))
            p.drawRect(gx, gy, gw, gh)
        p.setPen(QPen(QColor(0, 255, 255, 200), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        sl_y = cy - R + int((R * 2) * ((ph * 0.6) % 1.0))
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.drawLine(cx - R, sl_y, cx + R, sl_y)

    def _viz_liquid(self, p, cx, cy, R, c1, c2, pulse):
        """Liquid — рідина"""
        ph = self.phase
        drops = [
            (math.sin(ph * 1.1) * R * 0.25, math.cos(ph * 0.9) * R * 0.2, 0.55),
            (math.sin(ph * 0.7 + 2) * R * 0.2, math.cos(ph * 1.3 + 1) * R * 0.25, 0.4),
            (math.sin(ph * 1.5 + 4) * R * 0.15, math.cos(ph * 0.5 + 3) * R * 0.3, 0.35),
        ]
        for dx, dy, scale in drops:
            gr = int(R * scale)
            lx, ly = int(cx + dx), int(cy + dy)
            g = QRadialGradient(lx, ly, gr)
            a1 = int(160 * pulse)
            g.setColorAt(0.0, QColor(c1.red(), c1.green(), c1.blue(), a1))
            g.setColorAt(0.6, QColor(c2.red(), c2.green(), c2.blue(), a1 // 2))
            g.setColorAt(1.0, QColor(c1.red(), c1.green(), c1.blue(), 0))
            p.setBrush(QBrush(g))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(lx - gr, ly - gr, gr * 2, gr * 2)
        n_rip = 4
        for i in range(n_rip):
            t = (ph * 0.5 + i / n_rip) % 1.0
            rr = int(R * 0.2 + R * 0.8 * t)
            ra = max(0, int(200 * (1 - t)))
            p.setPen(QPen(QColor(c1.red(), c1.green(), c1.blue(), ra), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cx - rr, cy - rr, rr * 2, rr * 2)

    # ── Mouse / Keyboard events ───────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position().toPoint()
            gesture_rect = getattr(self, '_gesture_btn_rect', None)
            if gesture_rect is not None:
                bx, by, bw, bh = gesture_rect
                if bx <= pos.x() <= bx + bw and by <= pos.y() <= by + bh:
                    self._toggle_gestures()
                    return
            stt_rect = getattr(self, '_stt_btn_rect', None)
            if stt_rect is not None:
                bx, by, bw, bh = stt_rect
                if bx <= pos.x() <= bx + bw and by <= pos.y() <= by + bh:
                    self._toggle_stt_provider()
                    return
            tg_rect = getattr(self, '_tg_btn_rect', None)
            if tg_rect is not None:
                bx, by, bw, bh = tg_rect
                if bx <= pos.x() <= bx + bw and by <= pos.y() <= by + bh:
                    self._on_telegram_btn_click()
                    return
            ti_rect = getattr(self, '_ti_btn_rect', None)
            if ti_rect is not None:
                bx, by, bw, bh = ti_rect
                if bx <= pos.x() <= bx + bw and by <= pos.y() <= by + bh:
                    self._show_text_input()
                    return
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.drag_pos:
                dist = (e.globalPosition().toPoint() - self.frameGeometry().topLeft() - self.drag_pos).manhattanLength()
                if dist < 10:
                    self.continuous_listen = True
                    self.start_listening()
        self.drag_pos = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._show_text_input()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and self.drag_pos:
            self.move(e.globalPosition().toPoint() - self.drag_pos)

    # ── Text input popup ──────────────────────────────────────────────────────

    def _show_text_input(self):
        """Show a floating text-input bar below the sphere."""
        if self._text_input and self._text_input.isVisible():
            self._text_input.hide()
            return
        if self._text_input is None:
            inp = QLineEdit(self)
            inp.setFixedHeight(36)
            inp.setPlaceholderText("✏️ Напишіть промпт асистенту...")
            inp.setStyleSheet("""
                QLineEdit {
                    background: #0d0f1b;
                    color: #e0e6ff;
                    border: 1.5px solid #00d4ff;
                    border-radius: 18px;
                    padding: 4px 16px;
                    font-size: 13px;
                    font-family: 'Segoe UI', sans-serif;
                }
                QLineEdit:focus { border-color: #a78bfa; }
            """)
            inp.returnPressed.connect(self._submit_text_input)
            inp.keyPressEvent = self._text_input_key
            self._text_input = inp
        w = self.width()
        inp_w = max(w + 60, 320)
        self._text_input.setFixedWidth(inp_w)
        sx = self.x() + (w - inp_w) // 2
        sy = self.y() + self.height() + 8
        self._text_input.setParent(None)
        self._text_input.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self._text_input.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self._text_input.move(sx, sy)
        self._text_input.clear()
        self._text_input.show()
        self._text_input.setFocus()
        self._text_input.raise_()

    def _text_input_key(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._text_input.hide()
        else:
            QLineEdit.keyPressEvent(self._text_input, event)

    def _submit_text_input(self):
        """Process typed text as voice command."""
        text = self._text_input.text().strip()
        self._text_input.hide()
        if not text:
            return
        self.show_orb()
        self.user_text = text
        self.response_text = ""
        self.update()
        self.on_recognized(text)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #1a1a2e; color: white; border: 1px solid #333; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #00d4ff; color: black; }
        """)
        menu.addAction("🎤 Слухати", self.start_listening)
        menu.addAction("✏️ Ввести текст", self._show_text_input)
        menu.addAction("🔇 Тихий режим", self.hide_orb)
        menu.addSeparator()
        menu.addAction("🎛️ Панель AXIS OS", self.open_panel)
        menu.addSeparator()
        auto_act = menu.addAction("🚀 Автозапуск з Windows")
        auto_act.setCheckable(True)
        auto_act.setChecked(self._is_autostart_enabled())
        auto_act.triggered.connect(self._toggle_autostart)
        menu.addSeparator()
        try:
            from core.voice_filter import get_voice_filter
            vf = get_voice_filter()
            vf_label = ("🔒 Фільтр голосу: ON" if vf.enabled else "🔓 Фільтр голосу: OFF")
            vf_act = menu.addAction(vf_label)
            vf_act.triggered.connect(lambda: vf.set_enabled(not vf.enabled))
            menu.addSeparator()
        except Exception:
            pass
        menu.addAction("❌ Вийти", self.quit_app)
        menu.exec(e.globalPos())

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space:
            self.continuous_listen = True
            self.start_listening()
        elif e.key() == Qt.Key.Key_T:
            self._show_text_input()
        elif e.key() == Qt.Key.Key_Escape:
            self.hide_orb()

    # ── Misc ──────────────────────────────────────────────────────────────────

    def clear(self):
        if self.state == self.IDLE:
            self.user_text, self.response_text = "", ""

    def closeEvent(self, e):
        e.ignore()
        self.hide_orb()
