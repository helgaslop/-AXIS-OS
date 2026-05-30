"""AXIS OS — entry point."""
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtGui import QIcon


def load_config() -> dict:
    from core.paths import CONFIG_FILE, migrate_data
    migrate_data()
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {}   # перший запуск — норма
    except json.JSONDecodeError as e:
        print(f"[AXIS] ⚠ config.json пошкоджений ({e}) — використовуємо налаштування за замовчуванням")
        # Зберігаємо резервну копію перед скиданням
        try:
            import shutil, time
            backup = str(CONFIG_FILE) + f".bak.{int(time.time())}"
            shutil.copy2(CONFIG_FILE, backup)
            print(f"[AXIS] Резервну копію збережено: {backup}")
        except Exception:
            pass
        cfg = {}
    except Exception as e:
        print(f"[AXIS] ⚠ Не вдалось завантажити config.json: {e}")
        cfg = {}
    # One-time migration: move any plaintext API keys into Credential Manager
    try:
        from core.secrets import migrate_from_config
        api_keys = cfg.get("api_keys", {})
        if any(v for v in api_keys.values() if isinstance(v, str) and v):
            moved = migrate_from_config(api_keys)
            if moved:
                import json as _j
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    _j.dump(cfg, f, ensure_ascii=False, indent=2)
                print(f"[AXIS] Migrated {moved} API key(s) to Windows Credential Manager")
    except Exception as e:
        print(f"[AXIS] Secrets migration skipped: {e}")
    return cfg


def main():
    # Must be set before QApplication
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setApplicationName("AXIS OS")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AXIS")

    config = load_config()

    # Import here so QApplication exists first
    from gui.main_window import AxisWindow
    window = AxisWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
