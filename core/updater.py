"""AXIS OS — Auto-updater (local folder / network share + GitHub Releases)."""
import os
import sys
import json
import shutil
import subprocess
import threading
import tempfile
import zipfile
import urllib.request
import urllib.error
from pathlib import Path

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) \
          else Path(__file__).parent.parent


def _read_version(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8').strip()
    except Exception:
        return ''


def _ver_tuple(v: str):
    try:
        return tuple(int(x) for x in v.strip().lstrip('v').split('.'))
    except Exception:
        return (0,)


def get_current_version() -> str:
    return _read_version(APP_DIR / 'version.txt') or '1.0.0'


# ═══════════════════════════════════════════════════════════════
#  LOCAL FOLDER UPDATE  (old system, kept for compatibility)
# ═══════════════════════════════════════════════════════════════

def check_for_update(update_folder: str) -> dict | None:
    """
    Перевіряє папку update_folder на наявність нової версії.
    Повертає {'version': str, 'folder': str, 'installer': str|None}
    або None якщо оновлень немає.
    """
    if not update_folder or not os.path.isdir(update_folder):
        return None
    try:
        remote_ver = _read_version(Path(update_folder) / 'version.txt')
        if not remote_ver:
            return None
        cur = get_current_version()
        if _ver_tuple(remote_ver) <= _ver_tuple(cur):
            return None
        installer = None
        for f in Path(update_folder).glob('AXIS_OS_Setup*.exe'):
            installer = str(f)
            break
        return {'version': remote_ver, 'folder': update_folder,
                'installer': installer}
    except Exception:
        return None


def apply_update(update_info: dict, restart: bool = True):
    """
    Застосовує оновлення.
    Якщо є інсталятор — запускає його.
    Якщо є папка files/ — копіює файли поверх.
    """
    folder    = update_info['folder']
    installer = update_info.get('installer')

    if installer and os.path.exists(installer):
        subprocess.Popen([installer, '/SILENT', '/CLOSEAPPLICATIONS'],
                         creationflags=subprocess.DETACHED_PROCESS | _NO_WINDOW)
        if restart:
            sys.exit(0)
        return True

    files_dir = Path(folder) / 'files'
    if files_dir.is_dir():
        try:
            for src in files_dir.rglob('*'):
                rel  = src.relative_to(files_dir)
                dest = APP_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src.is_file():
                    shutil.copy2(str(src), str(dest))
            ver_src = Path(folder) / 'version.txt'
            if ver_src.exists():
                shutil.copy2(str(ver_src), str(APP_DIR / 'version.txt'))
            if restart:
                exe = str(APP_DIR / 'AXIS_OS.exe') \
                      if getattr(sys, 'frozen', False) else sys.executable
                args = [exe] if getattr(sys, 'frozen', False) \
                       else [exe, str(APP_DIR / 'main.py')]
                subprocess.Popen(args, creationflags=_NO_WINDOW)
                sys.exit(0)
            return True
        except Exception as e:
            print(f'[Updater] apply error: {e}')
            return False

    return False


# ═══════════════════════════════════════════════════════════════
#  GITHUB RELEASES UPDATE
# ═══════════════════════════════════════════════════════════════

GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
_SKIP_SSL  = True   # antivirus може підміняти сертифікат


def _gh_get(url: str) -> dict:
    """GET GitHub API з обходом SSL-перехоплення антивірусу."""
    import ssl
    ctx = ssl.create_default_context()
    if _SKIP_SSL:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url,
        headers={
            "Accept":     "application/vnd.github.v3+json",
            "User-Agent": "AXIS-OS/1.0",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub API HTTP {e.code}: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"GitHub API помилка: {e}")


def check_github_update(repo: str) -> dict | None:
    """
    Перевіряє GitHub Releases на наявність нової версії.
    repo — рядок 'owner/repo', напр. 'myname/AXIS-OS'

    Повертає:
      {
        'version':      '1.2.0',
        'tag':          'v1.2.0',
        'current':      '1.0.0',
        'release_url':  'https://github.com/.../releases/tag/v1.2.0',
        'body':         'Список змін...',
        'published_at': '2025-06-01T12:00:00Z',
        'assets': [
          {'name': 'AXIS_OS_1.2.0.zip', 'url': 'https://...', 'size': 12345678},
          ...
        ]
      }
    або None якщо версія актуальна.
    Може кинути RuntimeError якщо немає з'єднання.
    """
    repo = repo.strip().strip("/")
    if not repo or "/" not in repo:
        raise ValueError(f"Невірний формат репо: '{repo}'  (потрібно 'owner/repo')")

    data = _gh_get(GITHUB_API.format(repo=repo))

    tag = data.get("tag_name", "").strip()
    if not tag:
        raise RuntimeError("Реліз не містить tag_name")

    remote_ver = tag.lstrip("v")
    cur        = get_current_version()

    if _ver_tuple(remote_ver) <= _ver_tuple(cur):
        return None   # актуально

    assets = []
    for a in data.get("assets", []):
        assets.append({
            "name": a.get("name", ""),
            "url":  a.get("browser_download_url", ""),
            "size": a.get("size", 0),
        })

    return {
        "version":      remote_ver,
        "tag":          tag,
        "current":      cur,
        "release_url":  data.get("html_url", ""),
        "body":         data.get("body", "").strip()[:2000],
        "published_at": data.get("published_at", ""),
        "assets":       assets,
    }


def download_github_asset(url: str, on_progress=None) -> str:
    """
    Завантажує файл за URL у тимчасову папку.
    on_progress(downloaded_bytes, total_bytes) — опційний callback.
    Повертає шлях до завантаженого файлу.
    """
    import ssl
    ctx = ssl.create_default_context()
    if _SKIP_SSL:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={"User-Agent": "AXIS-OS/1.0"})
    tmp_dir  = tempfile.mkdtemp(prefix="axis_upd_")
    filename = url.split("/")[-1].split("?")[0] or "update.zip"
    dest     = os.path.join(tmp_dir, filename)

    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        total = int(r.headers.get("Content-Length", 0))
        done  = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if on_progress:
                    try:
                        on_progress(done, total)
                    except Exception:
                        pass

    return dest


