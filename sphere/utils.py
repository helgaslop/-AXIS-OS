# -*- coding: utf-8 -*-
"""
sphere/utils.py  –  Загальні утиліти (перенесено з aivon_sphere.py рядки 150–748)

Вміст:
  - _open_mic_stream, _to_mono        (PyAudio helpers)
  - get_pc_context                    (PC info for AI prompt)
  - pc_search_files, pc_running_apps  (file/process search)
  - _get_steam_path, get_steam_games, find_steam_game  (Steam)
  - _get_memory_file, load_memory, save_memory_fact, query_memory
  - _get_watch_history_file, load_watch_history, save_watch_entry,
    get_most_watched, get_vlc_recent, _open_video_fullscreen
  - build_wake_lists
"""

import os
import sys
import re
import json
import time
import struct as _struct
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

# ── Runtime flag helpers (set by aivon_sphere.py at startup) ─────────────────
# Lazily imported to avoid circular deps.
def _get_psutil():
    try:
        import psutil as _ps
        return _ps
    except ImportError:
        return None

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ── Video helpers ─────────────────────────────────────────────────────────────
_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
                     ".m4v", ".mpg", ".mpeg", ".webm", ".ts"}

_STREAMING_SITES = {
    "netflix": "Netflix",
    "youtube": "YouTube",
    "disney":  "Disney+",
    "hbo":     "HBO Max",
    "prime":   "Amazon Prime",
    "kinopoisk": "Кінопошук",
    "megogo":  "Megogo",
    "toloka":  "Толока",
}

_WORK_APPS = {
    "code.exe", "code", "pycharm64.exe", "pycharm", "idea64.exe",
    "webstorm64.exe", "devenv.exe", "sublime_text.exe",
    "notepad++.exe", "atom.exe", "cursor.exe",
    "python.exe", "node.exe", "java.exe",
}


# ─── PyAudio mic helper ───────────────────────────────────────────────────────

def _open_mic_stream(pa, rate: int, chunk_frames: int):
    """Open the default input stream with auto-detected channel count.

    Returns (stream, channels).  Tries mono first, then stereo.
    Raises RuntimeError if the mic cannot be opened.
    """
    for channels in (1, 2):
        try:
            import pyaudio
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                frames_per_buffer=chunk_frames,
            )
            return stream, channels
        except Exception:
            continue
    raise RuntimeError("Cannot open microphone input stream")


def _to_mono(pcm_bytes: bytes, channels: int) -> bytes:
    """Convert interleaved stereo PCM-16 to mono by averaging channels.
    If already mono, returns unchanged.
    """
    if channels == 1:
        return pcm_bytes
    n = len(pcm_bytes) // 2          # total int16 samples
    samples = _struct.unpack(f"{n}h", pcm_bytes)
    mono = [
        (samples[i] + samples[i + 1]) // 2
        for i in range(0, n, 2)
    ]
    return _struct.pack(f"{len(mono)}h", *mono)


# ─── PC Context helper ────────────────────────────────────────────────────────

def get_pc_context() -> str:
    """Збирає поточний стан ПК для передачі в AI системний prompt."""
    lines = [f"Поточний час: {datetime.now().strftime('%H:%M %d.%m.%Y')}"]
    try:
        import platform
        lines.append(f"ОС: {platform.system()} {platform.release()}, ПК: {platform.node()}")
        lines.append(f"Користувач: {os.environ.get('USERNAME') or os.environ.get('USER', '?')}")
    except Exception:
        pass
    _psutil = _get_psutil()
    if _psutil:
        try:
            cpu = _psutil.cpu_percent(interval=0.2)
            ram = _psutil.virtual_memory()
            lines.append(f"CPU: {cpu:.0f}%, RAM: {ram.percent:.0f}% "
                         f"({ram.used//1024**2}MB з {ram.total//1024**2}MB)")
            disks = []
            for dp in _psutil.disk_partitions(all=False):
                try:
                    u = _psutil.disk_usage(dp.mountpoint)
                    disks.append(f"{dp.device} {u.free//1024**3}GB вільно")
                except Exception:
                    pass
            if disks:
                lines.append("Диски: " + "; ".join(disks))
            # Top CPU processes
            procs = []
            for p in _psutil.process_iter(['name', 'cpu_percent']):
                try:
                    c = p.info['cpu_percent'] or 0
                    if c > 1.0:
                        procs.append((c, p.info['name']))
                except Exception:
                    pass
            procs.sort(reverse=True)
            if procs:
                lines.append("Активні процеси: " +
                             ", ".join(f"{n}({c:.0f}%)" for c, n in procs[:6]))
        except Exception:
            pass
    # Active window title (Windows)
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value:
                lines.append(f"Активне вікно: {buf.value[:80]}")
        except Exception:
            pass
    return "\n".join(lines)


