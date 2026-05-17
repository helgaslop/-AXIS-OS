"""All tools available to agents — file system, system, network."""
import os
import sys
import json
import shutil
import subprocess
import platform
import tempfile
from pathlib import Path

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ─── Lint helper ─────────────────────────────────────────────────────────────

def _lint_file(path: str) -> str | None:
    """
    Quick syntax check after writing a file.
    Returns a short warning string on error, or None if OK / not applicable.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        try:
            import py_compile, io
            err_buf = io.StringIO()
            try:
                py_compile.compile(path, doraise=True)
            except py_compile.PyCompileError as e:
                return f"⚠ Синтаксична помилка Python: {str(e)}"
        except Exception:
            pass
    elif ext in (".json",):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            return f"⚠ JSON помилка: {e}"
    return None

# ─── Implementations ──────────────────────────────────────────────────────────

def _read_file(path: str, start_line: int = None, end_line: int = None) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            if start_line is not None or end_line is not None:
                lines = f.readlines()
                s = max(0, (start_line or 1) - 1)
                e = end_line if end_line else len(lines)
                selected = lines[s:e]
                content = "".join(selected)
                return {
                    "success": True,
                    "result": content[:20000],
                    "info": f"Lines {s+1}-{min(e, len(lines))} of {len(lines)} total",
                }
            content = f.read()
        return {"success": True, "result": content[:50000]}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _str_replace(path: str, old_str: str, new_str: str) -> dict:
    """Targeted surgical edit: replace first occurrence of old_str with new_str."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        if old_str not in content:
            # Return FULL file so agent can find correct old_str without another read_file
            return {
                "success": False,
                "error": (
                    f"Text not found in {path}. Use EXACTLY the text from the file below "
                    f"(copy-paste, do not paraphrase).\n"
                    f"=== CURRENT FILE CONTENT ===\n{content[:6000]}"
                ),
            }
        new_content = content.replace(old_str, new_str, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        delta = new_str.count("\n") - old_str.count("\n")
        # Generate a simple line diff (capped at 20 lines each side)
        old_lines = old_str.splitlines()
        new_lines = new_str.splitlines()
        diff_lines = []
        for line in old_lines[:20]:
            diff_lines.append("-" + line)
        for line in new_lines[:20]:
            diff_lines.append("+" + line)
        diff_str = "\n".join(diff_lines)
        lint_warn = _lint_file(path)
        result_msg = f"str_replace applied to {path} (line delta: {delta:+d})"
        if lint_warn:
            result_msg += f"\n{lint_warn}"
        return {"success": True, "result": result_msg, "diff": diff_str, "path": path}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _insert_text(path: str, insert_after: str, text: str) -> dict:
    """Insert text immediately after a specific marker string in a file."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        if insert_after not in content:
            return {"success": False, "error": f"Marker not found in {path}: {insert_after!r}"}
        idx = content.index(insert_after) + len(insert_after)
        new_content = content[:idx] + text + content[idx:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return {"success": True, "result": f"Inserted {len(text)} chars into {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _write_file(path: str, content: str) -> dict:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        result_msg = f"Written {len(content)} chars → {path}"
        lint_warn = _lint_file(path)
        if lint_warn:
            result_msg += f"\n{lint_warn}"
        return {"success": True, "result": result_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _create_file(path: str, content: str = "") -> dict:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "result": f"Created {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _delete_file(path: str) -> dict:
    try:
        os.remove(path)
        return {"success": True, "result": f"Deleted {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _move_file(src: str, dst: str) -> dict:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        shutil.move(src, dst)
        return {"success": True, "result": f"Moved {src} → {dst}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _rename_file(path: str, new_name: str) -> dict:
    try:
        new_path = os.path.join(os.path.dirname(path), new_name)
        os.rename(path, new_path)
        return {"success": True, "result": f"Renamed → {new_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _list_dir(path: str = ".", recursive: bool = False) -> dict:
    try:
        _SKIP = {"__pycache__", "node_modules", ".git", "venv", ".venv", "dist", "build"}
        if recursive:
            out = []
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in _SKIP and not d.startswith(".")]
                rel = os.path.relpath(root, path)
                for f in files:
                    out.append(os.path.join(rel, f).replace("\\", "/"))
                if len(out) > 1000:
                    out.append("... (truncated)")
                    break
            return {"success": True, "result": "\n".join(out)}
        entries = []
        for e in os.scandir(path):
            tag = "DIR " if e.is_dir() else "FILE"
            sz = f" ({e.stat().st_size}B)" if e.is_file() else ""
            entries.append(f"[{tag}] {e.name}{sz}")
        return {"success": True, "result": "\n".join(entries)}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _create_dir(path: str) -> dict:
    try:
        os.makedirs(path, exist_ok=True)
        return {"success": True, "result": f"Created directory {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _delete_dir(path: str) -> dict:
    try:
        shutil.rmtree(path)
        return {"success": True, "result": f"Deleted directory {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _search_files(pattern: str, path: str = ".", content_search: str = "") -> dict:
    try:
        import fnmatch
        _SKIP = {"__pycache__", "node_modules", ".git", "venv", ".venv"}
        matches = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in _SKIP and not d.startswith(".")]
            for fn in files:
                if fnmatch.fnmatch(fn, pattern):
                    fp = os.path.join(root, fn)
                    if content_search:
                        try:
                            with open(fp, encoding="utf-8", errors="ignore") as f:
                                if content_search in f.read():
                                    matches.append(fp)
                        except Exception:
                            pass
                    else:
                        matches.append(fp)
        return {"success": True, "result": "\n".join(matches[:300]), "count": len(matches)}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _run_command(command: str, cwd: str = None, timeout: int = 60,
                 stream_cb=None) -> dict:
    """Run a shell command. If stream_cb is provided, calls stream_cb(line) for each output line."""
    try:
        proc = subprocess.Popen(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd or None,
            creationflags=_NO_WINDOW,
        )
        output = ""
        try:
            for line in proc.stdout:
                output += line
                if stream_cb:
                    try:
                        stream_cb(line.rstrip("\n"))
                    except Exception:
                        pass
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"success": False, "error": f"Timeout ({timeout}s)", "result": output[:10000]}
        return {
            "success": proc.returncode == 0,
            "result":  output[:10000],
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def _run_python(code: str, cwd: str = None, timeout: int = 60,
                stream_cb=None) -> dict:
    """Run Python code in a temp file. Streams output if stream_cb is provided."""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        proc = subprocess.Popen(
            [sys.executable, tmp],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd or None, creationflags=_NO_WINDOW,
        )
        output = ""
        try:
            for line in proc.stdout:
                output += line
                if stream_cb:
                    try:
                        stream_cb(line.rstrip("\n"))
                    except Exception:
                        pass
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"success": False, "error": f"Timeout ({timeout}s)", "result": output[:10000]}
        return {"success": proc.returncode == 0, "result": output[:10000]}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

def _open_app(name_or_path: str) -> dict:
    try:
        if sys.platform == "win32":
            os.startfile(name_or_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", name_or_path])
        else:
            subprocess.Popen(["xdg-open", name_or_path])
        return {"success": True, "result": f"Opened: {name_or_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _kill_process(name_or_pid: str) -> dict:
    try:
        import psutil
        killed = 0
        try:
            psutil.Process(int(name_or_pid)).terminate()
            killed = 1
        except ValueError:
            for p in psutil.process_iter(["pid", "name"]):
                if name_or_pid.lower() in (p.info.get("name") or "").lower():
                    p.terminate()
                    killed += 1
        return {"success": killed > 0, "result": f"Terminated {killed} process(es)"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _get_system_info() -> dict:
    try:
        import psutil
        vm = psutil.virtual_memory()
        d  = psutil.disk_usage("/")
        info = {
            "os":          platform.system(),
            "os_version":  platform.version()[:80],
            "python":      sys.version.split()[0],
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_total_gb": round(vm.total / 1024**3, 1),
            "ram_used_gb":  round(vm.used  / 1024**3, 1),
            "disk_free_gb": round(d.free   / 1024**3, 1),
        }
        return {"success": True, "result": json.dumps(info, indent=2)}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _install_package(package: str, manager: str = "pip", cwd: str = None,
                     stream_cb=None) -> dict:
    cmds = {
        "pip":  [sys.executable, "-m", "pip", "install", package],
        "npm":  ["npm", "install", package],
        "yarn": ["yarn", "add", package],
    }
    cmd = cmds.get(manager)
    if not cmd:
        return {"success": False, "error": f"Unknown manager: {manager}"}
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, cwd=cwd or None, creationflags=_NO_WINDOW)
        output = ""
        for line in proc.stdout:
            output += line
            if stream_cb:
                try: stream_cb(line.rstrip("\n"))
                except Exception: pass
        proc.wait(timeout=120)
        return {"success": proc.returncode == 0, "result": output[-2000:]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout (2 min)"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _download_file(url: str, path: str) -> dict:
    try:
        import requests
        r = requests.get(url, timeout=30, stream=True)
        r.raise_for_status()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return {"success": True, "result": f"Downloaded {os.path.getsize(path)} bytes → {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _http_request(url: str, method: str = "GET",
                  headers: dict = None, body: str = None) -> dict:
    try:
        import requests
        r = requests.request(method, url, headers=headers or {}, data=body, timeout=15)
        return {"success": True, "result": r.text[:5000], "status": r.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _todo_write(tasks: list) -> dict:
    """Update the agent's task list (shown in chat UI)."""
    return {"success": True, "result": "todo_updated", "tasks": tasks}


def _search_in_files(query: str, path: str = ".", file_pattern: str = "*",
                     case_sensitive: bool = False, max_results: int = 50) -> dict:
    """Search for text in files with line numbers — like grep."""
    import fnmatch, re
    _SKIP = {"__pycache__", "node_modules", ".git", "venv", ".venv", "dist", "build"}
    results = []
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(re.escape(query), flags)
    except re.error:
        pattern = re.compile(query, flags)

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _SKIP and not d.startswith(".")]
        for fn in files:
            if file_pattern != "*" and not fnmatch.fnmatch(fn, file_pattern):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if pattern.search(line):
                            rel = os.path.relpath(fp, path).replace("\\", "/")
                            results.append(f"{rel}:{i}: {line.rstrip()}")
                            if len(results) >= max_results:
                                break
            except Exception:
                pass
        if len(results) >= max_results:
            break

    if not results:
        return {"success": True, "result": f"No matches found for '{query}'"}
    return {"success": True, "result": "\n".join(results), "count": len(results)}


