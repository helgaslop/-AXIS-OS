"""
AXIS OS — Wake-on-LAN сервер для Telegram
==========================================
Запускай на будь-якому пристрої що ЗАВЖДИ увімкнений:
  - Телефон (Android + Termux)
  - Raspberry Pi
  - Інший ПК в мережі

Встановлення:
  pip install requests

Запуск:
  python wake_server.py

Команди в Telegram:
  /wake   — разбудити ноутбук (WOL magic packet)
  /ping   — перевірити чи ноутбук онлайн
  /status — стан сервера
"""

import socket
import struct
import time
import json
import os
import sys
import threading

# ═══════════════════════════════════════════════
# НАЛАШТУВАННЯ — заповни або скопіюй з sphere_config.json
# ═══════════════════════════════════════════════
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "data", "wake_config.json")

DEFAULTS = {
    "telegram_token":       "",           # той самий що в сфері
    "telegram_allowed_ids": "",           # той самий chat id
    "target_mac":           "",   # MAC-адреса цільового ПК (налаштуй в панелі)
    "target_ip":            "",   # IP цільового ПК
    "broadcast_ip":         "",   # broadcast мережі (напр. 192.168.1.255)
    "hostname":             "",   # ім'я хоста (необов'язково)
}


def load_config():
    # Спочатку пробуємо взяти з sphere_config (AppData)
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    sphere_cfg = os.path.join(appdata, "AXIS OS", "sphere_config.json")
    cfg = dict(DEFAULTS)
    if os.path.exists(sphere_cfg):
        try:
            with open(sphere_cfg, encoding="utf-8") as f:
                sc = json.load(f)
            cfg["telegram_token"]       = sc.get("telegram_token", "")
            cfg["telegram_allowed_ids"] = sc.get("telegram_allowed_ids", "")
        except Exception:
            pass
    # Потім локальний wake_config.json (якщо є)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def send_magic_packet(mac: str, broadcast: str = "255.255.255.255"):
    """Відправляє WOL magic packet."""
    mac_clean = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(mac_clean) != 12:
        raise ValueError(f"Невірний MAC: {mac}")
    mac_bytes = bytes.fromhex(mac_clean)
    magic = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(magic, (broadcast, 9))
        s.sendto(magic, ("255.255.255.255", 9))
        s.sendto(magic, (broadcast, 7))
    print(f"[WOL] Magic packet → {mac} ({broadcast})")


def is_online(ip: str, timeout: float = 1.5) -> bool:
    """Ping через TCP (не потребує прав адміна)."""
    try:
        with socket.create_connection((ip, 80), timeout=timeout):
            return True
    except Exception:
        pass
    try:
        with socket.create_connection((ip, 445), timeout=timeout):
            return True
    except Exception:
        pass
    return False


