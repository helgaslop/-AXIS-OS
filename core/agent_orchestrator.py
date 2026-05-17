"""
core/agent_orchestrator.py
Master orchestrator: parses user request → builds task graph →
executes agents in parallel/sequential order → returns summary.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from core.agent_profiles import AGENTS_BY_NAME, AGENT_PROFILES
from core.agent_worker import AgentWorker, STATUS_IDLE

# ─── Result store ─────────────────────────────────────────────────────────────

class TaskResult:
    def __init__(self, task_id: str):
        self.task_id  = task_id
        self.agent    = ""
        self.success  = False
        self.result   = ""
        self.done_evt = threading.Event()

    def set(self, agent: str, success: bool, result: str):
        self.agent   = agent
        self.success = success
        self.result  = result
        self.done_evt.set()

    def wait(self, timeout: float = 300.0) -> bool:
        return self.done_evt.wait(timeout)


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class AgentOrchestrator:
    """
    Coordinates the full multi-agent pipeline.

    Parameters
    ----------
    ai_config       : same dict as AgentWorker (provider, api_key, model, …)
    status_cb       : callable(agent_name, status, detail)
    permission_cb   : callable(agent_name, tool_name, args) -> bool
    on_task_done    : callable(task_id, agent_name, success, result)
    on_finished     : callable(summary: str)
    max_workers     : thread-pool size (parallel agents)
    """

    def __init__(
        self,
        ai_config: dict,
        status_cb: Optional[Callable]      = None,
        permission_cb: Optional[Callable]  = None,
        on_task_done: Optional[Callable]   = None,
        on_finished: Optional[Callable]    = None,
        max_workers: int = 6,
    ):
        self.ai_config     = ai_config
        self.status_cb     = status_cb
        self.permission_cb = permission_cb
        self.on_task_done  = on_task_done
        self.on_finished   = on_finished
        self.max_workers   = max_workers

        self._stop_event   = threading.Event()
        self._allow_all    = False          # session-wide "allow all dangerous"
        self._pool: Optional[ThreadPoolExecutor] = None
        self._main_thread: Optional[threading.Thread] = None

    # ─── Public API ───────────────────────────────────────────────────────────

    def grant_allow_all(self):
        """User pressed 'Дозволити все' — no more permission prompts."""
        self._allow_all = True

    def stop(self):
        self._stop_event.set()
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)

    def run_async(self, user_request: str, context: str = ""):
        """Start orchestration in a background thread."""
        self._stop_event.clear()
        self._main_thread = threading.Thread(
            target=self._run, args=(user_request, context), daemon=True
        )
        self._main_thread.start()

    def run_sync(self, user_request: str, context: str = "") -> str:
        """Block until done. Returns summary string."""
        result_box: list[str] = []
        ev = threading.Event()

        orig_on_finished = self.on_finished
        def _capture(summary):
            result_box.append(summary)
            ev.set()
            if orig_on_finished:
                orig_on_finished(summary)
        self.on_finished = _capture

        self.run_async(user_request, context)
        ev.wait(timeout=1800)
        self.on_finished = orig_on_finished
        return result_box[0] if result_box else "Timeout."

    # ─── Internal pipeline ────────────────────────────────────────────────────

    def _run(self, user_request: str, context: str):
        try:
            # 1. Parse request with Orchestrator agent
            self._set_status("Orchestrator", "thinking", "Планування задач…")
            task_graph = self._plan(user_request, context)

            if self._stop_event.is_set():
                return

            if not task_graph:
                self._finish("Orchestrator не зміг побудувати план задач.")
                return

            # 2. Execute task graph
            results = self._execute_graph(task_graph, context)

            if self._stop_event.is_set():
                self._finish("Зупинено користувачем.")
                return

            # 3. Summarize
            self._set_status("Orchestrator", "thinking", "Підсумок…")
            summary = self._summarize(user_request, task_graph, results)
            self._set_status("Orchestrator", "done", "")
            self._finish(summary)

        except Exception as exc:
            self._set_status("Orchestrator", "error", str(exc)[:120])
            self._finish(f"Помилка оркестратора: {exc}")

    # ─── Planning ─────────────────────────────────────────────────────────────

    def _plan(self, user_request: str, context: str) -> list[dict]:
        """
        Ask Orchestrator to produce a JSON task graph.
        Returns list of task dicts:
          {
            "id":      str,          # e.g. "t1"
            "agent":   str,          # agent name from AGENTS_BY_NAME
            "task":    str,          # instruction for that agent
            "depends": [str, ...],   # ids that must finish first
          }
        """
        profile = AGENTS_BY_NAME.get("Orchestrator")
        if not profile:
            raise RuntimeError("Orchestrator profile not found")

        agent_list = "\n".join(
            f"- {p['name']} ({p['category']}): {p['description']}"
            for p in AGENT_PROFILES
            if p["name"] != "Orchestrator"
        )

        plan_prompt = f"""
