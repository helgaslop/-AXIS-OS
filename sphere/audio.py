# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/audio.py  –  STT, мікрофон, пробудження                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Standalone thread / helper classes (moved from aivon_sphere.py):            ║
║    WhisperSTT            – faster-whisper singleton wrapper                  ║
║    WhisperLoader         – async model loader                                ║
║    VoiceThread           – mic capture + STT                                 ║
║    InterruptMonitorThread– VAD monitor during TTS                            ║
║    WakeWordThread        – background wake-word detection                    ║
║                                                                              ║
║  Mixin:                                                                      ║
║    SphereAudioMixin      – methods for AivonSphere                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, QTimer, pyqtSignal


# ═══════════════════════════════════════════════════════════
# faster-whisper availability flag
# ═══════════════════════════════════════════════════════════

try:
    from faster_whisper import WhisperModel as _WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False


# ═══════════════════════════════════════════════════════════
# WhisperSTT – singleton offline STT via faster-whisper
# ═══════════════════════════════════════════════════════════

class WhisperSTT:
    """Singleton для офлайн STT через faster-whisper.
    Лінива ініціалізація — модель завантажується тільки при першому використанні.
    GPU (CUDA float16) якщо доступна, інакше CPU int8.
    """
    _instance:  "_WhisperModel | None" = None
    _model_size: str  = "small"   # tiny | base | small | medium
    _device:     str  = "auto"    # auto | cuda | cpu
    _loading:    bool = False

    @classmethod
    def _detect_device(cls) -> tuple[str, str]:
        """Повертає (device, compute_type)."""
        try:
            import ctranslate2
            if "float16" in ctranslate2.get_supported_compute_types("cuda"):
                return "cuda", "float16"
        except Exception:
            pass
        return "cpu", "int8"

    @classmethod
    def load(cls, model_size: str = "small", device: str = "auto"):
        """Завантажує модель (блокуючий виклик — запускати в потоці)."""
        if not HAS_WHISPER:
            raise RuntimeError("pip install faster-whisper")
        if cls._instance and cls._model_size == model_size:
            return cls._instance
        cls._loading = True
        dev, compute = (
            cls._detect_device() if device == "auto"
            else (device, "float16" if device == "cuda" else "int8")
        )
        print(f"[Whisper] Завантаження моделі '{model_size}' ({dev}/{compute})…")
        try:
            cls._instance   = _WhisperModel(model_size, device=dev, compute_type=compute)
            cls._model_size = model_size
            cls._device     = dev
            print(f"[Whisper] ✅ Модель готова ({dev})")
        finally:
            cls._loading = False
        return cls._instance

    @classmethod
    def _transcribe(cls, audio_data, lang: str) -> tuple[str, float]:
        """Внутрішній метод — повертає (text, avg_confidence)."""
        if not HAS_WHISPER or cls._instance is None:
            raise RuntimeError("Whisper не завантажено")
        import numpy as np
        wav_bytes  = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
        audio_np   = np.frombuffer(wav_bytes[44:], dtype=np.int16).astype(np.float32) / 32768.0
        whisper_lang = lang.split("-")[0].lower() if "-" in lang else lang.lower()
        segments_gen, info = cls._instance.transcribe(
            audio_np, language=whisper_lang, beam_size=5,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
            word_timestamps=False,
        )
        segments = list(segments_gen)
        text     = " ".join(s.text for s in segments).strip()
        if segments:
            avg_lp     = sum(s.avg_logprob for s in segments) / len(segments)
            confidence = max(0.0, min(1.0, 1.0 + avg_lp / 5.0))
        else:
            confidence = 0.0
        print(f"[Whisper] '{text[:60]}' conf={confidence:.2f} lang={info.language}")
        return text, confidence

    @classmethod
    def recognize(cls, audio_data, lang: str = "uk") -> str:
        """Транскрибує AudioData з speech_recognition → str."""
        text, _ = cls._transcribe(audio_data, lang)
        return text

    @classmethod
    def recognize_with_conf(cls, audio_data, lang: str = "uk") -> tuple[str, float]:
        """Транскрибує → (text, confidence 0..1)."""
        return cls._transcribe(audio_data, lang)


# ═══════════════════════════════════════════════════════════
# WhisperLoader – async model load
# ═══════════════════════════════════════════════════════════

