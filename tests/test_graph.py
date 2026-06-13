"""Graph — 编译 + 工具注册，全网最值钱的测试"""
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from tools.registry import TOOLS, get_filtered_tools


def test_graph_compiles():
    from agent.conversation_graph import build_conversation_graph
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    app = build_conversation_graph(checkpointer=saver)
    assert app is not None
    conn.close()


def test_tools_registered_and_filtered():
    names = [t.name for t in TOOLS]
    required = [
        "read_file", "write_file", "run_command",
        "web_search", "web_fetch",
        "browser_open", "browser_click", "browser_type", "browser_screenshot", "browser_inspect",
        "remember", "memory_search", "plan_task", "step_complete",
        "cron_add", "cron_list", "cron_remove",
        "session_search", "session_list",
        "list_skills", "load_skill",
    ]
    for name in required:
        assert name in names, f"缺少工具: {name}"
    filtered = get_filtered_tools()
    assert 0 < len(filtered) <= len(TOOLS)
