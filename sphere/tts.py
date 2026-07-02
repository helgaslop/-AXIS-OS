# -*- coding: utf-8 -*-
"""sphere/tts.py — TTS engines + queue mixin for AivonSphere."""

# NOTE: This file uses forward references to the parent class (AivonSphere).
# All self.* accesses work via multiple inheritance (SphereTTSMixin + AivonSphere).

import os
import sys
import time
import threading
import re
from PyQt6.QtCore import QThread, pyqtSignal, QTimer

# ── Standalone TTS classes (moved from aivon_sphere.py) ──────────────────────

class _DialogTTSThread(QThread):
    """TTS для діалогу — поважає tts_provider з конфігу.
    За замовчуванням edge-tts (безкоштовний), OpenAI тільки якщо явно вибраний."""
    done = pyqtSignal()

    def __init__(self, key, text, config, voice_override=None):
        super().__init__()
        self.key      = key
        self.text     = text[:500]
        self.config   = config
        self.provider = config.get("tts_provider", "edge")
        self.voice    = voice_override or config.get("voice", "onyx")
        self.speed    = config.get("tts_speed", 1.15)

    def run(self):
        # Безкоштовний edge-tts якщо provider != "openai"
        if self.provider != "openai":
            self._run_edge_tts()
            return
        try:
            import requests, tempfile
            r = requests.post("https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                json={"model": "tts-1", "input": self.text, "voice": self.voice,
                      "speed": self.speed, "response_format": "mp3"},
                timeout=10)
            if r.status_code != 200:
                print(f"[DialogTTS] OpenAI error {r.status_code} — fallback до edge-tts")
                self._run_edge_tts()
                return
            if r.status_code == 200:
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.write(r.content)
                tmp.close()
                try:
                    import pygame
                    if not pygame.mixer.get_init():
                        pygame.mixer.init(frequency=24000)
                    pygame.mixer.music.load(tmp.name)
                    pygame.mixer.music.play()
                    _tts_deadline = time.time() + 120
                    while pygame.mixer.music.get_busy() and time.time() < _tts_deadline:
                        time.sleep(0.05)
                    if time.time() >= _tts_deadline:
                        print("[TTS] ⚠ Playback timeout — force-stopping mixer")
                        try: pygame.mixer.music.stop()
                        except: pass
                except Exception:
                    if sys.platform == "win32":
                        import subprocess
                        _NO_WINDOW = subprocess.CREATE_NO_WINDOW
                        subprocess.run(["powershell", "-c",
                            f'(New-Object Media.SoundPlayer "{tmp.name}").PlaySync()'],
                            capture_output=True, timeout=15,
                            creationflags=_NO_WINDOW)
                try:
                    os.remove(tmp.name)
                except Exception:
                    pass
        except Exception as e:
            print(f"[Dialog TTS] OpenAI error: {e} — fallback до edge-tts")
            self._run_edge_tts()
            return
        self.done.emit()

    def _run_edge_tts(self):
        """Fallback на безкоштовний edge-tts."""
        try:
            import asyncio, tempfile, os as _os
            import edge_tts
            voice    = self.config.get("edge_voice", "uk-UA-PolinaNeural")
            speed    = float(self.config.get("tts_speed", 1.0))
            delta    = speed - 1.0
            rate_str = f"+{int(delta*100)}%" if delta >= 0 else f"{int(delta*100)}%"
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            async def _gen():
                c = edge_tts.Communicate(self.text, voice, rate=rate_str)
                await c.save(tmp.name)
            asyncio.run(_gen())
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=24000)
                pygame.mixer.music.load(tmp.name)
                pygame.mixer.music.play()
                _tts_deadline = time.time() + 120
                while pygame.mixer.music.get_busy() and time.time() < _tts_deadline:
                    time.sleep(0.05)
                if time.time() >= _tts_deadline:
                    print("[TTS] ⚠ Playback timeout — force-stopping mixer")
                    try: pygame.mixer.music.stop()
                    except: pass
            except Exception:
                pass
            try:
                _os.remove(tmp.name)
            except Exception:
                pass
        except Exception as e:
            print(f"[Dialog TTS] edge-tts error: {e}")
        self.done.emit()


