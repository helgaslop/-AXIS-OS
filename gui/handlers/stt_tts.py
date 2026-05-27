"""Speech-to-Text and Text-to-Speech handlers."""
import json
import os
import threading


class SttTtsHandlerMixin:
    _stt_starting = False  # guard against rapid double-click race condition

    # ── STT ───────────────────────────────────────────────────────────────────
    def _start_stt(self, p: dict):
        mode         = p.get("mode", "single")
        lang         = p.get("lang", "uk-UA")
        device_index = p.get("device_index", -1)
        sensitivity  = p.get("sensitivity", 50)
        device_index = None if device_index == -1 else int(device_index)
        energy = int(600 - (sensitivity / 90) * 500)
        if mode == "live":
            # Prevent race: if already starting, ignore duplicate call
            if self._stt_starting:
                return
            self._stt_starting = True
            threading.Thread(target=self._stt_live_start,
                             args=(lang, device_index, energy), daemon=True).start()
        else:
            threading.Thread(target=self._stt_once,
                             args=(lang, device_index, energy), daemon=True).start()

    def _list_mic_devices(self, p: dict):
        try:
            import speech_recognition as sr
            names = sr.Microphone.list_microphone_names()
            self.push_to_js.emit("mic_devices", json.dumps(
                [{"index": i, "label": n} for i, n in enumerate(names)]))
        except Exception:
            self.push_to_js.emit("mic_devices", json.dumps([]))

    def _stop_stt(self, p: dict):
        self._stt_active = False
        if self._stt_bg_stop:
            try:
                self._stt_bg_stop(wait_for_stop=False)
            except Exception:
                pass
            self._stt_bg_stop = None

    def _stt_recognize(self, recognizer, audio, lang: str) -> str:
        import speech_recognition as sr
        openai_key = self._get_api_keys().get("openai", "")
        if openai_key:
            try:
                prev = os.environ.get("OPENAI_API_KEY", "")
                os.environ["OPENAI_API_KEY"] = openai_key
                try:
                    return recognizer.recognize_openai(
                        audio, model="whisper-1", language=lang.split("-")[0])
                finally:
                    if prev: os.environ["OPENAI_API_KEY"] = prev
                    else:    os.environ.pop("OPENAI_API_KEY", None)
            except Exception:
                pass
        try:
            return recognizer.recognize_google(audio, language=lang)
        except sr.UnknownValueError:
            return ""
        except Exception:
            raise

    def _stt_once(self, lang: str, device_index=None, energy: int = 300):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            r.pause_threshold = 0.9
            r.energy_threshold = energy
            self.push_to_js.emit("stt_status", json.dumps({"status": "listening"}))
            mic = sr.Microphone(device_index=device_index)
            with mic as source:
                r.adjust_for_ambient_noise(source, duration=0.4)
                audio = r.listen(source, timeout=10, phrase_time_limit=20)
            text = self._stt_recognize(r, audio, lang)
            if text:
                self.push_to_js.emit("stt_result",
                    json.dumps({"text": text, "mode": "single"}))
            else:
                self.push_to_js.emit("stt_status", json.dumps({"status": "no_speech"}))
        except Exception as e:
            err = str(e)
            if "pyaudio" in err.lower() or "portaudio" in err.lower():
                err = "Мікрофон недоступний. Встановіть pyaudio: pip install pyaudio"
            self.push_to_js.emit("stt_error", json.dumps({"error": err}))

    def _stt_live_start(self, lang: str, device_index=None, energy: int = 300):
        try:
            import speech_recognition as sr
            if self._stt_bg_stop:
                try: self._stt_bg_stop(wait_for_stop=False)
                except Exception: pass
                self._stt_bg_stop = None

            r = sr.Recognizer()
            r.pause_threshold = 0.8
            r.energy_threshold = energy
            mic = sr.Microphone(device_index=device_index)
            with mic as source:
                r.adjust_for_ambient_noise(source, duration=0.5)

            self._stt_active = True
            self._stt_starting = False  # done starting, reset guard
            self.push_to_js.emit("stt_status", json.dumps({"status": "live_ready"}))

            def on_phrase(recognizer, audio):
                if not self._stt_active:
                    return
                try:
                    text = self._stt_recognize(recognizer, audio, lang)
                    if text:
                        self.push_to_js.emit("stt_result",
                            json.dumps({"text": text, "mode": "live"}))
                except Exception:
                    pass

            self._stt_bg_stop = r.listen_in_background(mic, on_phrase, phrase_time_limit=15)
        except Exception as e:
            self._stt_starting = False
            err = str(e)
            if "pyaudio" in err.lower() or "portaudio" in err.lower():
                err = "Мікрофон недоступний. Встановіть pyaudio: pip install pyaudio"
            self.push_to_js.emit("stt_error", json.dumps({"error": err}))

    # ── TTS ───────────────────────────────────────────────────────────────────
    def _tts_speak(self, p: dict):
        text     = p.get("text", "")
        provider = p.get("provider", "openai")
        voice    = p.get("voice", "onyx")
        if text:
            threading.Thread(target=self._tts_worker,
                             args=(text, provider, voice), daemon=True).start()

    def _tts_worker(self, text: str, provider: str, voice: str):
        import base64, json as _json
        try:
            key = self._get_api_keys().get(provider, "")
            if not key:
                self.push_to_js.emit("tts_error",
                    _json.dumps({"error": f"API ключ «{provider}» не налаштовано"}))
                return

            if provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=key)
                resp = client.audio.speech.create(
                    model="tts-1", voice=voice or "onyx", input=text[:4096])
                audio_b64 = base64.b64encode(resp.content).decode()
                self.push_to_js.emit("tts_audio",
                    _json.dumps({"audio_b64": audio_b64, "format": "mp3"}))

            elif provider == "google":
                import requests as _req
                url  = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}"
                lang = voice.rsplit("-", 2)[0] if voice.count("-") >= 2 else "uk-UA"
                body = {
                    "input": {"text": text[:5000]},
                    "voice": {"languageCode": lang, "name": voice or "uk-UA-Wavenet-A"},
                    "audioConfig": {"audioEncoding": "MP3"},
                }
                r = _req.post(url, json=body, timeout=20)
                r.raise_for_status()
                audio_b64 = r.json().get("audioContent", "")
                self.push_to_js.emit("tts_audio",
                    _json.dumps({"audio_b64": audio_b64, "format": "mp3"}))

            elif provider == "xai":
                import requests as _req
                r = _req.post(
                    "https://api.x.ai/v1/audio/speech",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={"model": "grok-voice-think-fast-1", "input": text[:4096]},
                    timeout=30,
                )
                r.raise_for_status()
                audio_b64 = base64.b64encode(r.content).decode()
                self.push_to_js.emit("tts_audio",
                    _json.dumps({"audio_b64": audio_b64, "format": "mp3"}))

        except Exception as e:
            self.push_to_js.emit("tts_error", _json.dumps({"error": str(e)}))
