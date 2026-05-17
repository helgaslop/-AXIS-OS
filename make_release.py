"""
AXIS OS — Make Release (source patch)
======================================
Збирає лише вихідні файли (.py / .html / .js / .css / .json шаблони тощо)
у маленький ZIP (~2-5 MB) без жодних бінарників та скомпільованих файлів.

Використання:
  python make_release.py 1.1.0        ← задаєш версію
  python make_release.py              ← запитає нову версію

Що потрапляє до ZIP:
  *.py, *.html, *.js, *.css, *.json (крім data/), *.ico, *.png, *.svg,
  *.txt (version.txt, requirements.txt), *.md, *.bat (launch/run/setup)

Що НЕ потрапляє:
  data/           — конфіг та команди користувача
  logs/           — логи
  dist/           — зкомпільований exe
  build/          — тимчасові файли PyInstaller
  __pycache__/    — байткод
  .git/           — git
  venv/ / .venv/  — virtual env

Структура ZIP:
  AXIS_OS/
    version.txt
    main.py
    aivon_sphere.py
    core/...
    gui/...
    assets/...
    ...
"""

import os
import sys
import zipfile
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
DIST = ROOT / "dist"

# ── Папки що НІКОЛИ не потрапляють в оновлення ─────────────────────────────
SKIP_DIRS = {
    "data",           # конфіг та команди користувача — НЕ перезаписуємо
    "logs",           # логи
    "dist",           # зкомпільований exe
    "build",          # PyInstaller cache
    "__pycache__",    # Python bytecode
    ".git", ".github", ".claude",
    "venv", ".venv", "env", ".env",
    "node_modules",
    ".idea", ".vscode",
}

# ── Розширення що включаємо ─────────────────────────────────────────────────
INCLUDE_EXTS = {
    # Код
    ".py", ".pyw",
    # UI
    ".html", ".js", ".css",
    # Дані (шаблони, не конфіги користувача)
    ".json",
    # Ресурси
    ".ico", ".png", ".jpg", ".svg", ".gif", ".webp",
    # Документи
    ".txt", ".md", ".rst",
    # Скрипти запуску
    ".bat", ".sh", ".iss",
    # Spec файли PyInstaller (опційно)
    ".spec",
}

# ── Конкретні файли що ПРОПУСКАЄМО ─────────────────────────────────────────
SKIP_FILES = {
    "make_release.py",   # сам скрипт — не потрібен кінцевому користувачу
    ".gitignore",
    ".gitattributes",
    ".env",
    "Thumbs.db",
    ".DS_Store",
    "build_log.txt",
    "build_log.json",
}

# ── Конкретні файли data/ що ВСЕ ОДНО включаємо (іконки, шаблони) ──────────
DATA_WHITELIST = {
    "icon_panel.ico",
    "icon_sphere.ico",
    "icon_ide.ico",
    "splash.png",
    "logo.png",
}


def should_include(rel: Path) -> bool:
    parts = rel.parts

    # Пропускаємо заборонені папки на будь-якому рівні
    for p in parts[:-1]:
        if p in SKIP_DIRS:
            # Але дозволяємо конкретні файли з data/
            if p == "data" and parts[-1] in DATA_WHITELIST:
                return True
            return False

    name = parts[-1] if parts else ""

    # Пропускаємо конкретні файли
    if name in SKIP_FILES:
        return False
    if name.startswith("."):
        return False

    # Перевіряємо розширення
    ext = Path(name).suffix.lower()
    return ext in INCLUDE_EXTS


def read_version() -> str:
    try:
        return (ROOT / "version.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return "1.0.0"


def write_version(v: str):
    (ROOT / "version.txt").write_text(v.strip(), encoding="utf-8")
    print(f"  version.txt  ->  {v.strip()}")


def make_zip(version: str) -> Path:
    DIST.mkdir(exist_ok=True)
    out = DIST / f"AXIS_OS_{version}.zip"
    if out.exists():
        out.unlink()

    included = []
    skipped_size = 0

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as zf:
        for src in sorted(ROOT.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(ROOT)
            if not should_include(rel):
                skipped_size += src.stat().st_size
                continue
            arcname = Path("AXIS_OS") / rel
            zf.write(src, arcname)
            included.append(str(rel))

    size_kb = out.stat().st_size / 1024
    size_mb = size_kb / 1024
    size_str = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{size_kb:.0f} KB"

    print(f"\n  Включено файлів : {len(included)}")
    print(f"  Розмір архіву  : {size_str}")

    # Показуємо перелік включених файлів
    print("\n  Файли в архіві:")
    by_folder: dict[str, list[str]] = {}
    for f in included:
        folder = str(Path(f).parent) if Path(f).parent != Path(".") else "(корінь)"
        by_folder.setdefault(folder, []).append(Path(f).name)
    for folder, files in sorted(by_folder.items()):
        print(f"    {folder}/  ({len(files)} файлів)")

    return out


def main():
    cur = read_version()
    print("=" * 48)
    print("   AXIS OS Release Builder (source patch)")
    print("=" * 48)
    print(f"\n  Поточна версія : {cur}")
    print(f"  Папка проекту  : {ROOT}")

    # Нова версія
    if len(sys.argv) > 1:
        new_ver = sys.argv[1].strip().lstrip("v")
    else:
        print()
        new_ver = input(f"  Нова версія [{cur}]: ").strip().lstrip("v")
        if not new_ver:
            new_ver = cur

    # Валідація формату X.Y.Z
    parts = new_ver.split(".")
    if not (2 <= len(parts) <= 4) or not all(p.isdigit() for p in parts):
        print(f"\n  ПОМИЛКА: невірний формат '{new_ver}'  (потрібно X.Y або X.Y.Z)")
        sys.exit(1)

    # Оновлюємо version.txt
    print()
    write_version(new_ver)

    # Пакуємо
    print("\n  Пакую...")
    out = make_zip(new_ver)

    print(f"\n  Архів: {out}")
    print()
    print("=" * 48)
    print("  ДАЛІ:")
    print("=" * 48)
    print()
    print("  1. git add .")
    print(f"  2. git commit -m \"v{new_ver}\"")
    print(f"  3. git tag v{new_ver}")
    print("  4. git push && git push --tags")
    print()
    print("  5. GitHub -> Releases -> Draft a new release")
    print(f"     Tag    : v{new_ver}")
    print(f"     Asset  : {out.name}  (перетягни файл)")
    print("     Publish release")
    print()
    print("  6. AXIS OS -> Налаштування -> Оновлення")
    print("     GitHub repo: твій_логін/AXIS-OS")
    print("     [Перевірити на GitHub]")
    print()


if __name__ == "__main__":
    main()