class WhisperLoader(QThread):
    """Завантажує модель Whisper у фоні щоб не блокувати UI."""
    done = pyqtSignal(bool, str)   # (success, message)

    def __init__(self, model_size: str = "small"):
        super().__init__()
        self.model_size = model_size

    def run(self):
        try:
            WhisperSTT.load(self.model_size)
            self.done.emit(True, f"Whisper '{self.model_size}' готовий ✅")
        except Exception as e:
            self.done.emit(False, f"Whisper помилка: {e}")


# ═══════════════════════════════════════════════════════════
# VoiceThread – mic capture + VAD + STT
# ═══════════════════════════════════════════════════════════

class VoiceThread(QThread):
    """Розпізнавання голосу.

    Task 7: Streaming pyaudio + VAD (Silero / energy-threshold).
    Chunks of 30 ms → VAD per chunk → 550 ms silence after speech → stop.
    Falls back to blocking speech_recognition if pyaudio unavailable.
    """
    recognized            = pyqtSignal(str)
    recognized_with_conf  = pyqtSignal(str, float)   # text, confidence 0..1
    recognized_with_audio = pyqtSignal(str, bytes)   # text, raw PCM-16 LE bytes @ 16kHz
    partial               = pyqtSignal(str)
    error                 = pyqtSignal(str)
    started_signal        = pyqtSignal()
    stopped               = pyqtSignal()

    # VAD constants
    _RATE         = 16000
    _CHUNK_MS     = 30
    _CHUNK_FRAMES = _RATE * _CHUNK_MS // 1000   # 480 samples
    _SILENCE_END  = 18   # ×30 ms = 540 ms silence → end of phrase
    _MIN_SPEECH   = 3    # ×30 ms = 90 ms minimum speech to accept
    _MAX_CHUNKS   = 500  # ×30 ms = 15 s hard limit
    _PRE_ROLL     = 5    # keep N silent chunks before speech onset

    def __init__(self, lang: str = "uk-UA", config: dict | None = None):
        super().__init__()
        self.lang        = lang
        self.config      = config or {}
        self.live_bridge = None   # LiveAudioBridge | None

    def set_live_bridge(self, bridge) -> None:
        """Task 2: attach a LiveAudioBridge; this thread streams PCM to it."""
        self.live_bridge = bridge

    # ── public entry point ────────────────────────────────────────────────────
    def run(self):
        self.started_signal.emit()
        if self.live_bridge is not None:
            self._run_live_mode()
            self.stopped.emit()
            return
        if self._run_streaming():
            self.stopped.emit()
            return
        self._run_legacy()
        self.stopped.emit()

    # ── Task 2: live audio bridge streaming mode ──────────────────────────────
    def _run_live_mode(self):
        """Stream VAD-active PCM chunks directly to self.live_bridge."""
        try:
            import pyaudio
            from core.silero_vad import is_speech
        except ImportError:
            print("[VoiceThread/live] pyaudio or core.silero_vad missing")
            return

        from aivon_sphere import _open_mic_stream, _to_mono  # type: ignore

        bridge   = self.live_bridge
        pa       = pyaudio.PyAudio()
        stream   = None
        channels = 1
        try:
            stream, channels = _open_mic_stream(pa, self._RATE, self._CHUNK_FRAMES)
            self.partial.emit("🎤 Live…")
            in_speech   = False
            silence_cnt = 0
            speech_cnt  = 0
            ring: list[bytes] = []

            while not self.isInterruptionRequested():
                raw    = stream.read(self._CHUNK_FRAMES, exception_on_overflow=False)
                chunk  = _to_mono(raw, channels)
                voiced = is_speech(chunk, self._RATE)

                if voiced:
                    if not in_speech:
                        in_speech = True
                        for r in ring:
                            bridge.send_audio_chunk(r)
                        ring.clear()
                    bridge.send_audio_chunk(chunk)
                    speech_cnt  += 1
                    silence_cnt  = 0
                elif in_speech:
                    silence_cnt += 1
                    bridge.send_audio_chunk(chunk)
                    if silence_cnt >= self._SILENCE_END:
                        bridge.signal_speech_end()
                        in_speech   = False
                        speech_cnt  = 0
                        silence_cnt = 0
                else:
                    ring.append(chunk)
                    if len(ring) > self._PRE_ROLL:
                        ring.pop(0)
        except Exception as e:
            print(f"[VoiceThread/live] error: {e}")
        finally:
            if stream:
                try: stream.stop_stream(); stream.close()
                except Exception: pass
            pa.terminate()

    # ── Task 7: streaming VAD capture ────────────────────────────────────────
    def _run_streaming(self) -> bool:
        """Stream mic with VAD. Returns True if ran (even on no_speech)."""
        try:
            import pyaudio
        except ImportError:
            return False

        try:
            from core.silero_vad import is_speech
        except Exception:
            return False

        from aivon_sphere import _open_mic_stream, _to_mono  # type: ignore

        pa       = pyaudio.PyAudio()
        stream   = None
        channels = 1
        try:
            stream, channels = _open_mic_stream(pa, self._RATE, self._CHUNK_FRAMES)
            self.partial.emit("🎤 Слухаю...")

            ring        = []
            speech_buf  = []
            in_speech   = False
            silence_cnt = 0
            speech_cnt  = 0
            total       = 0

            while total < self._MAX_CHUNKS:
                if self.isInterruptionRequested():
                    break
                raw    = stream.read(self._CHUNK_FRAMES, exception_on_overflow=False)
                total += 1
                mono   = _to_mono(raw, channels)
                voiced = is_speech(mono, self._RATE)

                if voiced:
                    if not in_speech:
                        in_speech = True
                        speech_buf.extend(ring)
                        ring.clear()
                    speech_buf.append(mono)
                    speech_cnt  += 1
                    silence_cnt  = 0
                elif in_speech:
                    speech_buf.append(mono)
                    silence_cnt += 1
                    if silence_cnt >= self._SILENCE_END:
                        break
                else:
                    ring.append(mono)
                    if len(ring) > self._PRE_ROLL:
                        ring.pop(0)
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            pa.terminate()

        if speech_cnt < self._MIN_SPEECH:
            self.error.emit("no_speech")
            return True

        audio_bytes = b"".join(speech_buf)
        self._transcribe(audio_bytes)
        return True

    def _transcribe(self, audio_bytes: bytes):
        """Transcribe raw 16-bit PCM bytes via Whisper or Google STT."""
        from aivon_sphere import load_config, save_config  # type: ignore

        use_whisper = (
            self.config.get("stt_provider", "google") == "whisper"
            and HAS_WHISPER
            and WhisperSTT._instance is not None
            and not self.config.get("_whisper_cuda_error", False)
        )

        text       = ""
        confidence = 0.85

        if use_whisper:
            self.partial.emit("🧠 Whisper...")
            try:
                import speech_recognition as sr
                audio_data = sr.AudioData(audio_bytes, self._RATE, 2)
                text, confidence = WhisperSTT.recognize_with_conf(audio_data, self.lang)
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ("cublas", "cuda", "dll", "ctranslate", "cudnn")):
                    self.config["_whisper_cuda_error"] = True
                    self.config["stt_provider"]        = "google"
                    try:
                        _cfg = load_config()
                        _cfg["stt_provider"]        = "google"
                        _cfg["_whisper_cuda_error"] = True
                        save_config(_cfg)
                    except Exception:
                        pass
                    use_whisper = False
                    self.partial.emit("⚡ Google STT (Whisper CUDA недоступний)")
                else:
                    self.error.emit(f"whisper: {str(e)[:40]}")
                    return

        if not use_whisper:
            self.partial.emit("🔄 Розпізнаю...")
            try:
                import speech_recognition as sr
                audio_data = sr.AudioData(audio_bytes, self._RATE, 2)
                result = sr.Recognizer().recognize_google(
                    audio_data, language=self.lang, show_all=True)
                if isinstance(result, dict):
                    alts = result.get("alternative", [])
                    if alts:
                        text       = alts[0].get("transcript", "")
                        confidence = float(alts[0].get("confidence", 0.85))
                else:
                    text = str(result) if result else ""
            except Exception:
                try:
                    import speech_recognition as sr
                    audio_data = sr.AudioData(audio_bytes, self._RATE, 2)
                    text       = sr.Recognizer().recognize_google(audio_data, language=self.lang)
                    confidence = 0.85
                except Exception:
                    self.error.emit("no_speech")
                    return

        if not text:
            self.error.emit("no_speech")
            return

        try:
            self.recognized_with_audio.emit(text, audio_bytes)
        except Exception:
            pass
        self.recognized.emit(text)
        self.recognized_with_conf.emit(text, confidence)

    # ── Legacy fallback (no pyaudio) ─────────────────────────────────────────
    def _run_legacy(self):
        from aivon_sphere import load_config, save_config  # type: ignore

        try:
            import speech_recognition as sr
        except ImportError:
            self.error.emit("SpeechRecognition not installed")
            return

        r = sr.Recognizer()
        r.energy_threshold         = 200
        r.dynamic_energy_threshold = True
        r.pause_threshold          = 0.8
        r.non_speaking_duration    = 0.5
        r.operation_timeout        = 10

        use_whisper = (
            self.config.get("stt_provider", "google") == "whisper"
            and HAS_WHISPER
            and WhisperSTT._instance is not None
            and not self.config.get("_whisper_cuda_error", False)
        )

        try:
            with sr.Microphone() as src:
                self.partial.emit("🎤 Слухаю...")
                r.adjust_for_ambient_noise(src, duration=0.2)
                audio = r.listen(src, timeout=7, phrase_time_limit=12)

            confidence = 1.0
            text       = ""

            if use_whisper:
                self.partial.emit("🧠 Whisper...")
                try:
                    text, confidence = WhisperSTT.recognize_with_conf(audio, self.lang)
                except Exception as whisper_err:
                    err_str = str(whisper_err).lower()
                    if any(k in err_str for k in ("cublas", "cuda", "dll", "ctranslate", "cudnn")):
                        self.config["_whisper_cuda_error"] = True
                        self.config["stt_provider"]        = "google"
                        try:
                            _cfg = load_config()
                            _cfg["stt_provider"]        = "google"
                            _cfg["_whisper_cuda_error"] = True
                            save_config(_cfg)
                        except Exception:
                            pass
                        self.partial.emit("⚡ Google STT (Whisper CUDA недоступний)")
                        use_whisper = False
                        text        = ""
                    else:
                        self.error.emit(f"whisper: {str(whisper_err)[:40]}")
                        return

            if not use_whisper:
                self.partial.emit("🔄 Розпізнаю...")
                try:
                    result = r.recognize_google(audio, language=self.lang, show_all=True)
                    if isinstance(result, dict):
                        alts = result.get("alternative", [])
                        if alts:
                            text       = alts[0].get("transcript", "")
                            confidence = float(alts[0].get("confidence", 0.85))
                        else:
                            text = ""
                    else:
                        text = str(result) if result else ""
                except Exception:
                    try:
                        text       = r.recognize_google(audio, language=self.lang)
                        confidence = 0.85
                    except sr.UnknownValueError:
                        self.error.emit("no_speech")
                        return

            if not text:
                self.error.emit("no_speech")
                return

            try:
                audio_bytes = audio.get_raw_data(convert_rate=16000, convert_width=2)
                self.recognized_with_audio.emit(text, audio_bytes)
            except Exception:
                pass
            self.recognized.emit(text)
            self.recognized_with_conf.emit(text, confidence)

        except sr.WaitTimeoutError:
            self.error.emit("timeout")
        except sr.UnknownValueError:
            self.error.emit("no_speech")
        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════════════════════
