# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  core/vosk_stt.py  –  Локальне потокове розпізнавання мови (Vosk)            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Офлайн, потокове: partial-текст з'являється ПОКИ користувач говорить,       ║
║  фінальний текст готовий одразу після кінця фрази (без HTTP round-trip).     ║
║                                                                              ║
║  Модель: data/models/vosk-model-small-uk-*  (українська, ~100 МБ)           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

_MODELS_DIR = Path(__file__).resolve().parent.parent / "data" / "models"

_lock   = threading.Lock()
_model  = None
_failed = False


def _find_model_dir() -> Path | None:
    if not _MODELS_DIR.exists():
        return None
    candidates = [p for p in sorted(_MODELS_DIR.glob("vosk-model*"))
                  if p.is_dir() and (p / "am").exists()]
    if not candidates:
        return None
    # Повна модель точніша за small/nano — віддаємо їй перевагу
    full = [p for p in candidates if "small" not in p.name and "nano" not in p.name]
    return (full or candidates)[0]


def available() -> bool:
    """True якщо vosk встановлено і модель на диску."""
    if _failed:
        return False
    try:
        import vosk  # noqa: F401
    except ImportError:
        return False
    return _find_model_dir() is not None


def get_model():
    """Лінива загрузка моделі (перший виклик ~1-3 c — робити у фоновому потоці)."""
    global _model, _failed
    with _lock:
        if _model is not None or _failed:
            return _model
        try:
            import vosk
            vosk.SetLogLevel(-1)
            mdir = _find_model_dir()
            if mdir is None:
                _failed = True
                return None
            print(f"[Vosk] Loading model: {mdir.name} ...")
            _model = vosk.Model(str(mdir))
            print("[Vosk] Model ready")
        except Exception as e:
            print(f"[Vosk] Model load failed: {e}")
            _failed = True
    return _model


def recognizer(rate: int = 16000, grammar: list[str] | None = None):
    """Новий KaldiRecognizer. grammar — обмежений словник (для wake-word)."""
    import vosk
    model = get_model()
    if model is None:
        return None
    if grammar:
        rec = vosk.KaldiRecognizer(model, rate, json.dumps(grammar, ensure_ascii=False))
    else:
        rec = vosk.KaldiRecognizer(model, rate)
    try:
        rec.SetWords(True)   # per-word confidence у фінальному результаті
    except Exception:
        pass
    return rec


def partial_text(rec) -> str:
    try:
        return json.loads(rec.PartialResult()).get("partial", "")
    except Exception:
        return ""


def final_text(rec) -> str:
    try:
        return json.loads(rec.FinalResult()).get("text", "")
    except Exception:
        return ""


def final_with_conf(rec) -> tuple[str, float]:
    """Фінальний текст + середня per-word confidence (0..1).
    Якщо confidence недоступна — повертає 1.0 (не блокуємо результат)."""
    try:
        data  = json.loads(rec.FinalResult())
        text  = data.get("text", "")
        words = data.get("result", [])
        if words:
            conf = sum(w.get("conf", 1.0) for w in words) / len(words)
        else:
            conf = 1.0 if text else 0.0
        return text, conf
    except Exception:
        return "", 0.0


def result_text(rec) -> str:
    try:
        return json.loads(rec.Result()).get("text", "")
    except Exception:
        return ""
