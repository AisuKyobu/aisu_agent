"""并行工具调度门控 — 判断一批 tool_calls 能否安全并发。"""

_NEVER_PARALLEL_TOOLS = frozenset({"clarify"})

_PARALLEL_SAFE_TOOLS = frozenset({
    "read_file", "search_files", "web_search", "web_fetch",
    "session_search", "session_list", "memory_search",
    "list_skills", "skill_view", "browser_screenshot", "browser_inspect",
    "delegate_task",
})

_PATH_SCOPED_TOOLS = frozenset({"read_file", "write_file"})
_DESTRUCTIVE_TOOLS = frozenset({"run_command", "browser_click", "browser_type"})


def should_parallelize_tool_batch(tool_calls: list) -> bool:
    if len(tool_calls) <= 1:
        return False

    tool_names = []
    for tc in tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
        tool_names.append(name)

    if any(n in _NEVER_PARALLEL_TOOLS for n in tool_names):
        return False

    if all(n in _PARALLEL_SAFE_TOOLS for n in tool_names):
        return True

    # 混合安全工具 + delegate_task → 可以并行（delegate 不操作共享状态）
    if set(tool_names) <= (_PARALLEL_SAFE_TOOLS | {"delegate_task"}):
        return True

    return False
