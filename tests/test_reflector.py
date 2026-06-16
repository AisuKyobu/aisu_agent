"""reflector 模块测试"""
from langchain_core.messages import AIMessage, HumanMessage

from agent.core.reflector import should_reflect, _extract_goal, _recent_progress_summary, REFLECT_INTERVAL


def test_should_reflect_every_n_steps():
    assert should_reflect(0) is False
    assert should_reflect(8) is True
    assert should_reflect(16) is True
    assert should_reflect(7) is False
    assert should_reflect(8, force=True) is True


def test_extract_goal_from_task_graph():
    state = {"task_graph": {"goal": "部署 Flask 应用"}, "messages": []}
    assert _extract_goal(state) == "部署 Flask 应用"


def test_extract_goal_fallback_to_last_human():
    state = {
        "task_graph": {},
        "messages": [
            HumanMessage(content="你好"),
            AIMessage(content="你好！"),
            HumanMessage(content="帮我写一个爬虫"),
        ],
    }
    assert _extract_goal(state) == "帮我写一个爬虫"


def test_extract_goal_empty():
    state = {"task_graph": {}, "messages": []}
    assert _extract_goal(state) == ""


def test_recent_progress_summary():
    state = {
        "messages": [
            HumanMessage(content="搜索 LangGraph"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "web_search", "args": {"q": "LangGraph"}}]),
            HumanMessage(content="继续"),
        ],
    }
    summary = _recent_progress_summary(state)
    assert "[用户] 搜索 LangGraph" in summary
    assert "web_search" in summary
    assert "[用户] 继续" in summary


def test_reflect_interval_constant():
    assert REFLECT_INTERVAL == 8
