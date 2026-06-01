"""Spotify Web API handler for the AXIS OS panel."""
import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import threading
import time

# ── WinAPI constants (defined once at module level) ──────────────────────────
_WM_APPCOMMAND               = 0x0319
_APPCOMMAND_MEDIA_PLAY_PAUSE = 0x000E0000
_INPUT_KEYBOARD  = 1
_KEYEVENTF_KEYUP = 0x0002
_VK_MEDIA_PLAY_PAUSE = 0xB3

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT)]
    _anonymous_ = ("_input",)
    _fields_    = [("type", ctypes.c_ulong), ("_input", _U)]


def _open_spotify_app(uri: str = "spotify:", auto_play: bool = False) -> None:
    """Відкриває Spotify URI. Якщо auto_play=True — через 2с натискає медіа-Play."""
    try:
        subprocess.Popen(f'start "" "{uri}"', shell=True,
                         creationflags=0x08000000)
    except Exception:
        import webbrowser
        webbrowser.open(uri if uri != "spotify:" else "https://open.spotify.com")
    if auto_play:
        threading.Thread(target=_press_media_play, args=(2.0,), daemon=True).start()


def _press_media_play(delay: float = 2.0) -> None:
    """Waits delay seconds then sends WM_APPCOMMAND play/pause to Spotify window,
    falling back to a global SendInput media key if no window found."""
    time.sleep(delay)
    try:
        _WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool,
                                           ctypes.wintypes.HWND,
                                           ctypes.wintypes.LPARAM)
        hwnd_box = [0]
        def _cb(hwnd, _):
            cls = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, cls, 256)
            if "Chrome_WidgetWin" in cls.value or "SpotifyMainWindow" in cls.value:
                ln  = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(ln + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, ln + 1)
                if "Spotify" in buf.value or not buf.value:
                    hwnd_box[0] = hwnd
            return True
        ctypes.windll.user32.EnumWindows(_WNDENUMPROC(_cb), 0)
        if hwnd_box[0]:
            ctypes.windll.user32.PostMessageW(
                hwnd_box[0], _WM_APPCOMMAND, 0, _APPCOMMAND_MEDIA_PLAY_PAUSE)
            return
        # Fallback: global SendInput with media key
        down = _INPUT(type=_INPUT_KEYBOARD,
                      ki=_KEYBDINPUT(wVk=_VK_MEDIA_PLAY_PAUSE, dwFlags=0))
        up   = _INPUT(type=_INPUT_KEYBOARD,
                      ki=_KEYBDINPUT(wVk=_VK_MEDIA_PLAY_PAUSE, dwFlags=_KEYEVENTF_KEYUP))
        ctypes.windll.user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(_INPUT))
        time.sleep(0.05)
        ctypes.windll.user32.SendInput(1, ctypes.byref(up),   ctypes.sizeof(_INPUT))
    except Exception as e:
        print(f"[Spotify] _press_media_play: {e}")


def _get_any_device(sp) -> str | None:
    """Повертає device_id активного або першого доступного пристрою."""
    try:
        devs = (sp.devices() or {}).get("devices", [])
        for d in devs:
            if d.get("is_active"):
                return d["id"]
        if devs:
            # Активуємо перший доступний
            sp.transfer_playback(devs[0]["id"], force_play=False)
            return devs[0]["id"]
    except Exception:
        pass
    return None


