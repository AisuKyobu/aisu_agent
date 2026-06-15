import asyncio
import logging
import os

logging.getLogger("httpx").setLevel(logging.WARNING)
import shutil
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agent.logger import NodeLogger

logger = logging.getLogger("aisu.server")
_server_log = NodeLogger("server")

from server.state import (get_app, list_cron_jobs, list_skills,
                           read_workspace_file, register_ws, remove_cron_job,
                           rename_session, unregister_ws,
                           write_workspace_file, list_sessions,
                           create_session, delete_session,
                           update_session_status, broadcast_monitor_update,
                           broadcast_monitor_async, get_sessions_with_status,
                           get_session_owner, check_session_access)
from server.auth import get_current_user, require_user, decode_jwt


@asynccontextmanager
async def lifespan(app):
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from agent.conversation_graph import build_conversation_graph
    from config import CONVERSATION_DB
    conn = await aiosqlite.connect(CONVERSATION_DB)
    saver = AsyncSqliteSaver(conn)
    conv_app = build_conversation_graph(checkpointer=saver)

    from agent.cron import get_manager as get_cron_manager
    get_cron_manager().set_app(conv_app)
    get_cron_manager().start()

    from agent.skills.registry import init_skills
    init_skills()

    from agent.memory.manager import get_manager as get_memory_manager
    mgr = get_memory_manager()
    mgr.initialize_all(profile="dev")

    from server.state import set_main_loop, set_app
    set_main_loop(asyncio.get_event_loop())
    set_app(conv_app)

    yield

    mgr.shutdown()
    await conn.close()


app = FastAPI(title="Aisu", lifespan=lifespan)

from server.auth import install_auth
install_auth(app)

# ── 静态资源 ──
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

_VUE_DIST = Path(__file__).parent.parent / "web" / "dist"
if _VUE_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_VUE_DIST / "assets")), name="assets")

templates = Jinja2Templates(directory="server/templates")


class WorkspaceWrite(BaseModel):
    filename: str
    content: str


class CronDelete(BaseModel):
    job_id: str


class SessionCreate(BaseModel):
    title: str = "新对话"


class SessionRename(BaseModel):
    title: str


class SkillToggle(BaseModel):
    enabled: bool


class SettingsUpdate(BaseModel):
    data: dict
    profile: str = "dev"


class ProfileSwitch(BaseModel):
    profile: str


# ── Page ──

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    vue_index = _VUE_DIST / "index.html"
    if vue_index.exists():
        return HTMLResponse(vue_index.read_text(encoding="utf-8"))
    skills = list_skills()
    agents_md = read_workspace_file("AGENTS.md")
    user_md = read_workspace_file("USER.md")
    cron_jobs = list_cron_jobs()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "skills": skills,
            "agents_md": agents_md,
            "user_md": user_md,
            "cron_jobs": cron_jobs,
        },
    )


# ── Sessions ──

@app.get("/api/sessions")
async def api_list_sessions(user: dict | None = Depends(get_current_user)):
    user_id = user["id"] if user else None
    return {"sessions": list_sessions(user_id=user_id)}


@app.get("/api/monitor/sessions")
async def api_monitor_sessions(user: dict = Depends(require_user)):
    return {"sessions": get_sessions_with_status()}


@app.post("/api/sessions")
async def api_create_session(data: SessionCreate, user: dict | None = Depends(get_current_user)):
    user_id = user["id"] if user else None
    session = create_session(data.title, user_id=user_id)
    return {"session": session}


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str, user: dict | None = Depends(get_current_user)):
    user_id = user["id"] if user else None
    if not check_session_access(session_id, user_id):
        raise HTTPException(status_code=403, detail="无权操作该会话")
    ok = delete_session(session_id)
    return {"ok": ok}


@app.patch("/api/sessions/{session_id}")
async def api_rename_session(session_id: str, data: SessionRename, user: dict | None = Depends(get_current_user)):
    user_id = user["id"] if user else None
    if not check_session_access(session_id, user_id):
        raise HTTPException(status_code=403, detail="无权操作该会话")
    ok = rename_session(session_id, data.title)
    return {"ok": ok}


