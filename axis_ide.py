"""
AXIS IDE — AI-First IDE
=======================
Standalone PyQt6 app (separate process).
Loads gui/ui/axis_ide.html in a frameless QWebEngineView.
Bridges to AIManager for all AI operations.
"""
import sys
import os
import re as _re_module
import json
import subprocess
import threading
import shutil
import socket
from pathlib import Path

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ── audioop compat shim ────────────────────────────────────────────────────
try:
    import audioop
except ImportError:
    try:
        import audioop_lts as audioop
        sys.modules["audioop"] = audioop
    except ImportError:
        pass

from PyQt6.QtCore import (
    Qt, QUrl, QObject, pyqtSignal, pyqtSlot, QFile, QTimer
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineScript, QWebEngineSettings
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox
)

# ── Agent orchestration ────────────────────────────────────────────────────
from gui.handlers.agents import AgentsHandlerMixin

# ── Paths ──────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    APP_DIR  = Path(sys.executable).parent          # де лежить .exe
    _RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))  # _internal/ (ресурси PyInstaller 6.x)
else:
    APP_DIR  = Path(__file__).parent
    _RES_DIR = APP_DIR

DATA_DIR    = APP_DIR / "data"                      # поруч з exe
IDE_CFG     = DATA_DIR / "agent_config.json"
MAIN_CFG    = DATA_DIR / "config.json"
HTML_PATH   = _RES_DIR / "gui" / "ui" / "axis_ide.html"  # всередині _internal

# ── Default IDE config ─────────────────────────────────────────────────────
DEFAULT_IDE_CFG = {
    "provider": "openai",
    "model": "gpt-4.1",
    "privacy_mode": False,
    "projects_dir": str(Path.home() / "Projects"),
    "recent_projects": [],
    "ollama_model": "llama3",
    "theme": "dark",
}

# ── Language map ───────────────────────────────────────────────────────────
EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".html": "html", ".htm": "html", ".css": "css",
    ".json": "json", ".md": "markdown", ".yaml": "yaml",
    ".yml": "yaml", ".sh": "shell", ".bash": "shell",
    ".cpp": "cpp", ".c": "c", ".h": "c", ".cs": "csharp",
    ".java": "java", ".go": "go", ".rs": "rust",
    ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".kt": "kotlin", ".sql": "sql", ".xml": "xml",
    ".toml": "toml", ".ini": "ini", ".env": "plaintext",
    ".txt": "plaintext", ".log": "plaintext",
}

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".idea", ".vscode", "dist", "build", ".next", ".cache",
    "*.egg-info",
}


# ══════════════════════════════════════════════════════════════════════════
# DAP Client  (Debug Adapter Protocol — talks to debugpy)
# ══════════════════════════════════════════════════════════════════════════
class DAPClient:
    """Minimal DAP socket client for connecting to a debugpy process."""

    def __init__(self):
        self.sock: socket.socket | None = None
        self.seq  = 1
        self._buf = b""
        self._thr: threading.Thread | None = None
        self._running = False
        self.on_message = None          # callable(dict)

    def connect(self, host: str = "localhost", port: int = 5679):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect((host, port))
        self.sock.settimeout(None)
        self._running = True
        self._thr = threading.Thread(target=self._read_loop, daemon=True)
        self._thr.start()

    def send(self, msg: dict):
        if not self.sock:
            return
        data   = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        try:
            self.sock.sendall(header + data)
        except OSError:
            pass

    def request(self, command: str, args: dict | None = None) -> int:
        seq = self.seq
        self.seq += 1
        self.send({"type": "request", "seq": seq,
                   "command": command, "arguments": args or {}})
        return seq

    def _read_loop(self):
        SEP = b"\r\n\r\n"
        while self._running:
            try:
                chunk = self.sock.recv(8192)
                if not chunk:
                    break
                self._buf += chunk
                while SEP in self._buf:
                    hdr, rest = self._buf.split(SEP, 1)
                    length = 0
                    for line in hdr.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            try:
                                length = int(line.split(b":", 1)[1].strip())
                            except ValueError:
                                pass
                    if len(rest) < length:
                        break
                    try:
                        msg = json.loads(rest[:length].decode("utf-8"))
                        if self.on_message:
                            self.on_message(msg)
                    except Exception:
                        pass
                    self._buf = rest[length:]
            except OSError:
                break

    def close(self):
        self._running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


