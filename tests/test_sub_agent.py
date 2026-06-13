"""Sub-Agent — spawn + 隔离性"""
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver


def test_spawn_sub_agent():
    from agent.conversation_graph import build_conversation_graph
    from agent.sub_agent import spawn_sub_agent

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    conv = build_conversation_graph(checkpointer=saver)

    skill_def = {
        "name": "test-skill",
        "nodes": [{"id": "s1", "cmd": "echo sub test", "desc": "test"}],
    }
    r1 = spawn_sub_agent(conv, skill_def)
    r2 = spawn_sub_agent(conv, skill_def)
    conn.close()
    assert isinstance(r1, dict)
    assert "thread_id" in r1
    assert r1["status"] in ("completed", "partial", "failed")
    assert r1["thread_id"] != r2["thread_id"]  # 隔离性
