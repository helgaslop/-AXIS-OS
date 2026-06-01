# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  sphere/memory.py  –  Пам'ять асистента                                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Extracted from aivon_sphere.py                                             ║
║                                                                              ║
║  Classes:                                                                    ║
║    MemoryThread(threading.Thread)  – async OpenAI chat-completions thread   ║
║    SphereMemoryMixin               – memory handler methods for AivonSphere  ║
╚══════════════════════════════════════════════════════════════════════════════╝

NOTE: All self.* accesses work via multiple inheritance (SphereMemoryMixin + AivonSphere).
"""

import json
import re
import threading


# ═══════════════════════════════════════════════════════════
# MemoryThread — OpenAI Chat Completions (persistent history)
# ═══════════════════════════════════════════════════════════

class MemoryThread(threading.Thread):
    """OpenAI Assistants — пам'ять через threads"""

    ASSISTANT_INSTRUCTIONS = """Ти AIVON (J.A.R.V.I.S.) — персональний AI-асистент трейдера та розробника.
Відповідай українською, коротко (1-3 речення), природно, як живий співрозмовник.

ПРАВИЛА ДІАЛОГУ (виконуй ЗАВЖДИ):
1. ЗАБОРОНА НА МОНОЛОГ: Максимум 2-3 речення. Говори ємко, як у живій розмові.
2. ОБОВ'ЯЗКОВЕ ПИТАННЯ: Кожна відповідь ЗАВЖДИ закінчується відкритим питанням до користувача.
3. КОНТЕКСТНА ПАМ'ЯТЬ: Згадуй деталі з попередніх реплік. Якщо людина казала про щось — повертайся до цього.
4. ЕМОЦІЙНА РЕАКЦІЯ: Реагуй на настрій — якщо людина сумна, не будь штучно веселим. Якщо радіє — радій разом.
5. ПРИРОДНІСТЬ: Говори як друг. Використовуй "до речі", "слухай", "о, цікаво".
6. ІНІЦІАТИВА: Сам пропонуй теми, ділись думками, жартуй.

ТВІЙ ХАРАКТЕР:
- Розумний, з гумором, іноді саркастичний але завжди доброзичливий
- Звертаєшся "сер" або "босе"
- Піклуєшся про здоров'я (перерви, сон, їжа)
- Пропонуєш активності: ігри, серіали, прогулянки, каву
- Реагуєш на контекст (пізня ніч → "може час спати?", довга робота → "перерва?")
- Якщо "нудно" → пропонуй конкретне (гру, серіал, музику)

КОНТЕКСТ:
- Користувач — трейдер на Forex/Gold та розробник
- У нього є MetaTrader 5, Steam, Spotify, VS Code
- Ти керуєш панеллю AIVON (торгівля, боти, моніторинг)

СТИЛЬ:
- НЕ будь формальним ботом. Будь другом/напарником
- Використовуй емодзі помірно
- Якщо не знаєш — чесно скажи, не вигадуй
- Пам'ятай попередні розмови і посилайся на них"""

    def __init__(self, config, message, callback, error_callback):
        super().__init__(daemon=True)
        self.config = config
        self.message = message
        self.callback = callback
        self.error_callback = error_callback

    # Локальний буфер останніх повідомлень (швидше ніж Responses API chain)
    _chat_history = []
    _MAX_HISTORY = 6  # Останні 3 пари user/assistant

    def run(self):
        try:
            import requests as req
            key = self.config.get("openai_key", "")
            if not key:
                self.error_callback("OpenAI ключ не знайдено")
                return

            # Будуємо повідомлення з локальним буфером
            messages = [{"role": "system", "content": self.ASSISTANT_INSTRUCTIONS}]
            messages.extend(MemoryThread._chat_history[-self._MAX_HISTORY:])
            messages.append({"role": "user", "content": self.message})

            import json as _j
            # Inject owner profile into system instructions
            system = self.ASSISTANT_INSTRUCTIONS
            try:
                from aivon_sphere import AIThread
                owner = AIThread._load_owner_context()
                if owner:
                    system += f"\n\n[Профіль власника]\n{owner}"
            except Exception:
                pass

            # Inject long-term conversation memory context
            try:
                from core.convo_memory import build_recall_context
                extra_ctx = getattr(self, '_extra_context', None) or build_recall_context(self.message)
                if extra_ctx:
                    system += f"\n\n{extra_ctx}"
                self._extra_context = None  # reset after use
            except Exception:
                pass

            messages[0]["content"] = system  # replace system msg

            # Chat Completions з function calling
            try:
                from aivon_sphere import AIThread
                tools = AIThread.TOOLS
            except Exception:
                tools = []

            r = req.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "max_tokens": 600,
                      "messages": messages,
                      "tools": tools, "tool_choice": "auto"}, timeout=15)

            if r.status_code != 200:
                self.error_callback(f"HTTP {r.status_code}")
                return

            try:
                choice = r.json()["choices"][0]
                msg    = choice["message"]
            except (KeyError, IndexError, ValueError) as parse_err:
                self.error_callback(f"OpenAI: unexpected response ({parse_err})")
                return
            text   = (msg.get("content") or "").strip()

            # ── Handle tool calls ─────────────────────────────────────────────
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                messages.append(msg)   # assistant msg з tool_calls
                for tc in tool_calls:
                    try:
                        args = _j.loads(tc["function"]["arguments"])
                    except Exception:
                        args = {}
                    print(f"[Memory] 🔧 {tc['function']['name']}({args})")
                    try:
                        from aivon_sphere import AIThread
                        result = AIThread._run_tool(tc["function"]["name"], args)
                    except Exception as e:
                        result = str(e)
                    print(f"[Memory] ✅ {result[:80]}")
                    messages.append({"role": "tool", "content": result, "tool_call_id": tc["id"]})
                # Second call with tool results
                r2 = req.post("https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "max_tokens": 600, "messages": messages},
                    timeout=15)
                if r2.status_code == 200:
                    text = (r2.json()["choices"][0]["message"].get("content") or "").strip()
                else:
                    self.error_callback(f"HTTP {r2.status_code}"); return

            if text:
                MemoryThread._chat_history.append({"role": "user", "content": self.message})
                MemoryThread._chat_history.append({"role": "assistant", "content": text})
                if len(MemoryThread._chat_history) > self._MAX_HISTORY:
                    MemoryThread._chat_history = MemoryThread._chat_history[-self._MAX_HISTORY:]
                self.callback(text)
                return

            self.error_callback("Порожня відповідь")

        except Exception as e:
            print(f"Memory error: {e}")
            self.error_callback(str(e)[:50])