# InterruptMonitorThread – VAD monitor during TTS (Task 8)
# ═══════════════════════════════════════════════════════════

class InterruptMonitorThread(QThread):
    """Task 8: Monitors mic during TTS playback.

    Opens a short-lived pyaudio stream, runs VAD on 30 ms chunks.
    Emits `interrupted` when continuous speech detected while TTS is playing.
    Immediately closes the stream before emitting so VoiceThread can open mic.
    """
    interrupted = pyqtSignal()

    _RATE           = 16000
    _CHUNK_MS       = 30
    _CHUNK_FRAMES   = _RATE * _CHUNK_MS // 1000   # 480 samples
    _SPEECH_CONFIRM = 4    # consecutive voiced chunks (~120 ms)
    _MAX_SECONDS    = 30   # give up after 30 s of TTS (safety)

    def __init__(self):
        super().__init__()
        self._active = True

    def stop_monitor(self):
        self._active = False
        self.requestInterruption()

    def run(self):
        try:
            import pyaudio
            from core.silero_vad import is_speech
        except ImportError:
            return

        from aivon_sphere import _open_mic_stream, _to_mono  # type: ignore

        pa       = pyaudio.PyAudio()
        stream   = None
        channels = 1
        try:
            stream, channels = _open_mic_stream(pa, self._RATE, self._CHUNK_FRAMES)
            voiced_run   = 0
            total_chunks = 0
            limit        = self._MAX_SECONDS * 1000 // self._CHUNK_MS

            while self._active and total_chunks < limit:
                if self.isInterruptionRequested():
                    break
                raw = stream.read(self._CHUNK_FRAMES, exception_on_overflow=False)
                total_chunks += 1
                mono = _to_mono(raw, channels)

                if is_speech(mono, self._RATE):
                    voiced_run += 1
                    if voiced_run >= self._SPEECH_CONFIRM:
                        stream.stop_stream()
                        stream.close()
                        stream = None
                        pa.terminate()
                        pa = None
                        self.interrupted.emit()
                        return
                else:
                    voiced_run = 0
        except Exception as e:
            print(f"[InterruptMonitor] error: {e}")
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if pa:
                pa.terminate()


