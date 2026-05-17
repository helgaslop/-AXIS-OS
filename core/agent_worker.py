"""
core/agent_worker.py
Single agent executor with tool-use loop.
Supports Anthropic and OpenAI-compatible APIs.
"""

from __future__ import annotations

import json
import sys
import threading
from typing import Any, Callable, Optional

from core.agent_tools import execute_tool, is_dangerous, tool_schemas_anthropic, tool_schemas_openai
from core.agent_providers import PROVIDERS, get_provider

# ─── Status constants ────────────────────────────────────────────────────────
STATUS_IDLE      = "idle"
STATUS_THINKING  = "thinking"
STATUS_TOOL      = "tool"
STATUS_DONE      = "done"
STATUS_ERROR     = "error"
STATUS_WAITING   = "waiting"   # waiting for permission

MAX_ITERATIONS = 50


class AgentWorker:
    """
    Runs a single agent profile against a task string.

    Parameters
    ----------
    profile         : agent profile dict from agent_profiles.py
    ai_config       : dict with keys: provider ("anthropic"|"openai"),
                      api_key, model, base_url (optional for openai-compat)
    permission_cb   : callable(agent_name, tool_name, args) -> bool
                      Called for dangerous tools; must return True/False.
                      Runs on a worker thread — bridge must marshal to UI.
    status_cb       : callable(agent_name, status, detail) -> None
                      Called on every status change (idle/thinking/tool/…).
    allow_all_cb    : callable() -> bool
                      Returns True if "allow all" was already granted for session.
    """

    def __init__(
        self,
        profile: dict,
        ai_config: dict,
        permission_cb: Optional[Callable] = None,
        status_cb: Optional[Callable] = None,
        allow_all_cb: Optional[Callable] = None,
        project_root: str = "",
    ):
        self.profile       = profile
        self.ai_config     = ai_config
        self.permission_cb = permission_cb
        self.status_cb     = status_cb
        self.allow_all_cb  = allow_all_cb
        self.project_root  = project_root   # used to resolve relative file paths
        self._stop_event   = threading.Event()
        self._backups: list[dict] = []  # [{path, backup, tool}]

    # ─── Path resolver ────────────────────────────────────────────────────────

    def _resolve_args(self, tool_name: str, args: dict) -> dict:
        """
        Resolve file paths in tool args:
        1. Relative paths → absolute (joined with project_root)
        2. Absolute paths that fall OUTSIDE project_root → redirected to project_root
           (prevents agent from writing to wrong/new folders when a project is open)
        """
        import os as _os
        PATH_KEYS = {"path", "src", "dst"}
        resolved = dict(args)

        for key in PATH_KEYS:
            if key not in resolved or not isinstance(resolved[key], str):
                continue
            p = resolved[key]
            if not p:
                continue

            if not _os.path.isabs(p):
                # Relative → make absolute under project_root if available
                if self.project_root:
                    resolved[key] = _os.path.normpath(_os.path.join(self.project_root, p))
            elif self.project_root:
                # Absolute: verify it lives inside project_root
                pr = _os.path.normcase(_os.path.normpath(self.project_root))
                pa = _os.path.normcase(_os.path.normpath(p))
                inside = pa == pr or pa.startswith(pr + _os.sep)
                if not inside:
                    # Agent invented a wrong path → redirect filename to project_root
                    # Try to preserve a sensible relative tail:
                    #   e.g. Desktop/WrongProject/js/app.js  →  project_root/js/app.js
                    # by stripping any leading path component that looks like a sibling dir.
                    try:
                        # Use the part after the last non-project ancestor directory
                        pr_parent = _os.path.normcase(_os.path.dirname(pr))
                        if pa.startswith(pr_parent + _os.sep):
                            # Same parent — strip the wrong project-folder name
                            rel = p[len(_os.path.dirname(self.project_root)) + 1:]
                            # rel is now "WrongProject/js/app.js" → drop first component
                            parts = rel.replace("\\", "/").split("/")
                            rel_tail = "/".join(parts[1:]) if len(parts) > 1 else parts[0]
                        else:
                            rel_tail = _os.path.basename(p)
                    except Exception:
                        rel_tail = _os.path.basename(p)

                    new_path = _os.path.normpath(_os.path.join(self.project_root, rel_tail))
                    print(f"[PathGuard] Redirected '{p}' -> '{new_path}'", flush=True)
                    resolved[key] = new_path

        return resolved

    # ─── Public API ───────────────────────────────────────────────────────────

    def stop(self):
        self._stop_event.set()

    def get_backups(self) -> list[dict]:
        return list(self._backups)

    def revert_file(self, path: str) -> bool:
        """Restore the most recent backup for the given file path."""
        import shutil as _shutil
        for bk in reversed(self._backups):
            if bk["path"] == path:
                try:
                    _shutil.copy2(bk["backup"], bk["path"])
                    return True
                except Exception:
                    return False
        return False

    def run_stream(
        self,
        task: str,
        context: str = "",
        on_token=None,        # callable(str) — called for each text token
        on_tool_start=None,   # callable(name, args)
        on_tool_done=None,    # callable(name, ok, preview, extra)
        history: list = None, # prior conversation [{role, content}]
        images: list  = None, # [{data: base64str, media_type: "image/jpeg"}]
        on_usage=None,        # callable(in_tok, out_tok)
        on_tool_output=None,  # callable(line: str) — streaming output from run_command/run_python
    ) -> dict:
        """Stream-first execution. Tokens delivered via on_token callback."""
        self._stop_event.clear()
        name = self.profile["name"]
        provider = self.ai_config.get("provider", "anthropic").lower()
        prov_info = get_provider(provider) or {}
        sdk_type  = prov_info.get("sdk_type", "openai_compat")

        # Set base_url from provider config if not overridden in ai_config
        if not self.ai_config.get("base_url") and prov_info.get("base_url"):
            self.ai_config["base_url"] = prov_info["base_url"]

        try:
            if sdk_type == "anthropic":
                result = self._stream_anthropic(task, context, on_token, on_tool_start, on_tool_done, history, images, on_usage, on_tool_output)
            elif sdk_type == "cohere":
                result = self._stream_cohere(task, context, on_token, on_tool_start, on_tool_done, history, images, on_usage, on_tool_output)
            else:
                # openai_compat covers: openai, google, mistral, groq, deepseek, xai,
                # perplexity, together, openrouter, azure, ollama
                result = self._stream_openai(task, context, on_token, on_tool_start, on_tool_done, history, images, on_usage, on_tool_output)
            self._set_status(STATUS_DONE, "")
            return {"success": True, "result": result, "agent": name}
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self._set_status(STATUS_ERROR, str(exc)[:120])
            err = f"[{type(exc).__name__}] {str(exc)}"
            if on_token:
                on_token(f"\n\n Помилка: {err[:400]}")
            return {"success": False, "result": err, "agent": name}

    def _stream_anthropic(self, task, context, on_token, on_tool_start, on_tool_done, history=None, images=None, on_usage=None, on_tool_output=None) -> str:
        try:
            import anthropic as _anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed")

        client = _anthropic.Anthropic(api_key=self.ai_config["api_key"])
        model  = self.ai_config.get("model", "claude-opus-4-5")
        tools  = tool_schemas_anthropic(self.profile["allowed_tools"])

        system = self.profile["system_prompt"]
        if context:
            system += f"\n\n# Context\n{context}"

        # Build messages: history (prior turns) + current user message
        messages: list[dict] = list(history or [])

        # Build user content — text + optional images (vision)
        if images:
            user_content: list = []
            for img in images:
                if isinstance(img, dict) and img.get("data") and img.get("media_type"):
                    user_content.append({
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": img["media_type"],
                            "data":       img["data"],
                        },
                    })
            user_content.append({"type": "text", "text": task})
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": task})
        full_text = ""
        _consecutive_errors = 0

        for _ in range(MAX_ITERATIONS):
            if self._stop_event.is_set():
                return full_text or "Зупинено."

            self._set_status(STATUS_THINKING, "")

            kwargs: dict = dict(model=model, max_tokens=8192, system=system, messages=messages)
            if tools:
                kwargs["tools"] = tools

            current_text = ""
            final_msg = None

            try:
                with client.messages.stream(**kwargs) as stream:
                    for event in stream:
                        if self._stop_event.is_set():
                            return full_text
                        etype = getattr(event, "type", "")
                        if etype == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            if delta and getattr(delta, "type", "") == "text_delta":
                                token = delta.text
                                current_text += token
                                full_text    += token
                                if on_token:
                                    on_token(token)
                    final_msg = stream.get_final_message()
            except Exception as e:
                raise RuntimeError(str(e))

            # Extract token usage and fire on_usage callback
            if final_msg and on_usage:
                usage = getattr(final_msg, "usage", None)
                if usage:
                    in_tok  = getattr(usage, "input_tokens",  0)
                    out_tok = getattr(usage, "output_tokens", 0)
                    on_usage(in_tok, out_tok)

            stop_reason = getattr(final_msg, "stop_reason", "end_turn") if final_msg else "end_turn"
            tool_calls  = [b for b in (final_msg.content if final_msg else [])
                           if getattr(b, "type", "") == "tool_use"]

            if not tool_calls or stop_reason == "end_turn":
                return full_text or "(no output)"

            messages.append({"role": "assistant", "content": final_msg.content})

            _BACKUP_TOOLS = {"write_file", "str_replace", "insert_text", "create_file"}
            tool_results: list[dict] = []
            for tc in tool_calls:
                if self._stop_event.is_set():
                    return full_text
                tool_name = tc.name
                tool_args = self._resolve_args(tool_name, getattr(tc, "input", {}) or {})

                if on_tool_start:
                    on_tool_start(tool_name, tool_args)

                # Backup file before modification
                file_path_bk = ""
                if tool_name in _BACKUP_TOOLS:
                    file_path_bk = tool_args.get("path", "")
                    if file_path_bk:
                        import os as _os
                        if _os.path.exists(file_path_bk):
                            try:
                                import tempfile as _tempfile, shutil as _shutil
                                bk_fd, bk_path = _tempfile.mkstemp(suffix=".axis_bk")
                                _os.close(bk_fd)
                                _shutil.copy2(file_path_bk, bk_path)
                                self._backups.append({"path": file_path_bk, "backup": bk_path, "tool": tool_name})
                            except Exception:
                                pass

                if not self._check_permission(tool_name, tool_args):
                    outcome = {"success": False, "error": "Permission denied"}
                else:
                    self._set_status(STATUS_TOOL, tool_name)
                    outcome = execute_tool(tool_name, tool_args, stream_cb=on_tool_output)

                if on_tool_done:
                    file_path = tool_args.get("path") or tool_args.get("src") or ""
                    preview = file_path or str(outcome.get("result", outcome.get("error", "")))[:200]
                    extra = {}
                    if "diff" in outcome:
                        extra["diff"] = outcome["diff"]
                    if "tasks" in outcome:
                        extra["tasks"] = outcome["tasks"]
                    # Include backup path if we made one
                    bk_entries = [b for b in self._backups if b["path"] == file_path_bk] if file_path_bk else []
                    if bk_entries:
                        extra["revertable"] = True
                        extra["path"] = file_path_bk
                    on_tool_done(tool_name, outcome.get("success", False), preview, extra)

                # Auto-fix: track consecutive failures for run_command/run_python
                _failed = (
                    not outcome.get("success")
                    or "error" in str(outcome.get("result", "")).lower()[:200]
                )
                if _failed and tool_name in ("run_command", "run_python"):
                    _consecutive_errors += 1
                else:
                    _consecutive_errors = 0

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": json.dumps(outcome, ensure_ascii=False),
                })

            messages.append({"role": "user", "content": tool_results})

            # Auto-fix injection: if 2+ consecutive failures, tell agent to fix
            if _consecutive_errors >= 2:
                messages.append({
                    "role": "user",
                    "content": (
                        f"\U0001F534 AUTO-FIX: The command failed {_consecutive_errors} times. "
                        "Analyze the error above, fix the root cause in the code, then try again."
                    ),
                })
                _consecutive_errors = 0

        return full_text or "Досягнуто ліміт ітерацій."

    def _stream_cohere(self, task, context, on_token, on_tool_start, on_tool_done, history=None, images=None, on_usage=None, on_tool_output=None) -> str:
        try:
            import cohere as _cohere
        except ImportError:
            raise RuntimeError("cohere package not installed. Run: pip install cohere")

        client = _cohere.ClientV2(api_key=self.ai_config["api_key"])
        model  = self.ai_config.get("model") or "command-r-plus"
        tools  = tool_schemas_openai(self.profile["allowed_tools"])

        sys_prompt = self.profile.get("system_prompt", "")
        if context:
            sys_prompt += f"\n\n# Context\n{context}"

        messages: list[dict] = []
        if history:
            for m in history[-20:]:
                if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                    messages.append({"role": m["role"], "content": str(m.get("content") or "")})

        user_content = f"{context}\n\n{task}" if context else task
        messages.append({"role": "user", "content": user_content})

        full_text = ""
        MAX_ITER  = 8

        for _iter in range(MAX_ITER):
            if self._stop_event.is_set():
                break
            self._set_status(STATUS_THINKING, "")

            resp = client.chat(
                model=model,
                messages=messages,
                system_prompt=sys_prompt,
                tools=tools if tools else None,
            )

            msg = resp.message
            tool_calls_found = []

            for block in (msg.content or []):
                if hasattr(block, "text"):
                    chunk = block.text
                    full_text += chunk
                    if on_token:
                        on_token(chunk)
                elif hasattr(block, "type") and block.type == "tool_use":
                    tool_calls_found.append(block)

            if on_usage and hasattr(resp, "usage"):
                u = resp.usage
                on_usage(getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))

            if not tool_calls_found:
                break

            messages.append({"role": "assistant", "content": msg.content})
            tool_results = []

            for tc in tool_calls_found:
                tool_name = tc.name
                tool_args = tc.parameters or {}

                if on_tool_start:
                    on_tool_start(tool_name, tool_args)

                if not self._check_permission(tool_name, tool_args):
                    outcome = {"success": False, "error": "Permission denied"}
                else:
                    self._set_status(STATUS_TOOL, tool_name)
                    outcome = execute_tool(tool_name, tool_args, stream_cb=on_tool_output)

                if on_tool_done:
                    preview = tool_args.get("path", str(outcome.get("result", ""))[:200])
                    on_tool_done(tool_name, outcome.get("success", False), str(preview), {})

                tool_results.append({"call": tc, "outputs": [{"output": json.dumps(outcome)}]})

            messages.append({"role": "tool", "content": tool_results})

        return full_text or "Done."

    def _stream_openai(self, task, context, on_token, on_tool_start, on_tool_done, history=None, images=None, on_usage=None, on_tool_output=None) -> str:
        try:
            import openai as _openai
        except ImportError:
            raise RuntimeError("openai package not installed")

        base_url = self.ai_config.get("base_url") or None  # empty string → None
        client   = _openai.OpenAI(api_key=self.ai_config["api_key"], base_url=base_url)
        model    = self.ai_config.get("model") or "gpt-4o"
        tools    = tool_schemas_openai(self.profile["allowed_tools"])

        system = self.profile["system_prompt"]
        if context:
            system += f"\n\n# Context\n{context}"

        # Build messages: system + history (prior turns) + current user message
        messages: list[dict] = [{"role": "system", "content": system}]
        messages.extend(history or [])

        # Vision support for OpenAI-compatible (gpt-4o, etc.)
        if images:
            user_content: list = []
            for img in images:
                if isinstance(img, dict) and img.get("data") and img.get("media_type"):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img['media_type']};base64,{img['data']}"
                        },
                    })
            user_content.append({"type": "text", "text": task})
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": task})
        full_text = ""

        for _ in range(MAX_ITERATIONS):
            if self._stop_event.is_set():
                return full_text or "Зупинено."

            self._set_status(STATUS_THINKING, "")
            kwargs: dict = dict(model=model, messages=messages, stream=True)
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            current_text  = ""
            tool_acc: dict = {}  # index → {id, name, args_str}
            finish_reason  = "stop"
            last_usage     = None

            for chunk in client.chat.completions.create(**kwargs):
                if self._stop_event.is_set():
                    return full_text
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    # Check for usage in final chunk (some providers)
                    if hasattr(chunk, "usage") and chunk.usage:
                        last_usage = chunk.usage
                    continue
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta
                if delta.content:
                    token = delta.content
                    current_text += token
                    full_text    += token
                    if on_token:
                        on_token(token)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_acc:
                            tool_acc[idx] = {"id": "", "name": "", "args_str": ""}
                        if tc.id:
                            tool_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_acc[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_acc[idx]["args_str"] += tc.function.arguments
                # Capture usage from chunk if present
                if hasattr(chunk, "usage") and chunk.usage:
                    last_usage = chunk.usage

            # Fire usage callback
            if last_usage and on_usage:
                in_tok  = getattr(last_usage, "prompt_tokens",     0)
                out_tok = getattr(last_usage, "completion_tokens", 0)
                on_usage(in_tok, out_tok)

            if finish_reason != "tool_calls" or not tool_acc:
                return full_text or current_text or "(no output)"

            tc_list = [{"id": v["id"], "type": "function",
                        "function": {"name": v["name"], "arguments": v["args_str"]}}
                       for v in tool_acc.values()]
            messages.append({"role": "assistant", "content": current_text or None, "tool_calls": tc_list})

            _BACKUP_TOOLS = {"write_file", "str_replace", "insert_text", "create_file"}
            for v in tool_acc.values():
                if self._stop_event.is_set():
                    return full_text
                tool_name = v["name"]
                try:
                    tool_args = self._resolve_args(v["name"], json.loads(v["args_str"] or "{}"))
                except Exception:
                    tool_args = {}

                if on_tool_start:
                    on_tool_start(tool_name, tool_args)

                # Backup file before modification
                file_path_bk = ""
                if tool_name in _BACKUP_TOOLS:
                    file_path_bk = tool_args.get("path", "")
                    if file_path_bk:
                        import os as _os
                        if _os.path.exists(file_path_bk):
                            try:
                                import tempfile as _tempfile, shutil as _shutil
                                bk_fd, bk_path = _tempfile.mkstemp(suffix=".axis_bk")
                                _os.close(bk_fd)
                                _shutil.copy2(file_path_bk, bk_path)
                                self._backups.append({"path": file_path_bk, "backup": bk_path, "tool": tool_name})
                            except Exception:
                                pass

                if not self._check_permission(tool_name, tool_args):
                    outcome = {"success": False, "error": "Permission denied"}
                else:
                    self._set_status(STATUS_TOOL, tool_name)
                    outcome = execute_tool(tool_name, tool_args, stream_cb=on_tool_output)

                if on_tool_done:
                    file_path = tool_args.get("path") or tool_args.get("src") or ""
                    preview = file_path or str(outcome.get("result", outcome.get("error", "")))[:200]
                    extra = {}
                    if "diff" in outcome:
                        extra["diff"] = outcome["diff"]
                    if "tasks" in outcome:
                        extra["tasks"] = outcome["tasks"]
                    bk_entries = [b for b in self._backups if b["path"] == file_path_bk] if file_path_bk else []
                    if bk_entries:
                        extra["revertable"] = True
                        extra["path"] = file_path_bk
                    on_tool_done(tool_name, outcome.get("success", False), preview, extra)

                messages.append({"role": "tool", "tool_call_id": v["id"],
                                 "content": json.dumps(outcome, ensure_ascii=False)})

        return full_text or "Досягнуто ліміт ітерацій."

    def run(self, task: str, context: str = "") -> dict:
        """
        Execute the agent on *task*.
        Returns {"success": bool, "result": str, "agent": str}
        """
        self._stop_event.clear()
        name = self.profile["name"]
        provider  = self.ai_config.get("provider", "anthropic").lower()
        prov_info = get_provider(provider) or {}
        sdk_type  = prov_info.get("sdk_type", "openai_compat")

        if not self.ai_config.get("base_url") and prov_info.get("base_url"):
            self.ai_config["base_url"] = prov_info["base_url"]

        try:
            if sdk_type == "anthropic":
                result = self._run_anthropic(task, context)
            else:
                result = self._run_openai(task, context)
            self._set_status(STATUS_DONE, result[:120])
            return {"success": True, "result": result, "agent": name}
        except Exception as exc:
            self._set_status(STATUS_ERROR, str(exc)[:120])
            return {"success": False, "result": str(exc), "agent": name}

    # ─── Anthropic tool-use loop ──────────────────────────────────────────────

    def _run_anthropic(self, task: str, context: str) -> str:
        try:
            import anthropic as _anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

        client = _anthropic.Anthropic(api_key=self.ai_config["api_key"])
        model  = self.ai_config.get("model", "claude-opus-4-5")
        tools  = tool_schemas_anthropic(self.profile["allowed_tools"])

        system = self.profile["system_prompt"]
        if context:
            system += f"\n\n# Current context\n{context}"

        messages: list[dict] = [{"role": "user", "content": task}]

        for _ in range(MAX_ITERATIONS):
            if self._stop_event.is_set():
                return "Зупинено користувачем."

            self._set_status(STATUS_THINKING, "")

            kwargs: dict = dict(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools or _anthropic.NOT_GIVEN,
                messages=messages,
            )
            if not tools:
                del kwargs["tools"]

            response = client.messages.create(**kwargs)

            # Collect text blocks
            text_parts: list[str] = []
            tool_calls: list[Any] = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(block)

            # No tool calls → final answer
            if not tool_calls or response.stop_reason == "end_turn":
                return "\n".join(text_parts) or "(no output)"

            # Add assistant message with all content blocks
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call
            tool_results: list[dict] = []
            for tc in tool_calls:
                if self._stop_event.is_set():
                    return "Зупинено користувачем."

                tool_name = tc.name
                tool_args = tc.input or {}

                # Permission check
                if not self._check_permission(tool_name, tool_args):
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": "Permission denied by user.",
                    })
                    continue

                self._set_status(STATUS_TOOL, f"{tool_name}({self._short_args(tool_args)})")
                outcome = execute_tool(tool_name, tool_args)
                content = json.dumps(outcome, ensure_ascii=False)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": content,
                })

            messages.append({"role": "user", "content": tool_results})

        return "Досягнуто ліміт ітерацій."

    # ─── OpenAI-compatible tool-use loop ─────────────────────────────────────

    def _run_openai(self, task: str, context: str) -> str:
        try:
            import openai as _openai
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

        base_url = self.ai_config.get("base_url") or None  # empty string → None
        client   = _openai.OpenAI(
            api_key=self.ai_config["api_key"],
            base_url=base_url,
        )
        model = self.ai_config.get("model", "gpt-4o")
        tools = tool_schemas_openai(self.profile["allowed_tools"])

        system = self.profile["system_prompt"]
        if context:
            system += f"\n\n# Current context\n{context}"

        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user",   "content": task},
        ]

        for _ in range(MAX_ITERATIONS):
            if self._stop_event.is_set():
                return "Зупинено користувачем."

            self._set_status(STATUS_THINKING, "")

            kwargs: dict = dict(model=model, messages=messages)
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**kwargs)
            msg = response.choices[0].message

            # No tool calls → final answer
            if not msg.tool_calls:
                return msg.content or "(no output)"

            messages.append(msg)

            for tc in msg.tool_calls:
                if self._stop_event.is_set():
                    return "Зупинено користувачем."

                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    tool_args = {}

                # Permission check
                if not self._check_permission(tool_name, tool_args):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "Permission denied by user.",
                    })
                    continue

                self._set_status(STATUS_TOOL, f"{tool_name}({self._short_args(tool_args)})")
                outcome = execute_tool(tool_name, tool_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(outcome, ensure_ascii=False),
                })

        return "Досягнуто ліміт ітерацій."

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _check_permission(self, tool_name: str, args: dict) -> bool:
        """Return True if allowed to execute the tool."""
        if not is_dangerous(tool_name):
            return True
        # Session-wide allow-all?
        if self.allow_all_cb and self.allow_all_cb():
            return True
        # Ask user
        if self.permission_cb:
            self._set_status(STATUS_WAITING, f"{tool_name}")
            allowed = self.permission_cb(self.profile["name"], tool_name, args)
            if not allowed:
                self._set_status(STATUS_THINKING, "")
            return allowed
        # No callback → deny dangerous by default
        return False

    def _set_status(self, status: str, detail: str = ""):
        if self.status_cb:
            try:
                self.status_cb(self.profile["name"], status, detail)
            except Exception:
                pass

    @staticmethod
    def _short_args(args: dict) -> str:
        s = json.dumps(args, ensure_ascii=False)
        return s[:60] + "…" if len(s) > 60 else s
