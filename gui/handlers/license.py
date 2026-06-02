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
        # If key exists, validate with server in background (non-blocking)
        status = mgr.get_status()
        self.push_to_js.emit("license_status", json.dumps(status))
        # Background server check (every 6h max)
        if status.get("key") and status.get("tier") not in ("trial",):
            threading.Thread(
                target=self._server_validate_key,
                args=(status["key"],),
                daemon=True
            ).start()

    def _server_validate_key(self, key: str):
        """Check revocation status with Netlify server. Non-blocking."""
        from core.license import LicenseManager
        from core.paths import USER_DATA_DIR
        import time, json as _json
        # Rate-limit: check at most once per 6 hours
        cache_file = USER_DATA_DIR / ".last_license_check"
        try:
            if cache_file.exists():
                last = float(cache_file.read_text())
                if time.time() - last < 21600:  # 6 hours
                    return
        except Exception:
            pass

        try:
            import urllib.request
            url = "https://axis-os-app.netlify.app/.netlify/functions/license-check"
            mgr = LicenseManager(USER_DATA_DIR)
            payload = _json.dumps({
                "key": key,
                "deviceId": mgr._machine_id()
            }).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = _json.loads(r.read().decode())

            # Update last check time
            cache_file.write_text(str(time.time()))

            if not data.get("valid"):
                # Key revoked — downgrade to trial locally
                mgr._data["tier"] = "trial"
                mgr._data["key"]  = None
                mgr._save()
                self.push_to_js.emit("license_status", _json.dumps(mgr.get_status()))
                self.push_to_js.emit("toast", _json.dumps({
                    "msg": "⚠️ Ваш ключ відкликано. Зверніться до підтримки."
                }))
                print(f"[License] Key {key} revoked by server")
        except Exception as e:
            print(f"[License] Server check skipped: {e}")

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
        # Add tier to result for UI celebration overlay
        if result.get("ok") and "tier" not in result:
            result["tier"] = mgr.tier()
        self.push_to_js.emit("license_result", json.dumps(result))
        if result.get("ok"):
            # Refresh status immediately
            self.push_to_js.emit("license_status", json.dumps(mgr.get_status()))
            # Reload license in AI manager
            try:
                self._ai.reload_license()
            except Exception:
                pass
            # Send welcome email in background thread
            threading.Thread(
                target=self._send_activation_email,
                args=(key, result.get("tier", "monthly")),
                daemon=True
            ).start()

    def _send_activation_email(self, key: str, tier: str):
        """Send activation welcome email via Gmail SMTP.
        Reads credentials from app config (data/config.json) or env vars.
        """
        import os, smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        # Try app config first, then env vars
        cfg = getattr(self, '_cfg', {})
        api_keys = cfg.get("api_keys", {})
        gmail_user = (api_keys.get("gmail_user") or cfg.get("gmail_user")
                      or os.environ.get("GMAIL_USER", "axis.os.assistant@gmail.com"))
        gmail_pass = (api_keys.get("gmail_pass") or cfg.get("gmail_pass")
                      or os.environ.get("GMAIL_PASS", ""))
        owner_email = (cfg.get("owner_email") or cfg.get("notification_email")
                       or os.environ.get("OWNER_EMAIL", gmail_user))

        if not gmail_pass:
            print("[License] Email skipped — gmail_pass not in config or env")
            return

        tier_names = {"monthly": "Місячний", "yearly": "Річний", "lifetime": "Lifetime ♾️"}
        tier_name = tier_names.get(tier, tier)

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"✅ AXIS OS — Ліцензію активовано! ({tier_name})"
            msg["From"]    = f'"AXIS OS" <{gmail_user}>'
            msg["To"]      = owner_email   # owner gets notif; set OWNER_EMAIL to customer if available

            html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="font-family:'Segoe UI',Arial,sans-serif;background:#080c14;color:#e6edf3;margin:0;padding:20px;">
<div style="max-width:520px;margin:0 auto;background:#0d1117;border:1px solid rgba(255,255,255,.1);border-radius:16px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#3fb950,#238636);padding:24px 32px;text-align:center;">
    <h1 style="margin:0;font-size:22px;font-weight:900;color:#fff;">⬡ AXIS OS</h1>
  </div>
  <div style="padding:28px 32px;">
    <div style="display:inline-block;background:rgba(63,185,80,.12);border:1px solid rgba(63,185,80,.3);color:#3fb950;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:700;margin-bottom:16px;">✅ Ліцензію активовано</div>
    <h2 style="font-size:20px;font-weight:800;margin:0 0 12px;">Вітаємо з активацією!</h2>
    <p style="color:#8b949e;font-size:14px;line-height:1.7;">Ваш AXIS OS тепер повністю активовано.</p>
    <div style="background:#161b22;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:16px 20px;margin:16px 0;">
      <div style="display:flex;justify-content:space-between;padding:5px 0;font-size:14px;">
        <span style="color:#8b949e;">Ключ</span>
        <span style="font-family:monospace;font-weight:700;color:#00d4ff;">{key}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:5px 0;font-size:14px;">
        <span style="color:#8b949e;">План</span>
        <span style="font-weight:700;">{tier_name}</span>
      </div>
    </div>
    <p style="color:#8b949e;font-size:13px;">Якщо у вас є питання — ми завжди готові допомогти.</p>
    <a href="https://t.me/Helgaslopp" style="display:block;text-align:center;background:linear-gradient(135deg,#00d4ff,#7c3aed);color:#000;font-weight:800;padding:13px;border-radius:10px;text-decoration:none;margin:20px 0 0;font-size:15px;">Підтримка @Helgaslopp</a>
  </div>
  <div style="text-align:center;padding:14px 32px;font-size:12px;color:#484f58;border-top:1px solid rgba(255,255,255,.06);">AXIS OS — Дякуємо за довіру!</div>
</div></body></html>"""

            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
                srv.login(gmail_user, gmail_pass)
                srv.sendmail(gmail_user, owner_email, msg.as_string())
            print(f"[License] Activation email sent to {owner_email}")
        except Exception as e:
            print(f"[License] Activation email failed: {e}")

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