User request: {user_request}

Available agents:
{agent_list}

Produce a JSON task graph — a JSON array of tasks.
Each task object MUST have:
  "id"      : unique string like "t1", "t2", …
  "agent"   : exact agent name from the list above
  "task"    : clear instruction string for that agent
  "depends" : array of task ids this task waits for (empty [] if independent)

Rules:
- Use as few agents as needed; quality over quantity.
- Independent tasks (no shared dependencies) will run in PARALLEL.
- Tasks that depend on prior results go in "depends".
- Return ONLY valid JSON array, no markdown, no explanation.

Example:
[
  {{"id":"t1","agent":"Planner","task":"Design folder structure for a React app","depends":[]}},
  {{"id":"t2","agent":"UI Developer","task":"Create App.tsx skeleton","depends":["t1"]}},
  {{"id":"t3","agent":"Style Designer","task":"Create index.css","depends":["t1"]}}
]
"""
        # Run orchestrator WITHOUT tools (pure planning pass)
        planning_profile = dict(profile)
        planning_profile["allowed_tools"] = []

        worker = AgentWorker(
            profile=planning_profile,
            ai_config=self.ai_config,
            status_cb=self.status_cb,
        )
        res = worker.run(plan_prompt, context)
        if not res["success"]:
            raise RuntimeError(res["result"])

        raw = res["result"].strip()

        # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
        import re as _re
        raw = _re.sub(r"```(?:json)?\s*", "", raw).strip()
        raw = raw.replace("```", "").strip()

        # Support both bare array [...] and wrapped {"tasks":[...]} or {"plan":..,"tasks":[...]}
        tasks_raw = raw
        if raw.startswith("{"):
            # Try to extract "tasks" array from object
            m = _re.search(r'"tasks"\s*:\s*(\[.*\])', raw, _re.DOTALL)
            if m:
                tasks_raw = m.group(1)
            else:
                # fallback: find first [ ... ]
                start = raw.find("[")
                end   = raw.rfind("]")
                if start != -1 and end != -1:
                    tasks_raw = raw[start:end + 1]
                else:
                    raise RuntimeError(f"Orchestrator returned unreadable plan: {raw[:300]}")
        else:
            start = tasks_raw.find("[")
            end   = tasks_raw.rfind("]")
            if start == -1 or end == -1:
                raise RuntimeError(f"Orchestrator returned non-JSON: {raw[:300]}")
            tasks_raw = tasks_raw[start:end + 1]

        try:
            tasks: list[dict] = json.loads(tasks_raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Plan JSON parse error: {e} — raw: {tasks_raw[:300]}")

        # Validate & fix
        valid = []
        seen_ids: set[str] = set()
        for t in tasks:
            if not isinstance(t, dict):
                continue
            tid    = str(t.get("id", f"t{len(valid)+1}"))
            agent  = t.get("agent", "")
            task   = t.get("task", "")
            # Support both "depends" and "depends_on" field names
            raw_deps = t.get("depends") or t.get("depends_on") or []
            deps   = [str(d) for d in raw_deps if str(d) in seen_ids]
            if agent not in AGENTS_BY_NAME:
                # Try fuzzy match
                agent = self._fuzzy_agent(agent)
            if not agent or not task:
                continue
            seen_ids.add(tid)
            valid.append({"id": tid, "agent": agent, "task": task, "depends": deps})

        return valid

    # ─── Graph execution ──────────────────────────────────────────────────────

    def _execute_graph(self, tasks: list[dict], context: str) -> dict[str, TaskResult]:
        results: dict[str, TaskResult] = {t["id"]: TaskResult(t["id"]) for t in tasks}

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            self._pool = pool
            futures: dict[str, Future] = {}

            def submit(task: dict):
                fut = pool.submit(self._run_task, task, context, results)
                futures[task["id"]] = fut

            # Build dependency map
            task_map = {t["id"]: t for t in tasks}
            pending  = set(task_map.keys())
            running  = set()
            done_ids : set[str] = set()

            while (pending or running) and not self._stop_event.is_set():
                # Submit tasks whose deps are all done
                ready = [
                    tid for tid in pending
                    if all(d in done_ids for d in task_map[tid]["depends"])
                ]
                for tid in ready:
                    pending.discard(tid)
                    running.add(tid)
                    submit(task_map[tid])

                # Collect finished futures
                finished_now = [
                    tid for tid in list(running)
                    if futures[tid].done()
                ]
                for tid in finished_now:
                    running.discard(tid)
                    done_ids.add(tid)
                    try:
                        futures[tid].result()  # re-raise if exception
                    except Exception:
                        pass  # already captured in TaskResult

                if not ready and not finished_now:
                    time.sleep(0.1)

            self._pool = None

        return results

    def _run_task(self, task: dict, context: str, results: dict[str, TaskResult]):
        task_id    = task["id"]
        agent_name = task["agent"]
        profile    = AGENTS_BY_NAME.get(agent_name)

        if not profile:
            results[task_id].set(agent_name, False, f"Unknown agent: {agent_name}")
            if self.on_task_done:
                self.on_task_done(task_id, agent_name, False, f"Unknown agent: {agent_name}")
            return

        # Build context enriched with dependency results
        dep_ctx = context
        for dep_id in task["depends"]:
            dep_res = results.get(dep_id)
            if dep_res:
                dep_res.wait(timeout=300)
                if dep_res.result:
                    dep_ctx += f"\n\n# Result from {dep_res.agent}:\n{dep_res.result}"

        worker = AgentWorker(
            profile=profile,
            ai_config=self.ai_config,
            permission_cb=self.permission_cb,
            status_cb=self.status_cb,
            allow_all_cb=lambda: self._allow_all,
        )

        out = worker.run(task["task"], dep_ctx)
        results[task_id].set(out["agent"], out["success"], out["result"])

        if self.on_task_done:
            self.on_task_done(task_id, out["agent"], out["success"], out["result"])

    # ─── Summary ─────────────────────────────────────────────────────────────

    def _summarize(self, request: str, tasks: list[dict], results: dict[str, TaskResult]) -> str:
        profile = AGENTS_BY_NAME.get("Orchestrator")
        if not profile:
            return "Готово."

        parts = []
        for t in tasks:
            r = results.get(t["id"])
            status = "✅" if (r and r.success) else "❌"
            snippet = (r.result[:300] + "…") if r and len(r.result) > 300 else (r.result if r else "")
            parts.append(f"{status} [{t['agent']}] {t['task']}\n{snippet}")

        task_summary = "\n\n".join(parts)

        summary_prompt = f"""
Original request: {request}

Task results:
{task_summary}

Write a concise summary in Ukrainian for the user:
- What was done
- What succeeded / what failed
- Any important output or file paths
Keep it short (under 200 words). Respond in Ukrainian.
"""
        planning_profile = dict(profile)
        planning_profile["allowed_tools"] = []

        worker = AgentWorker(
            profile=planning_profile,
            ai_config=self.ai_config,
        )
        res = worker.run(summary_prompt)
        return res["result"] if res["success"] else task_summary

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _set_status(self, agent: str, status: str, detail: str):
        if self.status_cb:
            try:
                self.status_cb(agent, status, detail)
            except Exception:
                pass

    def _finish(self, summary: str):
        if self.on_finished:
            try:
                self.on_finished(summary)
            except Exception:
                pass

    @staticmethod
    def _fuzzy_agent(name: str) -> str:
        """Try to find closest agent name by substring match."""
        name_lower = name.lower()
        for p in AGENT_PROFILES:
            if name_lower in p["name"].lower() or p["name"].lower() in name_lower:
                return p["name"]
        return ""