# ── WebSocket Chat (Streaming) ──

async def _send_agent_status(websocket, config, sid):
    try:
        conv = get_app()
        snapshot = await conv.aget_state(config)
        sv = snapshot.values
        tools_set = set()
        for m in sv.get("messages", []):
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                    if name:
                        tools_set.add(name)
        from tools.plan_tools import load_plan
        plan_data = load_plan()
        steps = []
        completed = set(plan_data.get("completed", []))
        for idx, s in enumerate(plan_data.get("steps", [])):
            steps.append({"text": s, "done": idx in completed})
        sv_tools = sorted(tools_set)

        # ── 检测限制命中 ──
        from agent.common import count_tool_calls
        from config import MAX_SEARCH_COUNT, REASONING_MAX_SEARCH, REASONING_MAX_TOOL_CALLS
        msgs = sv.get("messages", [])
        tt = sv.get("task_type", "")
        limit_hit = ""
        if tt == "search":
            sc = count_tool_calls(msgs, ("web_search", "web_fetch"), per_turn=True)
            if sc >= MAX_SEARCH_COUNT:
                limit_hit = f"搜索次数已达上限 ({sc}/{MAX_SEARCH_COUNT})"
        elif tt == "reasoning":
            sc = count_tool_calls(msgs, ("web_search", "web_fetch"), per_turn=True)
            if sc >= REASONING_MAX_SEARCH:
                limit_hit = f"推理搜索已达上限 ({sc}/{REASONING_MAX_SEARCH})"
            tc = count_tool_calls(msgs, ("read_file","write_file","run_command","web_search","web_fetch",
                "plan_task","step_complete","browser_open","browser_click","browser_type","browser_screenshot","cron_add"), per_turn=True)
            if tc >= REASONING_MAX_TOOL_CALLS:
                limit_hit = f"工具调用已达上限 ({tc}/{REASONING_MAX_TOOL_CALLS})"

        await websocket.send_json({
            "type": "agent_status",
            "task_type": sv.get("task_type", ""),
            "current_step": sv.get("current_step", 0),
            "max_steps": sv.get("max_steps", 10),
            "plan": steps,
            "tools_used": sv_tools,
            "loaded_skills": sv.get("loaded_skills", []),
            "missing_params": sv.get("missing_params", []),
            "session_id": sid,
            "limit_hit": limit_hit,
        })
        if limit_hit:
            await websocket.send_json({"type": "limit_hit", "reason": limit_hit, "session_id": sid})
        update_session_status(sid, status="idle",
            task_type=sv.get("task_type", ""),
            execution_mode=sv.get("execution_mode", "react"),
            step=sv.get("current_step", 0),
            max_steps=sv.get("max_steps", 10),
            tools_used=sv_tools)
        broadcast_monitor_update()
        for m in sv.get("messages", []):
            if hasattr(m, "content") and isinstance(m.content, str) and m.content.startswith("[系统错误]"):
                await websocket.send_json({"type": "system_error", "content": m.content})
                update_session_status(sid, status="error")
                broadcast_monitor_update()
                break
    except Exception:
        logger.exception("agent_status failed")
        update_session_status(sid, status="error")