def _run_status(on_status, status, label, pct=100):
    print(f"[Updater] {label}")
    if on_status:
        try:
            on_status(status, label, pct)
        except Exception:
            pass


def apply_installer_update(exe_path: str, on_status=None) -> bool:
    """
    Запускає Inno Setup інсталятор тихо (/SILENT).
    Використовується коли застосунок встановлений через інсталятор.
    """
    if not os.path.exists(exe_path):
        raise RuntimeError(f"Інсталятор не знайдено: {exe_path}")

    _run_status(on_status, "restarting", "🔧 Запускаю інсталятор оновлення...", 100)
    import time as _time
    _time.sleep(0.6)   # даємо UI отримати статус

    subprocess.Popen(
        [exe_path, '/SILENT', '/CLOSEAPPLICATIONS'],
        creationflags=subprocess.DETACHED_PROCESS | _NO_WINDOW
    )
    sys.exit(0)


def apply_github_update(zip_path: str, restart: bool = True,
                         on_status=None) -> bool:
    """
    Розпаковує zip і копіює файли поверх APP_DIR.

    on_status(status, label, pct) — колбек для UI прогресу:
      status: 'applying' | 'pip' | 'restarting' | 'error'

    Папки data/ та logs/ НЕ перезаписуються (конфіг користувача).
    Перезапуск через .bat щоб уникнути блокування запущеного .exe на Windows.
    """
    def _st(status, label, pct=100):
        _run_status(on_status, status, label, pct)

    try:
        _st("applying", "📂 Розпаковую архів...", 0)
        extract_dir = tempfile.mkdtemp(prefix="axis_ext_")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        # Визначаємо корінь (make_release.py кладе файли в AXIS_OS/)
        entries = list(Path(extract_dir).iterdir())
        root = entries[0] if len(entries) == 1 and entries[0].is_dir() \
               else Path(extract_dir)

        # Перевіряємо version.txt
        ver_file = root / "version.txt"
        if not ver_file.exists():
            raise RuntimeError("ZIP не містить version.txt — невірний формат архіву")

        new_ver = ver_file.read_text(encoding="utf-8").strip()

        # ── Копіюємо файли ────────────────────────────────────────────────────
        SKIP_ROOTS = {"data", "logs", "dist", "build", "__pycache__"}
        all_files = [f for f in root.rglob('*')
                     if f.is_file()
                     and (not f.relative_to(root).parts
                          or f.relative_to(root).parts[0] not in SKIP_ROOTS)
                     and f.name != "version.txt"]
        total = len(all_files) or 1
        copied = 0

        for src in all_files:
            rel  = src.relative_to(root)
            dest = APP_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(src), str(dest))
                copied += 1
            except PermissionError:
                print(f"[Updater] заблокований (пропущено): {rel}")
            pct = int(copied * 80 / total)   # 0-80%
            _st("applying", f"📂 Копіюю файли... {copied}/{total}", pct)

        # version.txt оновлюємо останнім
        shutil.copy2(str(ver_file), str(APP_DIR / 'version.txt'))
        _st("applying", f"✅ Скопійовано {copied} файлів  →  v{new_ver}", 80)

        # ── pip install нових пакетів ─────────────────────────────────────────
        req_file = APP_DIR / 'requirements.txt'
        if req_file.exists() and not getattr(sys, 'frozen', False):
            _st("pip", "📦 Встановлюю нові пакети...", 85)
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install",
                     "-r", str(req_file), "--quiet", "--exists-action", "i"],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    _st("pip", "📦 Пакети актуальні", 95)
                else:
                    _st("pip", f"📦 pip: {result.stderr[:120]}", 95)
            except Exception as e:
                _st("pip", f"📦 pip помилка (не критично): {e}", 95)

        # Прибираємо temp
        try:
            shutil.rmtree(extract_dir, ignore_errors=True)
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass

        if not restart:
            return True

        # ── Перезапуск ────────────────────────────────────────────────────────
        _st("restarting", "🔄 Перезапускаю AXIS OS...", 100)

        if getattr(sys, 'frozen', False):
            # Скомпільований .exe — чекаємо завершення через .bat
            exe_path = str(APP_DIR / 'AXIS_OS.exe')
            bat_path = str(APP_DIR / '_update_restart.bat')
            pid      = os.getpid()
            bat = (
                "@echo off\n"
                ":wait\n"
                f"tasklist /FI \"PID eq {pid}\" 2>nul | find \"{pid}\" >nul\n"
                f"if not errorlevel 1 ( timeout /t 1 /nobreak >nul & goto wait )\n"
                f"start \"\" \"{exe_path}\"\n"
                "del \"%~f0\"\n"
            )
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat)
            subprocess.Popen(
                ["cmd.exe", "/c", bat_path],
                creationflags=subprocess.DETACHED_PROCESS | _NO_WINDOW
            )
        else:
            # Запуск з вихідного коду
            subprocess.Popen(
                [sys.executable, str(APP_DIR / 'main.py')],
                creationflags=_NO_WINDOW
            )

        import time as _time
        _time.sleep(0.5)   # даємо час UI отримати статус "restarting"
        sys.exit(0)

    except Exception as e:
        print(f'[Updater] apply_github_update error: {e}')
        raise