class TTSThread(QThread):
    """OpenAI TTS - говорить напряму без плеєра"""
    done = pyqtSignal()

    def __init__(self, key, text, voice="onyx", speed=1.15):
        super().__init__()
        self.key, self.text, self.voice, self.speed = key, text, voice, speed

    def run(self):
        if not self.key or not self.text:
            self.done.emit()
            return

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.key)
            print(f"TTS: '{self.text[:30]}...'")

            # WAV формат для кращої сумісності
            res = client.audio.speech.create(
                model="tts-1",
                voice=self.voice,
                input=self.text[:4000],
                response_format="mp3",
                speed=self.speed
            )

            # Зберігаємо тимчасовий файл
            temp_path = os.path.join(os.environ.get('TEMP', '/tmp'), "axis_speech.mp3")
            with open(temp_path, 'wb') as f:
                f.write(res.content)

            # Відтворюємо напряму
            played = False

            # Спроба 1: pygame
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()
                _tts_deadline = time.time() + 120
                while pygame.mixer.music.get_busy() and time.time() < _tts_deadline:
                    time.sleep(0.1)
                if time.time() >= _tts_deadline:
                    print("[TTS] ⚠ Playback timeout — force-stopping mixer")
                    try: pygame.mixer.music.stop()
                    except: pass
                played = True
                print(f"TTS: pygame OK (speed={self.speed})")
            except Exception as e:
                print(f"TTS pygame: {e}")

            # Спроба 2: playsound / powershell fallback
            if not played and sys.platform == "win32":
                try:
                    import subprocess
                    _NO_WINDOW = subprocess.CREATE_NO_WINDOW
                    subprocess.run(
                        ['powershell', '-Command',
                         f'Add-Type -AssemblyName PresentationCore; '
                         f'$p=New-Object System.Windows.Media.MediaPlayer; '
                         f'$p.Open([Uri]"{temp_path}"); $p.Play(); '
                         f'Start-Sleep -Milliseconds 500; '
                         f'while($p.Position -lt $p.NaturalDuration.TimeSpan){{Start-Sleep -Milliseconds 100}}; '
                         f'$p.Close()'],
                        capture_output=True, timeout=30,
                        creationflags=_NO_WINDOW)
                    played = True
                    print("TTS: powershell MediaPlayer OK")
                except Exception as e:
                    print(f"TTS powershell: {e}")

            # Видаляємо файл
            try:
                time.sleep(0.2)
                os.remove(temp_path)
            except Exception:
                pass

        except Exception as e:
            print(f"TTS error: {e}")

        self.done.emit()


# ── TTS Mixin ────────────────────────────────────────────────────────────────

