"""Sphere process management, autostart, config & commands persistence."""
import json
import os
import subprocess
import sys
import threading

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ── Sphere log streamer ───────────────────────────────────────────────────────

_AXIS_PUSH_PREFIX = "__AXIS_PUSH__:"

def _stream_sphere_output(proc, push_fn):
    """Read stdout + stderr from sphere process and push lines to Panel log viewer.
    Runs in two background daemon threads (one per stream).
    push_fn(level, msg) — same signature as log_bridge.

    Special protocol: lines starting with __AXIS_PUSH__:type:json_data are forwarded
    directly as axisPush events to the Panel JS (not shown as log lines).
    """
    def _reader(stream, level):
        try:
            for raw in stream:
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line:
                        continue
                    if line.startswith(_AXIS_PUSH_PREFIX):
                        # Format: __AXIS_PUSH__:event_type:json_data
                        rest = line[len(_AXIS_PUSH_PREFIX):]
                        sep = rest.find(":")
                        if sep != -1:
                            event_type = rest[:sep]
                            event_data = rest[sep + 1:]
                            push_fn("__push__", f"{event_type}:{event_data}")
                    else:
                        push_fn(level, f"[Sphere] {line}")
                except Exception:
                    pass
        except Exception:
            pass

    t_out = threading.Thread(target=_reader, args=(proc.stdout, "info"),  daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, "error"), daemon=True)
    t_out.start()
    t_err.start()


