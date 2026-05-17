"""Window controls, run_macro, run_command, clipboard, updater handlers."""
import json
import os
import subprocess
import sys
import threading

# Hide CMD windows on Windows
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class SystemHandlerMixin:
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
                import webbrowser
                webbrowser.open(body)
                self.push_to_js.emit("toast", json.dumps({"msg": f"🌐 {name}"}))
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
                webbrowser.open(cmd)
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"🌐 Відкрито: {cmd[:50]}"}))
            except Exception as e:
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"URL помилка: {e}"}))

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
            from core.paths import CONFIG_FILE
            import json as _j
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                _j.dump(self._cfg, f, ensure_ascii=False, indent=2)
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
        from core.updater import download_github_asset, apply_github_update

        def on_download_progress(done, total):
            pct = int(done * 100 / total) if total else 0
            self.push_to_js.emit("github_download_status", json.dumps(
                {"status": "downloading", "pct": pct,
                 "done": done, "total": total}))

        def on_apply_status(status, label, pct):
            self.push_to_js.emit("github_download_status", json.dumps(
                {"status": status, "label": label, "pct": pct}))

        try:
            # 1. Завантажуємо ZIP
            self.push_to_js.emit("github_download_status",
                json.dumps({"status": "downloading", "pct": 0,
                            "label": "⬇ Завантажую архів..."}))
            zip_path = download_github_asset(url, on_progress=on_download_progress)

            # 2. Розпаковуємо + копіюємо + pip + перезапуск
            #    Всі статуси тепер йдуть через on_apply_status колбек
            apply_github_update(zip_path, restart=True, on_status=on_apply_status)
            # apply_github_update робить sys.exit(0) — далі не дійде

        except Exception as e:
            self.push_to_js.emit("github_download_status",
                json.dumps({"status": "error", "error": str(e)}))

    def _save_cfg_silent(self):
        """Зберігає self._cfg без сповіщень."""
        try:
            from core.paths import CONFIG_FILE
            import json as _j
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                _j.dump(self._cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