class SphereTTSMixin:
    """TTS queue and engine methods. Mixed into AivonSphere."""

    def _stop_tts(self):
        """Зупинити поточне озвучення (очистити чергу TTS)."""
        self._tts_queue.clear()
        self._tts_busy = False
        getattr(self, '_tts_prefetch', {}).clear()
        # Stop any currently playing audio
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.stop()
        except Exception:
            pass

    def _interrupt_tts(self):
        """Task 1+8: stop TTS playback AND abort in-flight AI generation."""
        print("[TTS] ⚡ Interrupted by user voice")
        # Task 1: abort AIThread — stops streaming generation
        ai_t = getattr(self, '_current_ai_thread', None)
        if ai_t is not None:
            ai_t.abort()
            self._current_ai_thread = None
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.stop()
        except Exception:
            pass
        # Stop any running TTS thread
        tts_t = getattr(self, '_current_tts_thread', None)
        if tts_t and hasattr(tts_t, 'requestInterruption'):
            tts_t.requestInterruption()
        # Stop interrupt monitor (it already released the mic before signalling)
        self._stop_interrupt_monitor()
        self._tts_queue.clear()
        self._tts_busy = False
        getattr(self, '_tts_prefetch', {}).clear()
        self._tg_stream_suppress = False

    def respond(self, text):
        """Додає відповідь у чергу TTS — виконує послідовно, не накладаючи"""
        self.hologram_auto_gesture(text)
        # Save to conversation memory
        try:
            if getattr(self, '_last_user_text', ''):
                self._save_memory(self._last_user_text, text)
        except Exception:
            pass

        # ── Mode-aware behavior ──
        mode = getattr(self, '_mode', 'normal')
        mode_cfg = self._MODE_CONFIGS.get(mode, self._MODE_CONFIGS["normal"])

        # Quiet mode: skip TTS, send to Telegram only
        if mode == "quiet" and not self.config.get("tts_enabled", True):
            self.state = self.SPEAKING
            self.response_text = text
            from PyQt6.QtCore import QTimer as _QT
            _QT.singleShot(1500, self._on_all_tts_done)
            self._tg_send(text)
            return

        # Game mode: shorten response for TTS (keep full for Telegram)
        if mode_cfg.get("short_responses") and len(text) > 80:
            # Only shorten for TTS — keep first sentence or 80 chars
            short = re.split(r'[.!?]', text)[0].strip()
            if len(short) > 80:
                short = short[:77] + "..."
            tts_text = short
        else:
            tts_text = text

        with self._tts_lock:
            self._tts_queue.append(tts_text)
            _should_play = not self._tts_busy
        if _should_play:
            self._play_next_tts()
        # Telegram: відправляємо повну відповідь в чат
        # (при streaming речення не шлемо окремо — повний текст піде наприкінці)
        if not getattr(self, '_tg_stream_suppress', False):
            self._tg_send(text)

    def respond_silent(self, text):
        """Показує текст на сфері БЕЗ озвучки TTS (для дій/команд)"""
        self.hologram_auto_gesture(text)
        self.state = self.SPEAKING
        self.response_text = text
        QTimer.singleShot(2000, self._on_all_tts_done)
        # Telegram: відправляємо відповідь в чат
        self._tg_send(text)

    def _play_next_tts(self):
        """Відтворює наступну відповідь з черги"""
        if not self._tts_queue:
            self._tts_busy = False
            self._on_all_tts_done()
            return

        self._tts_busy = True
        text = self._tts_queue.pop(0)
        self.state = self.SPEAKING
        self.response_text = text

        # Task 8: interrupt monitor стартує НЕ тут, а в TTS-движку одразу після
        # початку відтворення (pygame.play) — щоб baseline RMS замірявся під час
        # реального звучання TTS, інакше сфера переб'є сама себе.

        # Пауза wake word під час говоріння (щоб не чула сама себе)
        if self.wake_thread:
            self.wake_thread.pause()

        # Чекаємо поки JARVIS звук догравань (не блокуючи GUI)
        try:
            import pygame
            if pygame.mixer.get_busy():
                QTimer.singleShot(200, lambda: self._play_next_tts_after_jarvis(text))
                return
        except Exception:
            pass

        self._start_tts(text)

    def _play_next_tts_after_jarvis(self, text, _attempt=0):
        """Чекаємо поки JARVIS звук закінчиться, потім запускаємо TTS"""
        if _attempt > 200:
            print("[TTS] _play_next_tts_after_jarvis timeout — forcing start")
            self._start_tts(text)
            return
        try:
            import pygame
            if pygame.mixer.get_busy():
                QTimer.singleShot(150, lambda: self._play_next_tts_after_jarvis(text, _attempt + 1))
                return
        except Exception:
            pass
        self._start_tts(text)

    @staticmethod
    def _strip_html_for_tts(text: str) -> str:
        """Remove HTML tags and decode entities so TTS doesn't speak markup."""
        # Remove all <tags>
        clean = re.sub(r'<[^>]+>', ' ', text)
        # Decode common HTML entities
        clean = (clean
                 .replace('&amp;',  '&')
                 .replace('&lt;',   '<')
                 .replace('&gt;',   '>')
                 .replace('&nbsp;', ' ')
                 .replace('&#39;',  "'")
                 .replace('&quot;', '"')
                 .replace('&mdash;', '—')
                 .replace('&ndash;', '–'))
        # Collapse whitespace
        clean = re.sub(r'[ \t]+', ' ', clean).strip()
        return clean

    def _start_tts(self, text):
        """Озвучка тексту — маршрутизація за tts_provider"""
        # Strip HTML tags before any TTS engine receives the text
        text = self._strip_html_for_tts(text)
        if not text:
            self._on_single_tts_done()
            return
        if self.hologram_mode and getattr(self, '_holo_view', None):
            safe_text = text.replace("'", "\\'").replace("\n", " ")[:500]
            lang = self.config.get("language", "uk-UA")
            self._holo_view.page().runJavaScript(
                f"window.speakWithLipSync('{safe_text}', '{lang}', 1.0)")
            duration = max(2000, int(len(text) / 80 * 1000) + 500)
            QTimer.singleShot(duration, self._on_single_tts_done)
        else:
            provider = self.config.get("tts_provider", "auto")
            oai_key  = self.config.get("openai_key", "")
            if provider == "nari_dia":
                threading.Thread(target=self._nari_tts,   args=(text,),          daemon=True).start()
            elif provider == "silero_ua":
                threading.Thread(target=self._silero_tts,  args=(text,),          daemon=True).start()
            elif provider == "edge":
                threading.Thread(target=self._edge_tts,   args=(text,),          daemon=True).start()
            elif provider == "openai" and oai_key:
                threading.Thread(target=self._openai_tts, args=(text, oai_key),  daemon=True).start()
            elif provider == "openai" and not oai_key:
                threading.Thread(target=self._edge_tts,   args=(text,),          daemon=True).start()
            else:  # auto → завжди edge-tts (безкоштовний), економить токени клієнта
                threading.Thread(target=self._edge_tts, args=(text,), daemon=True).start()

    def _edge_tts(self, text):
        """edge-tts — безкоштовний Microsoft Neural TTS (підтримує українську)"""
        try:
            import asyncio, tempfile, os as _os
            try:
                import edge_tts
            except ImportError:
                raise ImportError("edge-tts не встановлено. Запусти: pip install edge-tts")
            voice     = self.config.get("edge_voice", "uk-UA-PolinaNeural")
            speed_val = float(self.config.get("tts_speed", 1.0))
            delta     = speed_val - 1.0
            rate_str  = f"+{int(delta*100)}%" if delta >= 0 else f"{int(delta*100)}%"

            async def _gen():
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.close()
                comm = edge_tts.Communicate(text[:4096], voice, rate=rate_str)
                await comm.save(tmp.name)
                return tmp.name

            loop = asyncio.new_event_loop()
            path = loop.run_until_complete(_gen())
            loop.close()

            import pygame
            try:
                if pygame.mixer.get_init(): pygame.mixer.quit()
                pygame.mixer.init(frequency=24000)
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                if self.config.get("tts_interrupt_vad", False):
                    QTimer.singleShot(0, self._start_interrupt_monitor)
                _tts_deadline = time.time() + 120
                while pygame.mixer.music.get_busy() and time.time() < _tts_deadline:
                    time.sleep(0.05)
                if time.time() >= _tts_deadline:
                    print("[TTS] ⚠ Playback timeout — force-stopping mixer")
                    try: pygame.mixer.music.stop()
                    except: pass
                pygame.mixer.music.unload()
                print("[TTS] ✅ edge-tts done")
            finally:
                try: _os.unlink(path)
                except: pass
        except Exception as e:
            print(f"[TTS] ❌ edge-tts error: {e}")
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty('rate', 170)
                for v in engine.getProperty('voices'):
                    if 'ru-ru' in v.id.lower():
                        engine.setProperty('voice', v.id); break
                engine.say(text)
                engine.runAndWait()
            except Exception as e2:
                print(f"[TTS] pyttsx3 fallback error: {e2}")
        finally:
            QTimer.singleShot(0, self._on_single_tts_done)

    def _silero_tts(self, text):
        """Silero TTS v3_ua — локальна українська нейро-TTS (CPU, ~50MB модель)"""
        _fallback = False
        try:
            import torch, tempfile, os as _os
            if not getattr(self, '_silero_model', None):
                with self._silero_lock:
                    if not getattr(self, '_silero_model', None):
                        print("[Silero] ⏳ Завантаження моделі uk-UA (перший запуск)...")
                        self._silero_model, _ = torch.hub.load(
                            repo_or_dir='snakers4/silero-models',
                            model='silero_tts',
                            language='ua',
                            speaker='v3_ua',
                            trust_repo=True
                        )
                        self._silero_model.to(torch.device('cpu'))
                        print("[Silero] ✅ Модель завантажена")
            speaker  = self.config.get("silero_speaker", "mykyta")
            sr       = 48000
            audio    = self._silero_model.apply_tts(
                text=text[:500],
                speaker=speaker,
                sample_rate=sr
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            import scipy.io.wavfile as wav
            import numpy as np
            wav.write(tmp.name, sr, (audio.numpy() * 32767).astype(np.int16))
            try:
                import pygame
                if pygame.mixer.get_init() and pygame.mixer.get_init()[0] != 48000: pygame.mixer.quit()
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=48000)
                speed = float(self.config.get("tts_speed", 1.0))
                pygame.mixer.music.load(tmp.name)
                pygame.mixer.music.play()
                _tts_deadline = time.time() + 120
                while pygame.mixer.music.get_busy() and time.time() < _tts_deadline:
                    import time; time.sleep(0.05)
                if time.time() >= _tts_deadline:
                    print("[TTS] ⚠ Playback timeout — force-stopping mixer")
                    try: pygame.mixer.music.stop()
                    except: pass
                pygame.mixer.music.unload()
                print("[TTS] ✅ Silero done")
            finally:
                try: _os.unlink(tmp.name)
                except: pass
        except Exception as e:
            print(f"[TTS] ❌ Silero error: {e} — перемикаюсь на edge-tts")
            self._silero_model = None
            _fallback = True
            threading.Thread(target=self._edge_tts, args=(text,), daemon=True).start()
        finally:
            if not _fallback:
                QTimer.singleShot(0, self._on_single_tts_done)

    def _nari_tts(self, text):
        """Nari Labs Dia 1.6B — локальна нейро-TTS (тільки англійська!)"""
        try:
            try:
                from dia.model import Dia
            except ImportError:
                raise ImportError(
                    "Nari Dia не встановлено. Запусти:\n"
                    "pip install git+https://github.com/nari-labs/dia.git sounddevice")
            if not getattr(self, '_dia_model', None):
                with self._dia_lock:
                    if not getattr(self, '_dia_model', None):
                        print("[Nari Dia] ⏳ Завантаження моделі (перший запуск — може зайняти хвилину)...")
                        self._dia_model = Dia.from_pretrained("nari-labs/Dia-1.6B", compute_dtype="float16")
                        print("[Nari Dia] ✅ Модель завантажена")
            audio = self._dia_model.generate(f"[S1] {text[:500]}")
            if audio is not None and len(audio) > 0:
                import sounddevice as sd
                sd.play(audio, samplerate=44100)
                sd.wait()
            print("[TTS] ✅ Nari Dia done")
        except Exception as e:
            print(f"[TTS] ❌ Nari Dia error: {e} — перемикаюсь на edge-tts")
            self._dia_model = None
            # Викликаємо edge-tts без finally (вони самі викличуть _on_single_tts_done)
            threading.Thread(target=self._edge_tts, args=(text,), daemon=True).start()
            return  # Пропускаємо finally нижче
        QTimer.singleShot(0, self._on_single_tts_done)

    def _generate_openai_mp3(self, text, key) -> bytes:
        """Генерує MP3 через OpenAI TTS API (без відтворення)."""
        import requests
        voice = self.config.get("voice", "onyx")
        speed = self.config.get("tts_speed", 1.15)
        r = requests.post("https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "tts-1", "input": text[:4096], "voice": voice,
                  "response_format": "mp3", "speed": speed}, timeout=15)
        if r.status_code != 200:
            raise Exception(f"TTS HTTP {r.status_code}: {r.text[:100]}")
        return r.content

    def _prefetch_next_tts(self, key):
        """Поки грає поточне речення — генеруємо MP3 наступного (без пауз)."""
        try:
            with self._tts_lock:
                nxt = self._tts_queue[0] if self._tts_queue else None
            if not nxt:
                return
            nxt = self._strip_html_for_tts(nxt)
            if not nxt:
                return
            if not hasattr(self, '_tts_prefetch'):
                self._tts_prefetch = {}
            if nxt in self._tts_prefetch:
                return
            def _gen(t=nxt):
                try:
                    self._tts_prefetch[t] = self._generate_openai_mp3(t, key)
                    print(f"[TTS] ⏩ prefetched next: '{t[:40]}...'")
                except Exception:
                    pass
            threading.Thread(target=_gen, daemon=True).start()
        except Exception:
            pass

    def _openai_tts(self, text, key):
        """OpenAI TTS — високоякісний голос"""
        try:
            import tempfile
            print(f"[TTS] OpenAI text={text[:50]}...")
            data = None
            if hasattr(self, '_tts_prefetch'):
                data = self._tts_prefetch.pop(text, None)
            if data is not None:
                print("[TTS] ⚡ using prefetched MP3")
            else:
                data = self._generate_openai_mp3(text, key)
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.write(data)
            tmp.close()
            print(f"[TTS] MP3 saved: {len(data)} bytes")
            # Поки це речення грає — заздалегідь генеруємо наступне з черги
            self._prefetch_next_tts(key)
            try:
                import pygame
                if pygame.mixer.get_init(): pygame.mixer.quit()
                pygame.mixer.init(frequency=24000)
                pygame.mixer.music.load(tmp.name)
                pygame.mixer.music.play()
                # Barge-in: монітор стартує коли TTS РЕАЛЬНО звучить,
                # щоб baseline включав гучність власного голосу з динаміків
                if self.config.get("tts_interrupt_vad", False):
                    QTimer.singleShot(0, self._start_interrupt_monitor)
                _tts_deadline = time.time() + 120
                while pygame.mixer.music.get_busy() and time.time() < _tts_deadline:
                    time.sleep(0.05)
                if time.time() >= _tts_deadline:
                    print("[TTS] ⚠ Playback timeout — force-stopping mixer")
                    try: pygame.mixer.music.stop()
                    except: pass
                pygame.mixer.music.unload()
                print("[TTS] ✅ Playback done")
            finally:
                try: os.unlink(tmp.name)
                except: pass
        except Exception as e:
            print(f"[TTS] ❌ OpenAI TTS error: {e}")
            raise
        finally:
            QTimer.singleShot(0, self._on_single_tts_done)

    def _on_single_tts_done(self):
        """Один TTS закінчився — переходимо до наступного в черзі"""
        # Task 8: stop interrupt monitor when this TTS segment ends
        self._stop_interrupt_monitor()
        with self._tts_lock:
            _has_more = bool(self._tts_queue)
            if not _has_more:
                self._tts_busy = False
        if _has_more:
            QTimer.singleShot(300, self._play_next_tts)
        else:
            self._on_all_tts_done()

    def _on_all_tts_done(self):
        """Вся черга TTS завершена — можна слухати далі"""
        # Streaming: AI ще генерує наступні речення — не вмикаємо мікрофон,
        # інакше сфера почне слухати посеред власної відповіді.
        # Після завершення генерації _on_stream_finished викличе нас знову.
        if getattr(self, '_stream_generating', False):
            return
        self.state = self.IDLE

        # ═══ ДІАЛОГ РЕЖИМ: бесшовний loop ═══
        if self.sphere_mode == "dialog":
            # НЕ ховаємо сферу! Одразу слухаємо далі через 0.5с
            print("[Dialog] TTS done → auto listen in 0.5s")
            QTimer.singleShot(500, self.start_listening)
            return

        if not self.is_hidden:
            # Сфера видима — продовжуємо слухати
            QTimer.singleShot(800, self.start_listening)
        else:
            # Сфера в треї — тільки wake word listener
            if self.wake_thread:
                QTimer.singleShot(800, self.wake_thread.resume)

    def _auto_hide(self):
        """Автоприховування після відповіді"""
        if self.state == self.IDLE:
            self.clear()
            self.hide_orb()