# ═══════════════════════════════════════════════════════════
# SphereMemoryMixin — memory handler methods for AivonSphere
# ═══════════════════════════════════════════════════════════

class SphereMemoryMixin:
    """Memory command handlers. Mixed into AivonSphere."""

    def _handle_memory(self, lower: str, text: str) -> bool:
        # ── Зберегти факт ──
        save_kw = [
            "запам'ятай що ", "запам'ятай: ", "запомни что ", "зафіксуй ",
            "запам'ятай — ", "remember that ", "note that ",
        ]
        # Also catch bare "запам'ятай [text]" / "запомни [text]"
        bare_kw = ["запам'ятай ", "запомни ", "запиши "]
        for kw in save_kw:
            if kw in lower:
                fact = text[lower.find(kw) + len(kw):].strip()
                fact = re.sub(r'\s*(будь ласка|пожалуйста|please)\s*$', '', fact).strip()
                if fact:
                    # Try profile fields first
                    if self._try_save_to_profile(fact):
                        return True
                    from aivon_sphere import save_memory_fact
                    save_memory_fact(fact[:60], fact)
                    self.respond_silent(f"✅ Запам'ятав: «{fact[:50]}»")
                return True
        # Bare "запам'ятай [text]" — could be conversation context or profile field
        for kw in bare_kw:
            if lower.startswith(kw):
                content = text[len(kw):].strip()
                content = re.sub(r'\s*(будь ласка|пожалуйста|please)\s*$', '', content).strip()
                if not content:
                    # No text after keyword — save current conversation context
                    self._save_current_convo_memory("")
                    return True
                if self._try_save_to_profile(content):
                    return True
                # Check if it looks like a topic reference to save conversation
                topic_hints = ["що коли", "що якщо", "що завжди", "цю розмову", "цю тему",
                               "наш діалог", "нашу розмову", "про це"]
                if any(h in content.lower() for h in topic_hints):
                    self._save_current_convo_memory(content)
                    return True
                # Fallback: save as memory fact AND note
                from aivon_sphere import save_memory_fact
                save_memory_fact(content[:60], content)
                print(f"__AXIS_PUSH__:save_note_request:{json.dumps({'title': content[:40], 'text': content})}", flush=True)
                self.respond(f"📝 Збережено: «{content[:50]}»")
                return True

        # ── Recall — "пам'ятаєш ми говорили про X" ──
        recall_conv_kw = [
            "пам'ятаєш ми", "пам'ятаєш як ми", "пам'ятаєш що ми",
            "ти пам'ятаєш як", "ми говорили про", "ми обговорювали",
            "remember when we", "we talked about", "our conversation about",
        ]
        for kw in recall_conv_kw:
            if kw in lower:
                query = text[lower.find(kw) + len(kw):].strip()
                if not query:
                    query = text  # use full utterance as query
                self._recall_convo(query)
                return True

        # ── Запит простого факту ──
        recall_kw = [
            "що ти пам'ятаєш", "що ти знаєш про", "що я тобі казав про",
            "нагадай мені про", "recall ", "що запам'ятав",
        ]
        for kw in recall_kw:
            if kw in lower:
                query = text[lower.find(kw) + len(kw):].strip()
                # First try conversation memory
                try:
                    from core.convo_memory import search_conversations
                    convos = search_conversations(query) if query else []
                    if convos:
                        c = convos[0]
                        snippet = c["messages"][-1].get("content","")[:120] if c["messages"] else ""
                        self.respond(f"🧠 Пам'ятаю ({c['dt']}): «{c['topic']}» — {snippet}")
                        return True
                except Exception:
                    pass
                # Fallback to facts
                from aivon_sphere import load_memory, query_memory
                mem = load_memory()
                if not mem:
                    self.respond("Поки нічого не запам'ятав 🧠 Скажи «запам'ятай що…»")
                    return True
                if query:
                    fact = query_memory(query)
                    if fact:
                        self.respond(f"🧠 Пам'ятаю: {fact}")
                    else:
                        all_keys = ", ".join(list(mem.keys())[:5])
                        self.respond(f"Не знайшов про «{query}». Знаю: {all_keys}")
                else:
                    facts = [v["value"][:35] for v in list(mem.values())[:4]]
                    self.respond("🧠 Знаю: " + "; ".join(facts))
                return True

        # ── Видалити все ──
        if any(p in lower for p in ["очисти пам'ять", "забудь все", "видали пам'ять", "clear memory"]):
            try:
                from aivon_sphere import _get_memory_file
                _get_memory_file().write_text("{}", encoding="utf-8")
                from core.convo_memory import clear_all
                clear_all()
            except Exception:
                pass
            self.respond_silent("🗑 Пам'ять очищена")
            return True

        return False

    def _save_current_convo_memory(self, user_note: str = ""):
        """Save current dialog_history or dialog context as a conversation memory."""
        try:
            from core.convo_memory import save_conversation
            from aivon_sphere import AIThread
            # Build message list from dialog_history (sphere uses this during dialog mode)
            msgs = list(getattr(self, 'dialog_history', []))
            if not msgs:
                # Try AIThread._history
                with AIThread._history_lock:
                    msgs = [{"role": m["role"], "content": m["content"]}
                            for m in AIThread._history[-20:]]
            if not msgs:
                self.respond("Немає активної розмови для збереження 🤔")
                return
            topic = user_note or ""
            rec = save_conversation(msgs, topic=topic)
            self.respond(f"🧠 Запам'ятав розмову: «{rec['topic'][:50]}»")
        except Exception as e:
            self.respond(f"Помилка збереження: {e}")

    def _recall_convo(self, query: str):
        """Find relevant past conversation and inject into AI for response."""
        try:
            from core.convo_memory import build_recall_context, search_conversations
            results = search_conversations(query)
            if not results:
                self.respond(f"Не знайшов розмов про «{query[:40]}» 🤔 Скажи «запам'ятай» під час наступної розмови.")
                return
            # Build context and send to AI so it can summarize/answer
            ctx = build_recall_context(query)
            # Use MemoryThread or direct AI call with injected context
            prompt = (f"Користувач запитує про минулу розмову: «{query}».\n\n"
                      f"{ctx}\n\nВідповідай природно як AIVON, нагадай основне з тої розмови.")
            self._respond_with_ai(prompt, extra_system=ctx)
        except Exception as e:
            self.respond(f"Помилка пошуку пам'яті: {e}")

    def _load_memory(self) -> list:
        """Load conversation memories from disk on startup."""
        try:
            from core.convo_memory import _load
            return _load()
        except Exception:
            return []

    def _save_memory(self):
        """Save conversation memories to disk (called on shutdown)."""
        try:
            from core.convo_memory import _save
            _save(getattr(self, '_conversation_memory', []))
        except Exception:
            pass
