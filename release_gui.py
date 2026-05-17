"""
AXIS OS — Release GUI Builder
==============================
Графічний інтерфейс для збірки та публікації релізу.
Запуск: python release_gui.py
"""

import os, sys, re, json, ssl, shutil, zipfile, subprocess
import urllib.request, urllib.error, urllib.parse
from pathlib import Path


from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup,
    QProgressBar, QTextEdit, QFrame, QDialog, QDialogButtonBox,
    QFormLayout, QSizePolicy, QScrollArea,
)
from PyQt6.QtCore  import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui   import QFont, QTextCursor, QIcon, QColor

# ── Paths ─────────────────────────────────────────────────────────────────────
# When running as .exe (frozen) → ROOT = folder where the .exe lives
# When running as script        → ROOT = folder of the .py file
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).parent

DIST     = ROOT / "dist"
CFG_FILE = ROOT / "data" / "release.cfg"
NO_WIN   = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#0d0f1a"
PANEL    = "#13162a"
CARD     = "#1a1d2e"
BORDER   = "#252840"
ACCENT   = "#6366f1"
GREEN    = "#22c55e"
YELLOW   = "#f59e0b"
RED      = "#ef4444"
TEXT     = "#e2e8f0"
MUTED    = "#64748b"

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG helpers
# ══════════════════════════════════════════════════════════════════════════════

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

