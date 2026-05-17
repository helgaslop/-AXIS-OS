"""
AXIS OS — Make Release + Auto-publish to GitHub
================================================
Збирає ZIP з вихідним кодом, перевіряє інсталятор,
автоматично створює GitHub реліз і завантажує assets.

Використання:
  python make_release.py 1.1.0   ← задаєш версію
  python make_release.py         ← запитає нову версію

При першому запуску попросить GitHub токен і збереже у data\release.cfg
(цей файл НЕ потрапляє у Git і НЕ у ZIP)
"""

import os, sys, re, json, ssl, zipfile, urllib.request, urllib.error
from pathlib import Path

# ── Windows console UTF-8 ───────────────────────────────────────────────────
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT      = Path(__file__).parent
DIST      = ROOT / "dist"
CFG_FILE  = ROOT / "data" / "release.cfg"   # токен і репо — НЕ в git

# ── SSL (обхід антивірусу) ───────────────────────────────────────────────────
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode    = ssl.CERT_NONE

# ═══════════════════════════════════════════════════════════════════════════════
#  КОНФІГУРАЦІЯ
# ═══════════════════════════════════════════════════════════════════════════════

def load_cfg() -> dict:
    if CFG_FILE.exists():
        try:
            return json.loads(CFG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_cfg(cfg: dict):
    CFG_FILE.parent.mkdir(exist_ok=True)
    CFG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False),
                        encoding="utf-8")

def setup_cfg(cfg: dict) -> dict:
    """Перший запуск — запитує токен і репо."""
    print()
    print("  Перший запуск — налаштування GitHub")
    print("  ─────────────────────────────────────")

    if not cfg.get("repo"):
        repo = input("  GitHub репо (напр. helgaslop/-AXIS-OS): ").strip()
        cfg["repo"] = repo

    if not cfg.get("token"):
        print()
        print("  Потрібен GitHub токен (Personal Access Token).")
        print("  Як отримати:")
        print("    github.com → Settings → Developer settings")
        print("    → Personal access tokens → Tokens (classic)")
        print("    → Generate new token → вибери: repo (повний)")
        print("    → Generate → скопіюй токен")
        print()
        token = input("  Встав токен: ").strip()
        cfg["token"] = token

    save_cfg(cfg)
    print("  Збережено у data/release.cfg  (не потрапляє в git)")
    return cfg

# ═══════════════════════════════════════════════════════════════════════════════
#  ФАЙЛИ ДЛЯ ZIP
# ═══════════════════════════════════════════════════════════════════════════════

SKIP_DIRS = {
    "data", "logs", "dist", "build", "__pycache__",
    ".git", ".github", ".claude",
    "venv", ".venv", "env", "node_modules",
    ".idea", ".vscode",
}
INCLUDE_EXTS = {
    ".py", ".pyw", ".html", ".js", ".css", ".json",
    ".ico", ".png", ".jpg", ".svg", ".gif", ".webp",
    ".txt", ".md", ".rst", ".bat", ".sh", ".iss", ".spec",
}
SKIP_FILES = {
    "make_release.py", ".gitignore", ".gitattributes",
    ".env", "Thumbs.db", ".DS_Store",
    "build_log.txt", "build_log.json", "release.cfg",
}
DATA_WHITELIST = {"icon_panel.ico", "icon_sphere.ico", "icon_ide.ico",
                  "splash.png", "logo.png"}

def should_include(rel: Path) -> bool:
    parts = rel.parts
    for p in parts[:-1]:
        if p in SKIP_DIRS:
            if p == "data" and parts[-1] in DATA_WHITELIST:
                return True
            return False
    name = parts[-1] if parts else ""
    if name in SKIP_FILES or name.startswith("."):
        return False
    return Path(name).suffix.lower() in INCLUDE_EXTS

