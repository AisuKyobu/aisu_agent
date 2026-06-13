"""Sub-Agent Spawn — 独立 thread_id 执行子图，支持 Skill DAG + 通用 goal + 并行批量。

安全加固 (L6):
  - SUBAGENT_BLOCKED_TOOLS 阻止委派/cron/澄清
  - child_depth 计数器 + MAX_SPAWN_DEPTH=1 防无限嵌套
"""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_core.messages import HumanMessage
from agent.logger import NodeLogger

_log = NodeLogger("sub_agent")

SUBAGENT_BLOCKED_TOOLS = frozenset({
    "delegate_task", "cron_add", "cron_list", "cron_remove",
})
MAX_SPAWN_DEPTH = 1
_MAX_PARALLEL = 4


def spawn_sub_agent(
    conv_app, task_def: dict, params: dict = None, timeout: int = 120,
    child_depth: int = 0,
) -> dict:
    """为 Skill DAG 或通用 goal 创建独立执行上下文。

    task_def 有两种形式:
      1. Skill 状态机: {"name":"x","nodes":[...],"params":{}} → execution_mode="dag"
      2. 通用任务:   {"goal":"分析项目A","toolsets":["web","file"]} → execution_mode="react"

    Returns:
        {"thread_id": str, "goal": str, "output": dict, "status": "completed"|"failed"|"partial"}
    """
    from agent.skills.executor import expand_to_taskgraph, skill_name_from_markdown

    if child_depth >= MAX_SPAWN_DEPTH:
        return {"thread_id": "", "status": "failed",
                "error": f"Max spawn depth ({MAX_SPAWN_DEPTH}) reached", "output": {}}

    # ── 区分 Skill DAG vs 通用 goal ──
    if task_def.get("nodes"):
        # Skill 状态机模式
        skill_name = task_def.get("name", skill_name_from_markdown(str(task_def)))
        sub_tid = f"sub_{skill_name}_{uuid.uuid4().hex[:6]}"
        params = params or {}
        tg = expand_to_taskgraph(task_def, params)

        if tg and tg.get("nodes"):
            filtered = {}
            for nid, node in tg["nodes"].items():
                if node.get("tool") in SUBAGENT_BLOCKED_TOOLS:
                    _log.warn(f"blocked tool in sub-agent: {node.get('tool')}")
                    continue
                filtered[nid] = node
            tg["nodes"] = filtered

        if not tg or not tg.get("nodes"):
            return {"thread_id": sub_tid, "status": "failed",
                    "error": "无法展开 skill task_graph", "output": {}}

        mode = "dag"
        verifier_level = task_def.get("execution", {}).get("verifier_level", "L1+L2")
        max_steps = len(tg["nodes"]) * 3 + 5
        goal_text = tg.get("goal", "")
        state_msg = HumanMessage(content=f"执行技能: {skill_name}, 参数: {str(params)[:100]}")
    else:
        # 通用委派模式 (delegate_task)
        goal_text = task_def.get("goal", "")
        sub_tid = f"delegate_{uuid.uuid4().hex[:8]}"
        mode = task_def.get("execution_mode", "react")
        verifier_level = task_def.get("verifier_level", "L1+L2")
        max_steps = task_def.get("max_steps",
            task_def.get("max_iterations", 50))
        tg = None
        state_msg = HumanMessage(content=f"执行任务: {goal_text}")

    state = {
        "messages": [state_msg],
        "task_graph": tg,
        "execution_mode": mode,
        "verifier_level": verifier_level,
        "max_steps": max_steps,
        "thread_id": sub_tid,
    }
    config = {"configurable": {"thread_id": sub_tid}, "recursion_limit": 100}

    try:
        result = conv_app.invoke(state, config)
        outputs = {}
        msgs = result.get("messages", [])
        tool_outputs = []
        for m in msgs:
            if hasattr(m, "type") and m.type == "tool":
                tool_outputs.append(
                    hasattr(m, "content") and str(m.content)[:200] or "")
        if tg:
            final_tg = result.get("task_graph", tg)
            nodes_done = sum(
                1 for n in final_tg.get("nodes", {}).values()
                if n.get("status") in ("completed",))
            total = len(final_tg.get("nodes", {}))
            status = "completed" if nodes_done >= total else "partial"
            outputs["nodes_completed"] = f"{nodes_done}/{total}"
        else:
            ai_msgs = [m for m in msgs if hasattr(m, "type") and m.type == "ai" and m.content]
            final_text = str(ai_msgs[-1].content)[:300] if ai_msgs else ""
            outputs["final_response"] = final_text
            status = "completed"

        outputs["tool_outputs"] = tool_outputs[-3:] if tool_outputs else []
        outputs["goal"] = goal_text

        try:
            from server.state import broadcast_monitor_update, update_session_status
            update_session_status(
                sub_tid, status="idle", source="sub", execution_mode=mode,
                step=len(msgs), max_steps=max_steps, tools_used=[])
            broadcast_monitor_update()
        except Exception:
            pass

        _log.step_done(f"sub-agent {sub_tid}: {status}")
        return {"thread_id": sub_tid, "goal": goal_text,
                "output": outputs, "status": status}
    except Exception as e:
        _log.warn(f"sub-agent failed: {sub_tid}")
        return {"thread_id": sub_tid, "status": "failed",
                "error": str(e), "output": {}}


def spawn_sub_agents_parallel(conv_app, tasks: list,
                               child_depth: int = 0) -> list[dict]:
    """并行执行多个子 Agent。

    tasks: [{"goal":"...","toolsets":[...]}, ...]
    """
    if len(tasks) <= 1:
        return [spawn_sub_agent(conv_app, t, child_depth=child_depth) for t in tasks]

    results = [None] * len(tasks)
    with ThreadPoolExecutor(max_workers=min(len(tasks), _MAX_PARALLEL)) as pool:
        futures = {
            pool.submit(spawn_sub_agent, conv_app, t, child_depth=child_depth): i
            for i, t in enumerate(tasks)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result(timeout=120)
            except Exception as e:
                results[idx] = {"thread_id": "", "status": "failed",
                                "error": str(e), "output": {}}
    return results
