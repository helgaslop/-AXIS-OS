# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/launcher.py  –  AppLauncher: запуск програм (з aivon_sphere.py)    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Клас:  AppLauncher  (рядки 910–1220)                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import subprocess
import webbrowser
from pathlib import Path

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _get_user_data_dir() -> Path:
    _appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(_appdata) / "AXIS OS"


class AppLauncher:
    """Пошук та запуск додатків і ігор на системі"""

    SCAN_DIRS = [
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs"),
        os.path.expanduser(r"~\Desktop"),
    ]

    # Steam та Epic Games
    GAME_DIRS = [
        r"C:\Program Files (x86)\Steam\steamapps\common",
        r"C:\Program Files\Steam\steamapps\common",
        r"D:\Steam\steamapps\common",
        r"D:\SteamLibrary\steamapps\common",
        r"E:\SteamLibrary\steamapps\common",
        r"C:\Program Files\Epic Games",
        r"D:\Epic Games",
    ]

    # Відомі скорочення/прізвиська для ігор і додатків
    ALIASES = {
        "контра": ["counter-strike", "csgo", "cs2", "counter strike"],
        "гта": ["grand theft auto", "gta", "rockstar"],
        "доту": ["dota", "dota 2"],
        "танки": ["world of tanks", "wot"],
        "кораблі": ["world of warships", "wows"],
        "майнкрафт": ["minecraft"],
        "фортнайт": ["fortnite"],
        "вітчер": ["witcher"],
        "кіберпанк": ["cyberpunk"],
        "діскорд": ["discord"],
        "хром": ["chrome", "google chrome"],
        "телеграм": ["telegram"],
        "вайбер": ["viber"],
        "скайп": ["skype"],
        "ворд": ["word", "winword"],
        "ексель": ["excel"],
        "блокнот": ["notepad"],
        "пейнт": ["paint", "mspaint"],
        "стім": ["steam"],
        "епік": ["epic games", "epicgameslauncher"],
        "файрфокс": ["firefox", "mozilla"],
        "опера": ["opera"],
        "бравзер": ["browser", "chrome", "firefox", "opera", "edge"],
        "код": ["visual studio code", "code"],
        "пошта": ["outlook", "thunderbird", "gmail"],
        "калькулятор": ["calc", "calculator"],
        "провідник": ["explorer"],
        "термінал": ["cmd", "powershell", "terminal"],
        "відеоплеєр": ["vlc", "mediaplayer"],
        "ноутбук": ["onenote", "notepad", "notion"],
        "студія": ["visual studio", "vs", "devenv"],
    }

    # Веб-додатки — відкриваються у браузері
    WEB_APPS = {
        # ── AI асистенти ──────────────────────────────────────
        "клод": "https://claude.ai",
        "claude": "https://claude.ai",
        "гпт": "https://chat.openai.com",
        "chatgpt": "https://chat.openai.com",
        "чат гпт": "https://chat.openai.com",
        "чатгпт": "https://chat.openai.com",
        "chat gpt": "https://chat.openai.com",
        "опенаі": "https://chat.openai.com",
        "openai": "https://chat.openai.com",
        "джемінай": "https://gemini.google.com",
        "джемін": "https://gemini.google.com",
        "gemini": "https://gemini.google.com",
        "барад": "https://gemini.google.com",
        "перплексіті": "https://perplexity.ai",
        "perplexity": "https://perplexity.ai",
        "кобот": "https://copilot.microsoft.com",
        "copilot": "https://copilot.microsoft.com",
        "коупілот": "https://copilot.microsoft.com",
        "міджорні": "https://midjourney.com",
        "midjourney": "https://midjourney.com",
        "ллама": "https://llama.meta.com",
        "llama": "https://llama.meta.com",
        "гроук": "https://grok.x.ai",
        "grok": "https://grok.x.ai",
        # ── Відео / Музика ────────────────────────────────────
        "ютуб": "https://youtube.com",
        "youtube": "https://youtube.com",
        "нетфлікс": "https://netflix.com",
        "netflix": "https://netflix.com",
        "кінопоіск": "https://kinopoisk.ru",
        "кінопошук": "https://kinopoisk.ru",
        "tвіч": "https://twitch.tv",
        "twitch": "https://twitch.tv",
        "спотіфай": "https://open.spotify.com",
        "дізер": "https://deezer.com",
        "deezer": "https://deezer.com",
        # ── Соцмережі ─────────────────────────────────────────
        "твіттер": "https://twitter.com",
        "twitter": "https://twitter.com",
        "іксі": "https://x.com",
        "інстаграм": "https://instagram.com",
        "instagram": "https://instagram.com",
        "фейсбук": "https://facebook.com",
        "facebook": "https://facebook.com",
        "редіт": "https://reddit.com",
        "reddit": "https://reddit.com",
        "тікток": "https://tiktok.com",
        "tiktok": "https://tiktok.com",
        "лінкедін": "https://linkedin.com",
        "linkedin": "https://linkedin.com",
        # ── Продуктивність ────────────────────────────────────
        "ноушн": "https://notion.so",
        "notion": "https://notion.so",
        "трелло": "https://trello.com",
        "trello": "https://trello.com",
        "ноушн ai": "https://notion.so",
        "гугл докс": "https://docs.google.com",
        "google docs": "https://docs.google.com",
        "гугл диск": "https://drive.google.com",
        "google drive": "https://drive.google.com",
        "гугл таблиці": "https://sheets.google.com",
        "google sheets": "https://sheets.google.com",
        "гугл": "https://google.com",
        "google": "https://google.com",
        "ґмейл": "https://gmail.com",
        "gmail": "https://gmail.com",
        "гмейл": "https://gmail.com",
        "фігма": "https://figma.com",
        "figma": "https://figma.com",
        "канва": "https://canva.com",
        "canva": "https://canva.com",
        # ── Розробка ──────────────────────────────────────────
        "гітхаб": "https://github.com",
        "github": "https://github.com",
        "стековерфлов": "https://stackoverflow.com",
        "stackoverflow": "https://stackoverflow.com",
        "версел": "https://vercel.com",
        "vercel": "https://vercel.com",
        "хероку": "https://heroku.com",
        "heroku": "https://heroku.com",
        # ── Месенджери ────────────────────────────────────────
        "вотсап": "https://web.whatsapp.com",
        "whatsapp": "https://web.whatsapp.com",
        # ── Новини / Пошук ────────────────────────────────────
        "бінг": "https://bing.com",
        "bing": "https://bing.com",
        "вікіпедія": "https://uk.wikipedia.org",
        "wikipedia": "https://en.wikipedia.org",
        "хабр": "https://habr.com",
        "habr": "https://habr.com",
        "медіум": "https://medium.com",
        "medium": "https://medium.com",
        # ── Магазини ─────────────────────────────────────────
        "прайм": "https://amazon.com",
        "amazon": "https://amazon.com",
        "алі": "https://aliexpress.com",
        "aliexpress": "https://aliexpress.com",
        "розетка": "https://rozetka.com.ua",
        "olx": "https://olx.ua",
    }

    def __init__(self):
        self.cache_file = _get_user_data_dir() / "app_cache.json"
        self.apps = {}
        self._load_cache()

    def _load_cache(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.apps = json.load(f)
            except Exception:
                self.apps = {}

    def _save_cache(self):
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.apps, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def scan(self):
        """Сканувати систему на наявність додатків"""
        print("AppLauncher: Scanning...")
        found = {}

        # Сканувати стандартні директорії
        for d in self.SCAN_DIRS + self.GAME_DIRS:
            if not os.path.exists(d):
                continue
            try:
                for root, dirs, files in os.walk(d):
                    # Не йти глибше 3 рівнів
                    depth = root.replace(d, '').count(os.sep)
                    if depth > 3:
                        dirs.clear()
                        continue
                    for f in files:
                        if f.lower().endswith(('.exe', '.lnk')):
                            name = os.path.splitext(f)[0].lower()
                            if name not in ('uninstall', 'uninst', 'update', 'updater', 'setup', 'installer'):
                                path = os.path.join(root, f)
                                found[name] = path
            except PermissionError:
                continue

        self.apps.update(found)
        self._save_cache()
        print(f"AppLauncher: Found {len(self.apps)} apps")
        return len(self.apps)

    def find(self, query):
        """Знайти додаток за запитом (підтримує прізвиська, веб-додатки, fuzzy)."""
        from difflib import SequenceMatcher
        q = query.lower().strip()
        if not q:
            return None

        # 1. Точний збіг серед встановлених
        if q in self.apps:
            return self.apps[q]

        # 2. Точний збіг у веб-додатках
        if q in self.WEB_APPS:
            return self.WEB_APPS[q]

        # 3. Прізвиська → встановлені
        for alias, targets in self.ALIASES.items():
            if alias in q or q in alias:
                for target in targets:
                    for name, path in self.apps.items():
                        if target in name:
                            return path

        # 4. Часткове входження у веб-додатках
        for name, url in self.WEB_APPS.items():
            if q in name or name in q:
                return url

        # 5. Часткове входження серед встановлених
        for name, path in self.apps.items():
            if q in name or name in q:
                return path

        # 6. Системні команди
        sys_cmds = {
            "блокнот": "notepad", "калькулятор": "calc",
            "провідник": "explorer", "діспетчер": "taskmgr",
            "пейнт": "mspaint", "термінал": "cmd",
            "диспетчер задач": "taskmgr",
        }
        if q in sys_cmds:
            return sys_cmds[q]

        # 7. Fuzzy match серед встановлених (поріг 0.55)
        best_score, best_path = 0.0, None
        for name, path in self.apps.items():
            score = SequenceMatcher(None, q, name).ratio()
            if score > best_score:
                best_score, best_path = score, path
        if best_score >= 0.55:
            return best_path

        # 8. Fuzzy match серед веб-додатків (поріг 0.6)
        best_score, best_url = 0.0, None
        for name, url in self.WEB_APPS.items():
            score = SequenceMatcher(None, q, name).ratio()
            if score > best_score:
                best_score, best_url = score, url
        if best_score >= 0.6:
            return best_url

        return None

    def find_multi(self, phrase: str) -> list:
        """Розбирає фразу, виділяє назви додатків і повертає список (name, path)."""
        # Роздільники між кількома додатками
        separators = [" і ", " та ", " and ", " й ", ", ", " + "]
        parts = [phrase]
        for sep in separators:
            new_parts = []
            for p in parts:
                new_parts.extend(p.split(sep))
            parts = new_parts
        parts = [p.strip() for p in parts if p.strip()]

        results = []
        for part in parts:
            path = self.find(part)
            if path:
                results.append((part, path))
        return results

    def launch(self, path):
        """Запустити додаток"""
        try:
            if path.startswith(("http://", "https://")):
                webbrowser.open(path)
            elif path.startswith("http"):
                # Reject malformed or non-http(s) http-prefixed strings
                print(f"[AXIS] Blocked non-http URL in launch: {path!r}")
                return False
            elif path.endswith('.lnk'):
                os.startfile(path)
            else:
                subprocess.Popen(path, shell=True, creationflags=_NO_WINDOW)
            return True
        except Exception as e:
            print(f"Launch error: {e}")
            return False
