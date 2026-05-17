"""
AXIS OS — Full Release Script
==============================
Один скрипт що робить все:
  1. Збирає додаток (PyInstaller x3)
  2. Збирає інсталятор (Inno Setup)
  3. Пакує ZIP з вихідним кодом
  4. Git commit + tag + push
  5. Створює GitHub реліз і завантажує assets

Використання:
  python release.py 1.1.0
  python release.py          ← запитає версію

При першому запуску попросить GitHub токен.
"""

import os, sys, re, json, ssl, time, shutil, zipfile, http.client
import subprocess, urllib.request, urllib.error, urllib.parse
from pathlib import Path

# ── UTF-8 консоль ────────────────────────────────────────────────────────────
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT     = Path(__file__).parent
DIST     = ROOT / "dist"
CFG_FILE = ROOT / "data" / "release.cfg"

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ── SSL (антивірус) ──────────────────────────────────────────────────────────
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode    = ssl.CERT_NONE

# ═══════════════════════════════════════
#  УТИЛІТИ
# ═══════════════════════════════════════

def header(text):
    print()
    print("─" * 52)
    print(f"  {text}")
    print("─" * 52)

def ok(text):   print(f"  ✅ {text}")
def info(text): print(f"  ·  {text}")
def err(text):  print(f"  ❌ {text}")

def run(cmd, check=True) -> bool:
    """Запускає команду, виводить результат, повертає успіх."""
    info(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=str(ROOT))
    if check and result.returncode != 0:
        err(f"Команда завершилась з помилкою: {cmd}")
        return False
    return result.returncode == 0

# ═══════════════════════════════════════
#  КОНФІГ
# ═══════════════════════════════════════