# ═══════════════════════════════════════════════════════════
# WakeWordThread – background wake-word detection
# ═══════════════════════════════════════════════════════════

class WakeWordThread(QThread):
    """Фонове прослуховування wake word."""
    wake_detected = pyqtSignal(str)  # 'greeting' або 'quick'

    def __init__(self, lang: str = "uk-UA", name: str = "Aivon"):
        super().__init__()
        self.lang    = lang
        self.running = True
        self.paused  = False
        from aivon_sphere import build_wake_lists  # type: ignore
        self.greeting_words, self.quick_words = build_wake_lists(name)

    def update_name(self, name: str):
        """Оновити wake-слова при зміні імені з налаштувань."""
        from aivon_sphere import build_wake_lists  # type: ignore
        self.greeting_words, self.quick_words = build_wake_lists(name)
        print(f"[Wake] ✏️ Нове ім'я: '{name}' → wake слів: "
              f"{len(self.greeting_words) + len(self.quick_words)}")

    def run(self):
        try:
            import speech_recognition as sr
        except ImportError:
            print("ERROR: pip install SpeechRecognition pyaudio")
            return

        r = sr.Recognizer()
        r.energy_threshold         = 250
        r.dynamic_energy_threshold = True
        r.pause_threshold          = 0.5

        try:
            mic_list = sr.Microphone.list_microphone_names()
            print(f"[Wake] Мікрофони: {len(mic_list)} знайдено")
            if mic_list:
                print(f"[Wake] Основний: {mic_list[0][:50]}")
        except Exception as e:
            print(f"[Wake] ⚠️ Помилка мікрофона: {e}")

        print(f"[Wake] Мова: {self.lang} | Слухаю wake words...")

        mic = sr.Microphone()
        while self.running:
            if self.paused:
                self.msleep(100)
                continue

            try:
                with mic as src:
                    r.adjust_for_ambient_noise(src, duration=0.3)
                    audio = r.listen(src, timeout=3, phrase_time_limit=4)

                text = r.recognize_google(audio, language=self.lang).lower()
                print(f"[Wake] Почув: '{text}'")

                detected = False
                for wake in self.greeting_words:
                    if wake in text:
                        print(f"[Wake] ✅ GREETING: '{wake}' в '{text}'")
                        self.wake_detected.emit('greeting')
                        self.msleep(2000)
                        detected = True
                        break
                if not detected:
                    for wake in self.quick_words:
                        if wake in text:
                            print(f"[Wake] ✅ QUICK: '{wake}' в '{text}'")
                            self.wake_detected.emit('quick')
                            self.msleep(2000)
                            break

            except sr.WaitTimeoutError:
                self.msleep(50)
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"[Wake] ⚠️ Google API помилка: {e}")
                self.msleep(3000)
            except OSError as e:
                print(f"[Wake] ❌ Мікрофон помилка: {e}")
                self.msleep(5000)
            except Exception as e:
                print(f"[Wake] ❌ Помилка: {type(e).__name__}: {e}")
                self.msleep(1000)

    def stop(self):
        self.running = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


