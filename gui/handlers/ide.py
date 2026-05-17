"""IDE process management and project scaffolding handlers."""
import json
import os
import subprocess
import sys
import threading

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class IdeHandlerMixin:
    _IDE_CONFIG_PATH = None  # resolved lazily

    def _ide_config_path(self) -> str:
        if not IdeHandlerMixin._IDE_CONFIG_PATH:
            from core.paths import AGENT_CONFIG_FILE
            IdeHandlerMixin._IDE_CONFIG_PATH = str(AGENT_CONFIG_FILE)
        return IdeHandlerMixin._IDE_CONFIG_PATH

    def _load_ide_config(self) -> dict:
        path = self._ide_config_path()
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _ide_pids(self) -> list:
        pids = []
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmd = ' '.join(proc.info.get('cmdline') or [])
                    if 'axis_ide.py' in cmd:
                        pids.append(proc.info['pid'])
                except Exception:
                    pass
        except Exception:
            pass
        return pids

    def _get_ide_status(self, _):
        running = len(self._ide_pids()) > 0
        cfg = self._load_ide_config()
        self.push_to_js.emit("ide_status", json.dumps({"running": running, "config": cfg}))

    def _stop_ide(self, _):
        try:
            import psutil
            killed = 0
            for pid in self._ide_pids():
                try:
                    psutil.Process(pid).terminate()
                    killed += 1
                except Exception:
                    pass
            msg = "⏹ IDE зупинено" if killed else "⚠ IDE не запущена"
            self.push_to_js.emit("toast", json.dumps({"msg": msg}))
        except Exception as e:
            self.push_to_js.emit("toast", json.dumps({"msg": f"⚠ Помилка: {e}"}))
        threading.Thread(target=self._push_ide_status_after, args=(0.8,), daemon=True).start()

    def _launch_ide(self, p: dict):
        if self._ide_pids():
            self.push_to_js.emit("toast", json.dumps({"msg": "🖥 IDE вже запущена"}))
            self._get_ide_status(None)
            return
        project_path = p.get("project_path", "")
        open_folder  = p.get("open_folder", False)
        if getattr(sys, "frozen", False):
            # Frozen: exe dir = parent of sys.executable
            axis_dir = os.path.dirname(sys.executable)
            ide_exe  = os.path.join(axis_dir, "AXIS_IDE.exe")
            if not os.path.exists(ide_exe):
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"⚠ AXIS_IDE.exe не знайдено: {axis_dir}"}))
                return
            args = [ide_exe]
            if project_path: args += ["--project", project_path]
            elif open_folder: args += ["--open-folder"]
            subprocess.Popen(args, cwd=axis_dir, creationflags=_NO_WINDOW)
        else:
            axis_dir   = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
            ide_script = os.path.join(axis_dir, "axis_ide.py")
            if not os.path.exists(ide_script):
                self.push_to_js.emit("toast",
                    json.dumps({"msg": f"⚠ axis_ide.py не знайдено: {axis_dir}"}))
                return
            args = [sys.executable, ide_script]
            if project_path: args += ["--project", project_path]
            elif open_folder: args += ["--open-folder"]
            subprocess.Popen(args, cwd=axis_dir, creationflags=_NO_WINDOW)
        self.push_to_js.emit("toast", json.dumps({"msg": "🖥 AXIS IDE запускається..."}))
        threading.Thread(target=self._push_ide_status_after, args=(3.5,), daemon=True).start()

    def _push_ide_status_after(self, delay: float):
        import time
        time.sleep(delay)
        self._get_ide_status(None)

    def _save_ide_config(self, p: dict):
        path = self._ide_config_path()
        try:
            existing = {}
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    existing = json.load(f)
            existing.update(p)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            self.push_to_js.emit("toast",
                json.dumps({"msg": "✓ Налаштування IDE збережено"}))
            self.push_to_js.emit("ide_config", json.dumps(existing))
        except Exception as e:
            self.push_to_js.emit("toast",
                json.dumps({"msg": f"⚠ Помилка збереження IDE: {e}"}))

    def _ide_new_project(self, p: dict):
        template = p.get("template", "python")
        from PyQt6.QtWidgets import QFileDialog, QInputDialog
        parent_dir = QFileDialog.getExistingDirectory(
            self._win, "Виберіть папку для нового проекту", os.path.expanduser("~"))
        if not parent_dir:
            return
        name, ok = QInputDialog.getText(
            self._win, "Назва проекту", "Введіть назву проекту:",
            text=f"my_{template}_project")
        if not ok or not name.strip():
            return
        name     = name.strip().replace(" ", "_")
        proj_dir = os.path.join(parent_dir, name)
        try:
            os.makedirs(proj_dir, exist_ok=True)
            templates = {
                "python": {
                    "main.py":          '# -*- coding: utf-8 -*-\n\ndef main():\n    print("Hello, World!")\n\nif __name__ == "__main__":\n    main()\n',
                    "requirements.txt": "",
                    ".gitignore":       "__pycache__/\n*.pyc\n.env\nvenv/\n",
                },
                "web": {
                    "index.html": '<!DOCTYPE html>\n<html lang="uk">\n<head>\n  <meta charset="UTF-8">\n  <title>Project</title>\n  <link rel="stylesheet" href="style.css">\n</head>\n<body>\n  <h1>Hello, World!</h1>\n  <script src="script.js"></script>\n</body>\n</html>\n',
                    "style.css":  "* { box-sizing: border-box; margin: 0; padding: 0; }\n",
                    "script.js":  "// main script\nconsole.log('Hello, World!');\n",
                },
                "node": {
                    "index.js":     "'use strict';\nconsole.log('Hello, World!');\n",
                    "package.json": json.dumps({"name": name, "version": "1.0.0",
                                                "main": "index.js",
                                                "scripts": {"start": "node index.js"}},
                                               indent=2) + "\n",
                    ".gitignore":   "node_modules/\n.env\n",
                },
                "empty": {},
            }
            for filename, content in templates.get(template, {}).items():
                with open(os.path.join(proj_dir, filename), "w", encoding="utf-8") as f:
                    f.write(content)
            cfg = self._load_ide_config()
            recent = cfg.get("recent_projects", [])
            if proj_dir not in recent:
                recent.insert(0, proj_dir)
            cfg["recent_projects"] = recent[:10]
            cfg_path = self._ide_config_path()
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self._launch_ide({"project_path": proj_dir})
        except Exception as e:
            self.push_to_js.emit("toast",
                json.dumps({"msg": f"⚠ Помилка створення проекту: {e}"}))