# ══════════════════════════════════════════════════════════════════════════
# IDE Bridge
# ══════════════════════════════════════════════════════════════════════════
class IDEBridge(QObject, AgentsHandlerMixin):
    push_to_js = pyqtSignal(str, str)   # (type, json_str)
    _js_signal  = pyqtSignal(str)        # thread-safe JS execution

    def __init__(self, window, ai_manager, ide_cfg: dict):
        super().__init__()
        self.window     = window
        self.ai         = ai_manager
        self.ide_cfg    = ide_cfg
        self.project_root: str = ""

        # ── Debugger state ──
        self._dap:          DAPClient | None = None
        self._debug_proc:   subprocess.Popen | None = None
        self._debug_thread_id = 1
        self._pending_confirms: dict = {}      # id → (threading.Event, [bool])

        # ── Project index (RAG) ──
        self._project_index:   list = []       # [{file, line, text}]
        self._project_symbols: dict = {}       # name → [{file, line}]

        # ── Auto-fix loop ──
        self._auto_fix_max: int = 3            # max auto-fix retries

        # ── Cursor-parity features ──
        self._axisrules: str = ""              # .axisrules content
        self._ghost_cancel: dict = {}          # reqId → cancelled flag

        # ── Agent orchestration ──
        self._agents_init()
        self._ide_config = self.ide_cfg   # shared ref for agents handler

        # Connect AI signals
        self.ai.response_token.connect(self._on_token)
        self.ai.response_done.connect(self._on_done)
        self.ai.response_error.connect(self._on_error)
        self.ai.response_ready.connect(self._on_ready)

        # Thread-safe JS: agent workers call _run_js from background threads →
        # emit signal → Qt queues it → _do_run_js runs on main thread
        self._js_signal.connect(self._do_run_js)

    # ── Push helper ────────────────────────────────────────────────────────
    def _push(self, evt_type: str, data):
        if isinstance(data, str):
            self.push_to_js.emit(evt_type, data)
        else:
            self.push_to_js.emit(evt_type, json.dumps(data, ensure_ascii=False))

    def _toast(self, msg: str, kind: str = "info"):
        self._push("toast", {"message": msg, "kind": kind})

    def _run_js(self, js_code: str):
        """
        Thread-safe JS execution.
        Agent workers run on background threads — emit a signal so Qt
        marshals the actual runJavaScript() call onto the main thread.
        """
        self._js_signal.emit(js_code)

    @pyqtSlot(str)
    def _do_run_js(self, js_code: str):
        """Must only be called from the main Qt thread (via _js_signal)."""
        try:
            self.window.view.page().runJavaScript(js_code)
        except Exception:
            pass

    # ── AI signal handlers ─────────────────────────────────────────────────
    def _on_token(self, req_id: str, token: str):
        self._push("ai_token", {"id": req_id, "token": token})

    def _on_done(self, req_id: str):
        self._push("ai_done", {"id": req_id})

    def _on_error(self, req_id: str, err: str):
        self._push("ai_error", {"id": req_id, "error": err})

    def _on_ready(self, req_id: str, text: str):
        self._push("ai_response", {"id": req_id, "text": text})

    # ══════════════════════════════════════════════════════════════════════
    # Main slot — called from JS
    # ══════════════════════════════════════════════════════════════════════
    @pyqtSlot(str, str)
    def call(self, cmd: str, data: str):
        try:
            payload = json.loads(data) if data else {}
        except Exception:
            payload = {"raw": data}

        handlers = {
            "open_folder":              self._open_folder,
            "open_file":                self._open_file,
            "read_file_for_mention":    self._read_file_for_mention,
            "open_or_create_axisrules": self._open_or_create_axisrules,
            "save_file":                self._save_file,
            "create_file":      self._create_file,
            "create_folder":    self._create_folder,
            "delete_file":      self._delete_file,
            "rename_file":      self._rename_file,
            "run_code":         self._run_code,
            "run_terminal":     self._run_terminal,
            "ai_send_stream":   self._ai_send_stream,
            "inline_edit":      self._inline_edit,
            "check_errors":     self._check_errors,
            "check_project":    self._check_project,
            "format_code":      self._format_code,
            "get_project_tree": self._get_project_tree,
            "save_config":      self._save_config,
            "get_config":       self._get_config,
            "minimize":         lambda p: self.window.showMinimized(),
            "maximize":         self._toggle_maximize,
            "close_app":        lambda p: self.window.close(),
            "start_stt":        self._start_stt,
            "open_in_explorer": self._open_in_explorer,
            "open_folder_path": self._open_folder_path,
            # Agent + extras
            "ai_agent":          self._ai_agent,
            "run_file":          self._run_file,
            "project_search":    self._project_search,
            "project_replace":   self._project_replace,
            "auto_save":         self._auto_save,
            # Debugger (DAP)
            "debug_start":       self._debug_start,
            "debug_stop":        self._debug_stop,
            "debug_continue":    self._debug_continue,
            "debug_step_over":   self._debug_step_over,
            "debug_step_into":   self._debug_step_into,
            "debug_step_out":    self._debug_step_out,
            "debug_confirm":     self._debug_confirm_response,
            # LSP (Jedi)
            "lsp_complete":      self._lsp_complete,
            "lsp_signature":     self._lsp_signature,
            # Git
            "git_status":        self._git_status,
            "git_commit":        self._git_commit,
            "git_checkout":      self._git_checkout,
            "git_branches":      self._git_branches,
            "git_diff_lines":    self._git_diff_lines,
            "git_init":          self._git_init,
            "git_push":          self._git_push,
            "git_pull":          self._git_pull,
            "git_fetch":         self._git_fetch,
            "git_log":           self._git_log,
            "git_remotes":       self._git_remotes,
            "git_stash":         self._git_stash,
            # RAG / Project index
            "index_project":     self._index_project,
            "query_index":       self._query_index,
            # Virtualenv manager
            "venv_create":       self._venv_create,
            "venv_install":      self._venv_install,
            "venv_status":       self._venv_status,
            "venv_run":          self._venv_run,
            # Cursor-parity
            "apply_code":        self._apply_code,
            "apply_diff":        self._apply_diff,
            "ghost_complete":    self._ghost_complete,
            "at_resolve":        self._at_resolve,
            "load_axisrules":    self._load_axisrules,
            "composer":          self._composer,
            "rename_symbol":     self._rename_symbol,
            # ── Agent orchestration ────────────────────────────────────────
            "agents_get_profiles":        self.handle_agents_get_profiles,
            "agents_set_config":          self.handle_agents_set_config,
            "agents_get_providers":       self.handle_agents_get_providers,
            "agents_set_provider":        self.handle_agents_set_provider,
            "agents_run":                 self.handle_agents_run,
            "agents_stop":                self.handle_agents_stop,
            "agents_permission_response": self.handle_agents_permission_response,
            "agents_clear_history":       self.handle_agents_clear_history,
            "agents_revert":              self.handle_agents_revert,
        }
        fn = handlers.get(cmd)
        if fn:
            try:
                fn(payload)
            except Exception as e:
                self._push("ai_error", {"id": "system", "error": str(e)})
        else:
            print(f"[IDE] Unknown command: {cmd}")

    # ── Window controls ────────────────────────────────────────────────────
    def _toggle_maximize(self, _):
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()

    # ── File system ops ────────────────────────────────────────────────────
    def _open_folder(self, _):
        path = QFileDialog.getExistingDirectory(
            self.window, "Відкрити проект",
            self.ide_cfg.get("projects_dir", str(Path.home()))
        )
        if not path:
            return
        self.project_root = path
        recents = self.ide_cfg.get("recent_projects", [])
        if path not in recents:
            recents.insert(0, path)
            self.ide_cfg["recent_projects"] = recents[:10]
            self._save_ide_cfg()
        tree = self._build_tree(path)
        self._push("project_opened", {
            "path": path,
            "name": os.path.basename(path),
            "tree": tree,
        })

    def _open_folder_path(self, payload: dict):
        """Open a folder directly by path (used from CLI --project arg)."""
        path = payload.get("path", "")
        if not path or not os.path.isdir(path):
            return
        self.project_root = path
        recents = self.ide_cfg.get("recent_projects", [])
        if path not in recents:
            recents.insert(0, path)
            self.ide_cfg["recent_projects"] = recents[:10]
            self._save_ide_cfg()
        tree = self._build_tree(path)
        self._push("project_opened", {
            "path": path,
            "name": os.path.basename(path),
            "tree": tree,
        })
        # Auto-load .axisrules
        self._load_axisrules({"root": path})

    def _open_file(self, payload):
        path = payload.get("path", "")
        if not path or not os.path.isfile(path):
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            self._push("ai_error", {"id": "file", "error": str(e)})
            return
        ext  = Path(path).suffix.lower()
        lang = EXT_LANG.get(ext, "plaintext")
        self._push("file_content", {
            "path": path,
            "name": os.path.basename(path),
            "content": content,
            "lang": lang,
        })

    def _open_or_create_axisrules(self, payload):
        """Open .axisrules in editor, creating it with a template if it doesn't exist."""
        path    = payload.get("path", "")
        project = payload.get("project", "")
        if not path:
            return

        template = (
            "# .axisrules — Project Rules for AXIS AI\n"
            "# This file is read by the AI agent at the start of every conversation.\n"
            "# Write rules, conventions and context for THIS project.\n\n"
            f"## Project\n"
            f"Name: {os.path.basename(project) if project else 'My Project'}\n"
            f"Stack: (e.g. HTML + CSS + Vanilla JS)\n\n"
            "## Code Style\n"
            "- (e.g. Use 2-space indentation)\n"
            "- (e.g. Ukrainian UI text)\n"
            "- (e.g. Dark theme: #0f172a background)\n\n"
            "## Architecture\n"
            "- (e.g. Single-page app, no frameworks)\n"
            "- (e.g. All data in script.js CARS array)\n\n"
            "## What NOT to do\n"
            "- (e.g. Don't use jQuery)\n"
            "- (e.g. Don't change the color scheme)\n\n"
            "## Extra context\n"
            "- (anything else the AI should know)\n"
        )

        is_new = not os.path.isfile(path)
        if is_new:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(template)
            except Exception as e:
                self._push("toast", {"message": f"Не вдалось створити .axisrules: {e}", "kind": "error"})
                return

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return

        event = "axisrules_created" if is_new else "file_content"
        self._push(event, {
            "path":    path,
            "name":    ".axisrules",
            "content": content,
            "lang":    "markdown",
        })

    def _read_file_for_mention(self, payload):
        """Read a file requested via @ mention in the chat, push content back to JS."""
        path = payload.get("path", "")
        if not path or not os.path.isfile(path):
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read(8000)   # cap at 8k chars for mention context
        except Exception:
            return
        self._push("at_mention_content", {
            "path": path,
            "name": os.path.basename(path),
            "content": content,
        })

    def _save_file(self, payload):
        path    = payload.get("path", "")
        content = payload.get("content", "")
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self._push("file_saved", {"path": path})
            self._toast(f"Збережено: {os.path.basename(path)}", "success")
        except Exception as e:
            self._toast(str(e), "error")

    def _create_file(self, payload):
        path = payload.get("path", "")
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            Path(path).touch(exist_ok=True)
            self._push("file_created", {"path": path})
            self._refresh_tree()
        except Exception as e:
            self._toast(str(e), "error")

    def _create_folder(self, payload):
        path = payload.get("path", "")
        if not path:
            return
        try:
            os.makedirs(path, exist_ok=True)
            self._refresh_tree()
        except Exception as e:
            self._toast(str(e), "error")

    def _delete_file(self, payload):
        path = payload.get("path", "")
        if not path or not os.path.exists(path):
            return
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            self._push("file_deleted", {"path": path})
            self._refresh_tree()
            self._toast(f"Видалено: {os.path.basename(path)}", "info")
        except Exception as e:
            self._toast(str(e), "error")

    def _rename_file(self, payload):
        old = payload.get("old_path", "")
        new = payload.get("new_path", "")
        if not old or not new:
            return
        try:
            os.rename(old, new)
            self._push("file_renamed", {"old_path": old, "new_path": new})
            self._refresh_tree()
        except Exception as e:
            self._toast(str(e), "error")

    def _build_tree(self, root: str) -> dict:
        root_path = Path(root)
        def _node(p: Path) -> dict:
            if p.is_dir():
                children = []
                try:
                    for child in sorted(p.iterdir(),
                                        key=lambda x: (x.is_file(), x.name.lower())):
                        if child.name in IGNORE_DIRS or child.name.endswith(".egg-info"):
                            continue
                        children.append(_node(child))
                except PermissionError:
                    pass
                return {"type": "dir", "name": p.name, "path": str(p), "children": children}
            else:
                ext  = p.suffix.lower()
                lang = EXT_LANG.get(ext, "file")
                return {"type": "file", "name": p.name, "path": str(p), "lang": lang}
        return _node(root_path)

    def _get_project_tree(self, _):
        if self.project_root:
            tree = self._build_tree(self.project_root)
            self._push("tree_updated", {"tree": tree})

    def _refresh_tree(self):
        if self.project_root:
            tree = self._build_tree(self.project_root)
            self._push("tree_updated", {"tree": tree})

    # ── Run / terminal ─────────────────────────────────────────────────────
    def _run_code(self, payload):
        path = payload.get("path", "")
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext == ".py":
            cmd = [sys.executable, path]
        elif ext == ".js":
            cmd = ["node", path]
        else:
            self._push("terminal_output", {"text": f"Не підтримується: {ext}", "kind": "error"})
            return
        self._exec_cmd(cmd, cwd=os.path.dirname(path) or ".")

    def _run_terminal(self, payload):
        cmd_str = payload.get("cmd", "")
        use_ai  = payload.get("ai", False)
        cwd     = payload.get("cwd", self.project_root or str(Path.home()))

        if use_ai:
            def _translate_and_run():
                try:
                    prov  = self._effective_provider()
                    model = self._effective_model()
                    import queue as _q
                    tok_q: _q.Queue = _q.Queue()

                    def _tok(rid, tok):
                        if rid == "__term_translate":
                            tok_q.put(tok)
                    def _done(rid):
                        if rid == "__term_translate":
                            tok_q.put(None)
                    def _err(rid, e):
                        if rid == "__term_translate":
                            tok_q.put(("error", e))

                    self.ai.response_token.connect(_tok)
                    self.ai.response_done.connect(_done)
                    self.ai.response_error.connect(_err)

                    msgs = [{"role": "user",
                             "content": f"Convert to a single shell command (Windows PowerShell / cmd). Output ONLY the command, no explanation:\n{cmd_str}"}]
                    self.ai.send_stream("__term_translate", prov, model, msgs,
                                        "You are a shell command translator. Output ONLY the raw command.")
                    translated = ""
                    while True:
                        item = tok_q.get(timeout=30)
                        if item is None:
                            break
                        if isinstance(item, tuple) and item[0] == "error":
                            translated = cmd_str
                            break
                        translated += item

                    self.ai.response_token.disconnect(_tok)
                    self.ai.response_done.disconnect(_done)
                    self.ai.response_error.disconnect(_err)

                    translated = translated.strip().strip("`").strip()
                    self._push("terminal_ai_cmd", {"original": cmd_str, "cmd": translated})
                    self._exec_shell(translated, cwd)
                except Exception as e:
                    self._push("terminal_output", {"text": str(e), "kind": "error"})

            threading.Thread(target=_translate_and_run, daemon=True).start()
        else:
            self._exec_shell(cmd_str, cwd)

    def _exec_cmd(self, cmd: list, cwd: str):
        def _run():
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    cwd=cwd, text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                for line in proc.stdout:
                    self._push("terminal_output", {"text": line.rstrip(), "kind": "out"})
                proc.wait()
                kind = "success" if proc.returncode == 0 else "error"
                self._push("terminal_output", {"text": f"\n[exit {proc.returncode}]", "kind": kind})
            except Exception as e:
                self._push("terminal_output", {"text": str(e), "kind": "error"})
        threading.Thread(target=_run, daemon=True).start()

    def _exec_shell(self, cmd_str: str, cwd: str):
        if sys.platform == "win32":
            cmd = ["cmd", "/c", cmd_str]
        else:
            cmd = ["bash", "-c", cmd_str]
        self._exec_cmd(cmd, cwd)

    # ── AI operations ──────────────────────────────────────────────────────
    def _effective_provider(self) -> str:
        if self.ide_cfg.get("privacy_mode"):
            return "ollama"
        return self.ide_cfg.get("provider", "openai")

    def _effective_model(self) -> str:
        if self.ide_cfg.get("privacy_mode"):
            return self.ide_cfg.get("ollama_model", "llama3")
        return self.ide_cfg.get("model", "gpt-4.1")

    def _ai_send_stream(self, payload):
        req_id   = payload.get("id", "chat_1")
        messages = payload.get("messages", [])
        prov     = self._effective_provider()
        model    = self._effective_model()

        # ── Build rich project-aware system prompt ──
        project_path    = payload.get("project_path",    self.project_root or "")
        project_name    = payload.get("project_name",    os.path.basename(project_path) if project_path else "")
        active_path     = payload.get("active_file_path",    "")
        active_name     = payload.get("active_file_name",    "")
        active_lang     = payload.get("active_file_lang",    "")
        active_content  = payload.get("active_file_content", "")
        open_tabs       = payload.get("open_tabs",        [])

        system = self._build_chat_system(
            project_path, project_name,
            active_path, active_name, active_lang, active_content,
            open_tabs,
        )

        # ── .axisrules: inject project rules (highest priority) ──
        if self._axisrules:
            system = self._axisrules + "\n\n" + system

        # ── RAG: enrich with relevant lines from index ──
        if messages and self._project_index:
            last_user = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
            )
            ctx = self._build_ai_context(last_user)
            if ctx:
                system = system + "\n\n" + ctx

        self.ai.send_stream(req_id, prov, model, messages, system)

    def _build_chat_system(
        self,
        project_path: str, project_name: str,
        active_path: str,  active_name: str, active_lang: str, active_content: str,
        open_tabs: list,
    ) -> str:
        """Build a rich, project-aware system prompt for the chat AI."""
        lines = [
            "Ти AI асистент вбудований у AXIS IDE.",
            "Відповідай тією мовою, якою пише користувач (українська або інша).",
            "Форматуй код у markdown-блоки з вказівкою мови.",
            "",
            "Ти маєш повний доступ до контексту проекту і можеш:",
            "— аналізувати код і архітектуру проекту",
            "— додавати нові функції, класи, методи",
            "— виправляти баги",
            "— пояснювати будь-який фрагмент коду",
            "— рефакторити і покращувати код",
            "— писати тести",
            "— відповідати на будь-які питання про проект",
        ]

        # Project info
        if project_name:
            lines += ["", f"## Проект: {project_name}"]
            if project_path:
                lines.append(f"Шлях: {project_path}")

        # File tree (fast, text-only)
        if project_path and os.path.isdir(project_path):
            tree_txt = self._build_tree_text(project_path)
            if tree_txt:
                lines += ["", "## Структура файлів:", "```", tree_txt, "```"]

        # Open tabs
        if open_tabs:
            tab_list = ", ".join(t.get("name", "") for t in open_tabs[:10] if t.get("name"))
            if tab_list:
                lines += ["", f"## Відкриті вкладки: {tab_list}"]

        # Active file — full content (most important context)
        if active_name and active_content:
            rel = os.path.relpath(active_path, project_path).replace("\\", "/") if project_path and active_path else active_name
            lines += [
                "",
                f"## Активний файл: {rel}",
                f"```{active_lang or ''}",
                active_content,
                "```",
            ]

        # Project snapshot (other files, lightweight)
        if project_path and os.path.isdir(project_path):
            snap = self._build_project_snapshot(project_path, max_chars=5000)
            # Remove active file from snapshot to avoid duplication
            if snap and active_name:
                snap_lines = []
                skip = False
                for ln in snap.splitlines():
                    if ln.startswith("# ") and active_name in ln:
                        skip = True
                    elif ln.startswith("# ") and skip:
                        skip = False
                    if not skip:
                        snap_lines.append(ln)
                snap = "\n".join(snap_lines)
            if snap:
                lines += ["", snap]

        return "\n".join(lines)

    def _build_tree_text(self, root: str, prefix: str = "", max_depth: int = 4) -> str:
        """Build a compact indented text tree of project files."""
        if not root or not os.path.isdir(root):
            return ""
        result = []
        try:
            entries = sorted(os.listdir(root))
        except PermissionError:
            return ""
        dirs  = [e for e in entries if os.path.isdir(os.path.join(root, e))
                 and e not in IGNORE_DIRS and not e.startswith(".")]
        files = [e for e in entries if os.path.isfile(os.path.join(root, e))]
        for f in files[:30]:
            result.append(prefix + f)
        if max_depth > 0:
            for d in dirs[:15]:
                result.append(prefix + d + "/")
                sub = self._build_tree_text(
                    os.path.join(root, d),
                    prefix + "  ",
                    max_depth - 1,
                )
                if sub:
                    result.append(sub)
        return "\n".join(result)

    def _inline_edit(self, payload):
        req_id   = payload.get("id", "inline_1")
        selected = payload.get("selected_code", "")
        instr    = payload.get("instruction", "")
        lang     = payload.get("lang", "python")
        system   = (
            f"You are a code editor. The user will give you code in {lang} and an instruction. "
            "Return ONLY the modified code — no explanation, no markdown fences."
        )
        messages = [{"role": "user",
                     "content": f"Code:\n```{lang}\n{selected}\n```\n\nInstruction: {instr}"}]
        prov  = self._effective_provider()
        model = self._effective_model()
        self.ai.send_stream(req_id, prov, model, messages, system)

    def _check_errors(self, payload):
        """Single-file check (legacy — used by inline error markers)."""
        path = payload.get("path", "")
        if not path:
            return
        def _run():
            issues = self._scan_file(path)
            self._push("check_errors_result", {"path": path, "issues": issues})
        threading.Thread(target=_run, daemon=True).start()

    def _check_project(self, payload):
        """Project-wide scan — pushes problems_update with all issues."""
        root = payload.get("root", self.project_root)
        if not root:
            self._push("problems_update", {"issues": [], "root": "", "scanning": False})
            return
        self._push("problems_update", {"issues": [], "root": root, "scanning": True})
        threading.Thread(target=self._scan_project_worker, args=(root,), daemon=True).start()

    def _scan_project_worker(self, root: str):
        PY_EXTS  = {".py"}
        JS_EXTS  = {".js", ".ts", ".jsx", ".tsx"}
        ALL_EXTS = PY_EXTS | JS_EXTS
        all_issues: list[dict] = []

        try:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if d not in IGNORE_DIRS and not d.startswith(".")
                ]
                for fname in filenames:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in ALL_EXTS:
                        continue
                    fpath = os.path.join(dirpath, fname)
                    if ext in PY_EXTS:
                        all_issues.extend(self._scan_file(fpath))
                    if len(all_issues) >= 1000:
                        break
                if len(all_issues) >= 1000:
                    break
        except Exception as e:
            print(f"[IDE] scan error: {e}")

        self._push("problems_update", {
            "issues":   all_issues,
            "root":     root,
            "scanning": False,
            "capped":   len(all_issues) >= 1000,
        })

    def _scan_file(self, path: str) -> list[dict]:
        """Scan a single file. Returns list of issue dicts."""
        issues: list[dict] = []
        ext = os.path.splitext(path)[1].lower()

        if ext == ".py":
            # 1. Fast AST syntax check (always available)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    src = fh.read()
                import ast as _ast
                _ast.parse(src, filename=path)
            except SyntaxError as e:
                issues.append({
                    "file": path, "line": e.lineno or 1, "col": e.offset or 0,
                    "type": "error", "message": str(e.msg), "symbol": "syntax-error",
                })
                return issues   # no point running linters on unparseable code

            # 2. pyflakes (fast, no install usually needed)
            try:
                import pyflakes.api as _pf
                import pyflakes.reporter as _pfr
                import io
                buf = io.StringIO()

                class _Rep(_pfr.Reporter):
                    def __init__(self):
                        self._issues: list[dict] = []
                    def unexpectedError(self, fn, msg):
                        pass
                    def syntaxError(self, fn, msg, lineno, offset, text):
                        self._issues.append({
                            "file": fn, "line": lineno or 1, "col": offset or 0,
                            "type": "error", "message": msg, "symbol": "syntax-error",
                        })
                    def flake(self, msg):
                        self._issues.append({
                            "file": msg.filename, "line": msg.lineno, "col": msg.col + 1,
                            "type": "warning", "message": str(msg.message % msg.message_args),
                            "symbol": msg.__class__.__name__,
                        })

                rep = _Rep()
                _pf.check(src, path, reporter=rep)
                issues.extend(rep._issues)
                if issues:
                    return issues
            except ImportError:
                pass

            # 3. pylint (thorough, but slow — only if pyflakes found nothing)
            try:
                result = subprocess.run(
                    ["pylint", "--output-format=json",
                     "--disable=C,R",  # skip conventions/refactors for speed
                     path],
                    capture_output=True, text=True, encoding="utf-8",
                    timeout=20,
                    creationflags=_NO_WINDOW,
                )
                if result.stdout.strip().startswith("["):
                    for i in json.loads(result.stdout):
                        t = i.get("type", "convention")
                        if t in ("error", "warning", "fatal"):
                            issues.append({
                                "file":    i.get("path", path),
                                "line":    i.get("line", 1),
                                "col":     i.get("column", 0),
                                "type":    "error" if t in ("error", "fatal") else "warning",
                                "message": i.get("message", ""),
                                "symbol":  i.get("symbol", ""),
                            })
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            except Exception:
                pass

        return issues

    def _format_code(self, payload):
        path    = payload.get("path", "")
        content = payload.get("content", "")
        if not path and not content:
            return
        def _run():
            try:
                tmp = None
                if content and not path:
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".py", delete=False,
                                                     mode="w", encoding="utf-8") as tf:
                        tf.write(content)
                        tmp = tf.name
                    target = tmp
                else:
                    target = path

                result = subprocess.run(
                    ["black", "--quiet", target],
                    capture_output=True, text=True, encoding="utf-8",
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                if result.returncode == 0:
                    with open(target, encoding="utf-8") as f:
                        formatted = f.read()
                    self._push("formatted_code", {"path": path, "content": formatted})
                    self._toast("Відформатовано", "success")
                else:
                    self._toast(f"black: {result.stderr[:120]}", "error")
                if tmp:
                    os.unlink(tmp)
            except FileNotFoundError:
                self._toast("black не знайдено. Встановіть: pip install black", "error")
            except Exception as e:
                self._toast(str(e), "error")
        threading.Thread(target=_run, daemon=True).start()

    # ── Config ─────────────────────────────────────────────────────────────
    def _get_config(self, _):
        if self.ide_cfg.get("privacy_mode"):
            cfg = dict(self.ide_cfg)
            cfg["provider"] = "ollama"
        else:
            cfg = self.ide_cfg
        self._push("config_data", cfg)

    def _save_config(self, payload):
        self.ide_cfg.update(payload)
        if self.ide_cfg.get("privacy_mode"):
            self.ide_cfg["provider"] = "ollama"
        self._save_ide_cfg()
        # Sync the unified config into agents handler so it can use it
        self._ide_config = self.ide_cfg          # <-- picked up by agents handler
        self._push("config_data", self.ide_cfg)
        self._toast("Конфіг збережено", "success")

    def _save_ide_cfg(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(IDE_CFG, "w", encoding="utf-8") as f:
            json.dump(self.ide_cfg, f, indent=2, ensure_ascii=False)

    # ── STT ────────────────────────────────────────────────────────────────
    def _start_stt(self, _):
        def _listen():
            try:
                import speech_recognition as sr
                self._push("stt_status", {"active": True})
                recognizer = sr.Recognizer()
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    audio = recognizer.listen(source, timeout=8, phrase_time_limit=12)
                text = recognizer.recognize_google(audio, language="uk-UA")
                self._push("stt_result", {"text": text})
            except Exception as e:
                self._push("stt_result", {"text": "", "error": str(e)})
            finally:
                self._push("stt_status", {"active": False})
        threading.Thread(target=_listen, daemon=True).start()

    # ── Explorer ───────────────────────────────────────────────────────────
    def _open_in_explorer(self, payload):
        path = payload.get("path", self.project_root)
        if not path:
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    # ── Auto-save ─────────────────────────────────────────────────────────
    def _auto_save(self, payload: dict):
        """Called from JS debounce when auto-save triggers."""
        path    = payload.get("path", "")
        content = payload.get("content", "")
        if not path or not content:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self._push("auto_saved", {"path": path, "name": os.path.basename(path)})
        except Exception as e:
            print(f"[IDE] auto_save error: {e}")

    # ── Run file in browser / node ─────────────────────────────────────────
    def _run_file(self, payload: dict):
        path = payload.get("path", "")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in (".html", ".htm"):
                import webbrowser
                webbrowser.open("file:///" + path.replace("\\", "/"))
                self._toast("🌐 Відкрито у браузері", "success")
            elif ext == ".js":
                # Try Node.js
                def _run_node():
                    try:
                        r = subprocess.run(
                            ["node", path],
                            capture_output=True, text=True, timeout=15,
                            cwd=os.path.dirname(path),
                            creationflags=_NO_WINDOW,
                        )
                        out = r.stdout + (r.stderr or "")
                        self._push("terminal_output", {"output": out or "(no output)"})
                        self._push("switch_panel", {"panel": "output"})
                    except FileNotFoundError:
                        self._toast("⚠ Node.js не знайдено. Встановіть nodejs.org", "error")
                    except Exception as exc:
                        self._push("terminal_output", {"output": str(exc)})
                threading.Thread(target=_run_node, daemon=True).start()
            else:
                # Fall back to generic run
                self._run_code(payload)
        except Exception as e:
            self._toast(f"⚠ Помилка запуску: {e}", "error")

    # ── Project-wide search ───────────────────────────────────────────────
    def _project_search(self, payload: dict):
        query   = payload.get("query", "").strip()
        case    = payload.get("case_sensitive", False)
        regex   = payload.get("regex", False)
        root    = payload.get("root", self.project_root)
        if not query or not root:
            self._push("search_results", {"results": [], "query": query})
            return
        threading.Thread(
            target=self._search_worker,
            args=(query, root, case, regex),
            daemon=True
        ).start()

    def _search_worker(self, query: str, root: str, case: bool, use_regex: bool):
        import re as _re
        results = []
        TEXT_EXTS = {
            ".py", ".js", ".ts", ".html", ".htm", ".css", ".json", ".md",
            ".yaml", ".yml", ".sh", ".txt", ".toml", ".ini", ".env", ".log",
            ".cpp", ".c", ".h", ".cs", ".java", ".go", ".rs", ".rb", ".php",
        }
        flags = 0 if case else _re.IGNORECASE
        try:
            pattern = _re.compile(query if use_regex else _re.escape(query), flags)
        except _re.error:
            pattern = _re.compile(_re.escape(query), flags)

        try:
            for dirpath, dirnames, filenames in os.walk(root):
                # Skip ignored dirs
                dirnames[:] = [
                    d for d in dirnames
                    if d not in IGNORE_DIRS and not d.startswith(".")
                ]
                for fname in filenames:
                    if os.path.splitext(fname)[1].lower() not in TEXT_EXTS:
                        continue
                    fpath = os.path.join(dirpath, fname)
                    try:
                        with open(fpath, encoding="utf-8", errors="ignore") as fh:
                            for lineno, line in enumerate(fh, 1):
                                if pattern.search(line):
                                    results.append({
                                        "path":   fpath,
                                        "name":   fname,
                                        "line":   lineno,
                                        "text":   line.rstrip()[:200],
                                    })
                                    if len(results) >= 500:
                                        break
                    except Exception:
                        pass
                    if len(results) >= 500:
                        break
        except Exception as e:
            print(f"[IDE] search error: {e}")
        self._push("search_results", {
            "results": results,
            "query":   query,
            "capped":  len(results) >= 500,
        })

    # ── Project-wide replace ──────────────────────────────────────────────
    def _project_replace(self, payload: dict):
        query       = payload.get("query", "").strip()
        replace_txt = payload.get("replace", "")
        case        = payload.get("case_sensitive", False)
        use_regex   = payload.get("regex", False)
        root        = payload.get("root", self.project_root)
        files       = payload.get("files")   # None = all, list = specific paths
        if not query or not root:
            return
        threading.Thread(
            target=self._replace_worker,
            args=(query, replace_txt, root, case, use_regex, files),
            daemon=True,
        ).start()

    def _replace_worker(
        self,
        query: str,
        replace_txt: str,
        root: str,
        case: bool,
        use_regex: bool,
        files,
    ):
        import re as _re
        TEXT_EXTS = {
            ".py", ".js", ".ts", ".html", ".htm", ".css", ".json", ".md",
            ".yaml", ".yml", ".sh", ".txt", ".toml", ".ini", ".env",
            ".cpp", ".c", ".h", ".cs", ".java", ".go", ".rs", ".rb", ".php",
        }
        flags = 0 if case else _re.IGNORECASE
        try:
            pattern = _re.compile(query if use_regex else _re.escape(query), flags)
        except _re.error:
            pattern = _re.compile(_re.escape(query), flags)

        total_files = 0
        total_repl  = 0
        changed_paths: list[str] = []

        paths_iter = files if files else []
        if not files:
            try:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [
                        d for d in dirnames
                        if d not in IGNORE_DIRS and not d.startswith(".")
                    ]
                    for fname in filenames:
                        if os.path.splitext(fname)[1].lower() in TEXT_EXTS:
                            paths_iter.append(os.path.join(dirpath, fname))
            except Exception:
                pass

        for fpath in paths_iter:
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as fh:
                    original = fh.read()
                new_content, n = pattern.subn(replace_txt, original)
                if n:
                    with open(fpath, "w", encoding="utf-8") as fh:
                        fh.write(new_content)
                    total_files += 1
                    total_repl  += n
                    changed_paths.append(fpath)
            except Exception:
                pass

        self._push("replace_done", {
            "files":   total_files,
            "count":   total_repl,
            "changed": changed_paths[:50],
        })

    # ── AI AGENT ──────────────────────────────────────────────────────────
    _AGENT_SYSTEM = (
        "Ти AXIS IDE Agent — AI асистент що автономно створює повноцінні проекти.\n"
        "На КОЖЕН запит відповідай ВИКЛЮЧНО валідним JSON (без markdown, без пояснень поза JSON):\n"
        "{\n"
        "  \"thoughts\": \"Коротко що плануєш\",\n"
        "  \"actions\": [\n"
        "    {\"type\": \"create_folder\", \"path\": \"назва_папки\"},\n"
        "    {\"type\": \"create_file\",   \"path\": \"папка/файл.ext\", \"content\": \"повний вміст\"},\n"
        "    {\"type\": \"fix_file\",      \"path\": \"папка/файл.ext\", \"content\": \"виправлений вміст\"},\n"
        "    {\"type\": \"pip_install\",   \"packages\": [\"назва_пакету\"]},\n"
        "    {\"type\": \"run_file\",      \"path\": \"папка/файл\"},\n"
        "    {\"type\": \"message\",       \"text\": \"Повідомлення\"}\n"
        "  ],\n"
        "  \"done\": true,\n"
        "  \"suggestions\": [\n"
        "    \"Ідея покращення 1\",\n"
        "    \"Ідея покращення 2\",\n"
        "    \"Ідея покращення 3\",\n"
        "    \"Ідея покращення 4\",\n"
        "    \"Ідея покращення 5\"\n"
        "  ]\n"
        "}\n\n"
        "Правила:\n"
        "- Завжди ПЕРШОЮ дією create_folder для кореня проекту\n"
        "- Пиши ПОВНИЙ робочий код (без TODO, без заглушок)\n"
        "- Якщо в проекті вже є файли (надані в контексті) — використовуй їх, не дублюй\n"
        "- Для ігор: HTML5 Canvas + JavaScript (один або два файли, відкривається в браузері)\n"
        "- Для Python-проектів: main.py + requirements.txt + README.md\n"
        "- Шляхи відносні: перший компонент = назва папки з першого create_folder\n"
        "- pip_install: вказуй пакети перед run_file якщо вони потрібні\n"
        "- suggestions: мінімум 5 конкретних ідей що можна покращити або додати\n"
        "- done: true тільки коли всі файли повністю написані\n"
    )

    _AUTO_FIX_SYSTEM = (
        "Ти Python debugger. Тобі дають код файлу та повідомлення про помилку.\n"
        "Відповідай ВИКЛЮЧНО валідним JSON (без markdown):\n"
        "{\n"
        "  \"thoughts\": \"Коротко що виправив\",\n"
        "  \"fix_file\": {\"path\": \"відносний/шлях\", \"content\": \"ПОВНИЙ виправлений код файлу\"}\n"
        "}\n"
        "ВАЖЛИВО: в fix_file.content пиши ПОВНИЙ вміст файлу, не фрагменти.\n"
    )

    def _ai_agent(self, payload: dict):
        task        = payload.get("task", "").strip()
        use_context = payload.get("project_context", True)
        if not task:
            return
        base_dir = self.project_root or self.ide_cfg.get("projects_dir", str(Path.home() / "Projects"))
        threading.Thread(target=self._agent_worker, args=(task, base_dir, use_context), daemon=True).start()

    def _agent_worker(self, task: str, base_dir: str, use_context: bool = True):
        import re as _re
        try:
            self._push("agent_start", {"task": task})
            provider = self._effective_provider()
            model    = self._effective_model()

            # ── Inject project snapshot (Feature: Project Context) ──
            system = self._AGENT_SYSTEM
            if use_context and self.project_root and os.path.isdir(self.project_root):
                snapshot = self._build_project_snapshot(self.project_root)
                if snapshot:
                    system = system + "\n\n" + snapshot

            messages = [{"role": "user", "content": task}]
            response = self._ai_call_sync(provider, model, messages, system)
            if not response:
                self._push("agent_error", {"error": "AI не відповів. Перевірте API ключ і модель."})
                return

            # Strip markdown fences
            clean = response.strip()
            if clean.startswith("```"):
                clean = _re.sub(r"^```\w*\n?", "", clean)
                clean = _re.sub(r"\n?```$", "", clean.strip())

            # Parse JSON
            try:
                data = json.loads(clean)
            except Exception:
                m = _re.search(r"\{[\s\S]*\}", clean)
                if m:
                    try:
                        data = json.loads(m.group())
                    except Exception:
                        self._push("agent_error", {"error": "Не вдалося розпарсити відповідь AI"})
                        self._push("agent_message", {"text": response[:1000]})
                        return
                else:
                    self._push("agent_error", {"error": "AI відповів не у JSON форматі"})
                    self._push("agent_message", {"text": response[:1000]})
                    return

            thoughts    = data.get("thoughts", "")
            actions     = data.get("actions", [])
            suggestions = data.get("suggestions", [])

            if thoughts:
                self._push("agent_thought", {"text": thoughts})

            project_folder = None
            os.makedirs(base_dir, exist_ok=True)

            for action in actions:
                atype = action.get("type", "")

                if atype == "create_folder":
                    rel = action.get("path", "new_project")
                    abs_path = os.path.normpath(os.path.join(base_dir, rel))
                    os.makedirs(abs_path, exist_ok=True)
                    if project_folder is None:
                        project_folder = abs_path
                        # Auto-open the new project
                        recents = self.ide_cfg.get("recent_projects", [])
                        if abs_path not in recents:
                            recents.insert(0, abs_path)
                            self.ide_cfg["recent_projects"] = recents[:10]
                            self._save_ide_cfg()
                        self.project_root = abs_path
                        tree = self._build_tree(abs_path)
                        self._push("project_opened", {
                            "path": abs_path,
                            "name": os.path.basename(abs_path),
                            "tree": tree,
                        })
                    self._push("agent_action", {
                        "type": "create_folder",
                        "path": rel,
                        "status": "done",
                    })

                elif atype == "create_file":
                    rel     = action.get("path", "file.txt")
                    content = action.get("content", "")
                    base    = project_folder or base_dir
                    abs_path = os.path.normpath(os.path.join(base, rel))
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    with open(abs_path, "w", encoding="utf-8") as fh:
                        fh.write(content)
                    # Refresh tree
                    if self.project_root:
                        tree = self._build_tree(self.project_root)
                        self._push("tree_updated", {"tree": tree})
                    # Auto-open key files in editor
                    main_exts = {".py", ".js", ".ts", ".html", ".htm", ".cpp", ".c", ".go", ".rs"}
                    if os.path.splitext(rel)[1].lower() in main_exts:
                        self._push("open_file_in_editor", {
                            "path":    abs_path,
                            "content": content,
                            "name":    os.path.basename(rel),
                        })
                    self._push("agent_action", {
                        "type":   "create_file",
                        "path":   rel,
                        "status": "done",
                        "lines":  len(content.splitlines()),
                    })

                elif atype == "fix_file":
                    # Direct file patch from agent
                    rel     = action.get("path", "")
                    content = action.get("content", "")
                    base    = project_folder or base_dir
                    abs_path = os.path.normpath(os.path.join(base, rel))
                    if content and abs_path:
                        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                        with open(abs_path, "w", encoding="utf-8") as fh:
                            fh.write(content)
                        self._push("open_file_in_editor", {
                            "path": abs_path, "content": content,
                            "name": os.path.basename(rel),
                        })
                        if self.project_root:
                            self._push("tree_updated", {"tree": self._build_tree(self.project_root)})
                    self._push("agent_action", {"type": "fix_file", "path": rel, "status": "done"})

                elif atype == "pip_install":
                    packages = action.get("packages", [])
                    if packages:
                        proj_root = project_folder or base_dir
                        self._push("agent_action", {"type": "pip_install", "packages": packages, "status": "running"})
                        py = self._venv_python(proj_root)
                        try:
                            r = subprocess.run(
                                [py, "-m", "pip", "install"] + packages,
                                capture_output=True, text=True, timeout=120,
                                cwd=proj_root, creationflags=_NO_WINDOW,
                            )
                            out = r.stdout + (r.stderr or "")
                            self._push("terminal_output", {"output": out})
                            self._push("agent_action", {
                                "type": "pip_install", "packages": packages,
                                "status": "ok" if r.returncode == 0 else "error",
                                "output": out[-300:],
                            })
                        except subprocess.TimeoutExpired:
                            self._push("agent_action", {"type": "pip_install", "packages": packages, "status": "timeout"})

                elif atype == "run_file":
                    rel  = action.get("path", "")
                    base = project_folder or base_dir
                    abs_path = os.path.normpath(os.path.join(base, rel))
                    ext = os.path.splitext(rel)[1].lower()
                    # ── Sandboxing: ask user to confirm execution ──
                    confirm_id = f"run_{id(action)}"
                    evt, result = threading.Event(), [True]
                    self._pending_confirms[confirm_id] = (evt, result)
                    self._push("agent_confirm", {
                        "id":      confirm_id,
                        "path":    rel,
                        "abs":     abs_path,
                        "message": f"Дозволити запуск: {rel}?",
                    })
                    evt.wait(timeout=25)
                    self._pending_confirms.pop(confirm_id, None)
                    if not result[0]:
                        self._push("agent_action", {"type": "run_file", "path": rel, "status": "skipped"})
                        continue
                    self._push("agent_action", {"type": "run_file", "path": rel, "status": "running"})
                    if ext in (".html", ".htm"):
                        import webbrowser
                        webbrowser.open("file:///" + abs_path.replace("\\", "/"))
                        self._push("agent_action", {"type": "run_file", "path": rel, "status": "opened_browser"})
                    elif ext == ".py":
                        # Use venv python if available (Feature: Virtualenv)
                        py = self._venv_python(project_folder or base_dir)
                        try:
                            r = subprocess.run(
                                [py, abs_path],
                                capture_output=True, text=True, timeout=20,
                                cwd=os.path.dirname(abs_path),
                                creationflags=_NO_WINDOW,
                            )
                            out = r.stdout + (r.stderr or "")
                            self._push("terminal_output", {"output": out})
                            if r.returncode == 0:
                                self._push("agent_action", {
                                    "type": "run_file", "path": rel,
                                    "status": "ok", "output": out[:300],
                                })
                            else:
                                self._push("agent_action", {
                                    "type": "run_file", "path": rel,
                                    "status": "error", "output": out[:300],
                                })
                                # ── Terminal-AI Loop: auto-fix ──
                                fixed, _ = self._auto_fix_loop(
                                    abs_path, out, project_folder or base_dir,
                                    provider, model
                                )
                                if fixed:
                                    self._push("agent_action", {
                                        "type": "run_file", "path": rel,
                                        "status": "fixed_and_ok",
                                    })
                        except subprocess.TimeoutExpired:
                            self._push("agent_action", {"type": "run_file", "path": rel, "status": "timeout"})
                    else:
                        self._push("agent_action", {"type": "run_file", "path": rel, "status": "done"})

                elif atype == "message":
                    self._push("agent_message", {"text": action.get("text", "")})

            self._push("agent_done", {
                "suggestions":   suggestions,
                "project_path":  project_folder or base_dir,
                "project_name":  os.path.basename(project_folder or base_dir),
            })

        except Exception as exc:
            import traceback
            self._push("agent_error", {"error": str(exc)})
            print(f"[IDE Agent] {traceback.format_exc()}")

    def _ai_call_sync(self, provider: str, model: str, messages: list, system: str) -> str:
        """Blocking AI call used by the agent worker thread."""
        import requests as _req
        keys = self.ide_cfg.get("api_keys", {})
        try:
            if provider == "openai":
                key  = keys.get("openai", "")
                msgs = [{"role": "system", "content": system}] + messages
                r = _req.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model or "gpt-4o", "messages": msgs, "temperature": 0.2, "max_tokens": 12000},
                    timeout=180,
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]

            elif provider == "anthropic":
                key = keys.get("anthropic", "")
                r = _req.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={"model": model or "claude-opus-4-5", "max_tokens": 12000, "system": system, "messages": messages},
                    timeout=180,
                )
                r.raise_for_status()
                return r.json()["content"][0]["text"]

            elif provider == "google":
                key        = keys.get("google", "")
                model_name = model or "gemini-2.0-flash"
                full_msg   = system + "\n\n" + messages[-1]["content"]
                r = _req.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": full_msg}]}], "generationConfig": {"maxOutputTokens": 12000, "temperature": 0.2}},
                    timeout=180,
                )
                r.raise_for_status()
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]

            elif provider == "ollama":
                base = self.ide_cfg.get("ollama_url", "http://localhost:11434")
                msgs = [{"role": "system", "content": system}] + messages
                r = _req.post(
                    f"{base}/api/chat",
                    json={"model": model or "llama3", "messages": msgs, "stream": False},
                    timeout=300,
                )
                r.raise_for_status()
                return r.json()["message"]["content"]

            elif provider in ("xai", "deepseek", "perplexity"):
                _urls = {
                    "xai":       "https://api.x.ai/v1/chat/completions",
                    "deepseek":  "https://api.deepseek.com/chat/completions",
                    "perplexity": "https://api.perplexity.ai/chat/completions",
                }
                _models = {"xai": "grok-3", "deepseek": "deepseek-chat", "perplexity": "sonar-pro"}
                key  = keys.get(provider, "")
                msgs = [{"role": "system", "content": system}] + messages
                r = _req.post(
                    _urls[provider],
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model or _models[provider], "messages": msgs, "temperature": 0.2, "max_tokens": 12000},
                    timeout=180,
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]

        except Exception as exc:
            print(f"[IDE Agent] _ai_call_sync({provider}): {exc}")
            return ""
        return ""

    # ══════════════════════════════════════════════════════════════════════
    # DEBUGGER  (DAP / debugpy)
    # ══════════════════════════════════════════════════════════════════════
    _DEBUG_PORT = 5679

    def _debug_start(self, payload: dict):
        path        = payload.get("path", "")
        breakpoints = payload.get("breakpoints", {})   # {abs_path: [line, ...]}
        if not path or not os.path.isfile(path):
            self._toast("Немає файлу для запуску дебага", "error")
            return
        # Kill previous session
        self._debug_stop({})
        # Confirm: show sandboxing prompt unless user already approved
        self._push("debug_state", {"state": "starting", "file": os.path.basename(path)})
        threading.Thread(
            target=self._debug_launch_worker,
            args=(path, breakpoints),
            daemon=True,
        ).start()

    def _debug_launch_worker(self, path: str, breakpoints: dict):
        import time
        try:
            port = self._DEBUG_PORT
            self._debug_proc = subprocess.Popen(
                [sys.executable, "-m", "debugpy",
                 "--listen", f"localhost:{port}",
                 "--wait-for-client", path],
                cwd=os.path.dirname(path),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=_NO_WINDOW,
            )
            # Wait for debugpy to start listening
            for _ in range(30):
                time.sleep(0.15)
                try:
                    s = socket.socket()
                    s.settimeout(0.5)
                    s.connect(("localhost", port))
                    s.close()
                    break
                except OSError:
                    pass
            else:
                self._push("debug_error", {"error": "debugpy не запустився. Встановіть: pip install debugpy"})
                self._push("debug_state", {"state": "stopped"})
                return

            # Create DAP client
            dap = DAPClient()
            dap.on_message = self._on_dap_msg
            dap.connect("localhost", port)
            self._dap = dap

            # DAP handshake
            dap.request("initialize", {
                "clientID": "axis-ide", "adapterID": "python",
                "pathFormat": "path", "linesStartAt1": True,
                "columnsStartAt1": True, "supportsVariableType": True,
            })
            time.sleep(0.1)
            # Set breakpoints
            for bp_path, lines in breakpoints.items():
                dap.request("setBreakpoints", {
                    "source": {"path": bp_path},
                    "breakpoints": [{"line": ln} for ln in lines],
                })
            time.sleep(0.05)
            dap.request("configurationDone")
            self._push("debug_state", {"state": "running"})

        except Exception as exc:
            self._push("debug_error", {"error": str(exc)})
            self._push("debug_state", {"state": "stopped"})

    def _on_dap_msg(self, msg: dict):
        mtype = msg.get("type", "")
        if mtype == "event":
            event = msg.get("event", "")
            body  = msg.get("body", {})
            if event == "stopped":
                self._debug_thread_id = body.get("threadId", 1)
                reason = body.get("reason", "breakpoint")
                self._push("debug_state", {"state": "paused", "reason": reason})
                # Request stack trace
                if self._dap:
                    self._dap.request("stackTrace", {
                        "threadId": self._debug_thread_id, "levels": 30
                    })
            elif event in ("terminated", "exited"):
                self._push("debug_state", {"state": "stopped"})
                self._debug_cleanup()
            elif event == "output":
                out = body.get("output", "")
                if out:
                    self._push("terminal_output", {"output": out, "kind": "out"})

        elif mtype == "response":
            cmd  = msg.get("command", "")
            body = msg.get("body", {})
            if cmd == "stackTrace":
                frames = body.get("stackFrames", [])
                if frames:
                    top = frames[0]
                    self._push("debug_frame", {
                        "file":   top.get("source", {}).get("path", ""),
                        "line":   top.get("line", 1),
                        "frames": [
                            {"name": f.get("name",""), "file": f.get("source",{}).get("path",""), "line": f.get("line",1)}
                            for f in frames[:15]
                        ],
                    })
                    if self._dap:
                        self._dap.request("scopes", {"frameId": top.get("id", 0)})

            elif cmd == "scopes":
                scopes = body.get("scopes", [])
                for sc in scopes:
                    if sc.get("name") in ("Locals", "Local"):
                        if self._dap:
                            self._dap.request("variables",
                                {"variablesReference": sc["variablesReference"]})

            elif cmd == "variables":
                raw = body.get("variables", [])
                self._push("debug_variables", {
                    "variables": [
                        {"name": v.get("name",""), "value": v.get("value",""), "type": v.get("type","")}
                        for v in raw[:60]
                        if not v.get("name","").startswith("__")
                    ]
                })

    def _debug_stop(self, _):
        if self._dap:
            try:
                self._dap.request("terminate")
            except Exception:
                pass
            self._dap.close()
            self._dap = None
        self._debug_cleanup()
        self._push("debug_state", {"state": "stopped"})

    def _debug_cleanup(self):
        if self._debug_proc:
            try:
                self._debug_proc.terminate()
            except Exception:
                pass
            self._debug_proc = None

    def _debug_continue(self, _):
        if self._dap:
            self._dap.request("continue", {"threadId": self._debug_thread_id})
            self._push("debug_state", {"state": "running"})

    def _debug_step_over(self, _):
        if self._dap:
            self._dap.request("next", {"threadId": self._debug_thread_id})

    def _debug_step_into(self, _):
        if self._dap:
            self._dap.request("stepIn", {"threadId": self._debug_thread_id})

    def _debug_step_out(self, _):
        if self._dap:
            self._dap.request("stepOut", {"threadId": self._debug_thread_id})

    def _debug_confirm_response(self, payload: dict):
        """JS → Python: user confirmed/declined an agent run-file dialog."""
        req_id    = payload.get("id", "")
        confirmed = bool(payload.get("confirmed", False))
        if req_id in self._pending_confirms:
            evt, result = self._pending_confirms[req_id]
            result[0] = confirmed
            evt.set()

    # ══════════════════════════════════════════════════════════════════════
    # LSP  (Jedi — Python completions + signatures)
    # ══════════════════════════════════════════════════════════════════════
    def _lsp_complete(self, payload: dict):
        req_id = payload.get("id", "")
        path   = payload.get("path", "") or None
        code   = payload.get("code", "")
        line   = int(payload.get("line", 1))
        col    = int(payload.get("col", 0))
        threading.Thread(
            target=self._lsp_complete_worker,
            args=(req_id, path, code, line, col),
            daemon=True,
        ).start()

    def _lsp_complete_worker(self, req_id, path, code, line, col):
        try:
            import jedi
            script = jedi.Script(code, path=path)
            completions = script.complete(line, col)
            items = []
            for c in completions[:80]:
                items.append({
                    "label":  c.name,
                    "kind":   c.type,
                    "detail": c.full_name or "",
                    "doc":    c.docstring(raw=True)[:300] if c.docstring() else "",
                })
            self._push("lsp_completions", {"id": req_id, "items": items})
        except ImportError:
            self._push("lsp_completions", {"id": req_id, "items": [],
                                            "hint": "pip install jedi"})
        except Exception as exc:
            self._push("lsp_completions", {"id": req_id, "items": []})
            print(f"[LSP] complete error: {exc}")

    def _lsp_signature(self, payload: dict):
        req_id = payload.get("id", "")
        path   = payload.get("path", "") or None
        code   = payload.get("code", "")
        line   = int(payload.get("line", 1))
        col    = int(payload.get("col", 0))
        def _worker():
            try:
                import jedi
                script = jedi.Script(code, path=path)
                sigs = script.get_signatures(line, col)
                if sigs:
                    s = sigs[0]
                    params = [p.description for p in s.params]
                    self._push("lsp_signature", {
                        "id":     req_id,
                        "label":  s.name + "(" + ", ".join(params) + ")",
                        "params": params,
                        "active": s.index if s.index is not None else 0,
                    })
                else:
                    self._push("lsp_signature", {"id": req_id, "label": "", "params": [], "active": 0})
            except Exception:
                self._push("lsp_signature", {"id": req_id, "label": "", "params": [], "active": 0})
        threading.Thread(target=_worker, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════
    # GIT
    # ══════════════════════════════════════════════════════════════════════
    def _git_run(self, *args, root: str, timeout: int = 10) -> tuple[str, str, int]:
        r = subprocess.run(
            list(args), capture_output=True, text=True,
            cwd=root, timeout=timeout,
            creationflags=_NO_WINDOW,
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode

    def _git_status(self, payload: dict):
        root = payload.get("root", self.project_root)
        if not root:
            return
        threading.Thread(target=self._git_status_worker, args=(root,), daemon=True).start()

    def _git_status_worker(self, root: str):
        try:
            st_out, _, rc = self._git_run("git", "status", "--porcelain", root=root)
            if rc != 0 and not st_out:
                self._push("git_status", {"error": "not_a_repo", "changes": [], "branch": "", "commits": []})
                return
            changes = []
            for line in st_out.splitlines():
                if len(line) > 2:
                    xy   = line[:2]
                    path = line[3:].strip().split(" -> ")[-1]
                    changes.append({
                        "status": xy.strip() or "?",
                        "path":   path,
                        "staged": xy[0] not in (" ", "?"),
                    })
            branch, _, _ = self._git_run("git", "branch", "--show-current", root=root)
            log, _, _ = self._git_run("git", "log", "--oneline", "-20", root=root)
            commits = [c for c in log.splitlines() if c]
            self._push("git_status", {
                "changes": changes,
                "branch":  branch or "HEAD",
                "commits": commits,
            })
        except FileNotFoundError:
            self._push("git_status", {"error": "git_not_found", "changes": [], "branch": "", "commits": []})
        except Exception as exc:
            self._push("git_status", {"error": str(exc), "changes": [], "branch": "", "commits": []})

    def _git_commit(self, payload: dict):
        msg  = payload.get("message", "").strip()
        root = payload.get("root", self.project_root)
        if not msg:
            self._toast("Введіть повідомлення коміту", "error")
            return
        def _do():
            try:
                self._git_run("git", "add", ".", root=root)
                out, err, rc = self._git_run("git", "commit", "-m", msg, root=root)
                result = (out or err).strip()
                ok = rc == 0
                self._push("git_commit_result", {"output": result, "ok": ok})
                self._git_status_worker(root)
            except Exception as exc:
                self._push("git_commit_result", {"output": str(exc), "ok": False})
        threading.Thread(target=_do, daemon=True).start()

    def _git_checkout(self, payload: dict):
        branch = payload.get("branch", "")
        root   = payload.get("root", self.project_root)
        create = bool(payload.get("create", False))
        if not branch or not root:
            return
        def _do():
            try:
                args = ["git", "checkout"] + (["-b", branch] if create else [branch])
                out, err, rc = self._git_run(*args, root=root)
                msg = (out or err or ("✓ checkout " + branch))[:120]
                self._push("toast", {"message": msg, "kind": "success" if rc == 0 else "error"})
                self._git_status_worker(root)
            except Exception as exc:
                self._push("toast", {"message": str(exc), "kind": "error"})
        threading.Thread(target=_do, daemon=True).start()

    def _git_branches(self, payload: dict):
        root = payload.get("root", self.project_root)
        if not root:
            return
        def _do():
            try:
                out, _, _ = self._git_run("git", "branch", "-a", root=root)
                branches, current = [], ""
                for line in out.splitlines():
                    line = line.strip()
                    is_current = line.startswith("* ")
                    name = line[2:].strip() if is_current else line
                    name = _re_module.sub(r"^remotes/origin/", "", name).strip()
                    if "->" in name or not name:
                        continue
                    if is_current:
                        current = name
                        branches.insert(0, name)
                    else:
                        if name not in branches:
                            branches.append(name)
                self._push("git_branches", {
                    "branches": branches[:30],
                    "current": current,
                })
            except Exception as exc:
                self._push("git_branches", {"branches": [], "current": "", "error": str(exc)})
        threading.Thread(target=_do, daemon=True).start()

    def _git_diff_lines(self, payload: dict):
        path = payload.get("path", "")
        root = payload.get("root", self.project_root)
        if not path or not root:
            return
        def _do():
            try:
                out, _, _ = self._git_run("git", "diff", "--unified=0", "--", path, root=root)
                added, modified = [], []
                for line in out.splitlines():
                    if line.startswith("@@"):
                        m = _re_module.search(r"\+(\d+)(?:,(\d+))?", line)
                        if m:
                            start = int(m.group(1))
                            count = int(m.group(2)) if m.group(2) is not None else 1
                            for ln in range(start, start + max(count, 1)):
                                added.append(ln)
                self._push("git_diff_lines", {"path": path, "added": added})
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()

    def _git_push(self, payload: dict):
        root   = payload.get("root", self.project_root)
        remote = payload.get("remote", "origin")
        branch = payload.get("branch", "")
        force  = bool(payload.get("force", False))
        def _do():
            try:
                args = ["git", "push", remote]
                if branch:
                    args += [branch]
                if force:
                    args.append("--force-with-lease")
                out, err, rc = self._git_run(*args, root=root, timeout=60)
                msg = (out or err or "push OK")[:200]
                self._push("git_op_result", {"op": "push", "ok": rc == 0, "output": msg})
                if rc == 0:
                    self._git_status_worker(root)
            except Exception as exc:
                self._push("git_op_result", {"op": "push", "ok": False, "output": str(exc)})
        threading.Thread(target=_do, daemon=True).start()

    def _git_pull(self, payload: dict):
        root   = payload.get("root", self.project_root)
        remote = payload.get("remote", "origin")
        branch = payload.get("branch", "")
        rebase = bool(payload.get("rebase", False))
        def _do():
            try:
                args = ["git", "pull"]
                if rebase:
                    args.append("--rebase")
                args.append(remote)
                if branch:
                    args.append(branch)
                out, err, rc = self._git_run(*args, root=root, timeout=60)
                msg = (out or err or "pull OK")[:200]
                self._push("git_op_result", {"op": "pull", "ok": rc == 0, "output": msg})
                if rc == 0:
                    self._git_status_worker(root)
            except Exception as exc:
                self._push("git_op_result", {"op": "pull", "ok": False, "output": str(exc)})
        threading.Thread(target=_do, daemon=True).start()

    def _git_fetch(self, payload: dict):
        root   = payload.get("root", self.project_root)
        remote = payload.get("remote", "origin")
        def _do():
            try:
                out, err, rc = self._git_run("git", "fetch", remote, "--prune",
                                              root=root, timeout=60)
                msg = (out or err or "fetch OK")[:200]
                self._push("git_op_result", {"op": "fetch", "ok": rc == 0, "output": msg})
                if rc == 0:
                    self._git_status_worker(root)
            except Exception as exc:
                self._push("git_op_result", {"op": "fetch", "ok": False, "output": str(exc)})
        threading.Thread(target=_do, daemon=True).start()

    def _git_log(self, payload: dict):
        root  = payload.get("root", self.project_root)
        limit = int(payload.get("limit", 50))
        def _do():
            try:
                fmt = "%H|%h|%an|%ae|%ar|%s"
                out, _, rc = self._git_run(
                    "git", "log", f"--pretty=format:{fmt}", f"-{limit}",
                    root=root, timeout=15,
                )
                commits = []
                for line in out.splitlines():
                    parts = line.split("|", 5)
                    if len(parts) == 6:
                        commits.append({
                            "hash":    parts[0],
                            "short":   parts[1],
                            "author":  parts[2],
                            "email":   parts[3],
                            "date":    parts[4],
                            "message": parts[5],
                        })
                self._push("git_log", {"commits": commits})
            except Exception as exc:
                self._push("git_log", {"commits": [], "error": str(exc)})
        threading.Thread(target=_do, daemon=True).start()

    def _git_remotes(self, payload: dict):
        root = payload.get("root", self.project_root)
        def _do():
            try:
                out, _, _ = self._git_run("git", "remote", "-v", root=root)
                remotes: dict[str, str] = {}
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and "(fetch)" in line:
                        remotes[parts[0]] = parts[1]
                self._push("git_remotes", {"remotes": remotes})
            except Exception as exc:
                self._push("git_remotes", {"remotes": {}, "error": str(exc)})
        threading.Thread(target=_do, daemon=True).start()

    def _git_stash(self, payload: dict):
        root = payload.get("root", self.project_root)
        action = payload.get("action", "push")   # push | pop | list
        def _do():
            try:
                if action == "push":
                    out, err, rc = self._git_run("git", "stash", "push", "-m",
                                                  payload.get("message", "stash"), root=root)
                elif action == "pop":
                    out, err, rc = self._git_run("git", "stash", "pop", root=root)
                else:
                    out, err, rc = self._git_run("git", "stash", "list", root=root)
                msg = (out or err or action + " OK")[:200]
                self._push("git_op_result", {"op": "stash_" + action, "ok": rc == 0, "output": msg})
                if rc == 0 and action in ("push", "pop"):
                    self._git_status_worker(root)
            except Exception as exc:
                self._push("git_op_result", {"op": "stash", "ok": False, "output": str(exc)})
        threading.Thread(target=_do, daemon=True).start()

    def _git_init(self, payload: dict):
        root = payload.get("root", self.project_root)
        if not root:
            return
        def _do():
            try:
                out, err, rc = self._git_run("git", "init", root=root)
                msg = (out or err or "git init")[:100]
                self._push("toast", {"message": ("✓ " + msg) if rc == 0 else msg,
                                     "kind": "success" if rc == 0 else "error"})
                self._git_status_worker(root)
            except Exception as exc:
                self._push("toast", {"message": str(exc), "kind": "error"})
        threading.Thread(target=_do, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════
    # RAG — Project Index
    # ══════════════════════════════════════════════════════════════════════
    _INDEX_EXTS = {
        ".py", ".js", ".ts", ".html", ".htm", ".css", ".json",
        ".md", ".yaml", ".yml", ".sh", ".txt", ".toml", ".ini",
        ".cpp", ".c", ".h", ".cs", ".java", ".go", ".rs", ".rb",
    }

    def _index_project(self, payload: dict):
        root = payload.get("root", self.project_root)
        if not root:
            return
        threading.Thread(target=self._indexer_worker, args=(root,), daemon=True).start()

    def _indexer_worker(self, root: str):
        index: list   = []
        symbols: dict = {}
        file_count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
                for fname in filenames:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in self._INDEX_EXTS:
                        continue
                    fpath = os.path.join(dirpath, fname)
                    file_count += 1
                    try:
                        with open(fpath, encoding="utf-8", errors="ignore") as fh:
                            for lineno, line in enumerate(fh, 1):
                                stripped = line.strip()
                                if not stripped:
                                    continue
                                index.append({"file": fpath, "line": lineno, "text": stripped[:300]})
                                # Extract Python/JS symbols
                                m = _re_module.match(r"(def|class|function|const|let|var)\s+(\w+)", stripped)
                                if m:
                                    sym = m.group(2)
                                    symbols.setdefault(sym, []).append({"file": fpath, "line": lineno, "text": stripped})
                    except Exception:
                        pass
                    if len(index) > 100_000:
                        break
        except Exception as exc:
            print(f"[IDE] indexer error: {exc}")
        self._project_index   = index
        self._project_symbols = symbols
        self._push("index_done", {
            "files": file_count,
            "entries": len(index),
            "symbols": len(symbols),
        })

    def _query_index(self, payload: dict):
        query = payload.get("query", "").strip()
        if not query or not self._project_index:
            self._push("index_results", {"results": [], "symbols": []})
            return
        q_lower = query.lower()
        results, seen = [], set()
        # Exact symbol match first
        sym_hits = []
        for sym, locs in self._project_symbols.items():
            if q_lower in sym.lower():
                sym_hits.extend(locs[:3])
        # Full-text fallback
        for entry in self._project_index:
            if q_lower in entry["text"].lower():
                key = (entry["file"], entry["line"])
                if key not in seen:
                    seen.add(key)
                    results.append(entry)
                    if len(results) >= 30:
                        break
        self._push("index_results", {"results": results[:30], "symbols": sym_hits[:10]})

    def _build_ai_context(self, user_message: str) -> str:
        """Build RAG context snippet for AI — called before ai_send_stream."""
        if not self._project_index:
            return ""
        q = user_message.lower()
        hits = []
        for entry in self._project_index:
            if any(w in entry["text"].lower() for w in q.split()[:6] if len(w) > 3):
                hits.append(entry)
                if len(hits) >= 12:
                    break
        if not hits:
            return ""
        # Group by file
        by_file: dict = {}
        for h in hits:
            by_file.setdefault(h["file"], []).append(h)
        ctx = "Relevant project code:\n"
        for fpath, entries in list(by_file.items())[:4]:
            fname = os.path.basename(fpath)
            ctx += f"\n# {fname}\n"
            for e in entries[:5]:
                ctx += f"  {e['line']}: {e['text']}\n"
        return ctx

    # ── Project Snapshot (Feature: Project Context) ───────────────────────
    def _build_project_snapshot(self, base_dir: str, max_chars: int = 8000) -> str:
        """Read all project source files and return a formatted snapshot for Agent context."""
        if not base_dir or not os.path.isdir(base_dir):
            return ""
        SNAP_EXTS = {
            ".py", ".js", ".ts", ".html", ".css", ".json",
            ".md", ".sh", ".toml", ".yaml", ".yml", ".txt",
        }
        parts: list = []
        total_chars = 0
        try:
            for dirpath, dirnames, filenames in os.walk(base_dir):
                dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
                for fname in sorted(filenames):
                    if total_chars >= max_chars:
                        break
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in SNAP_EXTS:
                        continue
                    fpath = os.path.join(dirpath, fname)
                    rel   = os.path.relpath(fpath, base_dir).replace("\\", "/")
                    try:
                        with open(fpath, encoding="utf-8", errors="ignore") as fh:
                            raw = fh.read(3000)
                        truncated = len(raw) >= 3000
                        part = f"# {rel}\n{raw}" + (" ...[truncated]\n" if truncated else "\n")
                        if total_chars + len(part) > max_chars:
                            break
                        parts.append(part)
                        total_chars += len(part)
                    except Exception:
                        pass
                if total_chars >= max_chars:
                    break
        except Exception:
            pass
        if not parts:
            return ""
        return "=== Existing project files ===\n" + "\n".join(parts)

    # ── Terminal-AI Auto-Fix Loop (Feature: Terminal-AI Loop) ─────────────
    def _auto_fix_loop(self, abs_path: str, error_output: str,
                       project_root: str, provider: str, model: str) -> tuple:
        """Auto-fix a Python file that errored. Returns (fixed: bool, last_output: str)."""
        import re as _re
        last_output = error_output
        for attempt in range(1, self._auto_fix_max + 1):
            rel = os.path.relpath(abs_path, project_root).replace("\\", "/") if project_root else os.path.basename(abs_path)
            self._push("agent_autofix", {
                "attempt": attempt,
                "max":     self._auto_fix_max,
                "path":    rel,
                "error":   last_output[:500],
            })
            try:
                content = open(abs_path, encoding="utf-8").read()
            except Exception:
                break
            messages = [{"role": "user", "content": (
                f"Файл: {rel}\n"
                f"Помилка виконання:\n```\n{last_output[:800]}\n```\n"
                f"Поточний код:\n```python\n{content[:3000]}\n```\n"
                f"Виправ помилку та поверни ПОВНИЙ виправлений файл у JSON форматі."
            )}]
            response = self._ai_call_sync(provider, model, messages, self._AUTO_FIX_SYSTEM)
            if not response:
                break
            # Strip markdown
            clean = response.strip()
            if clean.startswith("```"):
                clean = _re.sub(r"^```\w*\n?", "", clean)
                clean = _re.sub(r"\n?```$", "", clean.strip())
            try:
                data = json.loads(clean)
            except Exception:
                m = _re.search(r"\{[\s\S]*\}", clean)
                data = json.loads(m.group()) if m else {}
            thoughts = data.get("thoughts", "")
            if thoughts:
                self._push("agent_thought", {"text": f"[AutoFix {attempt}/{self._auto_fix_max}] {thoughts}"})
            fix = data.get("fix_file") or {}
            new_content = fix.get("content", "")
            if not new_content:
                break
            try:
                with open(abs_path, "w", encoding="utf-8") as fh:
                    fh.write(new_content)
                self._push("open_file_in_editor", {
                    "path": abs_path, "content": new_content,
                    "name": os.path.basename(abs_path),
                })
            except Exception as exc:
                self._push("agent_action", {"type": "autofix", "attempt": attempt, "status": "error", "error": str(exc)})
                break
            # Re-run
            py = self._venv_python(project_root)
            try:
                r = subprocess.run(
                    [py, abs_path],
                    capture_output=True, text=True, timeout=20,
                    cwd=os.path.dirname(abs_path),
                    creationflags=_NO_WINDOW,
                )
                out = r.stdout + (r.stderr or "")
                self._push("terminal_output", {"output": out})
                if r.returncode == 0:
                    self._push("agent_action", {
                        "type": "autofix", "attempt": attempt,
                        "status": "fixed", "path": rel, "output": out[:200],
                    })
                    return True, out
                else:
                    last_output = out
                    self._push("agent_action", {
                        "type": "autofix", "attempt": attempt,
                        "status": "retry", "path": rel, "error": out[:300],
                    })
            except subprocess.TimeoutExpired:
                self._push("agent_action", {"type": "autofix", "attempt": attempt, "status": "timeout"})
                break
        self._push("agent_action", {
            "type": "autofix", "attempt": self._auto_fix_max,
            "status": "failed",
            "path": os.path.relpath(abs_path, project_root).replace("\\", "/") if project_root else abs_path,
        })
        return False, last_output

    # ── Virtualenv Manager (Feature: Virtualenv) ──────────────────────────
    def _venv_python(self, root: str) -> str:
        """Return Python executable inside .venv, or sys.executable as fallback."""
        import sys as _sys
        if root and os.path.isdir(root):
            venv_dir = os.path.join(root, ".venv")
            win_py   = os.path.join(venv_dir, "Scripts", "python.exe")
            unix_py  = os.path.join(venv_dir, "bin", "python")
            if os.path.exists(win_py):
                return win_py
            if os.path.exists(unix_py):
                return unix_py
        return _sys.executable

    def _venv_create(self, payload: dict):
        root = payload.get("root", self.project_root)
        if not root:
            self._push("venv_error", {"error": "Проект не відкритий"}); return
        threading.Thread(target=self._venv_create_worker, args=(root,), daemon=True).start()

    def _venv_create_worker(self, root: str):
        import sys as _sys
        venv_dir = os.path.join(root, ".venv")
        self._push("venv_progress", {"message": "⏳ Створення .venv...", "done": False})
        try:
            r = subprocess.run(
                [_sys.executable, "-m", "venv", venv_dir],
                capture_output=True, text=True, timeout=60, cwd=root,
                creationflags=_NO_WINDOW,
            )
            if r.returncode == 0:
                py = self._venv_python(root)
                # Upgrade pip silently
                subprocess.run([py, "-m", "pip", "install", "--upgrade", "pip", "-q"],
                               capture_output=True, timeout=30,
                               creationflags=_NO_WINDOW)
                self._push("venv_created", {
                    "root": root, "path": venv_dir, "python": py,
                    "message": "✅ .venv створено",
                })
                self._toast("🐍 Virtual environment створено", "success")
            else:
                err = (r.stderr or r.stdout or "Невідома помилка")[:400]
                self._push("venv_error", {"error": err})
                self._toast("⚠ Помилка створення venv", "error")
        except Exception as exc:
            self._push("venv_error", {"error": str(exc)})

    def _venv_install(self, payload: dict):
        root     = payload.get("root", self.project_root)
        packages = payload.get("packages", [])
        req_file = payload.get("requirements", None)
        if not root:
            self._push("venv_error", {"error": "Проект не відкритий"}); return
        threading.Thread(target=self._venv_install_worker,
                         args=(root, packages, req_file), daemon=True).start()

    def _venv_install_worker(self, root: str, packages: list, req_file):
        py = self._venv_python(root)
        import sys as _sys
        if py == _sys.executable:
            self._push("venv_error", {"error": "Спочатку створіть .venv для проекту"}); return
        # Determine install source
        if packages:
            cmd   = [py, "-m", "pip", "install"] + packages
            label = ", ".join(packages)
        else:
            # Auto-locate requirements.txt
            req_path = (req_file if (req_file and os.path.isabs(req_file))
                        else os.path.join(root, req_file or "requirements.txt"))
            if not os.path.exists(req_path):
                self._push("venv_error", {"error": "requirements.txt не знайдено"}); return
            cmd   = [py, "-m", "pip", "install", "-r", req_path]
            label = os.path.basename(req_path)

        self._push("venv_progress", {"message": f"📦 pip install {label}...", "done": False})
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=root,
                               creationflags=_NO_WINDOW)
            out = r.stdout + (r.stderr or "")
            self._push("terminal_output", {"output": out})
            self._push("switch_panel",    {"panel": "output"})
            self._push("venv_installed",  {
                "packages": packages, "label": label,
                "success": r.returncode == 0,
                "output":  out[-400:],
            })
            if r.returncode == 0:
                self._toast(f"📦 Встановлено: {label}", "success")
                self._venv_status_worker(root)  # refresh status
            else:
                self._toast("⚠ pip install завершився з помилкою", "error")
        except subprocess.TimeoutExpired:
            self._push("venv_error", {"error": "pip install timeout (3 хв)"})
        except Exception as exc:
            self._push("venv_error", {"error": str(exc)})

    def _venv_status(self, payload: dict):
        root = payload.get("root", self.project_root)
        threading.Thread(target=self._venv_status_worker, args=(root,), daemon=True).start()

    def _venv_status_worker(self, root: str):
        import sys as _sys
        if not root:
            self._push("venv_status", {"exists": False, "root": ""}); return
        venv_dir = os.path.join(root, ".venv")
        py       = self._venv_python(root)
        exists   = (os.path.exists(venv_dir) and py != _sys.executable)
        packages: list = []
        req_exists = os.path.exists(os.path.join(root, "requirements.txt"))
        if exists:
            try:
                r = subprocess.run(
                    [py, "-m", "pip", "list", "--format=columns"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_NO_WINDOW,
                )
                if r.returncode == 0:
                    lines = r.stdout.strip().splitlines()[2:]
                    packages = [ln.split()[0] for ln in lines if ln.strip()][:40]
            except Exception:
                pass
        self._push("venv_status", {
            "exists":     exists,
            "root":       root,
            "path":       venv_dir,
            "python":     py,
            "packages":   packages,
            "req_exists": req_exists,
        })

    def _venv_run(self, payload: dict):
        """Run a .py file with the project's venv Python."""
        path = payload.get("path", "")
        root = payload.get("root", self.project_root)
        if not path:
            return
        threading.Thread(target=self._venv_run_worker, args=(path, root), daemon=True).start()

    def _venv_run_worker(self, path: str, root: str):
        py = self._venv_python(root)
        self._push("terminal_output", {"output": f"▸ {py} {path}\n"})
        self._push("switch_panel", {"panel": "output"})
        try:
            r = subprocess.run(
                [py, path],
                capture_output=True, text=True, timeout=30,
                cwd=root or os.path.dirname(path),
                creationflags=_NO_WINDOW,
            )
            out = r.stdout + (r.stderr or "")
            self._push("terminal_output", {"output": out or "(немає виводу)"})
            if r.returncode != 0:
                self._push("run_error", {
                    "path": path, "error": out, "exit_code": r.returncode,
                })
        except subprocess.TimeoutExpired:
            self._push("terminal_output", {"output": "⏱ Timeout (30s)\n"})
        except Exception as exc:
            self._push("terminal_output", {"output": str(exc)})

    # ════════════════════════════════════════════════════════════════════
    # CURSOR-PARITY FEATURES
    # ════════════════════════════════════════════════════════════════════

    # ── 1. Apply code block to file ──────────────────────────────────────
    def _apply_code(self, payload: dict):
        path    = payload.get("path", "")
        code    = payload.get("code", "")
        mode    = payload.get("mode", "replace")  # replace | append | diff
        if not path or not code:
            return
        try:
            if mode == "append":
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("\n" + code)
                self._push("code_applied", {"path": path, "mode": "append"})
            elif mode == "diff":
                # Read original, show diff to user
                try:
                    original = open(path, encoding="utf-8").read()
                except Exception:
                    original = ""
                self._push("show_diff", {
                    "path":     path,
                    "original": original,
                    "modified": code,
                    "lang":     EXT_LANG.get(os.path.splitext(path)[1].lower(), "plaintext"),
                })
            else:
                # replace: write and update editor
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(code)
                self._push("code_applied", {"path": path, "mode": "replace", "content": code})
            self._toast("✅ Код застосовано", "success")
        except Exception as exc:
            self._toast(f"⚠ Помилка: {exc}", "error")

    # ── 2. Accept diff (write modified to disk) ──────────────────────────
    def _apply_diff(self, payload: dict):
        path    = payload.get("path", "")
        content = payload.get("content", "")
        if not path or not content:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self._push("code_applied", {"path": path, "mode": "replace", "content": content})
            self._toast("✅ Зміни прийнято", "success")
        except Exception as exc:
            self._toast(f"⚠ Помилка запису: {exc}", "error")

    # ── 3. Ghost text (AI inline completions) ────────────────────────────
    def _ghost_complete(self, payload: dict):
        req_id   = payload.get("id", "")
        path     = payload.get("path", "")
        code_before = payload.get("code_before", "")
        if not req_id or not code_before.strip():
            return
        self._ghost_cancel[req_id] = False
        threading.Thread(
            target=self._ghost_worker,
            args=(req_id, path, code_before),
            daemon=True,
        ).start()

    def _ghost_worker(self, req_id: str, path: str, code_before: str):
        _GHOST_SYS = (
            "You are a code completion engine. "
            "Complete the code at the cursor position. "
            "Return ONLY the completion text (1-4 lines max), no explanation, "
            "no markdown, no repetition of existing code."
        )
        try:
            provider = self._effective_provider()
            model    = self._effective_model()
            # Use a fast/cheap model for ghost text
            fast_models = {
                "openai":     "gpt-4o-mini",
                "anthropic":  "claude-haiku-4-5",
                "google":     "gemini-2.0-flash",
            }
            ghost_model = fast_models.get(provider, model)
            messages = [{"role": "user", "content": (
                f"File: {os.path.basename(path)}\n"
                f"Code up to cursor:\n```\n{code_before[-1500:]}\n```\n"
                f"Complete the next 1-3 lines:"
            )}]
            result = self._ai_call_sync(provider, ghost_model, messages, _GHOST_SYS)
            if self._ghost_cancel.pop(req_id, False):
                return
            if result:
                # Clean up: strip markdown, limit to 4 lines
                import re as _re
                clean = result.strip()
                clean = _re.sub(r"^```\w*\n?", "", clean)
                clean = _re.sub(r"\n?```$", "", clean)
                lines = clean.splitlines()[:4]
                self._push("ghost_complete", {"id": req_id, "text": "\n".join(lines)})
        except Exception:
            pass
        finally:
            self._ghost_cancel.pop(req_id, None)

    # ── 4. @-mention: resolve file path → content ────────────────────────
    def _at_resolve(self, payload: dict):
        """Resolve @filename mentions to file content for chat context."""
        mentions = payload.get("mentions", [])  # list of {name, path}
        resolved = []
        for m in mentions:
            fpath = m.get("path", "")
            if fpath and os.path.isfile(fpath):
                try:
                    content = open(fpath, encoding="utf-8", errors="ignore").read(4000)
                    resolved.append({
                        "name":    m.get("name", os.path.basename(fpath)),
                        "path":    fpath,
                        "content": content,
                        "lines":   len(content.splitlines()),
                    })
                except Exception:
                    pass
        self._push("at_resolved", {"resolved": resolved})

    # ── 5. .axisrules support ─────────────────────────────────────────────
    def _load_axisrules(self, payload: dict):
        root = payload.get("root", self.project_root)
        if not root:
            return
        rules_path = os.path.join(root, ".axisrules")
        if os.path.exists(rules_path):
            try:
                self._axisrules = open(rules_path, encoding="utf-8").read().strip()
                self._push("axisrules_loaded", {
                    "path":    rules_path,
                    "content": self._axisrules[:200],
                    "lines":   len(self._axisrules.splitlines()),
                })
                self._toast(f"📜 .axisrules завантажено ({len(self._axisrules.splitlines())} рядків)", "success")
            except Exception as exc:
                self._axisrules = ""
                self._push("axisrules_loaded", {"path": "", "content": ""})
        else:
            self._axisrules = ""
            self._push("axisrules_loaded", {"path": "", "content": ""})

    # ── 6. Composer: multi-file edit agent ───────────────────────────────
    _COMPOSER_SYSTEM = (
        "Ти AXIS Composer — AI редактор коду що редагує існуючі файли проекту.\n"
        "На КОЖЕН запит відповідай ВИКЛЮЧНО валідним JSON (без markdown):\n"
        "{\n"
        "  \"thoughts\": \"що плануєш зробити\",\n"
        "  \"edits\": [\n"
        "    {\"path\": \"відносний/шлях/файл.py\", \"content\": \"ПОВНИЙ новий вміст файлу\","
        " \"description\": \"що змінено\"}\n"
        "  ],\n"
        "  \"done\": true,\n"
        "  \"summary\": \"короткий опис всіх змін\"\n"
        "}\n\n"
        "Правила:\n"
        "- paths відносні до кореня проекту\n"
        "- content = ПОВНИЙ вміст файлу (не фрагменти)\n"
        "- редагуй тільки файли що треба змінити\n"
        "- можна створювати нові файли\n"
        "- якщо надано контекст файлів — використовуй їх\n"
    )

    def _composer(self, payload: dict):
        task        = payload.get("task", "").strip()
        use_context = payload.get("project_context", True)
        if not task:
            return
        base_dir = self.project_root or self.ide_cfg.get("projects_dir", str(Path.home() / "Projects"))
        threading.Thread(target=self._composer_worker, args=(task, base_dir, use_context), daemon=True).start()

    def _composer_worker(self, task: str, base_dir: str, use_context: bool):
        import re as _re
        try:
            self._push("composer_start", {"task": task})
            provider = self._effective_provider()
            model    = self._effective_model()

            system = self._COMPOSER_SYSTEM
            if self._axisrules:
                system = self._axisrules + "\n\n" + system
            if use_context and base_dir and os.path.isdir(base_dir):
                snapshot = self._build_project_snapshot(base_dir)
                if snapshot:
                    system = system + "\n\n" + snapshot

            messages = [{"role": "user", "content": task}]
            response = self._ai_call_sync(provider, model, messages, system)
            if not response:
                self._push("composer_error", {"error": "AI не відповів"}); return

            clean = response.strip()
            if clean.startswith("```"):
                clean = _re.sub(r"^```\w*\n?", "", clean)
                clean = _re.sub(r"\n?```$", "", clean.strip())
            try:
                data = json.loads(clean)
            except Exception:
                m = _re.search(r"\{[\s\S]*\}", clean)
                data = json.loads(m.group()) if m else {}

            thoughts = data.get("thoughts", "")
            edits    = data.get("edits", [])
            summary  = data.get("summary", "")

            if thoughts:
                self._push("composer_thought", {"text": thoughts})

            diff_queue = []
            for edit in edits:
                rel     = edit.get("path", "").replace("\\", "/")
                content = edit.get("content", "")
                desc    = edit.get("description", "")
                if not rel or not content:
                    continue
                abs_path = os.path.normpath(os.path.join(base_dir, rel))
                # Read original for diff
                try:
                    original = open(abs_path, encoding="utf-8").read() if os.path.exists(abs_path) else ""
                except Exception:
                    original = ""
                lang = EXT_LANG.get(os.path.splitext(rel)[1].lower(), "plaintext")
                diff_queue.append({
                    "path":     abs_path,
                    "rel":      rel,
                    "original": original,
                    "modified": content,
                    "lang":     lang,
                    "description": desc,
                })

            # Send all diffs to UI for Accept/Reject
            self._push("composer_diffs", {
                "diffs":   diff_queue,
                "summary": summary,
                "task":    task,
            })
        except Exception as exc:
            import traceback
            self._push("composer_error", {"error": str(exc)})
            print(f"[IDE Composer] {traceback.format_exc()}")

    # ── 7. Rename symbol across project ──────────────────────────────────
    def _rename_symbol(self, payload: dict):
        old_name = payload.get("old_name", "").strip()
        new_name = payload.get("new_name", "").strip()
        root     = payload.get("root", self.project_root)
        if not old_name or not new_name or not root:
            self._push("rename_result", {"changed": [], "error": "Неповні параметри"}); return
        threading.Thread(target=self._rename_worker, args=(old_name, new_name, root), daemon=True).start()

    def _rename_worker(self, old_name: str, new_name: str, root: str):
        import re as _re
        TEXT_EXTS = {".py",".js",".ts",".html",".css",".json",".md",".yaml",".yml",".sh",".toml"}
        changed = []
        pattern = _re.compile(r'\b' + _re.escape(old_name) + r'\b')
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
                for fname in filenames:
                    if os.path.splitext(fname)[1].lower() not in TEXT_EXTS:
                        continue
                    fpath = os.path.join(dirpath, fname)
                    try:
                        text = open(fpath, encoding="utf-8", errors="ignore").read()
                        new_text = pattern.sub(new_name, text)
                        if new_text != text:
                            with open(fpath, "w", encoding="utf-8") as fh:
                                fh.write(new_text)
                            count = len(pattern.findall(text))
                            changed.append({
                                "path":  fpath,
                                "rel":   os.path.relpath(fpath, root).replace("\\", "/"),
                                "count": count,
                            })
                    except Exception:
                        pass
        except Exception as exc:
            self._push("rename_result", {"changed": [], "error": str(exc)}); return
        self._push("rename_result", {
            "old_name": old_name, "new_name": new_name,
            "changed":  changed,
            "total":    sum(c["count"] for c in changed),
        })
        if changed:
            self._toast(f"✅ Перейменовано '{old_name}' → '{new_name}' у {len(changed)} файлах", "success")
        else:
            self._toast(f"⚠ '{old_name}' не знайдено в проекті", "warn")


# ══════════════════════════════════════════════════════════════════════════
# IDE Window
# ══════════════════════════════════════════════════════════════════════════
class IDEWindow(QMainWindow):
    def __init__(self, ide_cfg: dict, ai_manager):
        super().__init__()
        self.setWindowTitle("AXIS IDE")
        self.resize(1440, 900)
        self.setMinimumSize(900, 600)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        icon_path = DATA_DIR / "icon_ide.ico"
        if not icon_path.exists():
            icon_path = DATA_DIR / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2,
        )

        # Web view
        self.view = QWebEngineView()
        s = self.view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        # Bridge & channel
        self.bridge  = IDEBridge(self, ai_manager, ide_cfg)
        self.channel = QWebChannel()
        self.channel.registerObject("ideBridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.bridge.push_to_js.connect(self._push_to_js)

        self._inject_bridge_js()

        self.view.load(QUrl.fromLocalFile(str(HTML_PATH.resolve())))
        self.view.loadFinished.connect(self._on_load)

        self.setCentralWidget(self.view)
        self._drag_pos = None

    # ── qwebchannel injection ──────────────────────────────────────────────
    def _inject_bridge_js(self):
        qwc = QFile(":/qtwebchannel/qwebchannel.js")
        js_src = ""
        if qwc.open(QFile.OpenModeFlag.ReadOnly):
            js_src = bytes(qwc.readAll()).decode("utf-8")
            qwc.close()

        setup_js = """
(function() {
    var _queue = [];
    var _bridge = null;

    window.ideCall = function(cmd, data) {
        var payload = (data === undefined || data === null) ? '' :
                      (typeof data === 'string' ? data : JSON.stringify(data));
        if (_bridge) {
            _bridge.call(cmd, payload);
        } else {
            _queue.push([cmd, payload]);
        }
    };

    window.idePush = function(type, jsonStr) { /* filled by Python */ };

    function _ready(bridge) {
        _bridge = bridge;
        _queue.forEach(function(item) { bridge.call(item[0], item[1]); });
        _queue = [];
    }

    function _initChannel() {
        if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined') {
            new QWebChannel(qt.webChannelTransport, function(channel) {
                _ready(channel.objects.ideBridge);
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
        script.setName("ide_bridge_init")
        script.setSourceCode(full_src)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        self.view.page().scripts().insert(script)

    def _on_load(self, ok: bool):
        if not ok:
            print("[IDE] Page load failed")
            return
        self.bridge.call("get_config", "")

    # ── Push to JS ─────────────────────────────────────────────────────────
    def _push_to_js(self, evt_type: str, json_str: str):
        safe = json_str.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        js = f"if(window.idePush) window.idePush({json.dumps(evt_type)}, `{safe}`);"
        self.view.page().runJavaScript(js)

    # ── Frameless drag ─────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════
def _load_config(path: Path, defaults: dict) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            merged = {**defaults, **data}
            return merged
        except Exception:
            pass
    return dict(defaults)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AXIS IDE")
    parser.add_argument("--project",     metavar="PATH", default="",
                        help="Open a project folder on startup")
    parser.add_argument("--open-folder", action="store_true",
                        help="Show folder picker on startup")
    # parse_known_args so Qt args (like --platform) pass through
    cli_args, qt_argv = parser.parse_known_args()
    # Reconstruct sys.argv for Qt (keep argv[0])
    sys.argv = [sys.argv[0]] + qt_argv

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("AXIS IDE")
    app.setApplicationVersion("1.0.0")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Load configs
    ide_cfg  = _load_config(IDE_CFG, DEFAULT_IDE_CFG)
    main_cfg = _load_config(MAIN_CFG, {})

    # Merge API keys from main config into ide cfg for AIManager
    ai_cfg = dict(main_cfg)
    if "api_keys" not in ai_cfg:
        ai_cfg["api_keys"] = {}

    # Privacy mode enforcement
    if ide_cfg.get("privacy_mode"):
        ide_cfg["provider"] = "ollama"

    from core.ai_manager import AIManager
    ai_manager = AIManager(ai_cfg)

    window = IDEWindow(ide_cfg, ai_manager)
    window.show()

    # Handle CLI startup args after the window is shown
    if cli_args.project and os.path.isdir(cli_args.project):
        window.bridge.call("open_folder_path",
                           json.dumps({"path": cli_args.project}))
    elif cli_args.open_folder:
        # Defer folder dialog until event loop is running
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, lambda: window.bridge._open_folder({}))
    else:
        # Auto-reopen last project from recent_projects
        last = ide_cfg.get("recent_projects", [])
        if last and os.path.isdir(last[0]):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(600, lambda: window.bridge._open_folder_path({"path": last[0]}))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