def read_version() -> str:
    try:
        return (ROOT / "version.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return "1.0.0"

# ══════════════════════════════════════════════════════════════════════════════
#  WORKER THREAD
# ══════════════════════════════════════════════════════════════════════════════

class Worker(QThread):
    sig_log   = pyqtSignal(str, str)      # (text, level)
    sig_step  = pyqtSignal(str, int, str) # (step_id, percent, status_text)
    sig_done  = pyqtSignal(str)           # release URL
    sig_fail  = pyqtSignal(str)           # error message

    def __init__(self, version: str, mode: str, cfg: dict):
        super().__init__()
        self.version = version
        self.mode    = mode   # "full" | "zip"
        self.cfg     = cfg
        self._stop   = False

    def stop(self):
        self._stop = True

    # ── internal helpers ──────────────────────────────────────────────────────

    def _log(self, text: str, level: str = "info"):
        self.sig_log.emit(text, level)

    def _step(self, sid: str, pct: int, txt: str = ""):
        self.sig_step.emit(sid, pct, txt)

    def _popen_stream(self, cmd, sid: str, p0: int, p1: int) -> bool:
        """Run a command, stream stdout→log, fake incremental progress."""
        if isinstance(cmd, str):
            self._log(f"$ {cmd}", "cmd")
        else:
            self._log("$ " + " ".join(str(c) for c in cmd), "cmd")

        proc = subprocess.Popen(
            cmd, shell=isinstance(cmd, str), cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        lines = 0
        for raw in iter(proc.stdout.readline, b""):
            if self._stop:
                proc.kill(); return False
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                self._log(line, "sub")
                lines += 1
                approx = min(p0 + int((p1 - p0) * min(lines / 200, 0.9)), p1 - 1)
                self._step(sid, approx, "")
        proc.wait()
        return proc.returncode == 0

    # ── main ─────────────────────────────────────────────────────────────────

    def run(self):
        try:
            self._release()
        except Exception as ex:
            import traceback
            self._log(traceback.format_exc(), "err")
            self.sig_fail.emit(str(ex))

    def _release(self):
        ver = self.version
        cfg = self.cfg

        # ─── 1. VERSION ───────────────────────────────────────────────────────
        self._log("━━━ Версія ━━━", "head")
        self._step("version", 0, "Оновлення...")
        (ROOT / "version.txt").write_text(ver, encoding="utf-8")
        self._log(f"version.txt → {ver}", "ok")
        iss = ROOT / "setup.iss"
        if iss.exists():
            txt = iss.read_text(encoding="utf-8")
            txt = re.sub(r"(AppVersion=)[\d.]+",                      rf"\g<1>{ver}", txt)
            txt = re.sub(r"(AppVerName=AXIS OS )[\d.]+",               rf"\g<1>{ver}", txt)
            txt = re.sub(r"(OutputBaseFilename=AXIS_OS_Setup_)[\d.]+", rf"\g<1>{ver}", txt)
            iss.write_text(txt, encoding="utf-8")
            self._log(f"setup.iss → v{ver}", "ok")
        self._step("version", 100, "✓")

        installer = None

        # ─── 2. PYINSTALLER (full only) ───────────────────────────────────────
        if self.mode == "full":
            self._log("━━━ PyInstaller ━━━", "head")
            self._step("build", 0, "Очищення...")
            for d in ["dist/AXIS_OS","dist/AXIS_Sphere","dist/AXIS_IDE",
                      "build/AXIS_OS","build/AXIS_Sphere","build/AXIS_IDE"]:
                p = ROOT / d
                if p.exists():
                    shutil.rmtree(p, ignore_errors=True)
            self._log("Стара збірка видалена", "ok")

            specs = [(s, n) for s, n in [
                ("axis_os.spec","AXIS Panel"),
                ("axis_sphere.spec","AXIS Sphere"),
                ("axis_ide.spec","AXIS IDE"),
            ] if (ROOT / s).exists()]

            for i, (spec, name) in enumerate(specs):
                p0 = int(i * 70 / len(specs))
                p1 = int((i+1) * 70 / len(specs))
                self._step("build", p0, f"{name}...")
                if not self._popen_stream(
                    f"pyinstaller {spec} --noconfirm", "build", p0, p1
                ):
                    raise RuntimeError(f"PyInstaller помилка: {spec}")
                self._log(f"✓ {name} зібрано", "ok")

            # merge
            self._step("build", 75, "Об'єднання...")
            axis_dir = DIST / "AXIS_OS"
            if axis_dir.exists():
                for name in ["AXIS_Sphere", "AXIS_IDE"]:
                    exe = DIST / name / f"{name}.exe"
                    idir = DIST / name / "_internal"
                    if exe.exists():
                        shutil.copy2(exe, axis_dir / f"{name}.exe")
                    if idir.exists():
                        shutil.copytree(idir, axis_dir / "_internal", dirs_exist_ok=True)
                for folder in ["assets", "data"]:
                    src = ROOT / folder
                    if src.exists():
                        shutil.copytree(src, axis_dir / folder, dirs_exist_ok=True)
                shutil.copy2(ROOT / "version.txt", axis_dir / "version.txt")
                self._log("dist/AXIS_OS зібрано", "ok")
            self._step("build", 100, "✓")

            # ─── 3. INNO SETUP ────────────────────────────────────────────────
            self._log("━━━ Inno Setup ━━━", "head")
            self._step("installer", 0, "Пошук iscc...")
            iscc = shutil.which("iscc")
            for p in [r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                      r"C:\Program Files\Inno Setup 6\ISCC.exe"]:
                if not iscc and os.path.exists(p):
                    iscc = p; break

            if iscc:
                ok = self._popen_stream([iscc, str(ROOT / "setup.iss")],
                                        "installer", 5, 95)
                if ok:
                    installer = DIST / f"AXIS_OS_Setup_{ver}.exe"
                    if not (installer and installer.exists()):
                        installer = next(DIST.glob("AXIS_OS_Setup*.exe"), None)
                    if installer:
                        mb = installer.stat().st_size / 1024 / 1024
                        self._log(f"Інсталятор: {installer.name}  ({mb:.0f} MB)", "ok")
                    else:
                        self._log("Інсталятор не знайдено", "err")
                else:
                    self._log("Inno Setup завершився з помилкою", "err")
            else:
                self._log("Inno Setup не знайдено — пропускаємо", "info")
            self._step("installer", 100, installer and "✓" or "пропущено")
        else:
            installer = next(DIST.glob("AXIS_OS_Setup*.exe"), None)
            if installer:
                self._log(f"Знайдено інсталятор: {installer.name}", "info")

        # ─── 4. ZIP ───────────────────────────────────────────────────────────
        self._log("━━━ ZIP ━━━", "head")
        self._step("zip", 0, "Пакування...")
        zip_out = self._make_zip(ver)
        self._step("zip", 100, "✓")

        # ─── 5. GIT ───────────────────────────────────────────────────────────
        self._log("━━━ Git ━━━", "head")
        self._step("git", 0, "git add...")
        tag = f"v{ver}"
        for cmd in [
            "git add .",
            f'git commit -m "{tag}" --allow-empty',
            f"git tag -f {tag}",
            "git push",
            f"git push origin {tag} --force",
        ]:
            self._log(f"$ {cmd}", "cmd")
            r = subprocess.run(cmd, shell=True, cwd=str(ROOT),
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.stdout.strip(): self._log(r.stdout.strip(), "sub")
            if r.stderr.strip(): self._log(r.stderr.strip(), "sub")
        self._step("git", 100, "✓")
        self._log("Git: готово", "ok")

        # ─── 6. GITHUB RELEASE ────────────────────────────────────────────────
        self._log("━━━ GitHub Release ━━━", "head")
        self._step("upload", 0, "Створення релізу...")
        release_url, upload_url = self._create_release(cfg["repo"], cfg["token"], ver)
        self._log(f"Реліз: {release_url}", "ok")

        assets = [a for a in [installer, zip_out] if a and a.exists()]
        n = len(assets)
        for i, asset in enumerate(assets):
            self._log(f"Завантажую {asset.name}...", "info")
            self._upload(upload_url, cfg["token"], asset,
                         int(i * 90 / n), int((i+1) * 90 / n))

        self._step("upload", 100, "✓")
        self.sig_done.emit(release_url)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _make_zip(self, ver: str) -> Path:
        SKIP = {"data","logs","dist","build","__pycache__",".git",".github",
                ".claude","venv",".venv","env","node_modules",".idea",".vscode"}
        EXTS = {".py",".pyw",".html",".js",".css",".json",".ico",".png",
                ".jpg",".svg",".gif",".txt",".md",".bat",".sh",".iss",".spec"}
        SKIP_F = {"release.py","release_gui.py","make_release.py",
                  ".gitignore",".env","Thumbs.db","release.cfg"}
        WL = {"icon_panel.ico","icon_sphere.ico","icon_ide.ico"}

        def _ok(rel: Path) -> bool:
            parts = rel.parts
            for p in parts[:-1]:
                if p in SKIP:
                    return p == "data" and parts[-1] in WL
            nm = parts[-1] if parts else ""
            if nm in SKIP_F or nm.startswith("."): return False
            return Path(nm).suffix.lower() in EXTS

        DIST.mkdir(exist_ok=True)
        out = DIST / f"AXIS_OS_{ver}.zip"
        if out.exists(): out.unlink()
        cnt = 0
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=7) as zf:
            for src in sorted(ROOT.rglob("*")):
                if src.is_file():
                    rel = src.relative_to(ROOT)
                    if _ok(rel):
                        zf.write(src, Path("AXIS_OS") / rel)
                        cnt += 1
        mb = out.stat().st_size / 1024 / 1024
        self._log(f"ZIP: {out.name}  ({cnt} файлів, {mb:.1f} MB)", "ok")
        return out

    def _gh(self, method, url, token, data=None):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        hdrs = {"Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AXIS-OS/release-gui"}
        body = json.dumps(data).encode() if data is not None else None
        if body: hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"GitHub {e.code}: {e.read().decode('utf-8','replace')[:300]}")

    def _create_release(self, repo, token, ver):
        tag = f"v{ver}"
        api = f"https://api.github.com/repos/{repo}/releases"
        try:
            old = self._gh("GET", f"{api}/tags/{tag}", token)
            if old.get("id"):
                self._log(f"Видаляю старий реліз {tag}...", "info")
                self._gh("DELETE", f"{api}/{old['id']}", token)
        except Exception:
            pass
        rel = self._gh("POST", api, token, {
            "tag_name": tag, "name": f"AXIS OS {tag}",
            "body": f"AXIS OS {tag}", "draft": False, "prerelease": False,
        })
        return rel["html_url"], rel["upload_url"]

    def _upload(self, upload_url: str, token: str, path: Path,
                step_start: int, step_end: int):
        url = upload_url.split("{")[0] + f"?name={urllib.parse.quote(path.name)}"

        curl = shutil.which("curl") or r"C:\Windows\System32\curl.exe"
        if os.path.exists(curl):
            cmd = [curl,
                   "-X", "POST",
                   "-H", f"Authorization: token {token}",
                   "-H", "Content-Type: application/octet-stream",
                   "-H", "User-Agent: AXIS-OS/release-gui",
                   "--data-binary", f"@{path}",
                   "--ssl-no-revoke",
                   "--connect-timeout", "60",
                   "-m", "7200",
                   url]
            self._log(f"$ curl ... {path.name}", "cmd")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, cwd=str(ROOT))
            total_mb = path.stat().st_size / 1024 / 1024
            while True:
                if self._stop: proc.kill(); return
                line = proc.stderr.readline()
                if not line: break
                line_s = line.decode("utf-8", errors="replace").strip()
                if line_s:
                    parts = line_s.split()
                    if len(parts) >= 5:
                        try:
                            up_pct = int(parts[4])
                            if 0 <= up_pct <= 100:
                                mapped = step_start + int(
                                    (step_end - step_start) * up_pct / 100)
                                done_mb = total_mb * up_pct / 100
                                self._step("upload", mapped,
                                           f"{up_pct}%  ({done_mb:.0f}/{total_mb:.0f} MB)")
                        except (ValueError, IndexError):
                            pass
            proc.wait()
            if proc.returncode == 0:
                self._log(f"✓ {path.name} завантажено", "ok")
            else:
                out = proc.stdout.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"curl помилка {proc.returncode}: {out[-200:]}")
            return

        # fallback: requests
        try:
            import requests as _req, urllib3
            urllib3.disable_warnings()
            total = path.stat().st_size
            sent  = [0]
            def _gen():
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(256 * 1024)
                        if not chunk: break
                        sent[0] += len(chunk)
                        pct = int(sent[0] * 100 / total)
                        mapped = step_start + int((step_end - step_start) * pct / 100)
                        self._step("upload", mapped,
                                   f"{pct}%  ({sent[0]/1024/1024:.0f}/{total/1024/1024:.0f} MB)")
                        yield chunk
            hdrs = {"Authorization": f"token {token}",
                    "Content-Type": "application/octet-stream",
                    "User-Agent": "AXIS-OS/release-gui",
                    "Content-Length": str(total)}
            r = _req.post(url, data=_gen(), headers=hdrs, verify=False, timeout=7200)
            if r.status_code not in (200, 201):
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            self._log(f"✓ {path.name} завантажено", "ok")
        except ImportError:
            raise RuntimeError("Встанови requests: pip install requests")


