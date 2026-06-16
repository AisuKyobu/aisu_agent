"""Summarizer node — 统一终止出口: 工具/步数超限 / needs_human 均在此外送 LLM 总结回复"""
from langchain_core.messages import AIMessage, SystemMessage

from agent.common import invoke_with_retry, sanitize_raw_tool_calls
from agent.logger import NodeLogger
from agent.state import AgentState


def _safe_context(msgs: list, window: int = 8) -> list:
    """取最后 N 条消息，清理未配对的 tool_calls 避免 API 400 错误。

    问题: msgs[-N:] 可能裁断了 tool_calls → tool 的配对——
    前 N 条内 AI 消息带了 tool_calls, 但对应的 ToolMessage 在 N 条之外。
    DeepSeek 等 LLM 要求每个 tool_calls 后必须紧跟对应的 tool 响应。
    """
    tail = msgs[-window:]
    clean: list = []
    tc_ids: set = set()
    # 第一遍: 收集窗口内所有 ToolMessage 的 tool_call_id
    for m in tail:
        if hasattr(m, "tool_call_id") and m.tool_call_id:
            tc_ids.add(m.tool_call_id)
    # 第二遍: 清理
    for m in tail:
        is_ai = hasattr(m, "tool_calls") and m.tool_calls
        is_tool = hasattr(m, "tool_call_id") and m.tool_call_id
        if is_ai:
            valid = [tc for tc in m.tool_calls
                     if (tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)) in tc_ids]
            if valid:
                # 有配对的 tool 响应 → 保留 tool_calls
                clean.append(m)
            else:
                # 无配对 → 去掉 tool_calls 再追加
                cp = m.model_copy() if hasattr(m, "model_copy") else m
                if hasattr(cp, "tool_calls"):
                    cp.tool_calls = []
                clean.append(cp)
        elif is_tool:
            # 只保留有对应 AI 调用的 tool 消息
            ai_ids = set()
            for am in tail:
                if hasattr(am, "tool_calls") and am.tool_calls:
                    for tc in am.tool_calls:
                        tid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", "")
                        if tid:
                            ai_ids.add(tid)
            if m.tool_call_id in ai_ids:
                clean.append(m)
            # 否则跳过孤立的 tool 消息
        else:
            clean.append(m)
    return clean


def _build_reason(state: AgentState) -> str:
    """根据 state 中的终止原因动态生成总结指令。"""
    msgs = state["messages"]
    tt = state.get("task_type", "")
    step = state.get("current_step", 0)
    max_s = state.get("max_steps", 0)

    if state.get("needs_human"):
        fixes = state.get("pending_fixes", [])
        # HITL 触发（待用户授权） ≠ 执行失败
        if not fixes:
            return "命令不在白名单中，需要用户授权才能执行。请将安全提示展示给用户，等待用户在下一条消息中明确回复“允许”或“同意”。不要调用任何工具。不要自己假设用户已经同意。"
        last_fail = fixes[-1]["reason"] if fixes else "未知错误"
        return (f"连续操作失败（最近错误: {last_fail[:80]}）。"
                "请根据已获取的信息总结当前进展，并向用户说明遇到了什么问题、可以尝试什么替代方案。不要调用任何工具。")

    if tt == "search":
        return "搜索次数已达上限。请根据搜索中已获取的一切信息，做一次完整的总结回复给用户。不要调用任何工具。"

    if tt == "reasoning":
        return "工具调用次数已达上限。请根据分析过程中已获取的所有信息，给出一个尽可能完整的结论。不要调用任何工具。"

    if step >= max_s > 0:
        return f"执行步数已达上限（{step}/{max_s}）。请根据已完成的进度总结当前进展，告知用户哪些已完成、哪些未完成。不要调用任何工具。"

    total_tc = sum(1 for m in msgs if hasattr(m, "tool_calls") and m.tool_calls)
    if total_tc >= 20:
        return "工具调用总数已达全局上限。请根据对话中已获取的一切信息，做一次完整的总结回复给用户。不要调用任何工具。"

    return "搜索或工具调用次数已达上限。请根据对话中已获取的一切信息，做一次完整的总结回复给用户。不要调用任何工具。"


def summarizer_node(state: AgentState, ctx=None) -> dict:
    _log = NodeLogger("summarizer")
    _log.bind(state.get("thread_id", ""), state.get("current_step", 0))
    msgs = state["messages"]
    reason = _build_reason(state)
    _log.step_start(f"summarizing ({len(msgs)} msgs) — reason: {reason[:60]}")
    context = [
        SystemMessage(content=reason),
        *_safe_context(msgs, window=8),
    ]
    llm = getattr(ctx, "llm_plain", None) or ctx.llm
    response = invoke_with_retry(llm, context, label="summarizer")
    if response is None:
        _log.warn("null response")
        return {"messages": [AIMessage(content="任务已达到执行上限，请稍后重试或调整需求。")]}
    # 剥离 LLM 可能幻觉出的 tool_calls（总结阶段不应再调用任何工具）
    if hasattr(response, "tool_calls") and response.tool_calls:
        response.tool_calls = []
        _log.debug("stripped hallucinated tool_calls from summarizer response")
    # 清理 content 里的原始工具调用标记
    content = str(getattr(response, "content", "") or "")
    clean_content = sanitize_raw_tool_calls(content)
    if clean_content != content:
        response.content = clean_content
        _log.debug("sanitized raw tool call markup from summarizer content")
    if not clean_content:
        response.content = "任务已达到执行上限，已根据已有信息完成总结。"
    _log.step_done(f"done ({len(str(getattr(response,'content','')))} chars)")
    return {"messages": [response]}
