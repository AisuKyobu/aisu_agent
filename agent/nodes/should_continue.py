"""should_continue — 条件边函数: 判定 Agent 下一步走向"""
from langgraph.graph import END

from agent.common import count_tool_calls
from agent.logger import NodeLogger
from agent.state import AgentState


def _get_setting(key: str, default, profile: str = "dev"):
    try:
        from agent.settings import get
        return get(key, profile=profile, default=default)
    except Exception:
        return default


def should_continue(state: AgentState, ctx=None) -> str:
    _log = NodeLogger("should_continue")
    _log.bind(state.get("thread_id", ""), state.get("current_step", 0))
    last = state["messages"][-1]
    has_tc = hasattr(last, "tool_calls") and bool(last.tool_calls)

    _profile = state.get("profile", "dev")
    max_search = _get_setting("MAX_SEARCH_COUNT", 7, profile=_profile)
    max_steps_val = _get_setting("MAX_STEPS", 20, profile=_profile)
    reasoning_max_steps = _get_setting("REASONING_MAX_STEPS", 20, profile=_profile)
    reasoning_max_tools = _get_setting("REASONING_MAX_TOOL_CALLS", 15, profile=_profile)
    reasoning_max_reads = _get_setting("REASONING_MAX_FILE_READS", 20, profile=_profile)
    reasoning_max_search = _get_setting("REASONING_MAX_SEARCH", 3, profile=_profile)

    if not has_tc:
        _log.debug("END: no tool_calls")
        return END

    if state.get("needs_human", False):
        _log.event("summarize: needs_human")
        return "summarize"

    tt = state.get("task_type", "")
    _effective_max = (reasoning_max_steps if tt == "reasoning"
                   else 15 if tt == "planning"
                   else state.get("max_steps", max_steps_val))

    def _pending():
        return hasattr(state["messages"][-1], "tool_calls") and bool(state["messages"][-1].tool_calls)

    if tt == "search":
        sc = count_tool_calls(state["messages"], ("web_search", "web_fetch"))
        if sc > max_search:
            if _pending() and sc <= max_search + 2:
                _log.step_done(f"continue (search {sc}/{max_search}, last_allow)")
                return "tools"
            _log.event(f"summarize (search {sc}>{max_search})")
            return "summarize"

    if tt == "reasoning":
        sc = count_tool_calls(state["messages"], ("web_search", "web_fetch"))
        if sc > reasoning_max_search:
            if _pending() and sc <= reasoning_max_search + 2:
                return "tools"
            _log.event(f"summarize (reasoning search {sc}>{reasoning_max_search})")
            return "summarize"
        fc = count_tool_calls(state["messages"], ("read_file",))
        if fc > reasoning_max_reads:
            if _pending() and fc <= reasoning_max_reads + 2:
                return "tools"
            _log.event(f"summarize (file_reads {fc}>{reasoning_max_reads})")
            return "summarize"
        total_tools = count_tool_calls(state["messages"], (
            "read_file", "write_file", "run_command", "web_search", "web_fetch",
            "plan_task", "step_complete", "browser_open", "browser_click",
            "browser_type", "browser_screenshot", "cron_add"))
        if total_tools > reasoning_max_tools:
            if _pending() and total_tools <= reasoning_max_tools + 2:
                return "tools"
            _log.event(f"summarize (total_tools {total_tools}>{reasoning_max_tools})")
            return "summarize"

    _last_human_idx = 0
    for i in range(len(state["messages"]) - 1, -1, -1):
        if hasattr(state["messages"][i], "type") and state["messages"][i].type == "human":
            _last_human_idx = i
            break
    _turn_msgs = state["messages"][_last_human_idx:]
    tool_msg_count = sum(1 for m in _turn_msgs if hasattr(m, "tool_calls") and m.tool_calls)
    if tool_msg_count >= max_steps_val:
        if _pending():
            _log.step_done(f"continue (step limit {tool_msg_count}≥{max_steps_val}, last_allow)")
            return "tools"
        _log.event(f"summarize (step limit {tool_msg_count}≥{max_steps_val})")
        return "summarize"

    if state.get("current_step", 0) >= _effective_max:
        if _pending():
            _log.step_done(f"continue (max_steps {_effective_max}, last_allow)")
            return "tools"
        _log.event(f"summarize (max_steps {_effective_max})")
        return "summarize"

    _log.debug("continue → tools")
    return "tools"