# ═══════════════════════════════════════════════════════════
# SphereAudioMixin – methods added to AivonSphere
# ═══════════════════════════════════════════════════════════

class SphereAudioMixin:
    """Mixin that provides STT/audio/wake-word methods for AivonSphere.

    Requires the host class to have:
        self.config, self.state, self.response_text,
        self.update(), self.respond(), self.respond_silent(),
        self._respond_signal, self._tts_busy,
        self.voice_thread, self.wake_thread,
        self._interrupt_tts(), self._on_all_tts_done(),
        self.on_recognized(), self.on_voice_stopped(), self.on_error(),
        self._on_stt_confidence(),
        LISTENING / IDLE constants.
    """

    # ── Public API ────────────────────────────────────────────────────────────
    def start_listening(self):
        """Почати слухати. Task 8: TTS busy no longer blocks — interrupt instead."""
        if self.voice_thread and self.voice_thread.isRunning():
            return
        if self._tts_busy:
            self._interrupt_tts()
        self.user_text, self.response_text = "", ""
        self.retry_count = 0
        if self.wake_thread:
            self.wake_thread.pause()
        self._do_listen()

    def _start_interrupt_monitor(self):
        """Task 8: start background VAD monitor during TTS."""
        self._stop_interrupt_monitor()
        mon = InterruptMonitorThread()
        mon.interrupted.connect(self._on_tts_interrupted)
        mon.start()
        self._interrupt_monitor = mon

    def _stop_interrupt_monitor(self):
        """Stop the interrupt monitor thread if running."""
        mon = getattr(self, '_interrupt_monitor', None)
        if mon and mon.isRunning():
            mon.stop_monitor()
            mon.wait(300)
        self._interrupt_monitor = None

    def _on_tts_interrupted(self):
        """Task 8: called from InterruptMonitorThread when user speaks during TTS."""
        if self._tts_busy:
            self._interrupt_tts()
            QTimer.singleShot(80, self.start_listening)

    def _do_listen(self):
        """Внутрішній метод слухання."""
        from aivon_sphere import load_config  # type: ignore
        _fresh_cfg  = load_config()
        self.voice_thread = VoiceThread(
            _fresh_cfg.get("language", "uk-UA"), _fresh_cfg)
        self.voice_thread.started_signal.connect(
            lambda: setattr(self, 'state', self.LISTENING))
        self.voice_thread.partial.connect(
            lambda t: setattr(self, 'response_text', t))
        self.voice_thread.stopped.connect(self.on_voice_stopped)
        self.voice_thread.recognized_with_audio.connect(self._on_voice_with_audio)
        self.voice_thread.recognized.connect(self.on_recognized)
        self.voice_thread.recognized_with_conf.connect(self._on_stt_confidence)
        self.voice_thread.error.connect(self.on_error)
        self.voice_thread.start()

    def _on_voice_with_audio(self, text: str, audio_bytes: bytes):
        """Speaker verification slot."""
        if getattr(self, '_enrolling_voice', False):
            try:
                from core.voice_filter import get_voice_filter
                vf     = get_voice_filter()
                result = vf.enroll_sample(audio_bytes)
                self.respond(result["msg"])
                if result.get("ready"):
                    vf.set_enabled(True)
                    self._enrolling_voice = False
                    self.respond(
                        "✅ Фільтр голосу увімкнено! "
                        "Тепер сфера реагує тільки на ваш голос.")
            except Exception as e:
                self.respond(f"Помилка реєстрації голосу: {e}")
            return

        try:
            from core.voice_filter import get_voice_filter
            vf = get_voice_filter()
            if vf.enabled:
                res = vf.verify(audio_bytes)
                if not res["ok"]:
                    print(f"[VoiceFilter] Відхилено: score={res['score']} < threshold")
                    self.response_text = f"🚫 {res['score']:.0%}"
                    self.update()
                    QTimer.singleShot(1500, lambda: setattr(self, 'response_text', ''))
                    self._voice_rejected = True
                    return
        except Exception:
            pass
        self._voice_rejected = False

    def on_voice_stopped(self):
        if self.state == self.LISTENING:
            self.state = self.IDLE

    # ── Whisper loader helpers ────────────────────────────────────────────────
    def _load_whisper_model(self):
        """Завантажує Whisper модель у фоні."""
        if not HAS_WHISPER:
            print("[Whisper] faster-whisper не встановлено — pip install faster-whisper")
            return
        if WhisperSTT._instance:
            return
        model_size = self.config.get("whisper_model", "small")
        self.respond_silent(f"🧠 Завантажую Whisper '{model_size}'...")
        self._whisper_loader = WhisperLoader(model_size)
        self._whisper_loader.done.connect(self._on_whisper_loaded)
        self._whisper_loader.start()

    def _on_whisper_loaded(self, success: bool, msg: str):
        print(f"[Whisper] {msg}")
        if success:
            self.respond_silent(f"🧠 {msg}")
        else:
            self.respond_silent(f"⚠ {msg}")
