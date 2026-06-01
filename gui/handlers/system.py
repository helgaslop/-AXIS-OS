"""Window controls, run_macro, run_command, clipboard, updater handlers."""
import base64
import json
import os
import re
import subprocess
import sys
import threading
import zipfile

from gui.handlers.ai import _cfg_lock

# Hide CMD windows on Windows
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class SystemHandlerMixin:
    @staticmethod
    def _to_spotify_uri(body: str) -> str | None:
        """Convert a Spotify URL or URI to a spotify: URI. Returns None if not Spotify."""
        b = body.strip()
        if b.startswith("spotify:"):
            return b
        m = re.match(r"https?://open\.spotify\.com/([a-z]+)/([A-Za-z0-9]+)", b)
        return f"spotify:{m.group(1)}:{m.group(2)}" if m else None

    # ── Window controls ───────────────────────────────────────────────────────
    def _minimize(self, _): self._win.showMinimized()

    def _maximize(self, _):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()

    def _close(self, _): self._win.close()

    # ── Execute a user command directly ──────────────────────────────────────
    def _run_command(self, p: dict):
        cmd_type = p.get("type", "shell")
        body     = p.get("body", "")
        name     = p.get("name", body)
        if not body:
            return
        try:
            if cmd_type == "shell":
                subprocess.Popen(body, shell=True, creationflags=_NO_WINDOW)
                self.push_to_js.emit("toast", json.dumps({"msg": f"▶ {name}"}))
            elif cmd_type == "url":
                # Spotify URI / open.spotify.com → route through Spotify player
                spotify_uri = self._to_spotify_uri(body)
                if spotify_uri:
                    self._spotify_action({"action": "play_uri", "uri": spotify_uri})
                elif body.startswith(("http://", "https://")):
                    import webbrowser
                    webbrowser.open(body)
                    self.push_to_js.emit("toast", json.dumps({"msg": f"🌐 {name}"}))
                else:
                    print(f"[AXIS] Blocked non-http URL in run_command: {body!r}")
                    self.push_to_js.emit("toast",
                        json.dumps({"msg": f"⚠ Заблоковано: не http(s) URL"}))
            elif cmd_type == "python":
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".py", delete=False,
                                                 mode="w", encoding="utf-8") as tmp:
                    tmp.write(body)
                    tmp_path = tmp.name
                subprocess.Popen([sys.executable, tmp_path], creationflags=_NO_WINDOW)
                self.push_to_js.emit("toast", json.dumps({"msg": f"🐍 {name}"}))
            elif cmd_type == "internal":
                self.push_to_js.emit("internal_cmd", json.dumps({"cmd": body}))
        except Exception as e:
            self.push_to_js.emit("toast",
                json.dumps({"msg": f"⚠ Помилка команди: {e}"}))

    # ── Macros / run_macro ────────────────────────────────────────────────────
    def _run_macro(self, p: dict):
        cmd   = p.get("command", "")
        mtype = p.get("type", "shell")
        if not cmd:
            return

        if mtype == "shell":
            try:
                subprocess.Popen(cmd, shell=True, creationflags=_NO_WINDOW)
                silent = cmd.startswith("powershell -c") or p.get("silent", False)
                if not silent:
                    label = p.get("label") or p.get("name") or cmd[:50]
                    self.push_to_js.emit("toast", json.dumps({"msg": f"▶ {label}"}))
            except Exception as e:
                self.push_to_js.emit("toast", json.dumps({"msg": f"Помилка: {e}"}))

        elif mtype == "python":
            import tempfile
            try:
                with tempfile.NamedTemporaryFile(suffix=".py", delete=False,
                                                 mode="w", encoding="utf-8") as tmp:
                    tmp.write(cmd)
                    tmp_path = tmp.name
                subprocess.Popen([sys.executable, tmp_path], creationflags=_NO_WINDOW)
                self.push_to_js.emit("toast",
                    json.dumps({"msg": "🐍 Python скрипт запущено"}))
            except Exception as e:
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"Python помилка: {e}"}))

        elif mtype == "url":
            try:
                import webbrowser
                if cmd.startswith(("http://", "https://")):
                    webbrowser.open(cmd)
                    self.push_to_js.emit("toast",
                        json.dumps({"msg": f"🌐 Відкрито: {cmd[:50]}"}))
                else:
                    print(f"[AXIS] Blocked non-http URL in run_macro: {cmd!r}")
                    self.push_to_js.emit("toast",
                        json.dumps({"msg": f"⚠ Заблоковано: не http(s) URL"}))
            except Exception as e:
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"URL помилка: {e}"}))

        elif mtype == "keystroke":
            try:
                import ctypes
                # Parse key combo like "ctrl+shift+s", "win+d", "alt+f4"
                parts = [k.strip().lower() for k in cmd.replace('+', ' ').split()]
                VK = {
                    'ctrl':0x11,'control':0x11,'shift':0x10,'alt':0x12,'win':0x5B,
                    'enter':0x0D,'esc':0x1B,'tab':0x09,'space':0x20,'backspace':0x08,
                    'delete':0x2E,'home':0x24,'end':0x23,'up':0x26,'down':0x28,
                    'left':0x25,'right':0x27,'f1':0x70,'f2':0x71,'f3':0x72,'f4':0x73,
                    'f5':0x74,'f6':0x75,'f7':0x76,'f8':0x77,'f9':0x78,'f10':0x79,
                    'f11':0x7A,'f12':0x7B,
                }
                keys = [VK.get(p, ord(p.upper())) for p in parts if p]
                KEYEVENTF_KEYUP = 0x0002
                for k in keys:
                    ctypes.windll.user32.keybd_event(k, 0, 0, 0)
                for k in reversed(keys):
                    ctypes.windll.user32.keybd_event(k, 0, KEYEVENTF_KEYUP, 0)
                self.push_to_js.emit("toast", json.dumps({"msg": f"⌨ Клавіші: {cmd}"}))
            except Exception as e:
                self.push_to_js.emit("toast", json.dumps({"msg": f"Keystroke помилка: {e}"}))

        elif mtype == "internal":
            self.push_to_js.emit("internal_cmd", json.dumps({"cmd": cmd}))

    # ── Clipboard ─────────────────────────────────────────────────────────────
    def _get_clipboard(self, _):
        try:
            from PyQt6.QtWidgets import QApplication
            cb = QApplication.clipboard()
            text = cb.text() if cb else ""
            self.push_to_js.emit("clipboard_content", json.dumps({"text": text}))
        except Exception as e:
            self.push_to_js.emit("clipboard_content",
                json.dumps({"text": "", "error": str(e)}))

    def _set_clipboard(self, p: dict):
        try:
            from PyQt6.QtWidgets import QApplication
            cb = QApplication.clipboard()
            if cb:
                cb.setText(p.get("text", ""))
        except Exception:
            pass

    # ── Updater (local folder) ────────────────────────────────────────────────
    def _check_update(self, p: dict):
        folder = p.get("folder") or self._cfg.get("update_folder", "")
        threading.Thread(target=self._check_update_worker,
                         args=(folder,), daemon=True).start()

    def _check_update_worker(self, folder: str):
        from core.updater import check_for_update, get_current_version
        cur = get_current_version()
        if not folder:
            self.push_to_js.emit("update_status", json.dumps(
                {"status": "no_folder", "current": cur}))
            return
        info = check_for_update(folder)
        if info:
            self.push_to_js.emit("update_status", json.dumps(
                {"status": "available", "current": cur,
                 "version": info["version"], "folder": info["folder"],
                 "installer": info.get("installer") or ""}))
        else:
            self.push_to_js.emit("update_status", json.dumps(
                {"status": "up_to_date", "current": cur}))

    def _apply_update(self, p: dict):
        from core.updater import apply_update
        info = {
            "version":   p.get("version", ""),
            "folder":    p.get("folder", ""),
            "installer": p.get("installer", ""),
        }
        self.push_to_js.emit("toast", json.dumps(
            {"msg": "🔄 Застосовую оновлення..."}))
        threading.Thread(target=apply_update, args=(info, True),
                         daemon=True).start()

    def _save_update_folder(self, p: dict):
        folder = p.get("folder", "").strip()
        self._cfg["update_folder"] = folder
        try:
            self._save_config_file()
            self.push_to_js.emit("toast", json.dumps(
                {"msg": "✓ Папку оновлень збережено"}))
        except Exception as e:
            self.push_to_js.emit("toast", json.dumps({"msg": f"⚠ {e}"}))

    # ── Updater (GitHub Releases) ─────────────────────────────────────────────
    def _check_github_update(self, p: dict):
        repo = p.get("repo") or self._cfg.get("github_repo", "")
        if repo:
            # Зберігаємо репо в конфіг
            self._cfg["github_repo"] = repo.strip()
            self._save_cfg_silent()
        threading.Thread(target=self._check_github_worker,
                         args=(repo,), daemon=True).start()

    def _check_github_worker(self, repo: str):
        from core.updater import check_github_update, get_current_version
        cur = get_current_version()
        if not repo or "/" not in repo.strip():
            self.push_to_js.emit("github_update_status", json.dumps(
                {"status": "no_repo", "current": cur}))
            return
        try:
            info = check_github_update(repo.strip())
            if info:
                self.push_to_js.emit("github_update_status", json.dumps(
                    {"status": "available", **info}))
            else:
                self.push_to_js.emit("github_update_status", json.dumps(
                    {"status": "up_to_date", "current": cur}))
        except Exception as e:
            self.push_to_js.emit("github_update_status", json.dumps(
                {"status": "error", "current": cur, "error": str(e)}))

    def _download_github_update(self, p: dict):
        url     = p.get("url", "")
        version = p.get("version", "")
        if not url:
            self.push_to_js.emit("github_download_status",
                json.dumps({"status": "error", "error": "URL не вказано"}))
            return
        threading.Thread(target=self._download_github_worker,
                         args=(url, version), daemon=True).start()

    def _download_github_worker(self, url: str, version: str):
        from core.updater import (download_github_asset, apply_github_update,
                                   apply_installer_update)

        def on_download_progress(done, total):
            pct = int(done * 100 / total) if total else 0
            self.push_to_js.emit("github_download_status", json.dumps(
                {"status": "downloading", "pct": pct,
                 "done": done, "total": total}))

        def on_apply_status(status, label, pct):
            self.push_to_js.emit("github_download_status", json.dumps(
                {"status": status, "label": label, "pct": pct}))

        try:
            is_installer = url.lower().endswith('.exe')
            label_start  = "⬇ Завантажую інсталятор..." if is_installer \
                           else "⬇ Завантажую архів..."

            self.push_to_js.emit("github_download_status",
                json.dumps({"status": "downloading", "pct": 0,
                            "label": label_start}))

            file_path = download_github_asset(url, on_progress=on_download_progress)

            if is_installer:
                # Встановлений .exe → запускаємо інсталятор тихо
                apply_installer_update(file_path, on_status=on_apply_status)
            else:
                # Запуск з вихідного коду → патч-оновлення файлів
                apply_github_update(file_path, restart=True,
                                    on_status=on_apply_status)
            # обидві функції роблять sys.exit(0) — далі не дійде

        except Exception as e:
            self.push_to_js.emit("github_download_status",
                json.dumps({"status": "error", "error": str(e)}))

    def _save_cfg_silent(self):
        """Зберігає self._cfg без сповіщень."""
        try:
            self._save_config_file()
        except Exception:
            pass

    # ── Quick Search ──────────────────────────────────────────────────────────
    def _search_quick(self, p: dict):
        """Search commands/macros/pages and return results to JS."""
        q = p.get("q", "").strip().lower()
        results = []
        if not q:
            self.push_to_js.emit("search_results", json.dumps({"results": []}))
            return

        try:
            from core.paths import USER_DATA_DIR
            # Search user commands
            cmds_path = os.path.join(USER_DATA_DIR, "user_commands.json")
            if os.path.exists(cmds_path):
                with open(cmds_path, encoding="utf-8") as f:
                    cmds = json.load(f)
                if isinstance(cmds, list):
                    for c in cmds:
                        name = (c.get("name") or c.get("label") or "").lower()
                        body = (c.get("body") or "").lower()
                        if q in name or q in body:
                            results.append({
                                "icon": "🌐" if c.get("type") == "url" else "🐍" if c.get("type") == "python" else "📋",
                                "label": c.get("name") or c.get("label") or c.get("body", "")[:50],
                                "sub": c.get("body", "")[:60],
                                "category": "Команди (Python)",
                                "cmd": c,
                            })
            # Search macros
            macros_path = os.path.join(USER_DATA_DIR, "macros.json")
            if os.path.exists(macros_path):
                with open(macros_path, encoding="utf-8") as f:
                    macros_list = json.load(f)
                if isinstance(macros_list, list):
                    for m in macros_list:
                        name = (m.get("name") or m.get("label") or "").lower()
                        if q in name:
                            results.append({
                                "icon": "⚡",
                                "label": m.get("name") or m.get("label", ""),
                                "sub": (m.get("command") or "")[:60],
                                "category": "Макроси (Python)",
                                "action": "run_macro",
                                "data": m,
                            })
        except Exception as e:
            print(f"[AXIS search] error: {e}")

        self.push_to_js.emit("search_results", json.dumps({"results": results[:20]}))

    # ── Settings Backup Export ────────────────────────────────────────────────
    def _export_backup(self, _):
        threading.Thread(target=self._export_backup_worker, daemon=True).start()

    def _export_backup_worker(self):
        try:
            from core.paths import USER_DATA_DIR
            DATA_DIR = USER_DATA_DIR
            from datetime import datetime

            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"AXIS_OS_backup_{date_str}.zip"
            zip_path = os.path.join(desktop, zip_name)

            files_to_backup = [
                "config.json",
                "commands.json",
                "macros.json",
                "user_commands.json",
                "sphere_config.json",
            ]

            included = []
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in files_to_backup:
                    fpath = os.path.join(DATA_DIR, fname)
                    if os.path.exists(fpath):
                        zf.write(fpath, arcname=fname)
                        included.append(fname)

            # Open the folder
            if sys.platform == "win32":
                subprocess.Popen(f'explorer /select,"{zip_path}"', shell=True)

            self.push_to_js.emit("backup_status", json.dumps({
                "op": "export",
                "ok": True,
                "msg": f"✓ Збережено: {zip_name} ({len(included)} файлів)",
                "path": zip_path,
            }))
            self.push_to_js.emit("toast", json.dumps({
                "msg": f"✓ Бекап збережено на Робочому столі"
            }))
        except Exception as e:
            self.push_to_js.emit("backup_status", json.dumps({
                "op": "export",
                "ok": False,
                "msg": f"⚠ Помилка: {e}",
            }))

    # ── Settings Backup Import ────────────────────────────────────────────────
    def _import_backup(self, p: dict):
        data_b64 = p.get("data", "")
        filename  = p.get("filename", "backup.zip")
        threading.Thread(
            target=self._import_backup_worker,
            args=(data_b64, filename),
            daemon=True,
        ).start()

    def _import_backup_worker(self, data_b64: str, filename: str):
        try:
            from core.paths import USER_DATA_DIR
            DATA_DIR = USER_DATA_DIR
            import tempfile

            # Decode base64 ZIP data sent from JS FileReader
            zip_bytes = base64.b64decode(data_b64)

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(zip_bytes)
                tmp_path = tmp.name

            restored = []
            with zipfile.ZipFile(tmp_path, "r") as zf:
                for name in zf.namelist():
                    # Only restore known safe files
                    if name in ("config.json", "commands.json", "macros.json",
                                "user_commands.json", "sphere_config.json"):
                        zf.extract(name, DATA_DIR)
                        restored.append(name)

            os.unlink(tmp_path)

            # Reload config into memory
            try:
                from core.paths import CONFIG_FILE
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    new_cfg = json.load(f)
                with _cfg_lock:
                    self._cfg.update(new_cfg)
                self._save_config_file()
                # Refresh JS UI after backup restore
                try:
                    import json as _json
                    self.push_to_js.emit('sphere_config', _json.dumps(self._cfg))
                    print("[Backup] UI refreshed after import")
                except Exception as e:
                    print(f"[Backup] UI refresh failed: {e}")
            except Exception:
                pass

            self.push_to_js.emit("backup_status", json.dumps({
                "op": "import",
                "ok": True,
                "msg": f"✓ Відновлено: {len(restored)} файлів",
                "restored": restored,
            }))
            self.push_to_js.emit("toast", json.dumps({
                "msg": f"✓ Налаштування відновлено ({len(restored)} файлів)"
            }))
        except Exception as e:
            self.push_to_js.emit("backup_status", json.dumps({
                "op": "import",
                "ok": False,
                "msg": f"⚠ Помилка імпорту: {e}",
            }))
            self.push_to_js.emit("toast", json.dumps({
                "msg": f"⚠ Помилка імпорту: {e}"
            }))