class SpotifyHandlerMixin:
    _sp_instance = None

    def _get_sp(self):
        if SpotifyHandlerMixin._sp_instance:
            return SpotifyHandlerMixin._sp_instance
        keys = self._get_api_keys()
        cid  = keys.get("spotify_client_id", "")
        csec = keys.get("spotify_client_secret", "")
        if not cid or not csec:
            return None
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            from core.paths import SPOTIFY_TOKEN_FILE
            token_path = str(SPOTIFY_TOKEN_FILE)

            # Only init if a cached token file already exists — never block
            # the background thread waiting for browser OAuth flow.
            import os, json as _json
            if not os.path.exists(token_path):
                return None          # not authorised yet; use URI fallback

            # Validate the cached token has the required fields before using it
            try:
                with open(token_path, encoding="utf-8") as _f:
                    _tok = _json.load(_f)
                if not _tok.get("access_token") and not _tok.get("refresh_token"):
                    return None
            except Exception:
                return None

            auth = SpotifyOAuth(
                client_id=cid,
                client_secret=csec,
                redirect_uri="http://127.0.0.1:8000/callback",
                scope=(
                    "user-modify-playback-state "
                    "user-read-playback-state "
                    "user-read-currently-playing "
                    "user-read-playback-position "
                    "user-library-read "
                    "playlist-read-private"
                ),
                cache_path=token_path,
                open_browser=False,
            )
            SpotifyHandlerMixin._sp_instance = spotipy.Spotify(auth_manager=auth)
            return SpotifyHandlerMixin._sp_instance
        except Exception as e:
            print(f"[Spotify Panel] {e}")
            return None

    def _spotify_action(self, p: dict):
        threading.Thread(target=self._spotify_worker, args=(p,), daemon=True).start()

    def _spotify_worker(self, p: dict):
        action = p.get("action", "")
        sp = self._get_sp()

        # ── Поточний трек ──────────────────────────────────────────────────────
        if action == "current":
            if not sp:
                self.push_to_js.emit("spotify_track",
                    json.dumps({"error": "not_connected"}))
                return
            try:
                pb = sp.current_playback()
                if pb and pb.get("item"):
                    t      = pb["item"]
                    _imgs  = (t.get("album") or {}).get("images") or []
                    img    = _imgs[0]["url"] if _imgs else ""
                    _arts  = t.get("artists") or [{}]
                    self.push_to_js.emit("spotify_track", json.dumps({
                        "name":       t["name"],
                        "artist":     _arts[0].get("name", ""),
                        "album":      (t.get("album") or {}).get("name", ""),
                        "cover":      img,
                        "is_playing": pb.get("is_playing", False),
                        "progress":   pb.get("progress_ms", 0),
                        "duration":   t.get("duration_ms", 0),
                        "volume":     (pb.get("device") or {}).get("volume_percent", 50),
                        "shuffle":    pb.get("shuffle_state", False),
                        "uri":        t["uri"],
                    }))
                else:
                    self.push_to_js.emit("spotify_track", json.dumps({"idle": True}))
            except Exception as e:
                self.push_to_js.emit("spotify_track",
                    json.dumps({"error": str(e)[:80]}))

        # ── Play / Pause / Next / Prev ─────────────────────────────────────────
        elif action == "play":
            if sp:
                try:
                    sp.start_playback()
                    threading.Thread(target=self._delayed_track_push, args=(0.6,), daemon=True).start()
                except Exception as e:
                    if "no active device" in str(e).lower():
                        _open_spotify_app()
                    # else ignore

        elif action == "pause":
            if sp:
                try:    sp.pause_playback()
                except Exception as e: print(f"[Spotify] pause: {e}")
                threading.Thread(target=self._delayed_track_push, args=(0.4,), daemon=True).start()

        elif action == "next":
            if sp:
                try:    sp.next_track()
                except Exception as e: print(f"[Spotify] next: {e}")
                threading.Thread(target=self._delayed_track_push, args=(1.0,), daemon=True).start()

        elif action == "prev":
            if sp:
                try:    sp.previous_track()
                except Exception as e: print(f"[Spotify] prev: {e}")
                threading.Thread(target=self._delayed_track_push, args=(1.0,), daemon=True).start()

        # ── Гучність ──────────────────────────────────────────────────────────
        elif action == "volume":
            val = max(0, min(100, int(p.get("value", 50))))
            if sp:
                try:    sp.volume(val)
                except Exception as e: print(f"[Spotify] volume: {e}")

        # ── Шафл ──────────────────────────────────────────────────────────────
        elif action == "shuffle":
            state = bool(p.get("state", False))
            if sp:
                try:    sp.shuffle(state)
                except Exception as e: print(f"[Spotify] shuffle: {e}")

        # ── Програти трек за URI ───────────────────────────────────────────────
        elif action == "play_uri":
            uri = p.get("uri", "")
            if uri:
                if sp:
                    try:
                        device_id = _get_any_device(sp)
                        # Плейлісти, альбоми, артисти, колекція → context_uri
                        # Треки → uris=[]
                        _ctx_types = ("playlist", "album", "artist", "collection", "show", "episode")
                        is_context = any(f"spotify:{t}" in uri or uri == f"spotify:{t}" for t in _ctx_types)
                        if is_context:
                            sp.start_playback(device_id=device_id, context_uri=uri)
                        else:
                            sp.start_playback(device_id=device_id, uris=[uri])
                        threading.Thread(target=self._delayed_track_push,
                                         args=(1.2,), daemon=True).start()
                        return
                    except Exception as e:
                        err = str(e).lower()
                        if "no active device" in err or "404" in err or "premium" in err:
                            _open_spotify_app(uri, auto_play=True)
                            return
                        self.push_to_js.emit("toast",
                            json.dumps({"msg": f"⚠ Spotify: {str(e)[:50]}"}))
                else:
                    _open_spotify_app(uri, auto_play=True)

        # ── Пошук треків ──────────────────────────────────────────────────────
        elif action == "search":
            query = p.get("query", "").strip()
            if not sp or not query:
                self.push_to_js.emit("spotify_search", json.dumps([]))
                return
            try:
                res   = sp.search(q=query, type="track", limit=8)
                items = (res or {}).get("tracks", {}).get("items") or []
                tracks = [{
                    "name":   t["name"],
                    "artist": (t.get("artists") or [{}])[0].get("name", ""),
                    "album":  (t.get("album") or {}).get("name", ""),
                    "cover":  ((t.get("album") or {}).get("images") or [{}])[-1].get("url", ""),
                    "uri":    t["uri"],
                    "ms":     t.get("duration_ms", 0),
                } for t in items]
                self.push_to_js.emit("spotify_search", json.dumps(tracks))
            except Exception as e:
                self.push_to_js.emit("spotify_search", json.dumps([]))

    def _delayed_track_push(self, delay: float):
        import time
        time.sleep(delay)
        self._spotify_worker({"action": "current"})
