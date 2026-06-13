from langchain.tools import tool

from agent.session import list_sessions, search_sessions
from tools.tool_registry import registry


@tool
def session_search(query: str) -> str:
    """搜索历史会话摘要。query是搜索关键词，返回匹配的会话记录。"""
    results = search_sessions(query)
    if not results:
        return "未找到匹配的历史会话"
    lines = ["历史会话："]
    for r in results:
        tid = r.get("thread_id", "")
        summary = r.get("summary", "")[:120]
        lines.append(f"  [{tid}] {summary}")
    return "\n".join(lines)


@tool
def session_list(limit: int = 5) -> str:
    """列出最近的历史会话。limit指定返回条数。"""
    sessions = list_sessions(limit)
    if not sessions:
        return "暂无历史会话"
    lines = ["最近会话："]
    for s in sessions:
        tid = s.get("thread_id", "")
        summary = s.get("summary", "")[:80]
        lines.append(f"  [{tid}] {summary}")
    return "\n".join(lines)


registry.register(name="session_search", toolset="session", handler=session_search.func,
                  description="搜索历史会话摘要")
registry.register(name="session_list", toolset="session", handler=session_list.func,
                  description="列出最近的会话记录")