# ─── PC File/Process search helper ───────────────────────────────────────────

def pc_search_files(query: str, max_results: int = 8) -> str:
    """Шукає файли за назвою у домашніх папках користувача."""
    q = query.strip().lower()
    if not q:
        return "Не вказано що шукати"
    found = []
    home = Path.home()
    search_dirs = [
        home / "Desktop", home / "Documents", home / "Downloads",
        home / "Pictures",  home / "Videos", home / "Music", home,
    ]
    for base in search_dirs:
        if not base.exists():
            continue
        try:
            for f in base.rglob("*"):
                if q in f.name.lower():
                    found.append(str(f))
                if len(found) >= max_results:
                    break
        except Exception:
            pass
        if len(found) >= max_results:
            break
    if not found:
        return f"Файлів за запитом «{query}» не знайдено"
    if len(found) == 1:
        return f"Знайшов: {found[0]}"
    names = [Path(p).name for p in found[:5]]
    suffix = f" (+{len(found)-5} ще)" if len(found) > 5 else ""
    return f"Знайшов {len(found)} файл(ів): " + ", ".join(names) + suffix


def pc_running_apps() -> str:
    """Повертає список запущених помітних застосунків."""
    _psutil = _get_psutil()
    if not _psutil:
        # Fallback: tasklist
        if sys.platform == "win32":
            try:
                out = subprocess.check_output(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    creationflags=_NO_WINDOW, timeout=3
                ).decode(errors="replace")
                import csv, io
                names = []
                for row in csv.reader(io.StringIO(out)):
                    if len(row) >= 1:
                        n = row[0].strip('"')
                        if n and n not in names and not n.lower().startswith("svchost"):
                            names.append(n)
                return "Запущено: " + ", ".join(names[:15])
            except Exception:
                return "Не вдалося отримати список процесів"
        return "psutil не встановлено"
    try:
        SKIP = {"system idle process", "system", "registry", "smss.exe",
                "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
                "svchost.exe", "dwm.exe", "conhost.exe"}
        apps = []
        for p in _psutil.process_iter(['name', 'memory_percent']):
            try:
                n = (p.info['name'] or '').lower()
                if n and n not in SKIP and p.info['memory_percent'] > 0.1:
                    apps.append(p.info['name'])
            except Exception:
                pass
        apps = list(dict.fromkeys(apps))[:18]
        return "Запущено: " + ", ".join(apps)
    except Exception:
        return "Помилка отримання процесів"


# ─── Steam integration ────────────────────────────────────────────────────────

