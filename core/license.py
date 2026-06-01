"""AXIS OS — License Manager
Offline validation now. Server-ready: see _validate_server() placeholder below.
"""
import hashlib
import hmac
import json
import os
import platform
from datetime import datetime, timedelta
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
_SECRET      = os.environ.get("AXIS_LICENSE_SECRET", "AXIS-OS-LICENSE-2024-V1")
_TRIAL_DAYS  = 7
_SERVER_URL  = "https://api.axis-os.app"   # Uncomment when server is ready

TIERS = {
    "trial":    {"name": "Пробний",  "emoji": "⏳", "days": _TRIAL_DAYS},
    "monthly":  {"name": "Місячний", "emoji": "📅", "days": 30},
    "yearly":   {"name": "Річний",   "emoji": "🌟", "days": 365},
    "lifetime": {"name": "Назавжди", "emoji": "♾️",  "days": -1},
}

# ── Trial limits (per day; -1 = fully disabled) ────────────────────────────────
TRIAL_LIMITS: dict[str, int] = {
    "ai_messages":    20,   # AI chat messages per day
    "voice_commands": 30,   # voice commands per day
    "agents":         -1,   # AI Agents — disabled in trial
    "image_gen":      -1,   # Image/Video generation — disabled in trial
}

_TRIAL_BLOCKED_MSG: dict[str, str] = {
    "ai_messages":    "⏳ Пробний план: ліміт 20 AI повідомлень/день вичерпано. Активуй ліцензію.",
    "voice_commands": "⏳ Пробний план: ліміт 30 голосових команд/день вичерпано. Активуй ліцензію.",
    "agents":         "🔒 AI Агенти доступні лише на платному плані. Активуй ліцензію.",
    "image_gen":      "🔒 Генерація зображень/відео доступна лише на платному плані. Активуй ліцензію.",
}

# tier char → tier name
_TIER_CHAR = {"M": "monthly", "Y": "yearly", "L": "lifetime", "T": "trial"}
_CHAR_TIER = {v: k for k, v in _TIER_CHAR.items()}