def make_zip(version: str) -> Path:
    DIST.mkdir(exist_ok=True)
    out = DIST / f"AXIS_OS_{version}.zip"
    if out.exists():
        out.unlink()
    included = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as zf:
        for src in sorted(ROOT.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(ROOT)
            if not should_include(rel):
                continue
            zf.write(src, Path("AXIS_OS") / rel)
            included.append(str(rel))
    mb = out.stat().st_size / 1024 / 1024
    print(f"  ZIP: {out.name}  ({len(included)} файлів, {mb:.1f} MB)")
    return out

# ═══════════════════════════════════════════════════════════════════════════════
#  ВЕРСІЯ / SETUP.ISS
# ═══════════════════════════════════════════════════════════════════════════════

def read_version() -> str:
    try:
        return (ROOT / "version.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return "1.0.0"

def write_version(v: str):
    (ROOT / "version.txt").write_text(v.strip(), encoding="utf-8")
    print(f"  version.txt  ->  {v}")

def update_setup_iss(v: str):
    iss = ROOT / "setup.iss"
    if not iss.exists():
        return
    text = iss.read_text(encoding="utf-8")
    text = re.sub(r"(AppVersion=)[\d.]+",              rf"\g<1>{v}", text)
    text = re.sub(r"(AppVerName=AXIS OS )[\d.]+",       rf"\g<1>{v}", text)
    text = re.sub(r"(OutputBaseFilename=AXIS_OS_Setup_)[\d.]+", rf"\g<1>{v}", text)
    iss.write_text(text, encoding="utf-8")
    print(f"  setup.iss    ->  v{v}")

def find_installer(v: str) -> Path | None:
    for c in [DIST / f"AXIS_OS_Setup_{v}.exe", DIST / "AXIS_OS_Setup.exe"]:
        if c.exists():
            return c
    for f in DIST.glob("AXIS_OS_Setup*.exe"):
        return f
    return None

# ═══════════════════════════════════════════════════════════════════════════════
#  GITHUB API
# ═══════════════════════════════════════════════════════════════════════════════

def _gh(method: str, url: str, token: str, data=None,
        extra_headers: dict | None = None) -> dict:
    headers = {
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github.v3+json",
        "User-Agent":    "AXIS-OS/make_release",
    }
    if extra_headers:
        headers.update(extra_headers)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub {e.code}: {body_err[:300]}")

def _upload_asset(upload_url: str, token: str, path: Path):
    """Завантажує файл як реліз-asset."""
    # upload_url вигляду: https://uploads.github.com/repos/.../assets{?name,label}
    base_url = upload_url.split("{")[0]
    url      = f"{base_url}?name={path.name}"
    size     = path.stat().st_size
    headers  = {
        "Authorization": f"token {token}",
        "Content-Type":  "application/octet-stream",
        "User-Agent":    "AXIS-OS/make_release",
    }
    print(f"  Завантажую {path.name}  ({size/1024/1024:.1f} MB)...", end="", flush=True)
    req = urllib.request.Request(url, data=path.read_bytes(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=300) as r:
            result = json.loads(r.read())
            print(f"  ✅ {result.get('browser_download_url','')}")
            return result
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Upload {e.code}: {body_err[:300]}")

def publish_release(repo: str, token: str, version: str,
                    assets: list[Path], notes: str = "") -> str:
    """
    Створює GitHub реліз і завантажує assets.
    Повертає URL релізу.
    """
    tag     = f"v{version}"
    api_url = f"https://api.github.com/repos/{repo}/releases"

    # Перевіряємо чи реліз з таким тегом вже існує
    existing = _gh("GET", f"{api_url}/tags/{tag}", token)
    if existing.get("id"):
        print(f"  Реліз {tag} вже існує — видаляю...")
        _gh("DELETE", f"{api_url}/{existing['id']}", token)

    # Створюємо новий реліз
    print(f"  Створюю реліз {tag}...")
    rel = _gh("POST", api_url, token, {
        "tag_name":   tag,
        "name":       f"AXIS OS {tag}",
        "body":       notes or f"AXIS OS {tag}",
        "draft":      False,
        "prerelease": False,
    })
    upload_url  = rel["upload_url"]
    release_url = rel["html_url"]
    print(f"  Реліз створено: {release_url}")

    # Завантажуємо кожен файл
    for asset in assets:
        if asset and asset.exists():
            _upload_asset(upload_url, token, asset)

    return release_url

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    cur = read_version()
    print("=" * 52)
    print("   AXIS OS Release Builder  +  GitHub Publish")
    print("=" * 52)
    print(f"\n  Поточна версія : {cur}")
    print(f"  Папка проекту  : {ROOT}")

    # ── Нова версія ──────────────────────────────────────────────────────────
    new_ver = (sys.argv[1].strip().lstrip("v") if len(sys.argv) > 1
               else input(f"\n  Нова версія [{cur}]: ").strip().lstrip("v") or cur)
    parts = new_ver.split(".")
    if not (2 <= len(parts) <= 4) or not all(p.isdigit() for p in parts):
        print(f"\n  ПОМИЛКА: невірний формат '{new_ver}'")
        sys.exit(1)

    # ── Конфіг GitHub ────────────────────────────────────────────────────────
    cfg = load_cfg()
    if not cfg.get("token") or not cfg.get("repo"):
        cfg = setup_cfg(cfg)

    # ── Оновлюємо версії ─────────────────────────────────────────────────────
    print()
    write_version(new_ver)
    update_setup_iss(new_ver)

    # ── Git commit + tag ─────────────────────────────────────────────────────
    print()
    print("  Git...")
    os.system('git add .')
    os.system(f'git commit -m "v{new_ver}" --allow-empty')
    os.system(f'git tag -f v{new_ver}')
    os.system('git push')
    os.system(f'git push origin v{new_ver} --force')
    print("  Git: готово")

    # ── ZIP вихідного коду ───────────────────────────────────────────────────
    print()
    print("  Пакую вихідний код...")
    zip_out   = make_zip(new_ver)
    installer = find_installer(new_ver)

    if installer:
        mb = installer.stat().st_size / 1024 / 1024
        print(f"  EXE: {installer.name}  ({mb:.0f} MB)")
    else:
        print("  EXE: не знайдено (запусти build.bat спочатку)")

    # ── Завантажуємо на GitHub ────────────────────────────────────────────────
    print()
    print("  Публікую на GitHub...")
    assets = [a for a in [installer, zip_out] if a and a.exists()]
    try:
        url = publish_release(cfg["repo"], cfg["token"], new_ver, assets)
        print()
        print("=" * 52)
        print("  ГОТОВО!")
        print("=" * 52)
        print(f"\n  Реліз: {url}")
        if installer:
            print(f"\n  Користувачі побачать оновлення автоматично")
            print(f"  при наступному запуску AXIS OS")
        else:
            print(f"\n  Завантажено ZIP (без інсталятора)")
            print(f"  Для .exe оновлень — запусти build.bat потім знову цей скрипт")
    except Exception as e:
        print(f"\n  ПОМИЛКА GitHub: {e}")
        print(f"\n  Assets збережені локально:")
        for a in assets:
            print(f"    {a}")
        print(f"\n  Завантаж вручну на: github.com/{cfg['repo']}/releases")

if __name__ == "__main__":
    main()