def _git_status(path: str = ".") -> dict:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=path, capture_output=True, text=True, timeout=10,
            creationflags=_NO_WINDOW,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip() or "Not a git repo"}
        return {"success": True, "result": result.stdout.strip() or "Working tree clean"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _git_diff(path: str = ".", file: str = "") -> dict:
    try:
        cmd = ["git", "diff", "--", file] if file else ["git", "diff"]
        result = subprocess.run(cmd, cwd=path, capture_output=True, text=True, timeout=15,
                                creationflags=_NO_WINDOW)
        out = result.stdout[:8000] or "No changes"
        return {"success": True, "result": out}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _git_commit(path: str, message: str, add_all: bool = True) -> dict:
    try:
        if add_all:
            subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True, timeout=10,
                           creationflags=_NO_WINDOW)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=path, capture_output=True, text=True, timeout=15,
            creationflags=_NO_WINDOW,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}
        return {"success": True, "result": result.stdout.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _git_log(path: str = ".", n: int = 10) -> dict:
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--oneline", "--decorate"],
            cwd=path, capture_output=True, text=True, timeout=10,
            creationflags=_NO_WINDOW,
        )
        return {"success": True, "result": result.stdout.strip() or "No commits yet"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Eyes & Hands tools ────────────────────────────────────────────────────────

def _screenshot(save_path: str = None) -> dict:
    """Take a screenshot of the entire screen. Returns path to the saved PNG file."""
    try:
        import tempfile
        if not save_path:
            fd, save_path = tempfile.mkstemp(suffix=".png", prefix="axis_shot_")
            os.close(fd)
        # Try PIL first
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True)
            img.save(save_path)
            w, h = img.size
            return {"success": True, "result": f"Screenshot saved: {save_path} ({w}x{h})", "path": save_path}
        except ImportError:
            pass
        # Fallback: mss
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                img_data = sct.grab(monitor)
                mss.tools.to_png(img_data.rgb, img_data.size, output=save_path)
            return {"success": True, "result": f"Screenshot saved: {save_path}", "path": save_path}
        except ImportError:
            pass
        # Fallback: Windows API
        if sys.platform == "win32":
            import ctypes, ctypes.wintypes
            result = subprocess.run(
                ["powershell", "-Command",
                 f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.Screen]::PrimaryScreen | Out-Null; "
                 f"$bmp = New-Object System.Drawing.Bitmap([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); "
                 f"$g=[System.Drawing.Graphics]::FromImage($bmp); "
                 f"$g.CopyFromScreen(0,0,0,0,$bmp.Size); "
                 f"$bmp.Save('{save_path}')"],
                capture_output=True, timeout=10, creationflags=_NO_WINDOW
            )
            if os.path.exists(save_path):
                return {"success": True, "result": f"Screenshot: {save_path}", "path": save_path}
        return {"success": False, "error": "No screenshot library found. Install: pip install Pillow"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _mouse_click(x: int, y: int, button: str = "left", double: bool = False) -> dict:
    """Click the mouse at screen coordinates (x, y)."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        if double:
            pyautogui.doubleClick(x, y, button=button)
        else:
            pyautogui.click(x, y, button=button)
        return {"success": True, "result": f"{'Double-c' if double else 'C'}licked {button} at ({x}, {y})"}
    except ImportError:
        return {"success": False, "error": "pyautogui not installed. Run: pip install pyautogui"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _mouse_move(x: int, y: int) -> dict:
    """Move the mouse cursor to screen coordinates (x, y)."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.moveTo(x, y, duration=0.1)
        return {"success": True, "result": f"Mouse moved to ({x}, {y})"}
    except ImportError:
        return {"success": False, "error": "pyautogui not installed. Run: pip install pyautogui"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _type_text(text: str, interval: float = 0.02) -> dict:
    """Type text at the current cursor position using keyboard simulation."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        # Use clipboard for non-ASCII characters
        import subprocess as _sp
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            pyautogui.write(text, interval=interval)
        return {"success": True, "result": f"Typed {len(text)} chars"}
    except ImportError:
        return {"success": False, "error": "pyautogui not installed. Run: pip install pyautogui"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _press_key(key: str) -> dict:
    """Press a keyboard key or key combination (e.g. 'enter', 'ctrl+s', 'alt+f4')."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        if "+" in key:
            parts = [p.strip() for p in key.split("+")]
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(key)
        return {"success": True, "result": f"Pressed: {key}"}
    except ImportError:
        return {"success": False, "error": "pyautogui not installed. Run: pip install pyautogui"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_screen_info() -> dict:
    """Get screen resolution and mouse position."""
    try:
        import pyautogui
        w, h = pyautogui.size()
        mx, my = pyautogui.position()
        return {"success": True, "result": f"Screen: {w}x{h}, Mouse: ({mx}, {my})",
                "width": w, "height": h, "mouse_x": mx, "mouse_y": my}
    except ImportError:
        if sys.platform == "win32":
            import ctypes
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            return {"success": True, "result": f"Screen: {w}x{h}", "width": w, "height": h}
        return {"success": False, "error": "pyautogui not installed. Run: pip install pyautogui"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _search_system(query: str, search_path: str = None,
                   file_type: str = None, max_results: int = 100) -> dict:
    """Search the entire system for files by name. Searches all drives on Windows."""
    import fnmatch as _fnm
    _SKIP_DIRS = {
        "__pycache__", "node_modules", ".git", "$Recycle.Bin",
        "System Volume Information", "Windows\\WinSxS", "Windows\\Installer",
    }
    if search_path:
        roots = [search_path]
    elif sys.platform == "win32":
        import string
        roots = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    else:
        roots = [os.path.expanduser("~"), "/usr/local", "/opt"]

    results = []
    q = query.lower()
    ext_filter = ("." + file_type.lstrip(".")).lower() if file_type else None

    for root_path in roots:
        for root, dirs, files in os.walk(root_path, topdown=True):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith("$")]
            for fname in files:
                flow = fname.lower()
                if q in flow:
                    if ext_filter and not flow.endswith(ext_filter):
                        continue
                    results.append(os.path.join(root, fname))
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break

    if not results:
        return {"success": True, "result": f"Nothing found for '{query}' on the system"}
    return {"success": True, "result": "\n".join(results), "count": len(results)}


def _list_windows() -> dict:
    """List all open windows/applications on the system."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
                 "Select-Object Name, Id, MainWindowTitle | "
                 "Format-Table -AutoSize | Out-String"],
                capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW
            )
            return {"success": True, "result": result.stdout.strip()[:4000]}
        else:
            result = subprocess.run(
                ["wmctrl", "-l"], capture_output=True, text=True, timeout=5
            )
            return {"success": True, "result": result.stdout.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _scroll(direction: str = "down", amount: int = 3) -> dict:
    """Scroll the mouse wheel up or down."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        clicks = amount if direction == "down" else -amount
        pyautogui.scroll(clicks)
        return {"success": True, "result": f"Scrolled {direction} {amount} clicks"}
    except ImportError:
        return {"success": False, "error": "pyautogui not installed. Run: pip install pyautogui"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Tool registry ─────────────────────────────────────────────────────────────

TOOLS = {
    # ── Safe ──────────────────────────────────────────────────────────────────
    "read_file": {
        "fn": _read_file, "dangerous": False,
        "description": "Read contents of a file. Optionally specify start_line and end_line to read a range.",
        "parameters": {
            "type": "object",
            "properties": {
                "path":       {"type": "string",  "description": "Absolute or relative file path"},
                "start_line": {"type": "integer", "description": "First line to read (1-based, optional)"},
                "end_line":   {"type": "integer", "description": "Last line to read inclusive (optional)"},
            },
            "required": ["path"],
        },
    },
    "list_dir": {
        "fn": _list_dir, "dangerous": False,
        "description": "List directory contents",
        "parameters": {
            "type": "object",
            "properties": {
                "path":      {"type": "string",  "description": "Directory path", "default": "."},
                "recursive": {"type": "boolean", "description": "List recursively", "default": False},
            },
        },
    },
    "search_files": {
        "fn": _search_files, "dangerous": False,
        "description": "Search files by name pattern or inside content",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern":        {"type": "string", "description": "Filename glob pattern, e.g. '*.py'"},
                "path":           {"type": "string", "description": "Root dir", "default": "."},
                "content_search": {"type": "string", "description": "Text to find inside files", "default": ""},
            },
            "required": ["pattern"],
        },
    },
    "get_system_info": {
        "fn": _get_system_info, "dangerous": False,
        "description": "Get OS, CPU, RAM and disk info",
        "parameters": {"type": "object", "properties": {}},
    },
    "http_request": {
        "fn": _http_request, "dangerous": False,
        "description": "Make an HTTP request",
        "parameters": {
            "type": "object",
            "properties": {
                "url":     {"type": "string"},
                "method":  {"type": "string", "default": "GET"},
                "headers": {"type": "object", "default": {}},
                "body":    {"type": "string",  "default": None},
            },
            "required": ["url"],
        },
    },

    # ── Safe — targeted edits (like Claude Code str_replace / insert) ────────
    "str_replace": {
        "fn": _str_replace, "dangerous": False,
        "description": (
            "Surgical edit: replace the FIRST occurrence of old_str with new_str in a file. "
            "Use this to edit existing files instead of rewriting the whole file. "
            "old_str must be an EXACT match (copy from file context)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Absolute path to the file"},
                "old_str": {"type": "string", "description": "Exact text to find and replace"},
                "new_str": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    "insert_text": {
        "fn": _insert_text, "dangerous": False,
        "description": (
            "Insert text immediately after a marker string in a file. "
            "Useful for adding new functions, CSS rules, or HTML sections."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":         {"type": "string", "description": "Absolute path to the file"},
                "insert_after": {"type": "string", "description": "Insert new text after this exact string"},
                "text":         {"type": "string", "description": "Text to insert"},
            },
            "required": ["path", "insert_after", "text"],
        },
    },

    # ── Safe — file write ops (no permission needed, like Claude Code) ───────
    "write_file": {
        "fn": _write_file, "dangerous": False,
        "description": "Write content to a file (creates or overwrites)",
        "parameters": {
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    "create_file": {
        "fn": _create_file, "dangerous": False,
        "description": "Create a new file with optional initial content",
        "parameters": {
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "content": {"type": "string", "default": ""},
            },
            "required": ["path"],
        },
    },
    "move_file": {
        "fn": _move_file, "dangerous": False,
        "description": "Move or rename a file to a new location",
        "parameters": {
            "type": "object",
            "properties": {
                "src": {"type": "string"},
                "dst": {"type": "string"},
            },
            "required": ["src", "dst"],
        },
    },
    "rename_file": {
        "fn": _rename_file, "dangerous": False,
        "description": "Rename a file (same directory)",
        "parameters": {
            "type": "object",
            "properties": {
                "path":     {"type": "string"},
                "new_name": {"type": "string"},
            },
            "required": ["path", "new_name"],
        },
    },
    "create_dir": {
        "fn": _create_dir, "dangerous": False,
        "description": "Create a directory and any missing parents",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },

    # ── Dangerous — destructive & system ops (ask permission) ────────────────
    "delete_file": {
        "fn": _delete_file, "dangerous": True,
        "description": "Permanently delete a file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    "delete_dir": {
        "fn": _delete_dir, "dangerous": True,
        "description": "Delete a directory and ALL its contents",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },

    # ── Dangerous — system ────────────────────────────────────────────────────
    "run_command": {
        "fn": _run_command, "dangerous": True,
        "description": "Execute a shell / terminal command",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd":     {"type": "string", "description": "Working directory", "default": None},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        },
    },
    "run_python": {
        "fn": _run_python, "dangerous": True,
        "description": "Run Python code in a subprocess and return output",
        "parameters": {
            "type": "object",
            "properties": {
                "code":    {"type": "string"},
                "cwd":     {"type": "string", "default": None},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["code"],
        },
    },
    "open_app": {
        "fn": _open_app, "dangerous": True,
        "description": "Open an application or file with the default program",
        "parameters": {
            "type": "object",
            "properties": {"name_or_path": {"type": "string"}},
            "required": ["name_or_path"],
        },
    },
    "kill_process": {
        "fn": _kill_process, "dangerous": True,
        "description": "Kill a process by name or PID",
        "parameters": {
            "type": "object",
            "properties": {"name_or_pid": {"type": "string", "description": "Process name or numeric PID"}},
            "required": ["name_or_pid"],
        },
    },
    "install_package": {
        "fn": _install_package, "dangerous": True,
        "description": "Install a package via pip, npm, or yarn",
        "parameters": {
            "type": "object",
            "properties": {
                "package": {"type": "string"},
                "manager": {"type": "string", "enum": ["pip", "npm", "yarn"], "default": "pip"},
                "cwd":     {"type": "string", "default": None},
            },
            "required": ["package"],
        },
    },
    "download_file": {
        "fn": _download_file, "dangerous": True,
        "description": "Download a file from a URL and save it locally",
        "parameters": {
            "type": "object",
            "properties": {
                "url":  {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["url", "path"],
        },
    },

    # ── Search ────────────────────────────────────────────────────────────────
    "search_in_files": {
        "fn": _search_in_files, "dangerous": False,
        "description": "Search for text in project files with line numbers (like grep). Returns file:line: content matches.",
        "parameters": {
            "type": "object",
            "properties": {
                "query":          {"type": "string",  "description": "Text to search for"},
                "path":           {"type": "string",  "description": "Directory to search in", "default": "."},
                "file_pattern":   {"type": "string",  "description": "File filter e.g. '*.py', '*.js', '*'", "default": "*"},
                "case_sensitive": {"type": "boolean", "default": False},
                "max_results":    {"type": "integer", "default": 50},
            },
            "required": ["query"],
        },
    },

    # ── Git ───────────────────────────────────────────────────────────────────
    "git_status": {
        "fn": _git_status, "dangerous": False,
        "description": "Show git working tree status (modified, added, deleted files)",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Project root path", "default": "."}},
            "required": [],
        },
    },
    "git_diff": {
        "fn": _git_diff, "dangerous": False,
        "description": "Show git diff for the project or a specific file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "file": {"type": "string", "description": "Specific file path (optional)", "default": ""},
            },
            "required": [],
        },
    },
    "git_commit": {
        "fn": _git_commit, "dangerous": True,
        "description": "Stage all changes and create a git commit",
        "parameters": {
            "type": "object",
            "properties": {
                "path":    {"type": "string",  "description": "Project root"},
                "message": {"type": "string",  "description": "Commit message"},
                "add_all": {"type": "boolean", "default": True},
            },
            "required": ["path", "message"],
        },
    },
    "git_log": {
        "fn": _git_log, "dangerous": False,
        "description": "Show recent git commit history",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "n":    {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },

    # ── UI / task tracking (safe) ─────────────────────────────────────────────
    "todo_write": {
        "fn": _todo_write, "dangerous": False,
        "description": (
            "Update your task list shown in the IDE. Call this at the START of any multi-step task "
            "to show the plan, and call again to mark steps complete.\n"
            "tasks: list of {task: str, status: 'pending'|'in_progress'|'done'|'error'}"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task":   {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "done", "error"]},
                        },
                        "required": ["task", "status"],
                    },
                    "description": "List of tasks with their current status",
                }
            },
            "required": ["tasks"],
        },
    },

    # ── Eyes & Hands (system control) ─────────────────────────────────────────
    "screenshot": {
        "fn": _screenshot, "dangerous": False,
        "description": "Take a screenshot of the entire screen. Returns the file path to the saved PNG image. Use this to see what is currently on the screen.",
        "parameters": {
            "type": "object",
            "properties": {
                "save_path": {"type": "string", "description": "Optional path to save PNG. Auto-generated if not specified."},
            },
            "required": [],
        },
    },
    "mouse_click": {
        "fn": _mouse_click, "dangerous": True,
        "description": "Click the mouse at screen coordinates. Requires pyautogui.",
        "parameters": {
            "type": "object",
            "properties": {
                "x":      {"type": "integer", "description": "X screen coordinate"},
                "y":      {"type": "integer", "description": "Y screen coordinate"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "double": {"type": "boolean", "default": False},
            },
            "required": ["x", "y"],
        },
    },
    "mouse_move": {
        "fn": _mouse_move, "dangerous": False,
        "description": "Move mouse cursor to screen coordinates without clicking.",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["x", "y"],
        },
    },
    "type_text": {
        "fn": _type_text, "dangerous": True,
        "description": "Type text at the current cursor position using keyboard simulation.",
        "parameters": {
            "type": "object",
            "properties": {
                "text":     {"type": "string", "description": "Text to type"},
                "interval": {"type": "number", "default": 0.02, "description": "Delay between keystrokes in seconds"},
            },
            "required": ["text"],
        },
    },
    "press_key": {
        "fn": _press_key, "dangerous": True,
        "description": "Press a keyboard key or key combination. Examples: 'enter', 'ctrl+s', 'alt+f4', 'ctrl+c'.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name or combination with '+' separator"},
            },
            "required": ["key"],
        },
    },
    "scroll": {
        "fn": _scroll, "dangerous": False,
        "description": "Scroll the mouse wheel up or down.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"], "default": "down"},
                "amount":    {"type": "integer", "default": 3},
            },
            "required": [],
        },
    },
    "get_screen_info": {
        "fn": _get_screen_info, "dangerous": False,
        "description": "Get screen resolution and current mouse cursor position.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "search_system": {
        "fn": _search_system, "dangerous": False,
        "description": "Search the ENTIRE system (all drives) for files by name. Use this when the user asks to find something on their computer. E.g. find all .sln files, find games, find documents.",
        "parameters": {
            "type": "object",
            "properties": {
                "query":       {"type": "string", "description": "Filename fragment to search for (case-insensitive)"},
                "search_path": {"type": "string", "description": "Specific path to search in (optional, defaults to all drives)"},
                "file_type":   {"type": "string", "description": "File extension filter e.g. 'exe', 'sln', 'py'"},
                "max_results": {"type": "integer", "default": 100},
            },
            "required": ["query"],
        },
    },
    "list_windows": {
        "fn": _list_windows, "dangerous": False,
        "description": "List all open windows and running applications with their titles.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


# ─── Public helpers ───────────────────────────────────────────────────────────

_STREAMING_TOOLS = {"run_command", "run_python", "install_package"}

def execute_tool(name: str, args: dict, stream_cb=None) -> dict:
    """Execute a tool by name. For run_command/run_python, stream_cb(line) is called per output line."""
    tool = TOOLS.get(name)
    if not tool:
        return {"success": False, "error": f"Unknown tool: {name}"}
    try:
        clean = {k: v for k, v in (args or {}).items() if v is not None}
        if stream_cb and name in _STREAMING_TOOLS:
            return tool["fn"](**clean, stream_cb=stream_cb)
        return tool["fn"](**clean)
    except Exception as e:
        return {"success": False, "error": str(e)}


def is_dangerous(name: str) -> bool:
    return TOOLS.get(name, {}).get("dangerous", True)


def tool_schemas_anthropic(names: list) -> list:
    return [
        {"name": n, "description": TOOLS[n]["description"], "input_schema": TOOLS[n]["parameters"]}
        for n in names if n in TOOLS
    ]


def tool_schemas_openai(names: list) -> list:
    return [
        {"type": "function", "function": {
            "name": n, "description": TOOLS[n]["description"], "parameters": TOOLS[n]["parameters"]
        }}
        for n in names if n in TOOLS
    ]


ALL_TOOL_NAMES  = list(TOOLS.keys())
SAFE_TOOL_NAMES = [n for n, t in TOOLS.items() if not t["dangerous"]]