# ═══ Telegram API helpers ═══════════════════════════════════════
class WakeBot:
    POLL_TIMEOUT = 25

    def __init__(self):
        self.cfg = load_config()
        self.token = self.cfg.get("telegram_token", "").strip()
        self.allowed = [x.strip() for x in
                        str(self.cfg.get("telegram_allowed_ids", "")).split(",")
                        if x.strip()]
        self.mac       = self.cfg.get("target_mac",   DEFAULTS["target_mac"])
        self.target_ip = self.cfg.get("target_ip",    DEFAULTS["target_ip"])
        self.broadcast = self.cfg.get("broadcast_ip", DEFAULTS["broadcast_ip"])
        self.hostname  = self.cfg.get("hostname",     DEFAULTS["hostname"])
        self._offset   = 0
        self._running  = True

    @property
    def base(self):
        return f"https://api.telegram.org/bot{self.token}"

    def _get(self, method, **params):
        import urllib.request, urllib.parse
        url = f"{self.base}/{method}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=self.POLL_TIMEOUT + 5) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"[Bot] GET {method} error: {e}")
            return {}

    def _post(self, method, data: dict):
        import urllib.request
        url = f"{self.base}/{method}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"[Bot] POST {method} error: {e}")
            return {}

    def send(self, chat_id, text):
        self._post("sendMessage", {
            "chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML"
        })

    def _handle(self, upd):
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            return
        chat_id = str(msg["chat"]["id"])
        text    = (msg.get("text") or "").strip()
        cmd     = text.split("@")[0].lower() if text.startswith("/") else text.lower()
        first   = msg.get("from", {}).get("first_name", "") or ""

        # Перевірка дозволів
        if self.allowed and chat_id not in self.allowed:
            self.send(chat_id, "⛔ Немає доступу")
            return

        print(f"[Bot] {first} ({chat_id}): {cmd!r}")

        if cmd in ("/start", "/help", "start"):
            online = is_online(self.target_ip)
            status = "🟢 онлайн" if online else "🔴 офлайн"
            self.send(chat_id,
                f"╔══════════════════╗\n"
                f"║  🔮  <b>AXIS WOL Bot</b>  🔮  ║\n"
                f"╚══════════════════╝\n\n"
                f"💻 <b>{self.hostname}</b> — {status}\n"
                f"📡 MAC: <code>{self.mac}</code>\n\n"
                f"<b>Команди:</b>\n"
                f"  /wake — 🔌 Розбудити ноутбук\n"
                f"  /ping — 📡 Перевірити статус\n"
                f"  /status — ℹ️ Інфо"
            )

        elif cmd in ("/wake", "wake", "будь", "розбудити", "включи ноутбук", "увімкни ноутбук"):
            self.send(chat_id, f"⚡ Надсилаю magic packet на <code>{self.mac}</code>...")
            try:
                send_magic_packet(self.mac, self.broadcast)
                time.sleep(2)
                online = is_online(self.target_ip)
                if online:
                    self.send(chat_id, "✅ <b>Ноутбук онлайн!</b> Пробудження вдалося 🎉")
                else:
                    self.send(chat_id,
                        "📤 Magic packet надіслано!\n"
                        "⏳ Ноутбук ще не відповідає — зачекай 30-60 сек і перевір /ping\n\n"
                        "<i>Якщо не вмикається — перевір що WOL увімкнено в BIOS</i>"
                    )
            except Exception as e:
                self.send(chat_id, f"❌ Помилка: {e}")

        elif cmd in ("/ping", "ping", "статус ноутбук", "перевір ноутбук"):
            self.send(chat_id, "📡 Перевіряю...")
            online = is_online(self.target_ip)
            if online:
                self.send(chat_id, f"🟢 <b>{self.hostname}</b> онлайн! (<code>{self.target_ip}</code>)")
            else:
                self.send(chat_id, f"🔴 <b>{self.hostname}</b> офлайн або не відповідає")

        elif cmd in ("/status", "status"):
            self.send(chat_id,
                f"ℹ️ <b>WOL Сервер активний</b>\n"
                f"💻 Ціль: <code>{self.hostname}</code> / <code>{self.target_ip}</code>\n"
                f"📡 MAC: <code>{self.mac}</code>\n"
                f"📡 Broadcast: <code>{self.broadcast}</code>"
            )

    def run(self):
        if not self.token:
            print("❌ Токен не знайдено. Запусти setup_telegram.py спочатку.")
            return

        # Перевірка токена
        me = self._get("getMe")
        if not me.get("ok"):
            print(f"❌ Невірний токен: {me}")
            return
        bot_name = me["result"]["username"]
        print(f"✅ WOL Бот підключено: @{bot_name}")
        print(f"📡 MAC: {self.mac} | IP: {self.target_ip}")
        print(f"👥 Allowed IDs: {self.allowed or '(всі)'}")
        print("─" * 40)
        print("Очікую команди /wake /ping /status...")
        print("Ctrl+C для виходу")

        while self._running:
            try:
                resp = self._get("getUpdates",
                                 offset=self._offset,
                                 timeout=self.POLL_TIMEOUT)
                for upd in resp.get("result", []):
                    self._offset = upd["update_id"] + 1
                    try:
                        self._handle(upd)
                    except Exception as e:
                        print(f"[Bot] handle error: {e}")
            except KeyboardInterrupt:
                print("\nВихід...")
                break
            except Exception as e:
                print(f"[Bot] polling error: {e}")
                time.sleep(5)


# ═══ Інтерактивне налаштування ═════════════════════════════════
def setup_wizard():
    print("=" * 50)
    print("  🔮  AXIS OS — Wake-on-LAN сервер")
    print("=" * 50)
    cfg = load_config()
    print(f"\n📡 MAC ноутбука : {cfg['target_mac']}")
    print(f"🌐 IP ноутбука  : {cfg['target_ip']}")
    print(f"📡 Broadcast    : {cfg['broadcast_ip']}")
    print(f"🤖 Токен        : {'✅ є' if cfg['telegram_token'] else '❌ немає'}")
    print(f"👥 Chat ID      : {cfg['telegram_allowed_ids'] or '(не задано)'}")

    ch = input("\nНалаштувати? (Enter=пропустити налаштування, n=вийти): ").strip().lower()
    if ch == "n":
        return False

    if not cfg["telegram_token"]:
        t = input("Введи токен бота: ").strip()
        if t and ":" in t:
            cfg["telegram_token"] = t

    ids = input(f"Chat ID [{cfg['telegram_allowed_ids']}]: ").strip()
    if ids:
        cfg["telegram_allowed_ids"] = ids

    mac = input(f"MAC ноутбука [{cfg['target_mac']}]: ").strip()
    if mac:
        cfg["target_mac"] = mac.replace("-", ":").upper()

    ip = input(f"IP ноутбука [{cfg['target_ip']}]: ").strip()
    if ip:
        cfg["target_ip"] = ip
        # Автоматичний broadcast
        parts = ip.split(".")
        if len(parts) == 4:
            cfg["broadcast_ip"] = ".".join(parts[:3]) + ".255"

    save_config(cfg)
    print("✅ Збережено!")
    return True


if __name__ == "__main__":
    if "--setup" in sys.argv or not os.path.exists(CONFIG_FILE):
        if not setup_wizard():
            sys.exit(0)
    bot = WakeBot()
    bot.run()
