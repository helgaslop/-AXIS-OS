"""File open/save/analyze, run_code handlers."""
import json
import os
import subprocess
import sys

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class FilesHandlerMixin:
    # ── IDE file I/O ──────────────────────────────────────────────────────────
    def _open_ide_file(self, _):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self._win, "Відкрити файл у IDE", "",
            "Текстові файли (*.py *.js *.ts *.jsx *.tsx *.html *.htm *.css "
            "*.json *.yaml *.yml *.toml *.ini *.cfg *.txt *.md *.log *.sh *.bat *.ps1);;"
            "Python (*.py);;Веб (*.html *.htm *.css *.js);;Конфіги (*.json *.yaml *.yml);;Всі файли (*)",
        )
        if path:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self.push_to_js.emit("file_content",
                    json.dumps({"path": path, "content": content}))
            except Exception as e:
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"⚠ Помилка читання: {e}"}))

    def _open_file(self, p: dict):
        path = p.get("path", "")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                self.push_to_js.emit("file_content",
                    json.dumps({"path": path, "content": content}))
            except Exception as e:
                self.push_to_js.emit("toast", json.dumps({"msg": str(e)}))

    def _open_file_path(self, p: dict):
        """Open a specific file path in the IDE (from recent files sidebar)."""
        self._open_file(p)

    def _save_file(self, p: dict):
        path    = p.get("path", "")
        content = p.get("content", "")
        if not path:
            self.push_to_js.emit("toast",
                json.dumps({"msg": "⚠ Невідомий шлях — використайте «Зберегти як»"}))
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.push_to_js.emit("toast",
                json.dumps({"msg": f"💾 Збережено: {os.path.basename(path)}"}))
        except Exception as e:
            self.push_to_js.emit("toast",
                json.dumps({"msg": f"⚠ Помилка збереження: {e}"}))

    def _save_file_as(self, p: dict):
        from PyQt6.QtWidgets import QFileDialog
        content = p.get("content", "")
        path, _ = QFileDialog.getSaveFileName(
            self._win, "Зберегти файл як", "",
            "Python (*.py);;Веб (*.html);;JSON (*.json);;Текст (*.txt);;Всі файли (*)",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.push_to_js.emit("file_saved", json.dumps({"path": path}))
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"💾 Збережено: {os.path.basename(path)}"}))
            except Exception as e:
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"⚠ Помилка збереження: {e}"}))

    # ── File dialog for Commands page ─────────────────────────────────────────
    def _open_file_dialog(self, _):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self._win, "Вибрати файл для команди", "",
            "Всі файли (*);;"
            "Python (*.py);;Скрипти (*.bat *.cmd *.sh *.ps1);;"
            "Веб (*.html *.htm *.url);;Програми (*.exe);;"
            "Конфіги (*.json *.yaml *.yml *.toml *.ini *.cfg *.env);;"
            "Текст (*.txt *.md *.log)",
        )
        if path:
            info = self._analyze_file(path)
            self.push_to_js.emit("file_selected", json.dumps(info))

    def _analyze_file(self, path: str) -> dict:
        name  = os.path.basename(path)
        ext   = os.path.splitext(name)[1].lower()
        stem  = os.path.splitext(name)[0]
        display = stem.replace("_", " ").replace("-", " ").title()
        qpath   = f'"{path}"'
        table = {
            ".py":   ("python", "🐍", f'python {qpath}',          f"Python скрипт: {name}"),
            ".bat":  ("shell",  "⚙",  qpath,                       f"Batch файл: {name}"),
            ".cmd":  ("shell",  "⚙",  qpath,                       f"CMD скрипт: {name}"),
            ".sh":   ("shell",  "🐚", f'bash {qpath}',             f"Shell скрипт: {name}"),
            ".ps1":  ("shell",  "💙", f'powershell -File {qpath}', f"PowerShell: {name}"),
            ".exe":  ("shell",  "🚀", qpath,                       f"Програма: {name}"),
            ".html": ("url",    "🌐", path.replace("\\", "/"),     f"HTML файл: {name}"),
            ".htm":  ("url",    "🌐", path.replace("\\", "/"),     f"HTML файл: {name}"),
            ".url":  ("url",    "🔗", path,                        f"URL файл: {name}"),
            ".txt":  ("shell",  "📄", f'notepad {qpath}',          f"Текстовий файл: {name}"),
            ".md":   ("shell",  "📝", f'notepad {qpath}',          f"Markdown: {name}"),
            ".log":  ("shell",  "📋", f'notepad {qpath}',          f"Лог файл: {name}"),
            ".json": ("shell",  "⚙",  f'notepad {qpath}',          f"JSON конфіг: {name}"),
            ".yaml": ("shell",  "⚙",  f'notepad {qpath}',          f"YAML конфіг: {name}"),
            ".yml":  ("shell",  "⚙",  f'notepad {qpath}',          f"YAML конфіг: {name}"),
            ".toml": ("shell",  "⚙",  f'notepad {qpath}',          f"TOML конфіг: {name}"),
            ".env":  ("shell",  "🔒", f'notepad {qpath}',          f"ENV файл: {name}"),
        }
        cmd_type, ico, body, desc = table.get(ext, ("shell", "📁", qpath, f"Файл: {name}"))
        if ext == ".py":
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    body = f.read()
            except Exception:
                pass
        return {"path": path, "filename": name, "name": display,
                "ico": ico, "type": cmd_type, "body": body, "desc": desc}

    # ── Run code in terminal ───────────────────────────────────────────────────
    def _run_code(self, p: dict):
        code = p.get("code", "")
        lang = p.get("lang", "python")
        if lang == "python" and code:
            import tempfile, sys
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False,
                                             mode="w", encoding="utf-8") as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            try:
                result = subprocess.run(
                    [sys.executable, tmp_path],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_NO_WINDOW,
                )
                output = result.stdout + (result.stderr or "")
            except subprocess.TimeoutExpired:
                output = "⚠ Час виконання вичерпано (10 сек)"
            except Exception as e:
                output = str(e)
            finally:
                try: os.unlink(tmp_path)
                except Exception: pass
            self.push_to_js.emit("code_output", json.dumps({"output": output}))
