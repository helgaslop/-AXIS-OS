# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/config.py  –  Конфігурація Sphere (з aivon_sphere.py)              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Вміст: load_sphere_config, save_sphere_config, DEFAULT_CONFIG (SPHERE)     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
from pathlib import Path


def _get_user_data_dir() -> Path:
    _appdata = os.environ.get("APPDATA") or str(Path.home())
    p = Path(_appdata) / "AXIS OS"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _get_sphere_config_file() -> Path:
    return _get_user_data_dir() / "sphere_config.json"


def _get_config_file() -> Path:
    return _get_user_data_dir() / "config.json"


def _get_commands_file() -> Path:
    return _get_user_data_dir() / "commands.json"


# ── Default sphere config ─────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "sphere_name":           "Aivon",
    "sphere_wake":           "Aivon",
    "sphere_size":           "medium",      # small | medium | large
    "sphere_color":          "#00d4ff",
    "sphere_color2":         "#7b2cbf",
    "sphere_opacity":        90,            # 30–100
    "sphere_position":       "bottom-right", # bottom-right | bottom-left | center | top-right
    "sphere_anim":           "pulse",       # pulse | breathing | waves | electric | fire
    "sphere_anim_speed":     5,             # 1–10
    "sphere_particles":      True,
    "sphere_particle_count": 20,            # 5–50
    "sphere_autostart":      True,
    # Ollama offline fallback
    "ollama_model":          "llama3.2",
    "ollama_fallback":       True,
    # Mode profiles
    "current_mode":          "normal",
    # Automations
    "automations":           [],
}

# Alias kept for backward compatibility
SPHERE_CONFIG_DEFAULTS = DEFAULT_CONFIG


