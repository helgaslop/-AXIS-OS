"""Dashboard, Process Manager, Pomodoro, Quick Notes handlers."""
import json
import os
import threading
import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

_NO_WINDOW = 0
try:
    import subprocess, sys
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
except Exception:
    pass

# ── Path helpers ───────────────────────────────────────────────────────────────
def _data_dir():
    try:
        from core.paths import USER_DATA_DIR
        return str(USER_DATA_DIR)
    except Exception:
        return os.path.join(os.path.dirname(__file__), "..", "..", "data")

def _data_path(name):
    return os.path.join(_data_dir(), name)


# ── Process category mapping ───────────────────────────────────────────────────
_PROC_CATEGORIES = {
    "browsers": {
        "chrome", "firefox", "msedge", "opera", "brave", "safari",
        "iexplore", "chromium", "vivaldi", "edge"
    },
    "games": {
        "steam", "epicgameslauncher", "gog galaxy", "ubisoft connect",
        "leagueoflegends", "csgo", "dota2", "fortnite", "minecraft",
        "riotclientservices", "galaxyclient"
    },
    "dev": {
        "code", "pycharm64", "idea64", "webstorm64", "rider64", "clion64",
        "devenv", "notepad++", "sublime_text", "atom", "vim", "nvim",
        "git", "python", "node", "npm", "cargo", "rustc", "gcc", "clang",
        "docker", "wsl", "ubuntu", "bash", "powershell", "pwsh", "cmd",
        "conhost", "windowsterminal", "wt"
    },
    "system": {
        "system", "system idle process", "registry", "smss", "csrss",
        "wininit", "winlogon", "services", "lsass", "svchost", "explorer",
        "dwm", "taskeng", "taskhostw", "runtimebroker", "searchindexer",
        "searchhost", "sihost", "ctfmon", "spoolsv", "audiodg",
        "fontdrvhost", "lsaiso", "memory compression", "secure system"
    },
}

def _categorize(name: str) -> str:
    n = name.lower().replace(".exe", "")
    for cat, names in _PROC_CATEGORIES.items():
        if n in names:
            return cat
    return "other"


class DashboardHandlerMixin:
    # ── Process Manager ────────────────────────────────────────────────────────
    def _get_processes(self, _):
        threading.Thread(target=self._get_processes_worker, daemon=True).start()

    def _get_processes_worker(self):
        if not HAS_PSUTIL:
            self.push_to_js.emit("processes_data", json.dumps({"error": "psutil not installed"}))
            return
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
            try:
                mi = p.info.get("memory_info")
                ram_mb = round((mi.rss if mi else 0) / 1024 / 1024, 1)
                name = p.info.get("name") or "?"
                procs.append({
                    "pid":      p.info.get("pid", 0),
                    "name":     name,
                    "cpu":      round(p.info.get("cpu_percent") or 0, 1),
                    "ram":      ram_mb,
                    "status":   p.info.get("status", "?"),
                    "category": _categorize(name),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # Sort by CPU desc by default
        procs.sort(key=lambda x: x["cpu"], reverse=True)
        self.push_to_js.emit("processes_data", json.dumps(procs))

    def _kill_process(self, p: dict):
        pid = p.get("pid")
        if not pid:
            return
        try:
            if HAS_PSUTIL:
                proc = psutil.Process(int(pid))
                proc.kill()
                self.push_to_js.emit("toast", json.dumps({"msg": f"✓ Процес {pid} завершено"}))
            else:
                import subprocess, sys
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   creationflags=_NO_WINDOW, capture_output=True)
                else:
                    import os
                    os.kill(int(pid), 9)
                self.push_to_js.emit("toast", json.dumps({"msg": f"✓ Процес {pid} завершено"}))
        except Exception as e:
            self.push_to_js.emit("toast", json.dumps({"msg": f"⚠ Не вдалось завершити {pid}: {e}"}))

    # ── Pomodoro Stats ─────────────────────────────────────────────────────────
    def _save_pomodoro_stat(self, p: dict):
        path = _data_path("pomodoro_stats.json")
        try:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    stats = json.load(f)
            except Exception:
                stats = {}

            today = datetime.date.today().isoformat()
            day = stats.get(today, {"count": 0, "focus_minutes": 0})
            day["count"] = day.get("count", 0) + 1
            day["focus_minutes"] = day.get("focus_minutes", 0) + p.get("minutes", 25)
            stats[today] = day

            with open(path, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)

            self.push_to_js.emit("pomodoro_stats", json.dumps({"today": day, "all": stats}))
        except Exception as e:
            self.push_to_js.emit("toast", json.dumps({"msg": f"⚠ Pomodoro stat error: {e}"}))

    def _get_pomodoro_stats(self, _):
        path = _data_path("pomodoro_stats.json")
        try:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    stats = json.load(f)
            except Exception:
                stats = {}
            today = datetime.date.today().isoformat()
            day = stats.get(today, {"count": 0, "focus_minutes": 0})
            self.push_to_js.emit("pomodoro_stats", json.dumps({"today": day, "all": stats}))
        except Exception as e:
            self.push_to_js.emit("toast", json.dumps({"msg": f"⚠ {e}"}))

    # ── Quick Notes ────────────────────────────────────────────────────────────
    def _save_quick_notes(self, p: dict):
        path = _data_path("quick_notes.txt")
        try:
            text = p.get("text", "")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            self.push_to_js.emit("toast", json.dumps({"msg": f"⚠ Нотатки: {e}"}))

    def _get_quick_notes(self, _):
        path = _data_path("quick_notes.txt")
        try:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except FileNotFoundError:
                text = ""
            self.push_to_js.emit("quick_notes", json.dumps({"text": text}))
        except Exception as e:
            self.push_to_js.emit("quick_notes", json.dumps({"text": "", "error": str(e)}))
