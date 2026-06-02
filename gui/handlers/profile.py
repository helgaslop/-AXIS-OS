"""AXIS OS — Profile & Onboarding handler mixin."""
import json
from pathlib import Path


class ProfileHandlerMixin:

    def _profile_file(self) -> Path:
        from core.paths import USER_DATA_DIR
        return USER_DATA_DIR / "profile.json"

    def _onboarding_file(self) -> Path:
        from core.paths import USER_DATA_DIR
        return USER_DATA_DIR / "onboarding.json"

    def _stats_file(self) -> Path:
        from core.paths import USER_DATA_DIR
        return USER_DATA_DIR / "usage_stats.json"

    def _ai_style_file(self) -> Path:
        from core.paths import USER_DATA_DIR
        return USER_DATA_DIR / "ai_style.json"

    def _chat_memory_file(self) -> Path:
        from core.paths import USER_DATA_DIR
        return USER_DATA_DIR / "chat_memory.json"

    # ── Profile ───────────────────────────────────────────────────────────────
    def _get_profile(self, _):
        f = self._profile_file()
        data = {}
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        self.push_to_js.emit("profile_data", json.dumps(data))

    def _save_profile(self, p: dict):
        f = self._profile_file()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
            self.push_to_js.emit("toast", json.dumps({"msg": "✓ Профіль збережено"}))
        except Exception as e:
            print(f"[Profile] save error: {e}")

    # ── Onboarding ────────────────────────────────────────────────────────────
    def _get_onboarding_status(self, _):
        f = self._onboarding_file()
        data = {"done": False, "completed": False}
        if f.exists():
            try:
                saved = json.loads(f.read_text(encoding="utf-8"))
                # Migrate old files that only have "completed" but not "done"
                if saved.get("completed") and not saved.get("done"):
                    saved["done"] = True
                    f.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
                data = saved
            except Exception:
                pass
        self.push_to_js.emit("onboarding_status", json.dumps(data))

    def _complete_onboarding(self, p: dict):
        f = self._onboarding_file()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            # Both "done" and "completed" — JS checks "done", some code checks "completed"
            data = {"done": True, "completed": True, **p}
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.push_to_js.emit("onboarding_complete", json.dumps({"ok": True}))
        except Exception as e:
            print(f"[Onboarding] save error: {e}")

    # ── Stats ─────────────────────────────────────────────────────────────────
    def _increment_stat(self, p: dict):
        key = p.get("key", "")
        if not key:
            return
        f = self._stats_file()
        stats = {}
        if f.exists():
            try:
                stats = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        stats[key] = stats.get(key, 0) + 1
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[Stats] save error: {e}")

    # ── Chat memory ───────────────────────────────────────────────────────────
    def _save_chat_memory(self, p: dict):
        f = self._chat_memory_file()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            existing = []
            if f.exists():
                try:
                    existing = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if isinstance(existing, list):
                existing.append(p)
                existing = existing[-200:]  # keep last 200
            f.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[ChatMemory] save error: {e}")

    def _recall_chat_memory(self, p: dict):
        query = p.get("query", "").lower()
        f = self._chat_memory_file()
        results = []
        if f.exists():
            try:
                items = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(items, list):
                    results = [i for i in items
                                if query in json.dumps(i, ensure_ascii=False).lower()][-10:]
            except Exception:
                pass
        self.push_to_js.emit("chat_memory_results", json.dumps(results))

    # ── AI Style ──────────────────────────────────────────────────────────────
    def _get_ai_style(self, _):
        f = self._ai_style_file()
        data = {"style": "balanced", "tone": "friendly", "length": "medium"}
        if f.exists():
            try:
                data.update(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        self.push_to_js.emit("ai_style", json.dumps(data))

    def _set_ai_style(self, p: dict):
        f = self._ai_style_file()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
            self.push_to_js.emit("toast", json.dumps({"msg": "✓ Стиль AI збережено"}))
        except Exception as e:
            print(f"[AIStyle] save error: {e}")
