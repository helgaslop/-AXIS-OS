"""
Centralized path management for AXIS OS.
APP_DIR      - installation directory (read-only in Program Files)
USER_DATA_DIR - writable user data: %APPDATA%/AXIS OS/
"""
import os
import sys
import shutil
from pathlib import Path


def _get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _get_user_data_dir() -> Path:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(appdata) / "AXIS OS"
    d.mkdir(parents=True, exist_ok=True)
    return d


APP_DIR       = _get_app_dir()
USER_DATA_DIR = _get_user_data_dir()

# Read-only assets (icons, sounds, HTML)
ASSETS_DIR = APP_DIR / "assets"
GUI_DIR    = APP_DIR / "gui"

# Writable user files
CONFIG_FILE        = USER_DATA_DIR / "config.json"
SPHERE_CONFIG_FILE = USER_DATA_DIR / "sphere_config.json"
COMMANDS_FILE      = USER_DATA_DIR / "commands.json"
MACROS_FILE        = USER_DATA_DIR / "macros.json"
AGENT_CONFIG_FILE  = USER_DATA_DIR / "agent_config.json"
SPOTIFY_TOKEN_FILE = USER_DATA_DIR / ".spotify_token"
APP_CACHE_FILE     = USER_DATA_DIR / "app_cache.json"
VERSION_FILE       = APP_DIR / "version.txt"


def migrate_data():
    """
    On first run after install: copy default data files from APP_DIR/data/
    to USER_DATA_DIR if they don't exist yet.
    Copies: config.json, sphere_config.json, commands.json, macros.json
    Skips:  .ico files and other read-only assets
    """
    src_dir = APP_DIR / "data"
    if not src_dir.exists():
        return
    for fname in ("config.json", "sphere_config.json", "commands.json",
                  "macros.json", "agent_config.json"):
        src = src_dir / fname
        dst = USER_DATA_DIR / fname
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(str(src), str(dst))
            except Exception:
                pass
