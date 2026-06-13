"""delegate_task 工具 — 单元测试"""


def test_delegate_task_registered():
    """delegate_task 已注册到工具列表"""
    from tools.registry import TOOLS
    names = {t.name for t in TOOLS}
    assert "delegate_task" in names, f"delegate_task 未在 TOOLS 中: {names}"


def test_delegate_task_in_toolset():
    """delegate_task 属于 delegation toolset"""
    from tools.toolsets import resolve_toolset, get_all_tool_names
    delegation_tools = resolve_toolset("delegation")
    assert "delegate_task" in delegation_tools

    action_tools = resolve_toolset("action")
    assert "delegate_task" in action_tools, "action toolset 应包含 delegation"

    all_tools = get_all_tool_names()
    assert "delegate_task" in all_tools


def test_delegate_task_tool_callable():
    """delegate_task 工具函数可调用"""
    from tools.delegate_tool import delegate_task
    assert hasattr(delegate_task, "invoke")
    result = delegate_task.invoke({"goal": "test"})
    assert result is not None


def test_delegate_task_requires_goal():
    """delegate_task 没有 goal 时返回错误"""
    from tools.delegate_tool import delegate_task
    import json
    result = delegate_task.invoke({"goal": ""})
    data = json.loads(result)
    assert "error" in data


def test_sub_agent_blocked_tools():
    """子Agent 被禁止的工具列表正确"""
    from agent.sub_agent import SUBAGENT_BLOCKED_TOOLS
    assert "delegate_task" in SUBAGENT_BLOCKED_TOOLS, "子Agent 不能递归委派"
    assert "cron_add" in SUBAGENT_BLOCKED_TOOLS
    assert "cron_remove" in SUBAGENT_BLOCKED_TOOLS


def test_sub_agent_generic_goal():
    """spawn_sub_agent 支持通用 goal（无 DAG），直接返回结果"""
    from agent.sub_agent import spawn_sub_agent, SUBAGENT_BLOCKED_TOOLS

    task_def = {"goal": "echo hello", "execution_mode": "react", "max_steps": 2}
    from agent.conversation_graph import get_sub_app
    app = get_sub_app()
    result = spawn_sub_agent(app, task_def)
    assert isinstance(result, dict)
    assert "thread_id" in result
    assert result["status"] in ("completed", "failed", "partial")


def test_spawn_depth_limit():
    """MAX_SPAWN_DEPTH 到达限制时拒绝创建"""
    from agent.sub_agent import spawn_sub_agent, MAX_SPAWN_DEPTH
    task_def = {"goal": "test", "execution_mode": "react", "max_steps": 1}
    from agent.conversation_graph import get_sub_app
    app = get_sub_app()
    result = spawn_sub_agent(app, task_def, child_depth=MAX_SPAWN_DEPTH)
    assert result["status"] == "failed"
    assert "depth" in result.get("error", "").lower()


def test_parallel_spawn():
    """spawn_sub_agents_parallel 创建多个子Agent"""
    from agent.sub_agent import spawn_sub_agents_parallel
    from agent.conversation_graph import get_sub_app
    tasks = [
        {"goal": "echo A", "execution_mode": "react", "max_steps": 1},
        {"goal": "echo B", "execution_mode": "react", "max_steps": 1},
    ]
    app = get_sub_app()
    results = spawn_sub_agents_parallel(app, tasks)
    assert len(results) == 2
    for r in results:
        assert isinstance(r, dict)
        assert "status" in r
