import asyncio
import json
import os
import threading
import time
import uuid
from langchain_core.messages import HumanMessage
from agent.logger import NodeLogger
from config import CRON_FILE

_log = NodeLogger("cron")


class CronManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._app = None
        self._event_loop = None
        self._running = False
        self._thread = None
        self._jobs: dict = {}
        self._load()

    def set_app(self, app):
        self._app = app
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    def _load(self):
        if not os.path.isfile(CRON_FILE):
            return
        with open(CRON_FILE, "r", encoding="utf-8") as f:
            self._jobs = json.load(f)

    def _save(self):
        with open(CRON_FILE, "w", encoding="utf-8") as f:
            json.dump(self._jobs, f, ensure_ascii=False, indent=2)

    def add(self, interval: int, task: str, once: bool = False, session_id: str = "") -> str:
        job_id = f"cron_{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id, "interval": interval, "task": task,
                "once": once, "session_id": session_id,
                "next_run": time.time() + interval,
            }
            self._save()
        _log.step_done(f"cron add: {job_id} interval={interval} sid={session_id} task={task[:40]}")
        return job_id

    def remove(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                self._save()
                return True
        return False

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return list(self._jobs.values())

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            now = time.time()
            to_run = []
            with self._lock:
                for jid, job in list(self._jobs.items()):
                    if now >= job["next_run"]:
                        if job.get("once"):
                            del self._jobs[jid]
                        else:
                            job["next_run"] = now + job["interval"]
                        to_run.append(job)
            if to_run:
                self._save()
            for job in to_run:
                threading.Thread(target=self._execute, args=(job,), daemon=True).start()
            time.sleep(5)

    def _execute(self, job: dict):
        if not self._app or not self._event_loop:
            return
        ok = False
        err_msg = ""
        sid = job.get("session_id", "")
        tid = sid if sid else job["id"]

        try:
            msg = f"[定时任务] {job['task']}"
            state = {"messages": [HumanMessage(content=msg)]}
            config = {"configurable": {"thread_id": tid}, "recursion_limit": 100}
            future = asyncio.run_coroutine_threadsafe(
                self._app.ainvoke(state, config=config), self._event_loop
            )
            future.result(timeout=60)
            ok = True
        except Exception as e:
            err_msg = str(e)
            _log.warn(f"cron execute failed: {job['id']} — {err_msg[:120]}")

        try:
            from server.state import broadcast_sync
            payload = {
                "type": "cron_result",
                "task": job["task"],
                "status": "completed" if ok else "failed",
                "session_id": job.get("session_id", ""),
            }
            if not ok:
                payload["error"] = err_msg[:200]
            _log.step_done(f"cron broadcast: sid={job.get('session_id','')} task={job['task'][:40]}")
            broadcast_sync(payload)
            try:
                from agent.session import save_session
                save_session(tid, f"[定时任务] {job['task']}\n状态: {'完成' if ok else '失败'}", source="cron",
                    last_state={"status": "completed" if ok else "error",
                                "task_type": "action", "step": 1, "max_steps": 20, "tools_used": []})
                from server.state import update_session_status, broadcast_monitor_update
                update_session_status(tid, status="idle", source="cron")
                broadcast_monitor_update()
            except Exception:
                pass
        except Exception:
            _log.warn("cron broadcast failed")


_manager = CronManager()


def get_manager():
    return _manager
