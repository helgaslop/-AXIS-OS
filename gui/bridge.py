"""JavaScript ↔ Python bridge exposed via QWebChannel.

All logic is split into handler mixins under gui/handlers/.
This file only wires them together and registers the command map.
"""
import json
import threading

from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal

from .handlers import (
    AiHandlerMixin,
    FilesHandlerMixin,
    SystemHandlerMixin,
    SphereHandlerMixin,
    SttTtsHandlerMixin,
    IdeHandlerMixin,
    SpotifyHandlerMixin,
    DashboardHandlerMixin,
    LicenseHandlerMixin,
    ProfileHandlerMixin,
)


class AxisBridge(
    AiHandlerMixin,
    FilesHandlerMixin,
    SystemHandlerMixin,
    SphereHandlerMixin,
    SttTtsHandlerMixin,
    IdeHandlerMixin,
    SpotifyHandlerMixin,
    DashboardHandlerMixin,
    LicenseHandlerMixin,
    ProfileHandlerMixin,
    QObject,
):
    """All JS calls come through pyCall(cmd, data).
    Python pushes data back via window.axisPush(type, payload).
    """

    push_to_js = pyqtSignal(str, str)  # (type, json_payload)

    def __init__(self, window, ai_manager, config: dict):
        super().__init__()
        self._win = window
        self._ai  = ai_manager
        self._cfg = config

        # STT state (used by SttTtsHandlerMixin)
        self._stt_bg_stop = None
        self._stt_active  = False

        # Wire AI signals
        self._ai.response_ready.connect(self._on_ai_ready)
        self._ai.response_error.connect(self._on_ai_error)
        self._ai.response_token.connect(self._on_ai_token)
        self._ai.response_done.connect(self._on_ai_done)
        self._ai.image_ready.connect(self._on_image_ready)

    # ── Slot called from JavaScript ──────────────────────────────────────────
    @pyqtSlot(str, str)
    def call(self, cmd: str, data: str = ""):
        try:
            payload = json.loads(data) if data else {}
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[Bridge] ⚠ Bad JSON for '{cmd}': {e} — skipping")
            return

        handlers = {
            # Window
            "minimize":                 self._minimize,
            "minimize_window":          self._minimize,   # auto-sleep (settings.js)
            "maximize":                 self._maximize,
            "close_app":                self._close,
            # AI
            "ai_send":                  self._ai_send,
            "ai_send_stream":           self._ai_send_stream,
            "ai_cancel":                self._ai_cancel,
            "generate_image":           self._generate_image,
            "generate_video":           self._generate_video,
            "save_api_key":             self._save_api_key,
            "save_config":              self._save_config,
            "fetch_ollama":             self._fetch_ollama,
            "check_api_status":         self._check_api_status,
            "run_api_tests":            self._run_api_tests,
            "connect_spotify":          self._connect_spotify,
            "spotify_action":           self._spotify_action,
            # Commands
            "run_macro":                self._run_macro,
            "run_command":              self._run_command,
            "save_commands":            self._save_commands,
            "save_macros":              self._save_macros,
            "reload_commands":          self._reload_commands,
            # Files
            "open_file":                self._open_file,
            "open_file_path":           self._open_file_path,
            "open_folder":              self._open_folder,
            "run_code":                 self._run_code,
            "ide_run_code":             self._run_code,   # IDE JS runner (ide.js)
            "open_file_dialog":         self._open_file_dialog,
            "open_ide_file":            self._open_ide_file,
            "save_file":                self._save_file,
            "save_file_as":             self._save_file_as,
            # Sphere
            "launch_sphere":            self._launch_sphere,
            "stop_sphere":              self._stop_sphere,
            "sphere_status":            self._sphere_status,
            "save_sphere":              self._save_sphere,
            "get_sphere":               self._get_sphere,
            # Autostart
            "toggle_axis_autostart":    self._toggle_axis_autostart,
            "toggle_sphere_autostart":  self._toggle_sphere_autostart,
            "get_autostart_status":     self._get_autostart_status,
            # STT / TTS
            "tts_speak":                self._tts_speak,
            "start_stt":                self._start_stt,
            "stop_stt":                 self._stop_stt,
            "list_mic_devices":         self._list_mic_devices,
            # IDE control panel
            "launch_ide":               self._launch_ide,
            "stop_ide":                 self._stop_ide,
            "get_ide_status":           self._get_ide_status,
            "save_ide_config":          self._save_ide_config,
            "ide_new_project":          self._ide_new_project,
            # Clipboard
            "get_clipboard":            self._get_clipboard,
            "set_clipboard":            self._set_clipboard,
            # Updater (local)
            "check_update":             self._check_update,
            "apply_update":             self._apply_update,
            "save_update_folder":       self._save_update_folder,
            # Updater (GitHub)
            "check_github_update":      self._check_github_update,
            "download_github_update":   self._download_github_update,
            # Process Manager
            "get_processes":            self._get_processes,
            "kill_process":             self._kill_process,
            # Pomodoro
            "save_pomodoro_stat":       self._save_pomodoro_stat,
            "get_pomodoro_stats":       self._get_pomodoro_stats,
            # Quick Notes
            "save_quick_notes":         self._save_quick_notes,
            "get_quick_notes":          self._get_quick_notes,
            # Quick Search
            "search_quick":             self._search_quick,
            # Settings Backup/Restore
            "export_backup":            self._export_backup,
            "import_backup":            self._import_backup,
            # License & AI Subscriptions
            "get_license_status":       self._get_license_status,
            "activate_license":         self._activate_license,
            "get_ai_subscriptions":     self._get_ai_subscriptions,
            "save_ai_subscription":     self._save_ai_subscription,
            "check_ai_keys":            self._check_all_keys,
            "get_proxy_stats":          self._get_proxy_stats,
            "set_budget":               self._set_budget,
            # Profile & Onboarding
            "get_profile":              self._get_profile,
            "save_profile":             self._save_profile,
            "complete_onboarding":      self._complete_onboarding,
            "get_onboarding_status":    self._get_onboarding_status,
            "increment_stat":           self._increment_stat,
            "save_chat_memory":         self._save_chat_memory,
            "recall_chat_memory":       self._recall_chat_memory,
            "set_ai_style":             self._set_ai_style,
            "get_ai_style":             self._get_ai_style,
        }

        fn = handlers.get(cmd)
        if fn:
            try:
                fn(payload)
            except Exception as e:
                print(f"[Bridge] Handler {cmd!r} raised: {e}")
        else:
            print(f"[Bridge] Unknown command: {cmd!r}")
