import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Set

from config import SESSION_DIR, WORKSPACE_DIR
from fastapi import WebSocket

from agent.logger import NodeLogger

_log = NodeLogger("state")

_APP = None
_SESSION_INDEX = os.path.join(SESSION_DIR, "_index.json")


def set_app(app):
    global _APP
    _APP = app


def get_app():
    return _APP


def _ensure_index():
    os.makedirs(SESSION_DIR, exist_ok=True)
    if not os.path.isfile(_SESSION_INDEX):
        with open(_SESSION_INDEX, "w", encoding="utf-8") as f:
            json.dump([], f)


def _read_index() -> list:
    _ensure_index()
    with open(_SESSION_INDEX, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    # 清理内部会话和孤儿（无对应 JSON 文件 + 无内存活跃状态）
    cleaned = []
    changed = False
    for s in data:
        sid = s["id"]
        if sid.startswith("sub_") or sid.startswith("cron_") or sid.startswith("_") or sid.startswith("test"):
            changed = True
            continue
        sf = os.path.join(SESSION_DIR, f"{sid}.json")
        if not os.path.isfile(sf) and sid not in _active_status:
            changed = True
            continue
        cleaned.append(s)
    if changed:
        with open(_SESSION_INDEX, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
    return cleaned


def _write_index(data: list):
    with open(_SESSION_INDEX, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_sessions() -> list[dict]:
    index = _read_index()
    indexed_ids = {s["id"] for s in index}

    # 扫描 sessions/ 目录下的孤立会话文件
    orphan_ids = set()
    if os.path.isdir(SESSION_DIR):
        for f in os.scandir(SESSION_DIR):
            if f.name.endswith(".json") and f.name != "_index.json":
                tid = f.name[:-5]
                if tid not in indexed_ids:
                    orphan_ids.add(tid)

    for tid in sorted(orphan_ids):
        # sub_/cron_/test_ 等内部会话不显示
        if tid.startswith("sub_") or tid.startswith("cron_") or tid.startswith("_") or tid.startswith("test"):
            continue
        index.append({"id": tid, "title": tid, "created_at": 0})
    if orphan_ids:
        _write_index(index)

    # 过滤：隐藏 sub_/cron_/_/test 等内部会话
    return [s for s in index if not (
        s["id"].startswith("sub_") or
        s["id"].startswith("cron_") or
        s["id"].startswith("test") or
        s["id"].startswith("_")
    )]


def rename_session(session_id: str, title: str) -> bool:
    sessions = _read_index()
    for s in sessions:
        if s["id"] == session_id:
            s["title"] = title
            _write_index(sessions)
            return True
    return False


def create_session(title: str = "新对话") -> dict:
    sessions = _read_index()
    session = {
        "id": uuid.uuid4().hex[:12],
        "title": title,
        "created_at": time.time(),
    }
    sessions.insert(0, session)
    _write_index(sessions)
    return session


def delete_session(session_id: str) -> bool:
    sessions = _read_index()
    before = len(sessions)
    sessions = [s for s in sessions if s["id"] != session_id]
    if len(sessions) == before:
        return False
    _write_index(sessions)

    # 清理 SQLite checkpoints
    try:
        import sqlite3
        conn = sqlite3.connect("conversations.db")
        conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (session_id,))
        conn.execute("DELETE FROM writes WHERE thread_id = ?", (session_id,))
        conn.commit()
        conn.execute("VACUUM")
        conn.close()
    except Exception:
        pass

    # 清理 sessions/<id>.json
    try:
        sf = os.path.join(SESSION_DIR, f"{session_id}.json")
        if os.path.isfile(sf):
            os.remove(sf)
    except Exception:
        pass

    # 清理内存活跃状态
    _active_status.pop(session_id, None)

    return True


def list_skills():
    from agent.skills.registry import get_registry
    reg = get_registry()
    return [{"name": s.name, "description": s.description, "enabled": reg.is_enabled(s.name)} for s in reg.list_all()]


def _find_workspace_file(filename: str) -> str:
    """在 WORKSPACE_DIR 子目录中查找文件，支持纯文件名和相对路径"""
    if "/" in filename or "\\" in filename:
        path = os.path.join(WORKSPACE_DIR, filename.replace("\\", os.sep))
        if os.path.isfile(path):
            return path
    basename = os.path.basename(filename)
    for root, dirs, files in os.walk(WORKSPACE_DIR):
        for f in files:
            if f == basename:
                return os.path.join(root, f)
    return ""


def read_workspace_file(filename: str) -> str:
    path = _find_workspace_file(filename)
    if path:
        return Path(path).read_text(encoding="utf-8")
    return ""


def write_workspace_file(filename: str, content: str):
    path = _find_workspace_file(filename)
    if not path:
        # 新文件写入 shared 目录
        shared_dir = os.path.join(WORKSPACE_DIR, "shared")
        os.makedirs(shared_dir, exist_ok=True)
        path = os.path.join(shared_dir, os.path.basename(filename))
    Path(path).write_text(content, encoding="utf-8")


def list_cron_jobs():
    from agent.cron import get_manager
    return get_manager().list_jobs()


def remove_cron_job(job_id: str):
    from agent.cron import get_manager
    get_manager().remove(job_id)


# ── WebSocket 广播 ──

_ws_clients: Set[WebSocket] = set()
_main_loop: asyncio.AbstractEventLoop = None
_active_status: dict[str, dict] = {}  # sid → {status, task_type, step, tokens, source}

SOURCE_ICONS = {"web": "🖥", "qq": "💬", "cron": "⏰", "sub": "📦", "": "❓"}


def update_session_status(sid: str, **kwargs):
    """更新活跃会话状态；内部会话 (sub_/cron_/_) 不写入索引"""
    _active_status[sid] = {"updated_at": time.time(), **kwargs}
    # 内部会话不注册到前端侧边栏
    if sid.startswith("sub_") or sid.startswith("cron_") or sid.startswith("_"):
        return
    _ensure_index()
    index = _read_index()
    if not any(s["id"] == sid for s in index):
        title = sid
        if sid.startswith("qq_"): title = "QQ-" + sid[3:11]
        elif sid.startswith("web_"): title = "Web-" + sid[4:12]
        index.insert(0, {"id": sid, "title": title, "created_at": time.time()})
        _write_index(index)


def _cleanup_stale_status():
    """清理超过 30 分钟未更新的内存状态"""
    cutoff = time.time() - 1800
    stale = [sid for sid, v in _active_status.items() if v.get("updated_at", 0) < cutoff]
    for sid in stale:
        del _active_status[sid]


def get_sessions_with_status() -> list[dict]:
    """合并 sessions/ JSON 持久数据 + 内存活跃状态"""
    _cleanup_stale_status()
    index = _read_index()
    # 过滤内部会话
    index = [s for s in index if not (
        s["id"].startswith("sub_") or
        s["id"].startswith("cron_") or
        s["id"].startswith("_") or
        s["id"].startswith("test")
    )]
    result = []
    for s in index:
        tid = s["id"]
        entry = {"id": tid, "title": s.get("title", tid), "created_at": s.get("created_at", 0)}
        # 读持久化的 last_state
        sf = os.path.join(SESSION_DIR, f"{tid}.json")
        if os.path.isfile(sf):
            try:
                data = json.loads(Path(sf).read_text(encoding="utf-8"))
                entry["source"] = data.get("source", "")
                entry["summary"] = data.get("summary", "")[:200]
                entry["last_state"] = data.get("last_state", {})
                entry["updated_at"] = data.get("updated_at", 0)
            except Exception:
                pass
        # 覆盖活跃状态
        active = _active_status.get(tid)
        if active and active.get("updated_at", 0) > entry.get("updated_at", 0):
            entry["active"] = True
            entry["updated_at"] = active["updated_at"]  # 用活跃状态的时间
            entry["last_state"] = {**entry.get("last_state", {}), **active}
        # 推断来源：持久化 → ID 前缀 → 默认 web
        src = entry.get("source", "") or (active or {}).get("source", "")
        if not src:
            if tid.startswith("qq_"): src = "qq"
            elif tid.startswith("cron_"): src = "cron"
            else: src = "web"
        entry["source"] = src
        entry["source_icon"] = SOURCE_ICONS.get(src, "💬")
        entry["status"] = entry.get("last_state", {}).get("status", "idle")
        entry["execution_mode"] = entry.get("last_state", {}).get("execution_mode", "")
        result.append(entry)
    result.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    return result


def broadcast_monitor_update():
    """广播全局 Monitor 更新给所有前端 WS 客户端"""
    data = {"type": "monitor_global", "sessions": get_sessions_with_status()}
    loop = _main_loop
    if not loop:
        return
    for ws in list(_ws_clients):
        asyncio.run_coroutine_threadsafe(ws.send_json(data), loop)


async def broadcast_monitor_async():
    """异步版广播，从事件循环内直接调用"""
    data = {"type": "monitor_global", "sessions": get_sessions_with_status()}
    for ws in list(_ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            pass


def set_main_loop(loop: asyncio.AbstractEventLoop):
    global _main_loop
    _main_loop = loop


def register_ws(ws: WebSocket):
    _ws_clients.add(ws)


def unregister_ws(ws: WebSocket):
    _ws_clients.discard(ws)


def broadcast_sync(data: dict):
    """同步版广播，供 daemon 线程（如 CronManager）调用"""
    loop = _main_loop
    if not loop:
        _log.warn("broadcast: no main loop")
        return
    _log.debug(f"broadcast: type={data.get('type','?')} to {len(_ws_clients)} clients")
    for ws in list(_ws_clients):
        asyncio.run_coroutine_threadsafe(ws.send_json(data), loop)
