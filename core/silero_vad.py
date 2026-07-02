# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  core/silero_vad.py  –  Voice Activity Detection                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Silero VAD через onnxruntime (без torch, модель ~2 МБ).                     ║
║  Fallback: адаптивний енергетичний VAD якщо ONNX недоступний.                ║
║                                                                              ║
║  API:                                                                         ║
║    is_speech(chunk: bytes, rate: int) -> bool                                 ║
║        chunk — PCM-16 LE mono, рекомендовано 30 мс @ 16 кГц (480 семплів)    ║
║    reset() — скинути внутрішній стан (викликати на початку нового запису)    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

_MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "silero_vad.onnx"

_lock    = threading.Lock()
_session = None          # onnxruntime.InferenceSession | None
_failed  = False         # True → ONNX недоступний, працюємо на енергетичному VAD

# Silero v5 ONNX очікує вікна по 512 семплів @ 16 кГц + стан LSTM
_SILERO_WIN   = 512
_THRESHOLD    = 0.5

# ── внутрішній стан ───────────────────────────────────────────────────────────
_state   = None          # np.ndarray (2,1,128) — LSTM state
_context = None          # np.ndarray (1,64)    — контекст попереднього вікна
_buf     = np.zeros(0, dtype=np.float32)   # хвіст, що не влізло у вікно
_last    = False         # останнє рішення (для хвостів < 512 семплів)

# ── енергетичний fallback ─────────────────────────────────────────────────────
_noise_rms  = 150.0      # адаптивна оцінка шуму
_ENERGY_K   = 3.0        # мова = RMS > шум × K


def _load_session():
    global _session, _failed
    with _lock:
        if _session is not None or _failed:
            return _session
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            _session = ort.InferenceSession(
                str(_MODEL_PATH), sess_options=opts,
                providers=["CPUExecutionProvider"])
            print("[VAD] Silero VAD (onnx) OK")
        except Exception as e:
            print(f"[VAD] Silero onnx unavailable ({e}) -> energy VAD")
            _failed = True
    return _session


def reset():
    """Скинути стан (на початку нового сеансу запису)."""
    global _state, _context, _buf, _last
    _state   = None
    _context = None
    _buf     = np.zeros(0, dtype=np.float32)
    _last    = False


def _silero_prob(win: np.ndarray, rate: int) -> float:
    """Ймовірність мови для вікна 512 семплів (float32 -1..1)."""
    global _state, _context
    if _state is None:
        _state = np.zeros((2, 1, 128), dtype=np.float32)
    if _context is None:
        _context = np.zeros((1, 64), dtype=np.float32)
    x = np.concatenate([_context, win[np.newaxis, :]], axis=1)
    _context = win[np.newaxis, -64:]
    out, _state = _session.run(
        None, {"input": x, "state": _state, "sr": np.array(rate, dtype=np.int64)})
    return float(out[0][0])


def is_speech(chunk: bytes, rate: int = 16000) -> bool:
    """True якщо у chunk (PCM-16 LE mono) є мова."""
    global _buf, _last, _noise_rms

    pcm = np.frombuffer(chunk, dtype=np.int16)
    if pcm.size == 0:
        return False

    sess = _load_session()
    if sess is not None:
        try:
            _buf = np.concatenate([_buf, pcm.astype(np.float32) / 32768.0])
            voiced = None
            while _buf.size >= _SILERO_WIN:
                win  = _buf[:_SILERO_WIN]
                _buf = _buf[_SILERO_WIN:]
                p = _silero_prob(win, rate)
                voiced = (p >= _THRESHOLD) if voiced is None else (voiced or p >= _THRESHOLD)
            if voiced is not None:
                _last = voiced
            return _last
        except Exception as e:
            # Один раз повідомляємо і назавжди переходимо на fallback
            global _failed, _session
            print(f"[VAD] Silero inference error ({e}) -> energy VAD")
            with _lock:
                _session = None
                _failed  = True

    # ── Енергетичний fallback: адаптивний поріг по RMS ────────────────────────
    rms = float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2)))
    voiced = rms > _noise_rms * _ENERGY_K
    if not voiced:
        # повільно адаптуємо оцінку шуму
        _noise_rms = 0.95 * _noise_rms + 0.05 * max(rms, 1.0)
    return voiced


def rms_level(chunk: bytes) -> float:
    """RMS гучність chunk — для енергетичного гейта barge-in."""
    pcm = np.frombuffer(chunk, dtype=np.int16)
    if pcm.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2)))
