"""License & AI subscriptions handler mixin."""
import json
import threading
import urllib.request
import urllib.error
from pathlib import Path


class LicenseHandlerMixin:

    # ── AXIS OS License ───────────────────────────────────────────────────────
    def _get_license_status(self, _):
        from core.license import LicenseManager
        from core.paths import USER_DATA_DIR
        mgr = LicenseManager(USER_DATA_DIR)
        self.push_to_js.emit("license_status", json.dumps(mgr.get_status()))

    def _activate_license(self, p: dict):
        from core.license import LicenseManager
        from core.paths import USER_DATA_DIR
        key = p.get("key", "").strip()
        if not key:
            self.push_to_js.emit("license_result",
                json.dumps({"ok": False, "message": "Введіть ключ активації"}))
            return
        mgr = LicenseManager(USER_DATA_DIR)
        result = mgr.activate(key)
        self.push_to_js.emit("license_result", json.dumps(result))
        if result.get("ok"):
            # Refresh status after activation
            self.push_to_js.emit("license_status", json.dumps(mgr.get_status()))
            # Reload license in AI manager so proxy_active updates immediately
            try:
                self._ai.reload_license()
            except Exception:
                pass

    # ── AI Subscriptions ──────────────────────────────────────────────────────
    _AI_SUBS_FILE = None

    def _ai_subs_file(self) -> Path:
        from core.paths import USER_DATA_DIR
        return USER_DATA_DIR / "ai_subscriptions.json"

    def _load_ai_subs(self) -> dict:
        f = self._ai_subs_file()
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_ai_subs(self, data: dict):
        f = self._ai_subs_file()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        except Exception as e:
            print(f"[AISubs] save error: {e}")

    def _get_ai_subscriptions(self, _):
        """Return AI subscriptions + live key status + cost stats."""
        subs = self._load_ai_subs()
        self.push_to_js.emit("ai_subscriptions", json.dumps(subs))
        self.push_to_js.emit("ai_cost_stats", json.dumps(self._calc_cost_stats(subs)))
        threading.Thread(target=self._check_all_keys, daemon=True).start()

    def _calc_cost_stats(self, subs: dict) -> dict:
        """Parse cost strings (e.g. '$20/міс', '$5/mo', '200грн') → monthly total."""
        import re
        total_usd = 0.0
        breakdown = []
        for name, sub in subs.items():
            raw = (sub.get("cost") or "").strip()
            if not raw:
                continue
            # Extract first number (int or float)
            m = re.search(r'[\d]+(?:[.,]\d+)?', raw)
            if not m:
                breakdown.append({"name": name, "cost": raw, "usd": None})
                continue
            val = float(m.group().replace(",", "."))
            raw_lower = raw.lower()
            # Yearly → divide by 12
            if any(x in raw_lower for x in ["/рік", "/year", "/yr", "annual"]):
                val = round(val / 12, 2)
            # Convert UAH roughly (1 USD ≈ 41 UAH)
            if any(x in raw_lower for x in ["грн", "uah", "₴"]):
                val = round(val / 41, 2)
            total_usd += val
            breakdown.append({"name": name, "cost": raw, "usd": val})

        return {
            "total_usd": round(total_usd, 2),
            "breakdown": breakdown,
        }

    def _save_ai_subscription(self, p: dict):
        """Save/update single provider subscription info."""
        provider = p.get("provider")
        if not provider:
            return
        subs = self._load_ai_subs()
        subs[provider] = {
            "renewal":  p.get("renewal", ""),
            "cost":     p.get("cost", ""),
            "plan":     p.get("plan", ""),
            "notes":    p.get("notes", ""),
        }
        self._save_ai_subs(subs)
        self.push_to_js.emit("toast",
            json.dumps({"msg": f"✓ {provider} збережено"}))
        self.push_to_js.emit("ai_cost_stats", json.dumps(self._calc_cost_stats(subs)))

    def _check_all_keys(self, _=None):
        """Validate all configured API keys and push results."""
        # Use _get_api_keys() which reads from Credential Manager (keyring) + config
        all_keys = self._get_api_keys() if hasattr(self, '_get_api_keys') else {}
        providers = {
            "OpenAI":     (all_keys.get("openai", ""),     self._check_openai),
            "Gemini":     (all_keys.get("google", ""),     self._check_gemini),
            "Claude":     (all_keys.get("anthropic", ""),  self._check_anthropic),
            "xAI":        (all_keys.get("xai", ""),        self._check_xai),
            "Perplexity": (all_keys.get("perplexity", ""), self._check_perplexity),
        }
        results = {}
        for name, (key, check_fn) in providers.items():
            if not key:
                results[name] = {"status": "no_key", "label": "Ключ не задано"}
            else:
                try:
                    ok, msg = check_fn(key)
                    results[name] = {
                        "status": "ok" if ok else "error",
                        "label": msg,
                    }
                except Exception as e:
                    results[name] = {"status": "error", "label": str(e)[:60]}

        self.push_to_js.emit("ai_key_statuses", json.dumps(results))

    # ── Key checkers ──────────────────────────────────────────────────────────
    @staticmethod
    def _check_openai(key: str):
        try:
            import requests
            r = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=8,
            )
            if r.status_code == 200:
                return True, "✅ Активний"
            if r.status_code == 401:
                return False, "❌ Невірний ключ"
            if r.status_code == 429:
                return True, "⚠️ Ліміт вичерпано"
            return False, f"❌ {r.status_code}"
        except Exception as e:
            return False, f"⚠️ {str(e)[:40]}"

    @staticmethod
    def _check_gemini(key: str):
        try:
            import requests
            r = requests.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                timeout=8,
            )
            if r.status_code == 200:
                return True, "✅ Активний"
            if r.status_code == 400:
                return False, "❌ Невірний ключ"
            return False, f"❌ {r.status_code}"
        except Exception as e:
            return False, f"⚠️ {str(e)[:40]}"

    @staticmethod
    def _check_anthropic(key: str):
        try:
            import requests
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={"model": "claude-haiku-20240307", "max_tokens": 1,
                      "messages": [{"role": "user", "content": "hi"}]},
                timeout=10,
            )
            if r.status_code in (200, 400):
                return True, "✅ Активний"
            if r.status_code == 401:
                return False, "❌ Невірний ключ"
            return False, f"❌ {r.status_code}"
        except Exception as e:
            return False, f"⚠️ {str(e)[:40]}"

    @staticmethod
    def _check_xai(key: str):
        try:
            import requests
            r = requests.get(
                "https://api.x.ai/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=8,
            )
            return (True, "✅ Активний") if r.status_code == 200 else (False, f"❌ {r.status_code}")
        except Exception as e:
            return False, f"⚠️ {str(e)[:40]}"

    @staticmethod
    def _check_perplexity(key: str):
        try:
            import requests
            r = requests.get(
                "https://api.perplexity.ai/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=8,
            )
            return (True, "✅ Активний") if r.status_code == 200 else (False, f"❌ {r.status_code}")
        except Exception as e:
            return False, f"⚠️ {str(e)[:40]}"

    # ── Proxy spending stats ──────────────────────────────────────────────────
    def _get_proxy_stats(self, _=None):
        """Fetch spending stats from Railway proxy server."""
        threading.Thread(target=self._fetch_proxy_stats, daemon=True).start()

    def _fetch_proxy_stats(self):
        proxy_url = self._cfg.get("proxy_url", "").rstrip("/")
        admin_key = self._cfg.get("proxy_admin_key", "")
        if not proxy_url:
            self.push_to_js.emit("proxy_stats",
                json.dumps({"error": "proxy_url не вказано в config.json"}))
            return
        try:
            req = urllib.request.Request(
                f"{proxy_url}/api/v1/admin/stats",
                headers={"Authorization": f"Bearer {admin_key}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
                # Attach saved budget
                budget = self._load_budget()
                data["budget_usd"] = budget
                data["remaining_usd"] = max(0, round(budget - data.get("total_cost_usd", 0), 2))
                self.push_to_js.emit("proxy_stats", json.dumps(data))
        except urllib.error.HTTPError as e:
            self.push_to_js.emit("proxy_stats",
                json.dumps({"error": f"HTTP {e.code}: {e.read().decode()[:80]}"}))
        except Exception as e:
            self.push_to_js.emit("proxy_stats",
                json.dumps({"error": str(e)[:120]}))

    def _set_budget(self, p: dict):
        """Save user's budget (how much they topped up)."""
        amount = float(p.get("amount", 0) or 0)
        self._save_budget(amount)
        self.push_to_js.emit("toast",
            json.dumps({"msg": f"💰 Бюджет збережено: ${amount:.2f}"}))
        # Refresh stats with new budget
        self._get_proxy_stats()

    def _budget_file(self):
        from core.paths import USER_DATA_DIR
        return USER_DATA_DIR / "proxy_budget.json"

    def _load_budget(self) -> float:
        f = self._budget_file()
        if f.exists():
            try:
                return float(json.loads(f.read_text(encoding="utf-8")).get("budget_usd", 0))
            except Exception:
                pass
        return 0.0

    def _save_budget(self, amount: float):
        f = self._budget_file()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"budget_usd": amount}), encoding="utf-8")
        except Exception as e:
            print(f"[Budget] save error: {e}")
