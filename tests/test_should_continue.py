"""should_continue — 核心路由判定"""
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END
from agent.nodes.should_continue import should_continue


def test_end_when_no_tool_calls():
    state = {"messages": [AIMessage(content="hello")], "current_step": 0, "task_type": ""}
    assert should_continue(state) == END


def test_needs_human_goes_to_summarize():
    msgs = [HumanMessage(content="test"),
            AIMessage(content="ok", tool_calls=[{"name": "run_command", "args": {}, "id": "id_1"}])]
    state = {"messages": msgs, "task_type": "action", "needs_human": True, "current_step": 0}
    assert should_continue(state) == "summarize"


def test_summarize_when_search_exceeded():
    msgs = [HumanMessage(content="search test")]
    for i in range(10):
        msgs.append(AIMessage(content="ok", tool_calls=[
            {"name": "web_search", "args": {"query": f"test_{i}"}, "id": f"id_{i}"}
        ]))
    state = {"messages": msgs, "task_type": "search", "current_step": 15}
    assert should_continue(state) == "summarize"


def test_step_limit_last_allow():
    msgs = [HumanMessage(content="test")]
    for i in range(22):
        msgs.append(AIMessage(content="ok", tool_calls=[
            {"name": f"tool_{i}", "args": {}, "id": f"id_{i}"}
        ]))
    state = {"messages": msgs, "task_type": "action", "current_step": 22, "max_steps": 20}
    result = should_continue(state)
    assert result in ("tools", "summarize")