def load_sphere_config() -> dict:
    """
    Завантажує налаштування сфери з data/sphere_config.json
    Якщо файл не існує — повертає дефолтні значення
    """
    cfg_file = _get_sphere_config_file()
    if cfg_file.exists():
        try:
            with open(cfg_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {**DEFAULT_CONFIG, **data}
        except Exception as e:
            print(f"[SphereConfig] ⚠️ Помилка читання: {e}")
    return dict(DEFAULT_CONFIG)


def save_sphere_config(data: dict):
    """
    Зберігає налаштування сфери в data/sphere_config.json
    Викликається панеллю через Backend.save_sphere_config() або apply_sphere_now()
    """
    cfg_file = _get_sphere_config_file()
    try:
        _get_user_data_dir().mkdir(parents=True, exist_ok=True)
        existing = load_sphere_config()
        existing.update(data)
        with open(cfg_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"[SphereConfig] ✅ Збережено в {cfg_file}")
    except Exception as e:
        print(f"[SphereConfig] ❌ Помилка збереження: {e}")


def save_config(cfg: dict):
    """Зберігає головний config.json."""
    cfg_file = _get_config_file()
    with open(cfg_file, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_config() -> dict:
    """Завантажує config.json з дефолтними значеннями."""
    default = {
        "anthropic_key": "",
        "openai_key": "",
        "google_key": "",
        "xai_key": "",
        "perplexity_key": "",
        "spotify_client_id": "",
        "spotify_client_secret": "",
        "voice": "onyx",
        "language": "uk-UA",
        "tts_enabled": True,
        "tts_provider": "edge",
        "edge_voice": "uk-UA-PolinaNeural",
        "ai_provider": "openai",
        "dialog_provider": "gemini",
        "dialog_memory_size": 20,
        "tts_speed": 1.15,
        "voice_openai": "onyx",
        "voice_anthropic": "echo",
        "voice_gemini": "nova",
        "voice_xai": "alloy",
        "voice_perplexity": "fable",
        # ═══ SPHERE VISUAL SETTINGS ═══
        "sphere_name": "Aivon",
        "sphere_wake": "Aivon",
        "sphere_size": "medium",
        "sphere_color": "#00d4ff",
        "sphere_color2": "#7b2cbf",
        "sphere_opacity": 90,
        "sphere_position": "bottom-right",
        "sphere_anim": "pulse",
        "sphere_anim_speed": 5,
        "sphere_particles": True,
        "sphere_particle_count": 20,
        "sphere_autostart": True,
    }
    cfg_file = _get_config_file()
    if cfg_file.exists():
        try:
            with open(cfg_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # ── Axis OS зберігає ключі вкладено: api_keys.openai → openai_key ──
            # Після міграції в Credential Manager значення в api_keys порожні,
            # тому добираємо їх з керінга (core.secrets).
            api_keys = dict(data.get("api_keys", {}))
            try:
                from core.secrets import get_key as _get_secret
            except Exception:
                _get_secret = None
            if _get_secret:
                for _name in ("openai", "anthropic", "google", "xai", "perplexity",
                              "spotify_client_id", "spotify_client_secret"):
                    if not api_keys.get(_name):
                        _v = _get_secret(_name)
                        if _v:
                            api_keys[_name] = _v
            if api_keys:
                for _cfg_key, _src in (
                    ("openai_key",            "openai"),
                    ("anthropic_key",         "anthropic"),
                    ("google_key",            "google"),
                    ("xai_key",               "xai"),
                    ("perplexity_key",        "perplexity"),
                    ("spotify_client_id",     "spotify_client_id"),
                    ("spotify_client_secret", "spotify_client_secret"),
                ):
                    if not data.get(_cfg_key):
                        data[_cfg_key] = api_keys.get(_src, "")

            # ── Axis OS зберігає ai провайдера вкладено: ai.default_provider ──
            ai_block = data.get("ai", {})
            if ai_block:
                data.setdefault("ai_provider",     ai_block.get("default_provider", "openai"))
                data.setdefault("dialog_provider", ai_block.get("default_provider", "openai"))

            # ── Axis OS використовує tts_voice замість voice ──
            if "tts_voice" in data:
                data.setdefault("voice", data["tts_voice"])

            merged = {**default, **data}
            # Sphere config має пріоритет над головним конфігом
            sphere = load_sphere_config()
            merged.update(sphere)
            return merged
        except Exception:
            pass
    # Створюємо файл з дефолтними значеннями
    save_config(default)
    return default


def load_commands() -> list:
    """Завантажує команди з файлу - викликається перед кожною командою!"""
    default = [
        {"phrase": "час", "type": "time", "action": "", "response": ""},
        {"phrase": "година", "type": "time", "action": "", "response": ""},
        {"phrase": "дата", "type": "date", "action": "", "response": ""},
        {"phrase": "сьогодні", "type": "date", "action": "", "response": ""},
        {"phrase": "ютуб", "type": "url", "action": "https://youtube.com", "response": "Відкриваю YouTube"},
        {"phrase": "youtube", "type": "url", "action": "https://youtube.com", "response": "Відкриваю YouTube"},
        {"phrase": "гугл", "type": "url", "action": "https://google.com", "response": "Відкриваю Google"},
        {"phrase": "пошта", "type": "url", "action": "https://gmail.com", "response": "Відкриваю пошту"},
        {"phrase": "блокнот", "type": "app", "action": "notepad", "response": "Відкриваю блокнот"},
        {"phrase": "калькулятор", "type": "app", "action": "calc", "response": "Відкриваю калькулятор"},
        {"phrase": "привіт", "type": "speak", "action": "Привіт! Чим допомогти?", "response": ""},
        {"phrase": "дякую", "type": "speak", "action": "Будь ласка!", "response": ""},
        {"phrase": "сховайся", "type": "hide", "action": "До зустрічі!", "response": ""},
        {"phrase": "стоп", "type": "hide", "action": "Йду в тихий режим", "response": ""},
    ]
    cmds_file = _get_commands_file()
    if cmds_file.exists():
        try:
            with open(cmds_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    # Створюємо файл з дефолтними командами
    with open(cmds_file, 'w', encoding='utf-8') as f:
        json.dump(default, f, ensure_ascii=False, indent=2)
    return default