def load_cfg() -> dict:
    if CFG_FILE.exists():
        try:
            return json.loads(CFG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_cfg(cfg: dict):
    CFG_FILE.parent.mkdir(exist_ok=True)
    CFG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def setup_cfg(cfg: dict) -> dict:
    header("Перший запуск — налаштування")
    if not cfg.get("repo"):
        cfg["repo"] = input("  GitHub репо (напр. helgaslop/-AXIS-OS): ").strip()
    if not cfg.get("token"):
        print()
        print("  Потрібен GitHub Personal Access Token:")
        print("  github.com → Settings → Developer settings")
        print("  → Personal access tokens → Tokens (classic)")
        print("  → Generate new token → scope: repo → Generate")
        print()
        cfg["token"] = input("  Встав токен: ").strip()
    save_cfg(cfg)
    ok("Збережено у data/release.cfg")
    return cfg

# ═══════════════════════════════════════
#  ВЕРСІЯ
# ═══════════════════════════════════════

def read_version() -> str:
    try:
        return (ROOT / "version.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return "1.0.0"

def write_version(v: str):
    (ROOT / "version.txt").write_text(v, encoding="utf-8")
    ok(f"version.txt → {v}")

def update_setup_iss(v: str):
    iss = ROOT / "setup.iss"
    if not iss.exists():
        return
    text = iss.read_text(encoding="utf-8")
    text = re.sub(r"(AppVersion=)[\d.]+",                      rf"\g<1>{v}", text)
    text = re.sub(r"(AppVerName=AXIS OS )[\d.]+",               rf"\g<1>{v}", text)
    text = re.sub(r"(OutputBaseFilename=AXIS_OS_Setup_)[\d.]+", rf"\g<1>{v}", text)
    iss.write_text(text, encoding="utf-8")
    ok(f"setup.iss → v{v}")

# ═══════════════════════════════════════
#  ЗБІРКА
# ═══════════════════════════════════════

def clean_build():
    for folder in ["dist/AXIS_OS", "dist/AXIS_Sphere", "dist/AXIS_IDE",
                   "build/AXIS_OS", "build/AXIS_Sphere", "build/AXIS_IDE"]:
        p = ROOT / folder
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    ok("Стара збірка видалена")

def build_pyinstaller() -> bool:
    specs = [
        ("axis_os.spec",     "AXIS Panel"),
        ("axis_sphere.spec", "AXIS Sphere"),
        ("axis_ide.spec",    "AXIS IDE"),
    ]
    for spec, name in specs:
        if not (ROOT / spec).exists():
            info(f"{spec} не знайдено — пропускаємо")
            continue
        info(f"Збираю {name}...")
        if not run(f"pyinstaller {spec} --noconfirm"):
            return False
        ok(f"{name} зібрано")
    return True

def merge_dist() -> bool:
    """Збирає Sphere і IDE в папку AXIS_OS (як у build.bat)."""
    axis_dir = DIST / "AXIS_OS"
    if not axis_dir.exists():
        err("dist/AXIS_OS не знайдено після збірки")
        return False

    for name in ["AXIS_Sphere", "AXIS_IDE"]:
        src_exe = DIST / name / f"{name}.exe"
        src_int = DIST / name / "_internal"
        if src_exe.exists():
            shutil.copy2(src_exe, axis_dir / f"{name}.exe")
        if src_int.exists():
            shutil.copytree(src_int, axis_dir / "_internal",
                            dirs_exist_ok=True)

    # Assets і data
    for folder in ["assets", "data"]:
        src = ROOT / folder
        if src.exists():
            shutil.copytree(src, axis_dir / folder, dirs_exist_ok=True)

    shutil.copy2(ROOT / "version.txt", axis_dir / "version.txt")
    ok("dist/AXIS_OS зібрано")
    return True

def build_installer(version: str) -> Path | None:
    """Запускає Inno Setup якщо iscc доступний."""
    iscc = shutil.which("iscc")
    if not iscc:
        # Пробуємо стандартний шлях
        for p in [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
        ]:
            if os.path.exists(p):
                iscc = p
                break
    if not iscc:
        info("Inno Setup не знайдено — інсталятор пропускаємо")
        return None

    info("Збираю інсталятор (Inno Setup)...")
    result = subprocess.run([iscc, str(ROOT / "setup.iss")],
                            cwd=str(ROOT), capture_output=True)
    if result.returncode != 0:
        err("Inno Setup завершився з помилкою")
        info(result.stdout.decode("utf-8", errors="replace")[-500:])
        return None

    installer = DIST / f"AXIS_OS_Setup_{version}.exe"
    if installer.exists():
        mb = installer.stat().st_size / 1024 / 1024
        ok(f"Інсталятор: {installer.name}  ({mb:.0f} MB)")
        return installer

    # Шукаємо будь-який Setup*.exe
    for f in DIST.glob("AXIS_OS_Setup*.exe"):
        ok(f"Інсталятор: {f.name}")
        return f
    return None

# ═══════════════════════════════════════
#  ZIP ВИХІДНОГО КОДУ
# ═══════════════════════════════════════

SKIP_DIRS = {
    "data", "logs", "dist", "build", "__pycache__",
    ".git", ".github", ".claude",
    "venv", ".venv", "env", "node_modules",
    ".idea", ".vscode",
}
INCLUDE_EXTS = {
    ".py", ".pyw", ".html", ".js", ".css", ".json",
    ".ico", ".png", ".jpg", ".svg", ".gif",
    ".txt", ".md", ".bat", ".sh", ".iss", ".spec",
}
SKIP_FILES = {
    "release.py", "make_release.py",
    ".gitignore", ".gitattributes", ".env",
    "Thumbs.db", ".DS_Store",
    "build_log.txt", "build_log.json", "release.cfg",
}
DATA_WHITELIST = {"icon_panel.ico", "icon_sphere.ico", "icon_ide.ico"}

def _include(rel: Path) -> bool:
    parts = rel.parts
    for p in parts[:-1]:
        if p in SKIP_DIRS:
            return p == "data" and parts[-1] in DATA_WHITELIST
    name = parts[-1] if parts else ""
    if name in SKIP_FILES or name.startswith("."):
        return False
    return Path(name).suffix.lower() in INCLUDE_EXTS

def make_zip(version: str) -> Path:
    DIST.mkdir(exist_ok=True)
    out = DIST / f"AXIS_OS_{version}.zip"
    if out.exists():
        out.unlink()
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as zf:
        for src in sorted(ROOT.rglob("*")):
            if src.is_file():
                rel = src.relative_to(ROOT)
                if _include(rel):
                    zf.write(src, Path("AXIS_OS") / rel)
                    count += 1
    mb = out.stat().st_size / 1024 / 1024
    ok(f"ZIP: {out.name}  ({count} файлів, {mb:.1f} MB)")
    return out

# ═══════════════════════════════════════
#  GIT
# ═══════════════════════════════════════

def git_push(version: str):
    tag = f"v{version}"
    run("git add .",         check=False)
    run(f'git commit -m "{tag}" --allow-empty', check=False)
    run(f"git tag -f {tag}", check=False)
    run("git push",          check=False)
    run(f"git push origin {tag} --force", check=False)
    ok("Git: pushed")

# ═══════════════════════════════════════
#  GITHUB API
# ═══════════════════════════════════════

def _gh(method, url, token, data=None, extra_headers=None) -> dict:
    headers = {
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github.v3+json",
        "User-Agent":    "AXIS-OS/release",
    }
    if extra_headers:
        headers.update(extra_headers)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_SSL, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub {e.code}: {e.read().decode('utf-8','replace')[:300]}")

def _upload(upload_url, token, path: Path):
    """Стрімінговий upload з прогресом — не вантажить файл у RAM."""
    import http.client, urllib.parse

    url    = upload_url.split("{")[0] + f"?name={urllib.parse.quote(path.name)}"
    parsed = urllib.parse.urlparse(url)
    size   = path.stat().st_size
    mb     = size / 1024 / 1024
    info(f"Завантажую {path.name}  ({mb:.1f} MB)...")

    # Стрімінг через http.client щоб не тримати 371 МБ в пам'яті
    conn = http.client.HTTPSConnection(
        parsed.netloc, timeout=7200, context=_SSL   # 2 години максимум
    )
    path_qs = parsed.path + ("?" + parsed.query if parsed.query else "")
    conn.putrequest("POST", path_qs)
    conn.putheader("Authorization",  f"token {token}")
    conn.putheader("Content-Type",   "application/octet-stream")
    conn.putheader("Content-Length", str(size))
    conn.putheader("User-Agent",     "AXIS-OS/release")
    conn.endheaders()

    sent       = 0
    chunk_size = 1024 * 1024   # 1 МБ чанки
    last_pct   = -1
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            conn.send(chunk)
            sent += len(chunk)
            pct = int(sent * 100 / size)
            if pct // 10 != last_pct // 10:   # кожні 10%
                last_pct = pct
                print(f"\r    {pct}%  ({sent/1024/1024:.0f}/{mb:.0f} MB)", end="", flush=True)

    print()
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", errors="replace")
    if resp.status not in (200, 201):
        raise RuntimeError(f"Upload HTTP {resp.status}: {body[:300]}")
    dl_url = json.loads(body).get("browser_download_url", "")
    ok(f"Завантажено → {dl_url}")

def publish(repo, token, version, assets: list[Path]) -> str:
    tag = f"v{version}"
    api = f"https://api.github.com/repos/{repo}/releases"

    # Видаляємо старий реліз з таким тегом якщо є
    try:
        old = _gh("GET", f"{api}/tags/{tag}", token)
        if old.get("id"):
            info(f"Видаляю старий реліз {tag}...")
            _gh("DELETE", f"{api}/{old['id']}", token)
    except Exception:
        pass

    info(f"Створюю реліз {tag}...")
    rel = _gh("POST", api, token, {
        "tag_name": tag, "name": f"AXIS OS {tag}",
        "body": f"AXIS OS {tag}", "draft": False, "prerelease": False,
    })
    upload_url  = rel["upload_url"]
    release_url = rel["html_url"]
    ok(f"Реліз: {release_url}")

    for asset in assets:
        if asset and asset.exists():
            _upload(upload_url, token, asset)

    return release_url

# ═══════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════

def main():
    cur = read_version()

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║       AXIS OS  —  Full Release Script            ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"\n  Поточна версія : {cur}")

    # Версія
    new_ver = (sys.argv[1].strip().lstrip("v") if len(sys.argv) > 1
               else input(f"\n  Нова версія [{cur}]: ").strip().lstrip("v") or cur)
    parts = new_ver.split(".")
    if not (2 <= len(parts) <= 4) or not all(p.isdigit() for p in parts):
        err(f"Невірний формат '{new_ver}'")
        sys.exit(1)

    # Конфіг
    cfg = load_cfg()
    if not cfg.get("token") or not cfg.get("repo"):
        cfg = setup_cfg(cfg)

    # Що збираємо?
    print()
    print("  Що робити:")
    print("  [1] Повна збірка  (PyInstaller + Inno Setup + ZIP + GitHub)")
    print("  [2] Тільки ZIP + GitHub  (без PyInstaller, швидко)")
    choice = input("\n  Вибір [1/2]: ").strip() or "1"

    # ── КРОК 1: Версія ──────────────────────────────────────────────────────
    header("1/5  Версія")
    write_version(new_ver)
    update_setup_iss(new_ver)

    installer = None

    if choice == "1":
        # ── КРОК 2: PyInstaller ─────────────────────────────────────────────
        header("2/5  Збірка PyInstaller")

        # Перевіряємо чи є PyInstaller
        if not shutil.which("pyinstaller"):
            info("Встановлюю PyInstaller...")
            run("pip install pyinstaller")

        clean_build()
        if not build_pyinstaller():
            err("Збірка PyInstaller не вдалась")
            sys.exit(1)
        if not merge_dist():
            err("Злиття dist не вдалось")
            sys.exit(1)

        # ── КРОК 3: Інсталятор ──────────────────────────────────────────────
        header("3/5  Інсталятор (Inno Setup)")
        installer = build_installer(new_ver)
    else:
        # Шукаємо вже зібраний інсталятор
        installer = None
        for f in DIST.glob("AXIS_OS_Setup*.exe"):
            installer = f
            info(f"Знайдено існуючий інсталятор: {f.name}")
            break

    # ── КРОК 4: ZIP ─────────────────────────────────────────────────────────
    header("4/5  ZIP вихідного коду")
    zip_out = make_zip(new_ver)

    # ── КРОК 5: Git + GitHub ─────────────────────────────────────────────────
    header("5/5  Git + GitHub")
    git_push(new_ver)

    # Перевіряємо токен перед відправкою
    token = cfg.get("token", "")
    try:
        token.encode("latin-1")   # HTTP headers мають бути latin-1
    except (UnicodeEncodeError, UnicodeDecodeError):
        err("Токен містить недопустимі символи — відкрий data/release.cfg і встав правильний ghp_... токен")
        sys.exit(1)
    if not token.startswith(("ghp_", "github_pat_")) or len(token) < 20:
        err(f"Невірний токен: '{token[:30]}...' — має починатись з ghp_ або github_pat_")
        sys.exit(1)

    assets = [a for a in [installer, zip_out] if a and a.exists()]
    try:
        url = publish(cfg["repo"], cfg["token"], new_ver, assets)
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║                  ГОТОВО! ✅                      ║")
        print("╚══════════════════════════════════════════════════╝")
        print(f"\n  Реліз: {url}")
        if installer:
            print()
            print("  Користувачі побачать сповіщення про оновлення")
            print("  при наступному запуску AXIS OS ✨")
    except Exception as e:
        err(f"GitHub: {e}")
        print()
        print("  Assets збережені локально:")
        for a in assets:
            print(f"    {a}")

if __name__ == "__main__":
    main()