def _get_steam_path() -> "Path | None":
    """Шукає шлях до Steam (реєстр → відомі шляхи)."""
    if sys.platform == "win32":
        try:
            import winreg
            for reg_path in [
                r"SOFTWARE\WOW6432Node\Valve\Steam",
                r"SOFTWARE\Valve\Steam",
            ]:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                    p = Path(winreg.QueryValueEx(key, "InstallPath")[0])
                    if p.exists():
                        return p
                except Exception:
                    pass
        except Exception:
            pass
    # Common fallback paths
    candidates = [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def get_steam_games(max_games: int = 50) -> list:
    """Повертає список встановлених Steam-ігор, відсортованих по даті гри."""
    steam_path = _get_steam_path()
    if not steam_path:
        return []
    # Collect all steamapps dirs (including library folders)
    steamapps_dirs = [steam_path / "steamapps"]
    try:
        lf_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
        if lf_vdf.exists():
            content = lf_vdf.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'"path"\s+"([^"]+)"', content):
                p = Path(m.group(1).replace("\\\\", "\\")) / "steamapps"
                if p.exists():
                    steamapps_dirs.append(p)
    except Exception:
        pass
    games = []
    seen_ids = set()
    for sdir in steamapps_dirs:
        try:
            for acf in sdir.glob("appmanifest_*.acf"):
                try:
                    txt = acf.read_text(encoding="utf-8", errors="replace")
                    name_m  = re.search(r'"name"\s+"([^"]+)"', txt)
                    appid_m = re.search(r'"appid"\s+"(\d+)"', txt)
                    lp_m    = re.search(r'"LastPlayed"\s+"(\d+)"', txt)
                    pt_m    = re.search(r'"playtime_forever"\s+"(\d+)"', txt)
                    if name_m and appid_m:
                        aid = appid_m.group(1)
                        if aid in seen_ids:
                            continue
                        seen_ids.add(aid)
                        games.append({
                            "name":        name_m.group(1),
                            "appid":       aid,
                            "last_played": int(lp_m.group(1))  if lp_m  else 0,
                            "playtime_h":  int(pt_m.group(1)) // 60 if pt_m else 0,
                        })
                except Exception:
                    pass
        except Exception:
            pass
    games.sort(key=lambda g: g["last_played"], reverse=True)
    return games[:max_games]


def find_steam_game(query: str, games: "list | None" = None) -> "dict | None":
    """Шукає гру в бібліотеці за назвою (fuzzy)."""
    if games is None:
        games = get_steam_games()
    q = query.lower().strip()
    # Exact match first
    for g in games:
        if q == g["name"].lower():
            return g
    # Starts-with
    for g in games:
        if g["name"].lower().startswith(q):
            return g
    # Contains
    for g in games:
        if q in g["name"].lower():
            return g
    # Word overlap
    q_words = set(q.split())
    for g in games:
        g_words = set(g["name"].lower().split())
        if q_words & g_words:
            return g
    return None


# ─── Long-term memory ─────────────────────────────────────────────────────────

_MEMORY_FILE: "Path | None" = None

def _get_memory_file() -> Path:
    global _MEMORY_FILE
    if _MEMORY_FILE is None:
        _appdata3 = os.environ.get("APPDATA") or str(Path.home())
        _MEMORY_FILE = Path(_appdata3) / "AXIS OS" / "sphere_memory.json"
    return _MEMORY_FILE

def load_memory() -> dict:
    try:
        f = _get_memory_file()
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_memory_fact(key: str, value: str):
    mem = load_memory()
    mem[key.lower()[:60]] = {
        "value": value,
        "saved": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    try:
        f = _get_memory_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Memory] save error: {e}")

def query_memory(query: str) -> "str | None":
    """Шукає факт у пам'яті за ключовими словами."""
    mem = load_memory()
    q = query.lower()
    # Direct key match
    for k, v in mem.items():
        if q in k or k in q:
            return v["value"]
    # Word overlap
    q_words = set(q.split())
    for k, v in mem.items():
        if q_words & set(k.split()):
            return v["value"]
    return None


# ─── Watch History ────────────────────────────────────────────────────────────

WATCH_HISTORY_FILE = None   # set lazily

def _get_watch_history_file() -> Path:
    global WATCH_HISTORY_FILE
    if WATCH_HISTORY_FILE is None:
        _appdata2 = os.environ.get("APPDATA") or str(Path.home())
        WATCH_HISTORY_FILE = Path(_appdata2) / "AXIS OS" / "watch_history.json"
    return WATCH_HISTORY_FILE


