# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/sound.py  –  Звукові ефекти JarvisSound (з aivon_sphere.py)        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Клас:  JarvisSound  (рядки 785–904)                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import random
import time
from datetime import datetime
from pathlib import Path


def _get_app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _get_sound_dir() -> Path:
    return _get_app_dir() / "assets" / "sounds"


class JarvisSound:
    """Система кастомних JARVIS звуків"""

    # Категорії звуків — маппінг файлів
    CATEGORIES = {
        "confirm": ["Будет сделанно.wav", "Выполняю.wav", "Да сэр.wav",
                     "Да сэр(второй).wav", "Есть.wav", "Запрос выполнен сэр.wav"],
        "greeting": ["Джарвис - приветствие.wav", "Доброе утро.wav",
                      "Добрый вечер.wav", "Доброй ночи сэр.wav"],
        "ready": ["К вашим услугам сэр.wav", "Всегда к вашим услугам сэр.wav",
                   "Была рада помочь вам сэр.wav"],
        "loading": ["Загружаю сэр.wav", "Импортирую установки, начинаю калибровку виртуальной среды.wav"],
        "done": ["Готово.wav", "Запрос выполнен сэр.wav"],
        "science": ["1науч.wav", "2науч.wav", "3науч.wav"],
        "browser": ["Браузер.wav"],
        "vk": ["ВК.wav"],
        "monitor_off": ["Выключаю монитор.wav"],
        "new_element": ["Вы создали новый элемент.wav"],
        "no_info": ["Другой информации нет.wav"],
        "error": ["К сожалению его невозможно синтезировать.wav"],
        "activate": ["Да сэр.wav", "Есть.wav", "К вашим услугам сэр.wav"],
    }

    def __init__(self, sound_dir=None):
        self.sound_dir = Path(sound_dir) if sound_dir else _get_sound_dir()
        self.enabled = True
        self._mixer_ready = False
        self._init_mixer()

    def _init_mixer(self):
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100)
            self._mixer_ready = True
        except Exception as e:
            print(f"JarvisSound mixer error: {e}")
            self._mixer_ready = False

    def set_hologram(self, holo_view, port=8090):
        """Підключити QWebEngineView для lip-sync"""
        self._holo_view = holo_view
        self._holo_port = port

    def _resolve_file(self, filename):
        """Знайти файл у папці звуків"""
        fpath = self.sound_dir / filename
        if fpath.exists():
            return fpath
        for f in self.sound_dir.rglob(filename):
            return f
        return None

    def _to_http_url(self, fpath):
        """Конвертувати локальний шлях в HTTP URL для голограми"""
        import urllib.parse
        app_dir = _get_app_dir()
        rel = os.path.relpath(str(fpath), str(app_dir)).replace("\\", "/")
        return f"http://127.0.0.1:{self._holo_port}/{urllib.parse.quote(rel)}"

    def play(self, category, block=False):
        """Грати випадковий звук з категорії"""
        if not self.enabled or not self._mixer_ready:
            return
        files = self.CATEGORIES.get(category, [])
        if not files:
            return
        fname = random.choice(files)
        fpath = self._resolve_file(fname)
        if not fpath:
            print(f"Sound not found: {fname}")
            return
        # Lip-sync: send to hologram via HTTP URL
        if getattr(self, '_holo_view', None):
            url = self._to_http_url(fpath)
            self._holo_view.page().runJavaScript(f"window.playAudioWithLipSync('{url}')")
            return
        try:
            import pygame
            sound = pygame.mixer.Sound(str(fpath))
            sound.play()
            if block:
                while pygame.mixer.get_busy():
                    time.sleep(0.05)
        except Exception as e:
            print(f"Sound play error: {e}")

    def play_file(self, filename, block=False):
        """Грати конкретний файл"""
        if not self.enabled or not self._mixer_ready:
            return
        fpath = self._resolve_file(filename)
        if not fpath:
            return
        # Lip-sync: send to hologram via HTTP URL
        if getattr(self, '_holo_view', None):
            url = self._to_http_url(fpath)
            self._holo_view.page().runJavaScript(f"window.playAudioWithLipSync('{url}')")
            return
        try:
            import pygame
            sound = pygame.mixer.Sound(str(fpath))
            sound.play()
            if block:
                while pygame.mixer.get_busy():
                    time.sleep(0.05)
        except Exception as e:
            print(f"Sound play error: {e}")

    def play_greeting(self):
        """Привітання залежно від часу доби"""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            self.play_file("Доброе утро.wav")
        elif 12 <= hour < 18:
            self.play_file("Добрый вечер.wav")
        elif 18 <= hour < 23:
            self.play_file("Добрый вечер.wav")
        else:
            self.play_file("Доброй ночи сэр.wav")
