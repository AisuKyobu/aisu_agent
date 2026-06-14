"""Agent node — 核心 LLM 推理节点: 组装 System Prompt + 工具调用 + Token 预算压缩"""
import platform

from langchain_core.messages import AIMessage, RemoveMessage, SystemMessage

from agent.common import (context_refresh, invoke_with_retry)
from agent.compressor import compress_messages_structured, get_budget
from agent.logger import NodeLogger
from agent.core.reflector import REFLECT_INTERVAL, reflect as run_reflection
from agent.core.scheduler import (build_scoped_context, format_hint, scheduler_dispatch)
from agent.skills.registry import get_registry as get_skill_registry
from agent.state import AgentState
from agent.system_prompt import build_system_prompt, join_prompt_parts
from agent.types import TaskType
from config import REASONING_MAX_FILE_READS, REASONING_MAX_SEARCH, REASONING_MAX_TOOL_CALLS
from tools.plan_tools import format_plan, format_task_graph, load_plan, load_task_graph, set_plan_thread_id
from tools.tool_registry import registry


def _get_setting(key, default, profile="dev"):
    try:
        from agent.settings import get
        return get(key, profile=profile, default=default)
    except Exception:
        return default


_prompt_cache = {}


def agent_node(state: AgentState, ctx) -> dict:
    _log = NodeLogger("agent")
    summary = state.get("summary", "")
    tid = state.get("thread_id", "")
    set_plan_thread_id(tid)
    _log.bind(tid, state.get("current_step", 0))
    plan_data = load_plan(tid)
    plan = format_plan(plan_data)
    tg = load_task_graph(tid)
    messages = list(state["messages"])
    _profile = state.get("profile", "dev")
    keep_count = _get_setting("KEEP_MESSAGES", 80, profile=_profile)
    recent_msgs = messages[-keep_count:] if len(messages) > keep_count else messages
    em = state.get("execution_mode", "react")
    sd = scheduler_dispatch(em, tg, state)
    tt = state.get("task_type", "")

    context_length = _get_setting("CONTEXT_LENGTH", 128000, profile=_profile)
    budget = get_budget(session_id=tid, context_length=context_length)

    valid_tools = registry.get_all_tool_names()
    budget.estimate(messages, tools_count=len(valid_tools))

    _log.step_start(f"Agent({tt or '?'}) step={state.get('current_step',0)}/{state.get('max_steps','?')} msgs={len(messages)} est={budget._rough_estimate}")
    _current_step = state.get("current_step", 0)
    _tid_key = tid or "default"

    if _current_step == 0 or _tid_key not in _prompt_cache:
        guidance_text = ctx.workspace.load_file("GUIDANCE.md", profile=_profile)
        parts = build_system_prompt(
            system_prompt_base=ctx.system_prompt,
            valid_tool_names=valid_tools,
            workspace_blocks=ctx.workspace.load_all(profile=_profile),
            retrieved_memory=state.get("retrieved_memory", {}),
            summary=summary,
            task_type=tt,
            task_constraints=state.get("task_constraints", ""),
            thread_id=tid,
            guidance_text=guidance_text,
        )
        _prompt_cache[_tid_key] = parts
    else:
        parts = _prompt_cache[_tid_key]

    context = [SystemMessage(content=join_prompt_parts(parts))]

    context.append(SystemMessage(
        content=f"当前运行环境: {platform.system()} {platform.release()} | "
                f"命令规范: Windows→where/dir/find, Linux→which/ls/grep"))

    if tg and tg.get("goal"):
        cs = state.get("current_step", 0)
        if cs > 0 and cs % 5 == 0:
            context.append(SystemMessage(content=(
                f"⚠ 已执行 {cs} 步。请回顾上文，确认当前操作仍在推进目标。"
                f"如果发现偏离，立即回到目标主线。"
            )))

    loaded = state.get("loaded_skills", [])
    loaded_content = []
    for name in loaded:
        skill = get_skill_registry().get(name)
        if skill:
            loaded_content.append(f"--- {name} ---\n{skill.content}")
    if loaded_content:
        context.append(SystemMessage(content="\n\n".join(loaded_content)))

    if sd["scoped"] and sd["next_node"]:
        handoff = state.get("node_outputs", {}).get(sd["next_node"].get("deps", [None])[-1], {})
        scoped_ctx = build_scoped_context(tg.get("goal", ""), sd["next_node"], recent_msgs, handoff)
        context = [SystemMessage(content=join_prompt_parts(parts))] + scoped_ctx
        if em == "repair-loop":
            mem = state.get("retrieved_memory", {})
            if mem.get("similar_tasks"):
                lines = ["[历史参考 — 相似修复经验]"]
                for s in mem["similar_tasks"]:
                    lines.append(f"  · {s.get('goal','')[:60]} → {s.get('outcome','')}")
                context.append(SystemMessage(content="\n".join(lines)))
            if mem.get("reflections"):
                context.append(SystemMessage(content=f"[经验反思]\n{mem['reflections']}"))
    else:
        if tg and tg.get("nodes"):
            context.append(SystemMessage(content=f"当前任务 (DAG)：\n{format_task_graph(tg)}"))
            hint = format_hint(em, tg)
            if hint:
                context.append(SystemMessage(content=hint))
            blocked_nodes = [nid for nid, nd in tg.get("nodes", {}).items() if nd.get("status") == "blocked"]
            if blocked_nodes:
                context.append(SystemMessage(content=(
                    f"以下节点因上游失败被阻塞: {', '.join(blocked_nodes)}。"
                    f"可以选择: 1) 修复上游节点重试 2) 跳过阻塞节点直接继续")))
        elif plan:
            context.append(SystemMessage(content=f"当前计划：\n{plan}"))

    # Orphan cleanup
    tool_ids = set(); ai_tool_ids = set()
    for m in recent_msgs:
        if hasattr(m, "type") and m.type == "tool": tool_ids.add(m.tool_call_id)
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls: ai_tool_ids.add(tc.get("id"))
    for m in recent_msgs:
        if hasattr(m, "tool_calls") and m.tool_calls:
            valid = [tc for tc in m.tool_calls if tc.get("id") in tool_ids]
            if len(valid) != len(m.tool_calls): m.tool_calls = valid
    recent_msgs = [m for m in recent_msgs if not (
        hasattr(m, "type") and m.type == "tool" and m.tool_call_id not in ai_tool_ids)]

    # Observation compress
    for m in recent_msgs:
        if (hasattr(m, "type") and m.type == "tool" and hasattr(m, "content")
                and isinstance(m.content, str) and len(m.content) > 600):
            m.content = m.content[:600] + "\n[...输出过长已截断]"

    # Deep context rebuild
    if len(messages) > 120 and tg and tg.get("goal"):
        vlog = state.get("verification_log", [])
        rebuilt = context_refresh(tg["goal"], recent_msgs, summary, vlog)
        context = context[:3] + rebuilt
    else:
        context += recent_msgs

    # Reflection
    if state.get("current_step", 0) % REFLECT_INTERVAL == 0 and state.get("current_step", 0) > 0:
        try:
            refl = run_reflection(state)
            if refl and refl.get("hint"): context.append(SystemMessage(content=refl["hint"]))
        except Exception: pass

    # Plan A: 检查实际工具调用是否跨 toolset → 升级 task_type
    _upgrade = _check_toolset_upgrade(state)
    _task_type_changed = False
    if _upgrade and tt and tt != "react":
        _log.step_start(f"task_type upgrade: {tt} → {_upgrade}")
        tt = _upgrade
        _task_type_changed = True

    # LLM dispatch
    if tt == TaskType.DETERMINISTIC:
        response = invoke_with_retry(ctx.llm, context, label="agent(deterministic)")
    elif tt == TaskType.SEARCH:
        response = invoke_with_retry(ctx.llm_search, context, label="agent(search)")
    elif tt == TaskType.ACTION:
        response = invoke_with_retry(ctx.llm_action, context, label="agent(action)")
    elif tt == TaskType.REASONING:
        response = invoke_with_retry(ctx.llm_reasoning, context, label="agent(reasoning)")
    elif tt == TaskType.PLANNING:
        response = invoke_with_retry(ctx.llm_planning, context, label="agent(planning)")
    else:
        response = invoke_with_retry(ctx.llm_with_tools, context, label="agent(default)")

    # Plan B: raw XML tool call → 升级到全量工具重试一次
    if response and getattr(response, "_raw_tool_call", False):
        _log.warn("raw XML detected → upgrading to llm_with_tools, retry")
        response = invoke_with_retry(ctx.llm_with_tools, context, label="agent(recovery)")
        # 标记 task_type 升级，下轮 should_continue 不再踩坑
        if response:
            setattr(response, "_task_type_upgrade", "react")

    if response is None:
        return {"messages": [AIMessage(content="[系统错误] 网络请求失败，请稍后重试。")],
                "current_step": state.get("current_step", 0) + 1}

    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            args = str(tc.get("args", {})) if isinstance(tc, dict) else str(getattr(tc, "args", {}))
            _log.tool_call(name, args)
            if name == "cron_add":
                tc_args = tc.get("args", {}) if isinstance(tc, dict) else {}
                if not tc_args.get("session_id") and tid:
                    tc_args["session_id"] = tid

    # ── 真实 token 使用量跟踪 ──
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        budget.update_real(response.usage_metadata)
    elif hasattr(response, 'response_metadata') and 'token_usage' in getattr(response, 'response_metadata', {}):
        budget.update_real(response.response_metadata['token_usage'])

    updates = {"messages": [response], "current_step": state.get("current_step", 0) + 1}

    # Plan A: 传播 task_type 升级
    if _task_type_changed:
        updates["task_type"] = tt

    # Plan B: 传播 task_type 升级
    if getattr(response, "_task_type_upgrade", ""):
        updates["task_type"] = response._task_type_upgrade

    # ── Token 预算压缩：真实值优先 ──
    if budget.should_compress_real():
        _log.step_start(f"compress (real token budget)")
        to_summarize = messages[:-keep_count]
        goal_text = tg.get("goal", "") if tg else ""
        prefix_text = ctx.workspace.load_file("GUIDANCE.md", profile=_profile)
        new_summary = compress_messages_structured(
            ctx.llm, summary, to_summarize, goal_text, summary_prefix=prefix_text)
        remove_msgs = [RemoveMessage(id=m.id) for m in to_summarize]
        updates["messages"] = remove_msgs + [response]
        updates["summary"] = new_summary
    elif budget.should_compress_rough(messages, tools_count=len(valid_tools)):
        to_summarize = messages[:-keep_count]
        goal_text = tg.get("goal", "") if tg else ""
        prefix_text = ctx.workspace.load_file("GUIDANCE.md", profile=_profile)
        new_summary = compress_messages_structured(
            ctx.llm, summary, to_summarize, goal_text, summary_prefix=prefix_text)
        remove_msgs = [RemoveMessage(id=m.id) for m in to_summarize]
        updates["messages"] = remove_msgs + [response]
        updates["summary"] = new_summary

    _log.debug(f"Agent done — compressed={len(updates.get('summary','')) > 0 if 'summary' in updates else False}")
    return updates


def _check_toolset_upgrade(state: dict) -> str:
    """检查实际工具调用是否超出当前 task_type 工具集，返回建议升级的 task_type"""
    from tools.toolsets import get_tool_names_for_task
    tt = state.get("task_type", "")
    if not tt or tt == "react":
        return ""
    expected = set(get_tool_names_for_task(tt))
    actual = set()
    for m in state.get("messages", []):
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                n = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                if n:
                    actual.add(n)
    if not actual:
        return ""
    missing = actual - expected
    if len(missing) >= max(1, len(actual) // 2):
        return "action"
    return ""
