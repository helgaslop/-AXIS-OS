"""Spotify Web API handler for the AXIS OS panel."""
import json
import os
import threading


class SpotifyHandlerMixin:
    _sp_instance = None

    def _get_sp(self):
        if SpotifyHandlerMixin._sp_instance:
            return SpotifyHandlerMixin._sp_instance
        keys = self._cfg.get("api_keys", {})
        cid  = keys.get("spotify_client_id", "")
        csec = keys.get("spotify_client_secret", "")
        if not cid or not csec:
            return None
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            from core.paths import SPOTIFY_TOKEN_FILE
            auth = SpotifyOAuth(
                client_id=cid,
                client_secret=csec,
                redirect_uri="http://127.0.0.1:8888/callback",
                scope=(
                    "user-modify-playback-state "
                    "user-read-playback-state "
                    "user-read-currently-playing "
                    "user-read-playback-position "
                    "user-library-read "
                    "playlist-read-private"
                ),
                cache_path=str(SPOTIFY_TOKEN_FILE),
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
                    t   = pb["item"]
                    img = t["album"]["images"][0]["url"] if t["album"]["images"] else ""
                    self.push_to_js.emit("spotify_track", json.dumps({
                        "name":       t["name"],
                        "artist":     t["artists"][0]["name"],
                        "album":      t["album"]["name"],
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
                try:    sp.start_playback()
                except: pass
            threading.Thread(target=self._delayed_track_push, args=(0.6,), daemon=True).start()

        elif action == "pause":
            if sp:
                try:    sp.pause_playback()
                except: pass
            threading.Thread(target=self._delayed_track_push, args=(0.4,), daemon=True).start()

        elif action == "next":
            if sp:
                try:    sp.next_track()
                except: pass
            threading.Thread(target=self._delayed_track_push, args=(1.0,), daemon=True).start()

        elif action == "prev":
            if sp:
                try:    sp.previous_track()
                except: pass
            threading.Thread(target=self._delayed_track_push, args=(1.0,), daemon=True).start()

        # ── Гучність ──────────────────────────────────────────────────────────
        elif action == "volume":
            val = max(0, min(100, int(p.get("value", 50))))
            if sp:
                try:    sp.volume(val)
                except: pass

        # ── Шафл ──────────────────────────────────────────────────────────────
        elif action == "shuffle":
            state = bool(p.get("state", False))
            if sp:
                try:    sp.shuffle(state)
                except: pass

        # ── Програти трек за URI ───────────────────────────────────────────────
        elif action == "play_uri":
            uri = p.get("uri", "")
            if sp and uri:
                try:
                    sp.start_playback(uris=[uri])
                    threading.Thread(target=self._delayed_track_push,
                                     args=(1.2,), daemon=True).start()
                except Exception as e:
                    self.push_to_js.emit("toast",
                        json.dumps({"msg": f"⚠ Spotify: {str(e)[:50]}"}))

        # ── Пошук треків ──────────────────────────────────────────────────────
        elif action == "search":
            query = p.get("query", "").strip()
            if not sp or not query:
                self.push_to_js.emit("spotify_search", json.dumps([]))
                return
            try:
                res   = sp.search(q=query, type="track", limit=8)
                items = res["tracks"]["items"]
                tracks = [{
                    "name":   t["name"],
                    "artist": t["artists"][0]["name"],
                    "album":  t["album"]["name"],
                    "cover":  t["album"]["images"][-1]["url"] if t["album"]["images"] else "",
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
