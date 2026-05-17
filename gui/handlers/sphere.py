"""Sphere process management, autostart, config & commands persistence."""
import json
import os
import subprocess
import sys
import threading

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


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
        if getattr(sys, "frozen", False):
            # Frozen: exe dir = parent of sys.executable
            axis_dir = os.path.dirname(sys.executable)
            sphere_exe = os.path.join(axis_dir, "AXIS_Sphere.exe")
            if not os.path.exists(sphere_exe):
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"⚠ AXIS_Sphere.exe не знайдено: {axis_dir}"}))
                return
            subprocess.Popen([sphere_exe], cwd=axis_dir, creationflags=_NO_WINDOW)
        else:
            # Dev mode: project root is 2 levels up from gui/handlers/
            axis_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
            sphere_script = os.path.join(axis_dir, "aivon_sphere.py")
            if not os.path.exists(sphere_script):
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"⚠ aivon_sphere.py не знайдено: {axis_dir}"}))
                return
            subprocess.Popen([sys.executable, sphere_script], cwd=axis_dir, creationflags=_NO_WINDOW)
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