async def _save_session_snapshot(conv, config, sid, src="web"):
    try:
        from agent.session import save_session
        snapshot = await conv.aget_state(config)
        sv = snapshot.values
        msgs = sv.get("messages", [])
        last_human = ""
        last_ai = ""
        tools_set = set()
        for m in msgs:
            if hasattr(m, "type") and m.type == "human":
                last_human = str(m.content)[:80] if hasattr(m, "content") else ""
            if hasattr(m, "type") and m.type == "ai":
                ai_text = str(m.content) if hasattr(m, "content") else ""
                if ai_text:
                    last_ai = ai_text[:200]
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    n = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                    if n: tools_set.add(n)
        if last_ai:
            last_state = {
                "status": "idle",
                "task_type": sv.get("task_type", ""),
                "execution_mode": sv.get("execution_mode", "react"),
                "step": sv.get("current_step", 0),
                "max_steps": sv.get("max_steps", 10),
                "tools_used": sorted(tools_set),
            }
            save_session(sid, f"用户: {last_human}\nAI: {last_ai}", source=src, last_state=last_state)

            # ── Episodic Memory: 任务完成自动写入 ──
            try:
                tg = sv.get("task_graph", {})
                steps_data = [{"id": nid, **nd} for nid, nd in tg.get("nodes", {}).items()] if tg else []
                errs = sv.get("pending_fixes", [])
                vlog = sv.get("verification_log", [])
                outcome = "success" if not errs else "needs_human" if sv.get("needs_human") else "partial"
                from agent.memory.manager import get_manager as get_memory_manager
                mgr = get_memory_manager()
                mgr.save_episode(tg.get("goal", last_human), steps_data, errs, outcome, last_ai)
                if sv.get("task_type") in ("action", "planning", "reasoning"):
                    mgr.maybe_reflect()
                mgr.sync_all(last_human, last_ai)
            except Exception:
                pass
    except Exception:
        pass


@app.websocket("/ws")
async def ws_chat(websocket: WebSocket):
    token = websocket.query_params.get("token")
    ws_user = None
    if token:
        payload = decode_jwt(token)
        if payload:
            from server.db import get_user_by_id
            ws_user = get_user_by_id(payload["sub"])
    await websocket.accept()
    logger.info("WS connected: %s (user: %s)", websocket.client, ws_user["username"] if ws_user else "guest")
    conv = get_app()
    if not conv:
        await websocket.send_json({"type": "error", "content": "Agent 未就绪"})
        await websocket.close()
        return

    register_ws(websocket)
    loop = asyncio.get_event_loop()

    _echo_prefixes = ("你已经没有剩余步数", "工具调用次数即将达到上限", "你已经反复调用了多次工具")
    _echo_buf = ""

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") != "message":
                continue

            text = data.get("content", "").strip()
            sid = data.get("session_id", "ws_default")
            src = data.get("source", "web")
            profile = data.get("profile", "dev")
            if not text:
                continue
            _server_log.bind(sid, 0)
            _server_log.user_msg(src, text)

            update_session_status(sid, status="thinking", source=src)
            await broadcast_monitor_async()
            config = {"configurable": {"thread_id": sid}, "recursion_limit": 100}
            state = {"messages": [HumanMessage(content=text)], "thread_id": sid, "profile": profile,
                     "user_id": ws_user["id"] if ws_user else "guest"}
            _echo_buf = ""

            try:
                _node_times = {}
                _node_order = []
                _total_tokens = 0

                async for event in conv.astream_events(state, config, version="v2"):
                    kind = event["event"]
                    node = event.get("metadata", {}).get("langgraph_node", "")

                    # ── 节点进入/退出 → 发射给 Monitor ──
                    if kind == "on_chain_start" and node:
                        _node_times[node] = {"enter": asyncio.get_event_loop().time()}
                        await websocket.send_json({
                            "type": "node_enter", "node": node, "session_id": sid,
                        })
                    elif kind == "on_chain_end" and node:
                        tn = _node_times.get(node, {})
                        dur = round(asyncio.get_event_loop().time() - tn.get("enter", asyncio.get_event_loop().time()), 2)
                        _node_order.append(node)
                        await websocket.send_json({
                            "type": "node_exit", "node": node, "duration": dur, "session_id": sid,
                        })

                    # ── 状态快照（agent 节点完成后） ──
                    if kind == "on_chain_end" and node == "agent":
                        try:
                            ss = await conv.aget_state(config)
                            sv = ss.values
                            msgs = sv.get("messages", [])
                            await websocket.send_json({
                                "type": "state_snapshot",
                                "task_type": sv.get("task_type", ""),
                                "current_step": sv.get("current_step", 0),
                                "max_steps": sv.get("max_steps", 10),
                                "msg_count": len(msgs),
                                "tokens": _total_tokens,
                                "summary_len": len(sv.get("summary", "")),
                                "loaded_skills": sv.get("loaded_skills", []),
                                "session_id": sid,
                            })
                        except Exception:
                            pass

                    # ── LLM 流式 token ──
                    if kind == "on_chat_model_stream" and node not in ("analyzer", "router"):
                        chunk = event["data"].get("chunk")
                        if chunk and chunk.content:
                            token = chunk.content
                            _total_tokens += 1
                            probe = _echo_buf + token
                            is_echo = any(probe.startswith(p) for p in _echo_prefixes)
                            if is_echo and len(probe) < 80:
                                _echo_buf = probe
                                continue
                            if _echo_buf:
                                await websocket.send_json({"type": "token", "content": _echo_buf + token, "session_id": sid})
                                _echo_buf = ""
                            else:
                                await websocket.send_json({"type": "token", "content": token, "session_id": sid})

                    # ── 工具调用 ──
                    elif kind == "on_tool_start":
                        tool_name = event.get("name", "")
                        tool_input = event.get("data", {}).get("input")
                        if tool_name:
                            if isinstance(tool_input, dict):
                                pairs = [f"{k}={v}" for k, v in tool_input.items()]
                                args_str = ", ".join(pairs)[:200]
                            else:
                                args_str = str(tool_input)[:200] if tool_input else ""
                            _node_times[tool_name] = {"enter": asyncio.get_event_loop().time()}
                            await websocket.send_json({"type": "tool_call", "tools": [tool_name], "args": args_str, "session_id": sid})
                    elif kind == "on_tool_end":
                        tool_name = event.get("name", "")
                        output = event["data"].get("output", "")
                        tn = _node_times.get(tool_name, {})
                        dur = round(asyncio.get_event_loop().time() - tn.get("enter", asyncio.get_event_loop().time()), 2)
                        if output and str(output).strip():
                            await websocket.send_json({"type": "tool_result", "content": str(output)[:200], "duration": dur, "tool_name": tool_name, "session_id": sid})

                # Send agent status（对话完成后汇总）
                await _send_agent_status(websocket, config, sid)
                await _save_session_snapshot(conv, config, sid, src)

                # ── 日志：最终回复 ──
                try:
                    snapshot = await conv.aget_state(config)
                    sv = snapshot.values
                    for m in reversed(sv.get("messages", [])):
                        if hasattr(m, "type") and m.type == "ai" and hasattr(m, "content") and m.content:
                            if not (hasattr(m, "tool_calls") and m.tool_calls):
                                _server_log.bind(sid, 0)
                                _server_log.ai_msg(str(m.content)[:300])
                                break
                except Exception:
                    pass

                await websocket.send_json({
                    "type": "done",
                    "session_id": sid,
                    "node_order": _node_order,
                    "total_tokens": _total_tokens,
                })

            except Exception as e:
                await websocket.send_json({"type": "error", "content": str(e)[:500], "session_id": sid})

    except WebSocketDisconnect:
        pass
    finally:
        unregister_ws(websocket)