# ══════════════════════════════════════════════════════════════════════════════
#  STEP ROW WIDGET
# ══════════════════════════════════════════════════════════════════════════════

class StepRow(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: transparent;")

        h = QHBoxLayout(self)
        h.setContentsMargins(12, 6, 12, 6)
        h.setSpacing(10)

        self._ico = QLabel("○")
        self._ico.setFixedWidth(18)
        self._ico.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ico.setStyleSheet(f"color: {MUTED};")
        h.addWidget(self._ico)

        self._lbl = QLabel(label)
        self._lbl.setFont(QFont("Segoe UI", 10))
        self._lbl.setFixedWidth(175)
        self._lbl.setStyleSheet(f"color: {MUTED};")
        h.addWidget(self._lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(5)
        self._set_bar_color(ACCENT)
        h.addWidget(self._bar, 1)

        self._status = QLabel("—")
        self._status.setFont(QFont("Segoe UI", 9))
        self._status.setFixedWidth(110)
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._status.setStyleSheet(f"color: {MUTED};")
        h.addWidget(self._status)

    def _set_bar_color(self, color: str):
        self._bar.setStyleSheet(f"""
            QProgressBar {{background:{BORDER};border:none;border-radius:2px;}}
            QProgressBar::chunk {{background:{color};border-radius:2px;}}
        """)

    def reset(self):
        self._ico.setText("○"); self._ico.setStyleSheet(f"color:{MUTED};")
        self._lbl.setStyleSheet(f"color:{MUTED};")
        self._bar.setValue(0); self._set_bar_color(ACCENT)
        self._status.setText("—"); self._status.setStyleSheet(f"color:{MUTED};")

    def activate(self, txt=""):
        self._ico.setText("◉"); self._ico.setStyleSheet(f"color:{YELLOW};")
        self._lbl.setStyleSheet(f"color:{TEXT};")
        if txt:
            self._status.setText(txt[:18])
            self._status.setStyleSheet(f"color:{YELLOW};")

    def progress(self, pct: int, txt: str = ""):
        self._bar.setValue(pct)
        label = txt[:18] if txt else f"{pct}%"
        self._status.setText(label)
        self._status.setStyleSheet(f"color:{YELLOW};")

    def done(self, txt="✓"):
        self._ico.setText("✓"); self._ico.setStyleSheet(f"color:{GREEN};")
        self._lbl.setStyleSheet(f"color:{TEXT};")
        self._bar.setValue(100); self._set_bar_color(GREEN)
        self._status.setText(txt); self._status.setStyleSheet(f"color:{GREEN};")

    def error(self, txt="ПОМИЛКА"):
        self._ico.setText("✕"); self._ico.setStyleSheet(f"color:{RED};")
        self._lbl.setStyleSheet(f"color:{RED};")
        self._set_bar_color(RED)
        self._status.setText(txt[:18]); self._status.setStyleSheet(f"color:{RED};")

    def skip(self):
        self._ico.setText("—"); self._ico.setStyleSheet(f"color:{MUTED};")
        self._status.setText("пропущено")


# ══════════════════════════════════════════════════════════════════════════════
#  SETTINGS DIALOG
# ══════════════════════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Налаштування GitHub")
        self.setMinimumWidth(460)
        self.setStyleSheet(f"""
            QDialog {{ background:{PANEL}; color:{TEXT}; }}
            QLabel  {{ color:{TEXT}; font-size:11px; }}
            QLineEdit {{
                background:{CARD}; color:{TEXT}; border:1px solid {BORDER};
                border-radius:5px; padding:6px 10px; font-size:11px;
            }}
            QLineEdit:focus {{ border-color:{ACCENT}; }}
            QPushButton {{
                background:{ACCENT}; color:white; border:none;
                border-radius:5px; padding:7px 18px; font-size:11px;
            }}
            QPushButton:hover {{ background:#4f51d6; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel(
            "GitHub репо (напр. username/repo-name):"
        ))
        self._repo = QLineEdit(cfg.get("repo", ""))
        layout.addWidget(self._repo)

        layout.addWidget(QLabel(
            "GitHub Token (classic, scope: repo):"
        ))
        self._token = QLineEdit(cfg.get("token", ""))
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._token)

        hint = QLabel(
            "Отримати токен:\n"
            "github.com → Settings → Developer settings\n"
            "→ Personal access tokens → Tokens (classic)\n"
            "→ Generate new token → scope: repo"
        )
        hint.setStyleSheet(f"color:{MUTED}; font-size:10px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_cfg(self) -> dict:
        return {"repo": self._repo.text().strip(),
                "token": self._token.text().strip()}


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════

STEPS_FULL = [
    ("version",   "1. Версія"),
    ("build",     "2. PyInstaller"),
    ("installer", "3. Inno Setup"),
    ("zip",       "4. ZIP"),
    ("git",       "5. Git push"),
    ("upload",    "6. GitHub Upload"),
]
STEPS_ZIP = [
    ("version", "1. Версія"),
    ("zip",     "2. ZIP"),
    ("git",     "3. Git push"),
    ("upload",  "4. GitHub Upload"),
]

LOG_COLORS = {
    "head": "#a5b4fc",
    "ok":   GREEN,
    "err":  RED,
    "cmd":  "#94a3b8",
    "sub":  "#64748b",
    "info": TEXT,
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AXIS OS — Release Builder")
        self.resize(900, 680)
        self.setMinimumSize(760, 520)
        self._cfg    = load_cfg()
        self._worker = None

        self._build_ui()
        self._apply_theme()

    # ── build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── header ────────────────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(56)
        hh = QHBoxLayout(header)
        hh.setContentsMargins(20, 0, 20, 0)

        logo = QLabel("⬡  AXIS OS — Release Builder")
        logo.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        logo.setStyleSheet(f"color:{TEXT};")
        hh.addWidget(logo)
        hh.addStretch()

        self._ver_lbl = QLabel(f"v{read_version()}")
        self._ver_lbl.setFont(QFont("Segoe UI", 10))
        self._ver_lbl.setStyleSheet(f"color:{MUTED};")
        hh.addWidget(self._ver_lbl)

        outer.addWidget(header)

        # ── body ──────────────────────────────────────────────────────────────
        body = QWidget()
        body.setObjectName("body")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(18)
        outer.addWidget(body, 1)

        # left panel
        left = QWidget()
        left.setObjectName("left_panel")
        left.setFixedWidth(310)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 16, 16, 16)
        ll.setSpacing(14)

        # version input
        vl = QLabel("Нова версія")
        vl.setFont(QFont("Segoe UI", 9))
        vl.setStyleSheet(f"color:{MUTED};")
        ll.addWidget(vl)

        self._ver_inp = QLineEdit(read_version())
        self._ver_inp.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        self._ver_inp.setPlaceholderText("1.0.0")
        self._ver_inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self._ver_inp)

        # mode
        ml = QLabel("Режим збірки")
        ml.setFont(QFont("Segoe UI", 9))
        ml.setStyleSheet(f"color:{MUTED};")
        ll.addWidget(ml)

        mode_box = QWidget()
        mb = QVBoxLayout(mode_box)
        mb.setContentsMargins(0, 0, 0, 0)
        mb.setSpacing(6)

        self._rb_full = QRadioButton("Повна збірка  (PyInstaller + Inno Setup + ZIP)")
        self._rb_zip  = QRadioButton("Тільки ZIP + GitHub  (швидко, без .exe)")
        self._rb_zip.setChecked(True)
        self._mode_grp = QButtonGroup()
        self._mode_grp.addButton(self._rb_full)
        self._mode_grp.addButton(self._rb_zip)
        for rb in (self._rb_full, self._rb_zip):
            rb.setFont(QFont("Segoe UI", 10))
            rb.setStyleSheet(f"color:{TEXT};")
            mb.addWidget(rb)
        ll.addWidget(mode_box)

        ll.addWidget(self._sep())

        # steps
        steps_lbl = QLabel("Прогрес кроків")
        steps_lbl.setFont(QFont("Segoe UI", 9))
        steps_lbl.setStyleSheet(f"color:{MUTED};")
        ll.addWidget(steps_lbl)

        self._step_rows: dict[str, StepRow] = {}
        self._steps_widget = QWidget()
        self._steps_layout = QVBoxLayout(self._steps_widget)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(2)
        ll.addWidget(self._steps_widget)
        self._rebuild_steps(STEPS_ZIP)

        ll.addStretch()
        ll.addWidget(self._sep())

        # buttons
        self._btn_start = QPushButton("▶  Запустити реліз")
        self._btn_start.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        self._btn_start.setFixedHeight(42)
        self._btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_start.clicked.connect(self._start)
        ll.addWidget(self._btn_start)

        btn_row = QHBoxLayout()
        self._btn_cancel = QPushButton("✕  Зупинити")
        self._btn_cancel.setFixedHeight(34)
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self._btn_cancel)

        self._btn_cfg = QPushButton("⚙  GitHub")
        self._btn_cfg.setFixedHeight(34)
        self._btn_cfg.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cfg.clicked.connect(self._open_settings)
        btn_row.addWidget(self._btn_cfg)
        ll.addLayout(btn_row)

        bl.addWidget(left)

        # right panel — log
        right = QWidget()
        right.setObjectName("right_panel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        log_header = QHBoxLayout()
        log_lbl = QLabel("Лог виконання")
        log_lbl.setFont(QFont("Segoe UI", 9))
        log_lbl.setStyleSheet(f"color:{MUTED};")
        log_header.addWidget(log_lbl)
        log_header.addStretch()
        self._clear_btn = QPushButton("очистити")
        self._clear_btn.setStyleSheet(
            f"background:transparent;color:{MUTED};border:none;font-size:9px;")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._log_box.clear
                                        if hasattr(self, "_log_box") else lambda: None)
        log_header.addWidget(self._clear_btn)
        rl.addLayout(log_header)

        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setFont(QFont("Consolas", 9))
        self._log_box.setObjectName("log_box")
        rl.addWidget(self._log_box, 1)
        self._clear_btn.clicked.connect(self._log_box.clear)

        # status bar at bottom of log
        self._status_lbl = QLabel("Готовий до запуску")
        self._status_lbl.setFont(QFont("Segoe UI", 9))
        self._status_lbl.setStyleSheet(f"color:{MUTED};")
        rl.addWidget(self._status_lbl)

        bl.addWidget(right, 1)

        # connect mode change
        self._rb_full.toggled.connect(
            lambda c: self._rebuild_steps(STEPS_FULL if c else STEPS_ZIP))

    def _sep(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color:{BORDER};")
        return line

    def _rebuild_steps(self, steps):
        # clear old
        while self._steps_layout.count():
            item = self._steps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._step_rows.clear()
        for sid, lbl in steps:
            row = StepRow(lbl)
            self._step_rows[sid] = row
            self._steps_layout.addWidget(row)

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background:{BG}; color:{TEXT}; }}
            #header {{
                background:{PANEL};
                border-bottom:1px solid {BORDER};
            }}
            #left_panel {{
                background:{CARD};
                border-radius:10px;
                border:1px solid {BORDER};
            }}
            #right_panel {{ background:transparent; }}
            #log_box {{
                background:{CARD};
                color:{TEXT};
                border:1px solid {BORDER};
                border-radius:8px;
                padding:6px;
            }}
            QLineEdit {{
                background:{PANEL};
                color:{TEXT};
                border:1px solid {BORDER};
                border-radius:6px;
                padding:8px 12px;
                font-size:12px;
            }}
            QLineEdit:focus {{ border-color:{ACCENT}; }}
            QScrollBar:vertical {{
                background:{BG}; width:6px; border:none;
            }}
            QScrollBar::handle:vertical {{
                background:{BORDER}; border-radius:3px; min-height:20px;
            }}
        """)
        self._btn_start.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {ACCENT}, stop:1 #818cf8);
                color:white; border:none; border-radius:8px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #4f51d6, stop:1 #6366f1);
            }}
            QPushButton:disabled {{
                background:{BORDER}; color:{MUTED};
            }}
        """)
        for btn in (self._btn_cancel, self._btn_cfg):
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:{PANEL}; color:{TEXT};
                    border:1px solid {BORDER}; border-radius:6px;
                    font-size:10px;
                }}
                QPushButton:hover {{background:{BORDER};}}
                QPushButton:disabled {{color:{MUTED};}}
            """)
        for rb in (self._rb_full, self._rb_zip):
            rb.setStyleSheet(f"""
                QRadioButton {{ color:{TEXT}; spacing:8px; font-size:10px; }}
                QRadioButton::indicator {{
                    width:14px; height:14px;
                    border:2px solid {MUTED}; border-radius:7px;
                    background:{BG};
                }}
                QRadioButton::indicator:checked {{
                    border-color:{ACCENT}; background:{ACCENT};
                }}
            """)

    # ── actions ──────────────────────────────────────────────────────────────

    def _start(self):
        ver = self._ver_inp.text().strip().lstrip("v")
        if not ver:
            self._set_status("Введи версію!", RED); return
        parts = ver.split(".")
        if not (2 <= len(parts) <= 4) or not all(p.isdigit() for p in parts):
            self._set_status(f"Невірний формат версії: {ver}", RED); return

        if not self._cfg.get("token") or not self._cfg.get("repo"):
            self._open_settings()
            if not self._cfg.get("token") or not self._cfg.get("repo"):
                self._set_status("Налаштуй GitHub токен та репо!", RED)
                return

        mode = "full" if self._rb_full.isChecked() else "zip"
        steps = STEPS_FULL if mode == "full" else STEPS_ZIP

        self._rebuild_steps(steps)
        for row in self._step_rows.values():
            row.reset()

        self._log_box.clear()
        self._append_log(f"━━━ Реліз v{ver}  [{mode}] ━━━", "head")

        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._ver_inp.setEnabled(False)
        self._rb_full.setEnabled(False)
        self._rb_zip.setEnabled(False)
        self._set_status("⏳ Виконую...", YELLOW)

        self._worker = Worker(ver, mode, self._cfg)
        self._worker.sig_log.connect(self._on_log)
        self._worker.sig_step.connect(self._on_step)
        self._worker.sig_done.connect(self._on_done)
        self._worker.sig_fail.connect(self._on_fail)
        self._worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.stop()
        self._set_status("⛔ Зупинено", RED)
        self._unlock()

    def _open_settings(self):
        dlg = SettingsDialog(self._cfg, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_cfg = dlg.get_cfg()
            if new_cfg["repo"] and new_cfg["token"]:
                self._cfg.update(new_cfg)
                save_cfg(self._cfg)
                self._set_status("Налаштування збережено ✓", GREEN)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_log(self, text: str, level: str):
        self._append_log(text, level)

    def _on_step(self, sid: str, pct: int, txt: str):
        row = self._step_rows.get(sid)
        if not row:
            return
        if pct >= 100:
            row.done(txt or "✓")
        elif pct == 0:
            row.activate(txt)
        else:
            row.progress(pct, txt)

    def _on_done(self, url: str):
        self._append_log(f"\n🎉 Реліз опубліковано: {url}", "ok")
        self._set_status(f"✅ Готово! {url}", GREEN)
        self._unlock()

    def _on_fail(self, msg: str):
        self._append_log(f"\n❌ Помилка: {msg}", "err")
        self._set_status(f"❌ Помилка: {msg[:80]}", RED)
        for row in self._step_rows.values():
            pass  # last active row already shows error
        self._unlock()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _unlock(self):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._ver_inp.setEnabled(True)
        self._rb_full.setEnabled(True)
        self._rb_zip.setEnabled(True)

    def _set_status(self, text: str, color: str = TEXT):
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(f"color:{color};")

    def _append_log(self, text: str, level: str = "info"):
        color = LOG_COLORS.get(level, TEXT)
        cursor = self._log_box.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log_box.setTextCursor(cursor)
        self._log_box.setTextColor(QColor(color))
        self._log_box.insertPlainText(text + "\n")
        self._log_box.ensureCursorVisible()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # dark palette for native widgets
    p = app.palette()
    p.setColor(p.ColorRole.Window,          QColor(BG))
    p.setColor(p.ColorRole.WindowText,      QColor(TEXT))
    p.setColor(p.ColorRole.Base,            QColor(CARD))
    p.setColor(p.ColorRole.AlternateBase,   QColor(PANEL))
    p.setColor(p.ColorRole.Text,            QColor(TEXT))
    p.setColor(p.ColorRole.Button,          QColor(PANEL))
    p.setColor(p.ColorRole.ButtonText,      QColor(TEXT))
    p.setColor(p.ColorRole.Highlight,       QColor(ACCENT))
    p.setColor(p.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(p)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