class LicenseManager:
    """Manages AXIS OS license: trial, activation, status.

    Architecture is server-ready:
    - activate() calls _validate_local() now
    - Replace with _validate_server() when backend is live (1 line change)
    """

    def __init__(self, data_dir: Path):
        self._file = data_dir / "license.json"
        self._data = self._load()

    # ── Public API ─────────────────────────────────────────────────────────────
    def get_status(self) -> dict:
        """Return full license status dict for the UI."""
        tier        = self._data.get("tier", "trial")
        expires_str = self._data.get("expires")
        key         = self._data.get("key")

        if tier == "lifetime":
            return {
                "tier": "lifetime", "active": True,
                "days_left": -1, "expires": None,
                "name": TIERS["lifetime"]["name"],
                "emoji": TIERS["lifetime"]["emoji"],
                "key": key,
            }

        days_left = 0
        if expires_str:
            try:
                exp = datetime.fromisoformat(expires_str)
                days_left = max(0, (exp - datetime.now()).days)
            except Exception:
                pass

        active = days_left > 0
        base = {
            "tier": tier,
            "active": active,
            "days_left": days_left,
            "expires": expires_str,
            "name": TIERS.get(tier, {}).get("name", tier),
            "emoji": TIERS.get(tier, {}).get("emoji", ""),
            "key": key,
        }
        if tier == "trial":
            usage = self._today_usage()
            base["trial_usage"] = {
                feat: {"used": usage.get(feat, 0), "limit": lim}
                for feat, lim in TRIAL_LIMITS.items()
            }
        return base

    def activate(self, key: str) -> dict:
        """Activate license key.
        Tries Netlify server first (new AXIS-XXXX format),
        falls back to local HMAC (old AXIS-T-DDD format).
        """
        k = key.strip().upper().replace("-", "").replace(" ", "")
        if k.startswith("AXIS"):
            k = k[4:]
        # New-format key: first char is NOT a tier char → server validation
        if not k or k[0] not in ("M", "Y", "L", "T"):
            result = self._validate_server(key)
            if result.get("ok"):
                return result
            # If server unreachable, try local (for dev/offline)
            return result
        # Old HMAC key
        return self._validate_local(key)

    def days_left(self) -> int:
        st = self.get_status()
        return st["days_left"]

    def is_active(self) -> bool:
        return self.get_status()["active"]

    def tier(self) -> str:
        return self._data.get("tier", "trial")

    def is_trial(self) -> bool:
        return self._data.get("tier", "trial") == "trial"

    # ── Trial usage tracking ───────────────────────────────────────────────────
    def check(self, feature: str) -> dict:
        """Check if a feature is allowed under current license.
        Returns {"ok": bool, "msg": str, "used": int, "limit": int}
        Paid tiers always return ok=True.
        """
        if not self.is_trial():
            return {"ok": True, "msg": "", "used": 0, "limit": -1}

        limit = TRIAL_LIMITS.get(feature, -1)
        if limit == -1:
            # Feature completely disabled in trial
            return {"ok": False, "msg": _TRIAL_BLOCKED_MSG.get(feature, "🔒 Недоступно в пробному плані."),
                    "used": 0, "limit": 0}

        used = self._today_usage().get(feature, 0)
        if used >= limit:
            return {"ok": False, "msg": _TRIAL_BLOCKED_MSG.get(feature, "⏳ Ліміт вичерпано."),
                    "used": used, "limit": limit}

        return {"ok": True, "msg": "", "used": used, "limit": limit}

    def consume(self, feature: str) -> dict:
        """Check + increment usage counter. Returns same dict as check().
        Call this right before performing the action.
        """
        result = self.check(feature)
        if not result["ok"]:
            return result
        if self.is_trial() and TRIAL_LIMITS.get(feature, -1) > 0:
            usage = self._today_usage()
            usage[feature] = usage.get(feature, 0) + 1
            self._data["trial_usage"] = {
                "date":  datetime.now().strftime("%Y-%m-%d"),
                "counts": usage,
            }
            self._save()
        return result

    def _today_usage(self) -> dict:
        """Return today's usage counters, resetting if date changed."""
        entry = self._data.get("trial_usage", {})
        today = datetime.now().strftime("%Y-%m-%d")
        if entry.get("date") != today:
            return {}
        return dict(entry.get("counts", {}))

    # ── Key validation (offline) ───────────────────────────────────────────────
    def _validate_local(self, raw_key: str) -> dict:
        """Offline HMAC-based key validation.

        Key format: AXIS-T-DDD-EEEEEEEE-CCCC (with dashes stripped for parsing)
          T        = tier char (M/Y/L/T)
          DDD      = days in hex (e.g. 01E = 30)
          EEEEEEEE = expiry unix timestamp hex (0 = lifetime)
          CCCC     = first 4 hex chars of HMAC-SHA256(payload)
        """
        key = raw_key.strip().upper().replace("-", "").replace(" ", "")
        # Strip the human-readable "AXIS" prefix produced by generate_key()
        if key.startswith("AXIS"):
            key = key[4:]
        if len(key) < 12:
            return {"ok": False, "message": "Невірний формат ключа"}

        try:
            tier_char  = key[0]
            days_hex   = key[1:4]
            expiry_hex = key[4:12]
            checksum   = key[12:16]

            tier = _TIER_CHAR.get(tier_char)
            if not tier:
                return {"ok": False, "message": "Невідомий тип ліцензії"}

            payload  = f"{tier_char}{days_hex}{expiry_hex}"
            expected = hmac.new(
                _SECRET.encode(), payload.encode(), hashlib.sha256
            ).hexdigest()[:4].upper()

            if not hmac.compare_digest(expected, checksum):
                return {"ok": False, "message": "Ключ недійсний — перевірте правильність"}

            # Parse expiry
            expiry_ts = int(expiry_hex, 16)
            if expiry_ts > 0:
                expiry_dt = datetime.fromtimestamp(expiry_ts)
                if expiry_dt < datetime.now():
                    return {"ok": False, "message": "Термін дії ключа закінчився"}
                expires_iso = expiry_dt.isoformat()
            else:
                expires_iso = None  # lifetime

            self._data.update({
                "tier":    tier,
                "key":     raw_key.strip().upper(),
                "expires": expires_iso,
            })
            self._save()
            tier_name = TIERS.get(tier, {}).get("name", tier)
            return {"ok": True, "tier": tier, "message": f"✅ Активовано: {tier_name}!"}

        except Exception as e:
            return {"ok": False, "message": f"Помилка: {e}"}

    # ── Server validation (Netlify license-check function) ────────────────────
    def _validate_server(self, key: str) -> dict:
        """Online key validation against Netlify license-check function."""
        import urllib.request, urllib.error, json as _json
        license_url = os.environ.get(
            "AXIS_LICENSE_CHECK_URL",
            "https://helgaslop-axis-os.netlify.app/.netlify/functions/license-check"
        )
        try:
            payload = _json.dumps({
                "key": key.strip().upper(),
                "deviceId": self._machine_id()
            }).encode("utf-8")
            req = urllib.request.Request(
                license_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = _json.loads(r.read().decode("utf-8"))

            if data.get("valid"):
                tier = data.get("plan", "monthly")
                # Map plan → expiry
                from datetime import timedelta
                days_map = {"monthly": 30, "yearly": 365, "lifetime": -1}
                days = days_map.get(tier, 30)
                if days > 0:
                    expires_iso = (datetime.now() + timedelta(days=days)).isoformat()
                else:
                    expires_iso = None
                self._data.update({
                    "tier":    tier,
                    "key":     key.strip().upper(),
                    "expires": expires_iso,
                })
                self._save()
                tier_name = TIERS.get(tier, {}).get("name", tier)
                return {"ok": True, "tier": tier,
                        "message": f"✅ Активовано: {tier_name}!"}
            else:
                error = data.get("error", "Ключ недійсний")
                return {"ok": False, "message": f"❌ {error}"}

        except urllib.error.URLError:
            return {"ok": False,
                    "message": "🌐 Немає з'єднання з сервером ліцензій. Перевірте інтернет."}
        except Exception as e:
            return {"ok": False, "message": f"Помилка: {str(e)[:80]}"}

    # ── Key generator (admin tool) ─────────────────────────────────────────────
    @classmethod
    def generate_key(cls, tier: str = "monthly", days: int = 30) -> str:
        """Generate a valid license key.
        Run from console: python -c "from core.license import LicenseManager; print(LicenseManager.generate_key('monthly', 30))"
        """
        tc = _CHAR_TIER.get(tier, "M")
        if tier == "lifetime" or days < 0:
            expiry_ts = 0
            days_val  = 0
        else:
            expiry_ts = int((datetime.now() + timedelta(days=days)).timestamp())
            days_val  = days

        days_hex   = f"{days_val:03X}"
        expiry_hex = f"{expiry_ts:08X}"
        payload    = f"{tc}{days_hex}{expiry_hex}"
        checksum   = hmac.new(
            _SECRET.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()[:4].upper()

        raw = payload + checksum
        # Format: AXIS-T-DDD-EEEEEEEE-CCCC
        return f"AXIS-{raw[0]}-{raw[1:4]}-{raw[4:12]}-{raw[12:16]}"

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _load(self) -> dict:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self._init_trial()

    def _init_trial(self) -> dict:
        data = {
            "tier":       "trial",
            "started":    datetime.now().isoformat(),
            "expires":    (datetime.now() + timedelta(days=_TRIAL_DAYS)).isoformat(),
            "key":        None,
            "machine_id": self._machine_id(),
        }
        self._save(data)
        return data

    def _save(self, data: dict | None = None):
        if data is not None:
            self._data = data
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[License] save error: {e}")

    @staticmethod
    def _machine_id() -> str:
        raw = f"{platform.node()}-{platform.machine()}-{platform.processor()}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]