def load_watch_history() -> list:
    try:
        f = _get_watch_history_file()
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def save_watch_entry(title: str, path_or_url: str = "", source: str = ""):
    """Записує перегляд у watch_history.json."""
    try:
        history = load_watch_history()
        now = int(time.time())
        for entry in history:
            if entry.get("title", "").lower() == title.lower():
                entry["count"]        = entry.get("count", 1) + 1
                entry["last_watched"] = now
                if path_or_url:
                    entry["path"] = path_or_url
                break
        else:
            history.append({
                "title":        title,
                "path":         path_or_url,
                "source":       source,
                "count":        1,
                "last_watched": now,
            })
        history.sort(key=lambda e: e.get("last_watched", 0), reverse=True)
        wf = _get_watch_history_file()
        wf.parent.mkdir(parents=True, exist_ok=True)
        wf.write_text(
            json.dumps(history[:100], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Watch] save error: {e}")


def get_most_watched() -> list:
    """Повертає топ-5 найчастіше/нещодавно переглянутих."""
    h = load_watch_history()
    h.sort(key=lambda e: (e.get("count", 0), e.get("last_watched", 0)), reverse=True)
    return h[:5]


def get_vlc_recent() -> list:
    """Читає нещодавні файли з VLC."""
    results = []
    vlc_ini = Path(os.environ.get("APPDATA", "")) / "vlc" / "vlc-qt-interface.ini"
    if not vlc_ini.exists():
        return results
    try:
        content = vlc_ini.read_text(encoding="utf-8", errors="replace")
        section = False
        for line in content.splitlines():
            if "[RecentsMRL]" in line:
                section = True
                continue
            if section and line.startswith("["):
                break
            if section and "=" in line:
                _, _, val = line.partition("=")
                val = val.strip()
                if val.startswith("file:///"):
                    p = Path(val[8:].replace("/", os.sep))
                    if p.exists() and p.suffix.lower() in _VIDEO_EXTENSIONS:
                        results.append({"title": p.stem, "path": str(p), "source": "vlc"})
                elif val.startswith("file://"):
                    p = Path(val[7:])
                    if p.exists() and p.suffix.lower() in _VIDEO_EXTENSIONS:
                        results.append({"title": p.stem, "path": str(p), "source": "vlc"})
    except Exception:
        pass
    return results[:5]


def _open_video_fullscreen(path_or_url: str):
    """Відкриває відео у VLC або стандартному плеєрі в повноекранному режимі."""
    if path_or_url.startswith("http"):
        webbrowser.open(path_or_url)
        return
    p = str(path_or_url)
    # Try VLC with fullscreen flag
    vlc_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        "vlc",
    ]
    for vlc in vlc_paths:
        try:
            subprocess.Popen([vlc, "--fullscreen", p], creationflags=_NO_WINDOW)
            return
        except Exception:
            pass
    # Fallback: os.startfile
    try:
        os.startfile(p)
    except Exception:
        subprocess.Popen(p, shell=True, creationflags=_NO_WINDOW)


# ─── Wake-word builder ────────────────────────────────────────────────────────

def build_wake_lists(name: str):
    """Генерує WAKE_GREETING та WAKE_QUICK з будь-якого імені.
    Генерує фонетичні варіанти для надійного розпізнавання Google STT.
    """
    n = name.strip().lower()
    n4 = n[:4] if len(n) >= 4 else n

    greeting = [
        # Ukrainian greetings
        f"привіт {n}", f"привіт {n}е", f"привіт {n}!",
        f"привет {n}", f"привет {n}е",
        # English greetings
        f"hey {n}", f"окей {n}", f"hi {n}", f"hello {n}",
        # Short prefix
        f"привіт {n4}", f"привет {n4}",
        # "ok / okay" variants
        f"окей {n}", f"ок {n}", f"ok {n}",
    ]

    quick = [n, n + "е", n4]

    # Add phonetic transliteration variants for "Aivon"-style names
    translit_map = {
        "aivon": ["айвон", "айван", "evan", "ivan", "ayvon", "ai von"],
        "aivone": ["айвоне"],
        "aivo": ["айво", "aivo"],
        "jarvis": ["джарвіс", "джарвис", "жарвіс"],
        "axis": ["аксис", "аксіс", "ексіс"],
    }
    for word, variants in translit_map.items():
        if word in [n, n4, n + "е"]:
            quick.extend(variants)
            for v in variants:
                greeting.extend([f"привіт {v}", f"hey {v}", f"окей {v}"])

    # De-duplicate while preserving order
    seen: set = set()
    greeting_dedup = [x for x in greeting if not (x in seen or seen.add(x))]
    seen.clear()
    quick_dedup = [x for x in quick if not (x in seen or seen.add(x))]
    return greeting_dedup, quick_dedup
