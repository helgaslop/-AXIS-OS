"""Main PyQt6 window — loads axis_ui.html in a frameless WebEngineView."""
import json
import os

from PyQt6.QtCore import Qt, QUrl, QTimer, QFile
from PyQt6.QtGui import QIcon
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings
from PyQt6.QtWidgets import QMainWindow, QApplication

from gui.bridge import AxisBridge
from core.system_monitor import SystemMonitor
from core.ai_manager import AIManager


class AxisWindow(QMainWindow):
    def __init__(self, config: dict):
        super().__init__()
        self.config = config

        # ── Window setup ──────────────────────────────────────────────────────
        self.setWindowTitle("AXIS OS")
        win_cfg = config.get("window", {})
        self.resize(win_cfg.get("width", 1400), win_cfg.get("height", 860))
        self.setMinimumSize(900, 600)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        icon_path = os.path.join(os.path.dirname(__file__), "..", "data", "icon_panel.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Center on screen
        x, y = win_cfg.get("x", -1), win_cfg.get("y", -1)
        if x == -1:
            screen = QApplication.primaryScreen().geometry()
            self.move(
                (screen.width()  - self.width())  // 2,
                (screen.height() - self.height()) // 2,
            )
        else:
            self.move(x, y)

        # ── Web view ──────────────────────────────────────────────────────────
        self.view = QWebEngineView()
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        # ── Bridge & channel ──────────────────────────────────────────────────
        self.ai_manager = AIManager(config)
        self.bridge     = AxisBridge(self, self.ai_manager, config)
        self.channel    = QWebChannel()
        self.channel.registerObject("axisBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        # Bridge → JS
        self.bridge.push_to_js.connect(self._push_to_js)

        # ── Inject qwebchannel.js ─────────────────────────────────────────────
        self._inject_qwebchannel()

        # ── Load HTML ─────────────────────────────────────────────────────────
        html_path = os.path.join(os.path.dirname(__file__), "ui", "axis_ui.html")
        self.view.load(QUrl.fromLocalFile(os.path.abspath(html_path)))
        self.view.loadFinished.connect(self._on_load_finished)

        self.setCentralWidget(self.view)

        # ── System monitor ────────────────────────────────────────────────────
        self.monitor = SystemMonitor(interval_ms=2000)
        self.monitor.stats_ready.connect(self._on_stats)
        self.monitor.start()

        # ── Drag support (frameless) ──────────────────────────────────────────
        self._drag_pos = None

    # ── qwebchannel.js injection ──────────────────────────────────────────────
    def _inject_qwebchannel(self):
        qwc = QFile(":/qtwebchannel/qwebchannel.js")
        if qwc.open(QFile.OpenModeFlag.ReadOnly):
            js_src = bytes(qwc.readAll()).decode("utf-8")
            qwc.close()
        else:
            js_src = ""

        setup_js = """
(function() {
    var _queue = [];
    var _bridge = null;

    window.pyCall = function(cmd, data) {
        var payload = (data === undefined || data === null) ? '' :
                      (typeof data === 'string' ? data : JSON.stringify(data));
        if (_bridge) {
            _bridge.call(cmd, payload);
        } else {
            _queue.push([cmd, payload]);
        }
    };

    window.axisPush = function(type, jsonStr) { /* filled by Python */ };

    function _ready(bridge) {
        _bridge = bridge;
        _queue.forEach(function(item) { bridge.call(item[0], item[1]); });
        _queue = [];
    }

    function _initChannel() {
        if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined') {
            new QWebChannel(qt.webChannelTransport, function(channel) {
                _ready(channel.objects.axisBridge);
            });
        } else {
            setTimeout(_initChannel, 100);
        }
    }
    _initChannel();
})();
"""
        full_src = js_src + "\n" + setup_js

        script = QWebEngineScript()
        script.setName("axis_bridge_init")
        script.setSourceCode(full_src)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        self.view.page().scripts().insert(script)

    # ── Page load finished ────────────────────────────────────────────────────
    def _on_load_finished(self, ok: bool):
        if not ok:
            return
        # Redirect stdout/stderr → JS log panel
        try:
            from core.log_bridge import install as _log_install
            _log_install(lambda lvl, msg: self.bridge.push_to_js.emit(
                "log_line", __import__('json').dumps({"level": lvl, "msg": msg})
            ))
        except Exception:
            pass
        initial = self.monitor.get_initial()
        self._push_to_js("sys_stats", initial)
        self._push_to_js("sphere_config", json.dumps(self.config))

        from core.paths import COMMANDS_FILE, MACROS_FILE
        for fpath, push_type in [(COMMANDS_FILE, "user_commands"),
                                  (MACROS_FILE,   "macros_data")]:
            if fpath.exists():
                try:
                    with open(fpath, encoding="utf-8") as f:
                        self._push_to_js(push_type, f.read())
                except Exception:
                    pass


        # Auto-discover Ollama models in background
        self.bridge._fetch_ollama(None)
        # Push sphere status after a short delay (sphere may still be starting)
        import threading as _t
        _t.Thread(target=self._push_sphere_status_async, daemon=True).start()
        # Auto-check for updates in background (якщо є github_repo і auto_update увімкнено)
        if self.config.get("auto_update", True) and self.config.get("github_repo", ""):
            QTimer.singleShot(5000, self._auto_check_update)

    def _push_sphere_status_async(self):
        import time
        time.sleep(1.5)
        self.bridge._sphere_status(None)

    def _auto_check_update(self):
        """Тиха авто-перевірка оновлень при запуску."""
        import threading as _t
        repo = self.config.get("github_repo", "")
        if not repo:
            return
        _t.Thread(target=self._auto_check_worker, args=(repo,), daemon=True).start()

    def _auto_check_worker(self, repo: str):
        import time
        time.sleep(2)   # даємо UI повністю завантажитись
        try:
            from core.updater import check_github_update
            info = check_github_update(repo)
            if info:
                # Є нова версія — показуємо нотифікацію в UI
                self._push_to_js("github_update_status",
                    __import__('json').dumps({"status": "available", **info,
                                             "_auto": True}))
        except Exception:
            pass   # тиха перевірка — помилки ігноруємо

    # ── System monitor → JS ───────────────────────────────────────────────────
    def _on_stats(self, json_str: str):
        self._push_to_js("sys_stats", json_str)

    # ── Generic Python → JS push ──────────────────────────────────────────────
    def _push_to_js(self, msg_type: str, json_payload: str):
        # Guard: runJavaScript must run on the main thread.
        # If called from a background thread, re-route through the signal queue.
        from PyQt6.QtCore import QThread
        if QThread.currentThread() is not self.thread():
            self.bridge.push_to_js.emit(msg_type, json_payload)
            return
        # Escape for JS template literal:
        # 1. Backslashes first (must be first to avoid double-escaping)
        # 2. Backticks  — close the template literal
        # 3. ${ — prevent template literal expression injection (e.g. PowerShell $(...))
        escaped = (json_payload
                   .replace("\\", "\\\\")
                   .replace("`",  "\\`")
                   .replace("${", "\\${"))
        js = f"if(typeof axisPush==='function')axisPush('{msg_type}',`{escaped}`);"
        self.view.page().runJavaScript(js)

    # ── Frameless window drag ─────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if (self._drag_pos is not None and
                event.buttons() == Qt.MouseButton.LeftButton):
            self.move(self.pos() + event.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── Save window position on close ─────────────────────────────────────────
    def closeEvent(self, event):
        self.monitor.stop()
        pos = self.pos()
        self.config.setdefault("window", {}).update({
            "width": self.width(), "height": self.height(),
            "x": pos.x(), "y": pos.y(),
        })
        try:
            from core.paths import CONFIG_FILE
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        event.accept()