class SphereHandlerMixin:
    _SPHERE_VISUAL_KEYS = {
        "sphere_wake", "sphere_size", "sphere_color", "sphere_color2",
        "sphere_opacity", "sphere_position", "sphere_anim", "sphere_anim_speed",
        "sphere_particles", "sphere_particle_count", "sphere_autostart",
        "ai_provider", "dialog_provider",
        "language", "tts_provider", "tts_voice", "edge_voice", "tts_speed",
        "jarvis_sounds", "jarvis_volume", "tts_volume", "weather_city",
        "mic_on_phrase", "mic_off_phrase", "sphere_name", "sphere_visual",
        "hand_gestures",
        "gesture_camera", "gesture_cooldown",
        "gesture_open_palm", "gesture_fist", "gesture_thumbs_up",
        "gesture_right", "gesture_left",
        "stt_provider", "whisper_model",
        "telegram_enabled", "telegram_token", "telegram_allowed_ids",
        "telegram_commands",
    }
    _AUTOSTART_REG_PATH   = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _AXIS_AUTOSTART_KEY   = "AXIS OS"
    _SPHERE_AUTOSTART_KEY = "AIVON Sphere"

    # ── Sphere config ─────────────────────────────────────────────────────────
    def _get_sphere(self, _):
        self.push_to_js.emit("sphere_config", json.dumps(self._cfg))

    def _save_sphere(self, p: dict):
        self._cfg.update(p)
        self._save_config_file()
        from core.paths import SPHERE_CONFIG_FILE
        sphere_cfg_path = str(SPHERE_CONFIG_FILE)
        try:
            existing = {}
            if os.path.exists(sphere_cfg_path):
                with open(sphere_cfg_path, encoding="utf-8") as f:
                    existing = json.load(f)
            # Поля які НЕ перезаписуємо порожнім значенням
            _preserve_if_empty = {"telegram_token"}
            for k in self._SPHERE_VISUAL_KEYS:
                if k in p:
                    new_val = p[k]
                    # Зберігаємо старе значення якщо нове порожнє
                    if k in _preserve_if_empty and not new_val and existing.get(k):
                        continue
                    existing[k] = new_val
            with open(sphere_cfg_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[AXIS] sphere_config.json save error: {e}")
        if "sphere_autostart" in p:
            self._autostart_write(
                self._SPHERE_AUTOSTART_KEY, "launch_sphere.vbs", bool(p["sphere_autostart"]))

    # ── Autostart (Windows registry) ──────────────────────────────────────────
    def _autostart_read(self, name: str) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 self._AUTOSTART_REG_PATH, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, name)
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    def _autostart_write(self, name: str, vbs_filename: str, enable: bool) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 self._AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE)
            try:
                if enable:
                    axis_dir = os.path.normpath(
                        os.path.join(os.path.dirname(__file__), "..", ".."))
                    vbs_path = os.path.join(axis_dir, vbs_filename)
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ,
                                      f'wscript.exe "{vbs_path}"')
                else:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
                return True
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            print(f"[AXIS] autostart registry error: {e}")
            return False

    def _get_autostart_status(self, _):
        self.push_to_js.emit("autostart_status", json.dumps({
            "axis":   self._autostart_read(self._AXIS_AUTOSTART_KEY),
            "sphere": self._autostart_read(self._SPHERE_AUTOSTART_KEY),
        }))

    def _toggle_axis_autostart(self, p: dict):
        enabled = bool(p.get("enabled", False))
        ok  = self._autostart_write(self._AXIS_AUTOSTART_KEY, "launch_axis.vbs", enabled)
        msg = ("🚀 AXIS OS: автозапуск увімкнено!" if enabled else "⏹ AXIS OS: автозапуск вимкнено.") if ok \
              else "⚠ Не вдалося змінити автозапуск AXIS OS"
        self.push_to_js.emit("toast", json.dumps({"msg": msg}))
        self._get_autostart_status(None)

    def _toggle_sphere_autostart(self, p: dict):
        enabled = bool(p.get("enabled", False))
        ok  = self._autostart_write(self._SPHERE_AUTOSTART_KEY, "launch_sphere.vbs", enabled)
        msg = ("🚀 Sphere: автозапуск увімкнено!" if enabled else "⏹ Sphere: автозапуск вимкнено.") if ok \
              else "⚠ Не вдалося змінити автозапуск Sphere"
        self.push_to_js.emit("toast", json.dumps({"msg": msg}))
        self._get_autostart_status(None)

    # ── Sphere process management ─────────────────────────────────────────────
    def _sphere_pids(self) -> list:
        pids = []
        # ── Primary: psutil (cross-platform, preferred) ───────────────────────
        try:
            import psutil
            for p in psutil.process_iter(['pid', 'cmdline', 'name']):
                try:
                    name = (p.info.get('name') or '').lower()
                    cmd  = ' '.join(p.info.get('cmdline') or [])
                    if 'aivon_sphere.py' in cmd or 'axis_sphere' in name:
                        pids.append(p.info['pid'])
                except Exception:
                    pass
            return pids
        except Exception:
            pass
        # ── Fallback: AXIS_Sphere.exe only (frozen build) ────────────────────
        if sys.platform == "win32":
            try:
                out2 = subprocess.check_output(
                    ["tasklist", "/FI", "IMAGENAME eq AXIS_Sphere.exe",
                     "/FO", "CSV", "/NH"],
                    creationflags=_NO_WINDOW, timeout=3
                ).decode(errors="replace")
                import csv, io
                for row in csv.reader(io.StringIO(out2)):
                    if len(row) >= 2 and 'AXIS_Sphere' in row[0]:
                        try:
                            pids.append(int(row[1].strip()))
                        except ValueError:
                            pass
            except Exception:
                pass
        return pids

    def _sphere_really_running(self) -> bool:
        """More reliable check: psutil → wmic → AXIS_Sphere.exe tasklist."""
        # psutil-based check (most reliable, includes dev-mode python.exe)
        pids = self._sphere_pids()
        if pids:
            return True
        # No psutil: try wmic to find 'aivon_sphere' in command lines
        if sys.platform == "win32":
            try:
                out = subprocess.check_output(
                    ["wmic", "process", "where",
                     "name='python.exe' or name='AXIS_Sphere.exe'",
                     "get", "CommandLine", "/VALUE"],
                    creationflags=_NO_WINDOW, timeout=5
                ).decode(errors="replace")
                return "aivon_sphere" in out.lower() or "axis_sphere" in out.lower()
            except Exception:
                pass
        return False

    def _sphere_status(self, _):
        running = self._sphere_really_running()
        self.push_to_js.emit("sphere_status", json.dumps({"running": running}))

    def _stop_sphere(self, _):
        # Try stored proc first — cleanest shutdown
        if hasattr(self, '_sphere_proc') and self._sphere_proc and self._sphere_proc.poll() is None:
            try:
                self._sphere_proc.terminate()
                self._sphere_proc.wait(timeout=5)
                self._sphere_proc = None
                print("[Sphere] Process terminated via stored handle")
                self.push_to_js.emit("toast", json.dumps({"msg": "⏹ Sphere зупинено"}))
                threading.Thread(target=self._push_status_after, args=(0.8,), daemon=True).start()
                return
            except Exception as e:
                print(f"[Sphere] Terminate failed: {e}")
        pids = self._sphere_pids()
        killed = 0
        if pids:
            try:
                import psutil
                killed = sum(1 for pid in pids if self._try_kill(psutil, pid))
            except Exception:
                # psutil not available — use taskkill on Windows
                if sys.platform == "win32":
                    try:
                        for pid in pids:
                            subprocess.run(
                                ["taskkill", "/F", "/PID", str(pid)],
                                creationflags=_NO_WINDOW, timeout=3
                            )
                            killed += 1
                    except Exception:
                        pass
        # Also kill AXIS_Sphere.exe if running as frozen app
        if sys.platform == "win32":
            try:
                r = subprocess.run(
                    ["taskkill", "/F", "/IM", "AXIS_Sphere.exe"],
                    creationflags=_NO_WINDOW, capture_output=True, timeout=3
                )
                if r.returncode == 0:
                    killed += 1
            except Exception:
                pass
        msg = "⏹ Sphere зупинено" if killed else "⚠ Sphere не запущена"
        self.push_to_js.emit("toast", json.dumps({"msg": msg}))
        threading.Thread(target=self._push_status_after, args=(0.8,), daemon=True).start()

    def _launch_sphere(self, _):
        if self._sphere_really_running():
            self.push_to_js.emit("toast", json.dumps({"msg": "🔮 Sphere вже запущена"}))
            self._sphere_status(None)
            return

        # Build a push function that forwards sphere lines to the Panel log viewer.
        # Lines tagged "__push__" are axisPush events forwarded to Panel JS directly.
        def _push_log(level, msg):
            try:
                if level == "__push__":
                    # msg = "event_type:json_data"
                    sep = msg.find(":")
                    if sep != -1:
                        self.push_to_js.emit(msg[:sep], msg[sep + 1:])
                else:
                    self.push_to_js.emit("log_line", json.dumps({"level": level, "msg": msg}))
            except Exception:
                pass

        # Force unbuffered UTF-8 output so lines arrive without encoding errors
        import copy
        sphere_env = copy.copy(os.environ)
        sphere_env["PYTHONUNBUFFERED"]  = "1"
        sphere_env["PYTHONIOENCODING"]  = "utf-8"
        sphere_env["PYTHONUTF8"]        = "1"

        pipe_kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=sphere_env,
        )

        if getattr(sys, "frozen", False):
            # Frozen: exe dir = parent of sys.executable
            axis_dir = os.path.dirname(sys.executable)
            sphere_exe = os.path.join(axis_dir, "AXIS_Sphere.exe")
            if not os.path.exists(sphere_exe):
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"⚠ AXIS_Sphere.exe не знайдено: {axis_dir}"}))
                return
            proc = subprocess.Popen(
                [sphere_exe], cwd=axis_dir,
                creationflags=_NO_WINDOW, **pipe_kwargs)
        else:
            # Dev mode: project root is 2 levels up from gui/handlers/
            axis_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
            sphere_script = os.path.join(axis_dir, "aivon_sphere.py")
            if not os.path.exists(sphere_script):
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"⚠ aivon_sphere.py не знайдено: {axis_dir}"}))
                return
            proc = subprocess.Popen(
                [sys.executable, "-u", sphere_script],   # -u = unbuffered stdout
                cwd=axis_dir,
                creationflags=_NO_WINDOW, **pipe_kwargs)
        self._sphere_proc = proc

        # Stream sphere output to Panel log viewer
        _stream_sphere_output(proc, _push_log)

        self.push_to_js.emit("toast", json.dumps({"msg": "🔮 AIVON Sphere запускається..."}))
        # Check status at 3s and again at 6s (sphere can be slow to start)
        threading.Thread(target=self._push_status_after, args=(3.0,), daemon=True).start()
        threading.Thread(target=self._push_status_after, args=(6.0,), daemon=True).start()

    def _push_status_after(self, delay: float):
        import time
        time.sleep(delay)
        self._sphere_status(None)

    def _try_kill(self, psutil, pid: int) -> bool:
        try:
            psutil.Process(pid).terminate()
            return True
        except Exception:
            return False

    # ── Commands / macros persistence ─────────────────────────────────────────
    def _save_commands(self, p: dict):
        cmds = p.get("commands", [])
        try:
            from core.paths import COMMANDS_FILE
            with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
                json.dump(cmds, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[AXIS] save_commands error: {e}")

    def _reload_commands(self, _):
        """Re-read commands from file and push to JS (e.g. after sphere adds a command)."""
        try:
            from core.paths import COMMANDS_FILE
            if COMMANDS_FILE.exists():
                with open(COMMANDS_FILE, encoding="utf-8") as f:
                    content = f.read()
                self.push_to_js.emit("user_commands", content)
        except Exception as e:
            print(f"[AXIS] reload_commands error: {e}")

    def _save_macros(self, p: dict):
        macros = p.get("macros", [])
        try:
            from core.paths import MACROS_FILE
            with open(MACROS_FILE, "w", encoding="utf-8") as f:
                json.dump(macros, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[AXIS] save_macros error: {e}")
