"""
AXIS OS — Налаштування Telegram бота.
Запусти: python setup_telegram.py
"""
import json, os, sys

# Сфера зберігає конфіг у %APPDATA%\AXIS OS\ — пишемо туди
_APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
DATA_DIR = os.path.join(_APPDATA, "AXIS OS")
os.makedirs(DATA_DIR, exist_ok=True)

# Додатково оновлюємо локальну data/ якщо вона є
_LOCAL_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

DEFAULT_COMMANDS = [
    {"label": "🎮 Ігри",        "type": "submenu_steam"},
    {"label": "🎬 Серіал",      "type": "submenu_watch"},
    {"label": "🔊 Гучність",    "type": "submenu_volume"},
    {"label": "🖥️ Система",    "type": "submenu_system"},
    {"label": "💻 Робота",      "type": "command", "action": "відкрий робочий процес"},
    {"label": "🎵 Музика",      "type": "command", "action": "включи музику"},
    {"label": "📷 Скріншот",    "type": "command", "action": "зроби скріншот"},
    {"label": "❌ Вимкнути ПК", "type": "command", "action": "виключи пк"},
]

def load_json(path):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

print("=" * 52)
print("  🔮  AXIS OS — Налаштування Telegram бота")
print("=" * 52)

# Основні шляхи (AppData — де сфера РЕАЛЬНО читає)
cfg_path  = os.path.join(DATA_DIR, "sphere_config.json")
cfg2_path = os.path.join(DATA_DIR, "config.json")
# Локальні шляхи (додатково оновлюємо якщо є)
cfg_local_path  = os.path.join(_LOCAL_DATA_DIR, "sphere_config.json")
cfg_local2_path = os.path.join(_LOCAL_DATA_DIR, "config.json")

cfg  = load_json(cfg_path)
cfg2 = load_json(cfg2_path)

# Показуємо поточний стан
cur_token = cfg.get("telegram_token", "") or ""
cur_ids   = cfg.get("telegram_allowed_ids", "") or ""
cur_en    = cfg.get("telegram_enabled", False)
print(f"\nПоточний стан:")
print(f"  Увімкнено : {cur_en}")
print(f"  Токен     : {'✅ є' if cur_token else '❌ немає'}")
print(f"  Chat IDs  : {cur_ids or '(всі)'}")

print("\n─── Крок 1: Bot Token ───────────────────────────")
print("Як отримати: Telegram → @BotFather → /newbot")
if cur_token:
    print(f"Поточний токен збережено. Enter = залишити.")
token = input("Токен: ").strip() or cur_token

if not token or ":" not in token:
    print("❌ Токен не введено. Виходжу.")
    input("\nEnter для виходу...")
    sys.exit(0)

# Перевірка токена
try:
    import requests
    r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
    if r.ok and r.json().get("ok"):
        bot_user = r.json()["result"]["username"]
        print(f"✅ Бот знайдений: @{bot_user}")
    else:
        print(f"❌ Помилка токена: {r.json().get('description','')}")
        yn = input("Продовжити? (y/n): ").strip().lower()
        if yn != "y":
            sys.exit(0)
        bot_user = "unknown"
except Exception as e:
    print(f"⚠ Мережева помилка: {e}")
    bot_user = "unknown"

print("\n─── Крок 2: Chat ID ─────────────────────────────")
print("Як дізнатись: @userinfobot → /start (або напиши боту /start — він відповість)")
if cur_ids:
    print(f"Поточний ID: {cur_ids}. Enter = залишити.")
chat_ids = input("Chat ID(s) через кому: ").strip() or cur_ids

print("\n─── Збереження ───────────────────────────────────")

# Зберігаємо в AppData (де сфера РЕАЛЬНО читає конфіг)
for path, d in [(cfg_path, cfg), (cfg2_path, cfg2)]:
    d["telegram_enabled"]     = True
    d["telegram_token"]       = token
    d["telegram_allowed_ids"] = chat_ids
    d["telegram_commands"]    = DEFAULT_COMMANDS
    save_json(path, d)

# Дублюємо в локальну data/ якщо вона є
if os.path.isdir(_LOCAL_DATA_DIR):
    for path in [cfg_local_path, cfg_local2_path]:
        d2 = load_json(path)
        d2["telegram_enabled"]     = True
        d2["telegram_token"]       = token
        d2["telegram_allowed_ids"] = chat_ids
        d2["telegram_commands"]    = DEFAULT_COMMANDS
        save_json(path, d2)

print("✅ Збережено!")
print(f"   Токен : {token[:20]}...")
print(f"   IDs   : {chat_ids or '(всі)'}")
print(f"   Команди: {len(DEFAULT_COMMANDS)} кнопок")

# Надсилаємо тестове повідомлення
if chat_ids:
    first_id = chat_ids.split(",")[0].strip()
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": first_id,
                "parse_mode": "HTML",
                "text": (
                    "╔══════════════════════════╗\n"
                    "║  🔮  <b>AXIS OS</b>  ·  <b>AIVON</b>  🔮  ║\n"
                    "╚══════════════════════════╝\n\n"
                    "✅ <b>Налаштування збережено!</b>\n\n"
                    "Тепер <b>перезапусти сферу</b> і напиши /start\n"
                    "— з'являться кнопки керування 🎮🎬🔊🖥️"
                )
            },
            timeout=10
        )
        if r.ok:
            print(f"\n📱 Тестове повідомлення надіслано на {first_id}!")
        else:
            print(f"⚠ Помилка надсилання: {r.json().get('description','')}")
            print("   Перевір Chat ID")
    except Exception as e:
        print(f"⚠ {e}")

print("\n" + "─" * 52)
print("Тепер:")
print(f"  1. Перезапусти сферу (python aivon_sphere.py)")
print(f"  2. Напиши боту @{bot_user} → /start")
print(f"  3. З'являться кнопки: 🎮 Ігри, 🎬 Серіал, 🔊 Гучність...")
print("─" * 52)
input("\nEnter для виходу...")