# ── History ──

@app.get("/api/sessions/{session_id}/history")
async def get_session_history(session_id: str, user: dict | None = Depends(get_current_user)):
    user_id = user["id"] if user else None
    if not check_session_access(session_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问该会话")
    conv = get_app()
    if not conv:
        return {"ok": False, "error": "Agent 未就绪"}

    config = {"configurable": {"thread_id": session_id}}
    loop = asyncio.get_event_loop()
    try:
        snapshot = await loop.run_in_executor(None, conv.get_state, config)
    except Exception:
        return {"ok": True, "messages": []}

    msgs = []
    has_summary = snapshot.values.get("summary", "")
    if has_summary:
        msgs.append({"role": "system", "content": f"[历史摘要] {has_summary}"})
    for m in snapshot.values.get("messages", []):
        t = getattr(m, "type", "")
        if t == "ai":
            tc = getattr(m, "tool_calls", None)
            content = getattr(m, "content", "") or ""
            if not content and tc:
                continue
            msgs.append({"role": "ai", "content": content})
        elif t == "human":
            msgs.append({"role": "human", "content": getattr(m, "content", "")})
        elif t == "tool":
            c = getattr(m, "content", "") or ""
            if c:
                msgs.append({"role": "tool", "content": str(c)[:300], "name": getattr(m, "name", "")})
    return {"ok": True, "messages": msgs}


# ── Skills ──

@app.get("/api/skills")
async def get_skills():
    return {"skills": list_skills()}


@app.patch("/api/skills/{skill_name}")
async def toggle_skill(skill_name: str, data: SkillToggle, user: dict = Depends(require_user)):
    from agent.skills.registry import get_registry
    get_registry().set_enabled(skill_name, data.enabled)
    return {"ok": True}


@app.post("/api/skills/install")
async def install_skills_zip(file: UploadFile = File(...), user: dict = Depends(require_user)):
    if not file.filename or not file.filename.endswith(".zip"):
        return {"ok": False, "error": "仅支持 .zip 文件"}

    tmpdir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(file.file) as zf:
            zf.extractall(tmpdir)

        installed = 0
        installed_names = []
        skipped = {"README.md", ".git", ".gitignore", ".DS_Store", "__pycache__", ".clawhub", "node_modules", ".obsidian"}

        def _ignore(path, names):
            return {n for n in names if n in skipped or n.startswith(".")}

        for root, dirs, files in os.walk(tmpdir):
            if "SKILL.md" not in files:
                continue
            skill_name_from_file = None
            skill_file = os.path.join(root, "SKILL.md")
            for line in Path(skill_file).read_text(encoding="utf-8").split("\n")[:5]:
                line = line.strip()
                if line.startswith("name:"):
                    skill_name_from_file = line.split(":", 1)[1].strip()
                    break
            if not skill_name_from_file:
                continue

            dest = os.path.join("skills", skill_name_from_file)
            if os.path.exists(dest):
                continue

            shutil.copytree(root, dest, ignore=_ignore, dirs_exist_ok=True)
            installed += 1
            installed_names.append(skill_name_from_file)

        from agent.skills.registry import get_registry
        get_registry().discover()
        return {"ok": True, "installed": installed, "names": installed_names}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Workspace ──

@app.get("/api/workspace")
async def list_workspace(user: dict = Depends(require_user)):
    import os
    from config import WORKSPACE_DIR
    files = []
    for root, dirs, filenames in os.walk(WORKSPACE_DIR):
        rel = os.path.relpath(root, WORKSPACE_DIR)
        for fn in filenames:
            rp = os.path.join(rel, fn) if rel != "." else fn
            rp = rp.replace("\\", "/")
            files.append(rp)
    return {"files": files}


@app.get("/api/workspace/{filename:path}")
async def get_workspace(filename: str, user: dict = Depends(require_user)):
    return {"content": read_workspace_file(filename)}


@app.post("/api/workspace")
async def save_workspace(data: WorkspaceWrite, user: dict = Depends(require_user)):
    write_workspace_file(data.filename, data.content)
    return {"ok": True}


# ── Cron ──

@app.get("/api/cron")
async def get_cron():
    return {"jobs": list_cron_jobs()}


@app.post("/api/cron/remove")
async def delete_cron(data: CronDelete, user: dict = Depends(require_user)):
    remove_cron_job(data.job_id)
    return {"ok": True}


# ── Settings ──

@app.get("/api/settings")
async def get_settings(profile: str = "dev"):
    from agent.settings import get_all
    return {"settings": get_all(profile=profile)}


@app.post("/api/settings")
async def save_settings(data: SettingsUpdate, user: dict = Depends(require_user)):
    from agent.settings import save
    ok = save(data.data, profile=data.profile)
    return {"ok": ok}


# ── Profiles ──

@app.get("/api/profiles")
async def get_profiles():
    import os
    from config import WORKSPACE_DIR
    profiles = []
    ws_dir = WORKSPACE_DIR
    for name in sorted(os.listdir(ws_dir)):
        path = os.path.join(ws_dir, name)
        if os.path.isdir(path) and name not in ("shared",):
            profiles.append({"id": name, "label": {"dev": "开发助手", "qq": "QQ群管家"}.get(name, name)})
    if not profiles:
        profiles = [{"id": "dev", "label": "开发助手"}]
    return {"profiles": profiles}
