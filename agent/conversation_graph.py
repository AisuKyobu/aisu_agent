"""Conversation Graph — 构建 10 节点 StateGraph，所有节点逻辑已拆分到 agent/nodes/"""

from langchain_deepseek import ChatDeepSeek
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agent.graph_context import GraphContext
from agent.nodes.agent import agent_node
from agent.nodes.analyzer import analyzer_node
from agent.nodes.memory_retriever import memory_retriever_node
from agent.nodes.router import router_node
from agent.nodes.should_continue import should_continue
from agent.nodes.skill_loader import skill_loader_node
from agent.nodes.summarizer import summarizer_node
from agent.nodes.verifier import verifier_node
from agent.state import AgentState
from agent.sub_agent import spawn_sub_agent
from agent.workspace import Workspace
from config import (DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME, TEMPERATURE, WORKSPACE_DIR)
from tools.tool_dispatch import should_parallelize_tool_batch
from tools.registry import get_filtered_tools
from tools.tool_registry import registry as tool_registry
from tools.toolsets import get_tool_names_for_task, get_all_tool_names


class ParallelToolNode(ToolNode):
    """支持并行工具调度的 ToolNode 子类。

    门控规则: _NEVER_PARALLEL_TOOLS 中的工具强制串行；
    _PARALLEL_SAFE_TOOLS + delegate_task 可并行。
    """

    def _run_one(self, state, config=None):
        messages = state.get("messages", [])
        last = messages[-1] if messages else None
        if last is None or not hasattr(last, "tool_calls") or not last.tool_calls:
            return {}
        tool_calls = last.tool_calls
        if should_parallelize_tool_batch(tool_calls):
            return self._dispatch_concurrent(tool_calls, config)
        return super()._run_one(state, config)

    def _dispatch_concurrent(self, tool_calls, config):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from config import TOOL_TIMEOUT
        import json as _json
        results_by_id = {}
        num = len(tool_calls)
        with ThreadPoolExecutor(max_workers=min(num, 4)) as pool:
            futures = {}
            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                tid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", "")
                futures[pool.submit(
                    tool_registry.dispatch, name, args
                )] = (name, tid)
            for future in as_completed(futures):
                name, tid = futures[future]
                try:
                    results_by_id[tid] = future.result(timeout=TOOL_TIMEOUT)
                except Exception as e:
                    results_by_id[tid] = _json.dumps({"error": str(e)}, ensure_ascii=False)
        messages = []
        for tc in tool_calls:
            tid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", "")
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
            from langchain_core.messages import ToolMessage
            messages.append(ToolMessage(
                content=results_by_id.get(tid, ""), name=name, tool_call_id=tid
            ))
        return {"messages": messages}

_workspace = Workspace(WORKSPACE_DIR)

llm = ChatDeepSeek(model=MODEL_NAME, temperature=TEMPERATURE, api_key=DEEPSEEK_API_KEY, api_base=DEEPSEEK_BASE_URL)

_FILTERED_TOOLS = get_filtered_tools()
_all_tools = get_all_tool_names()
_search_tools = get_tool_names_for_task("search")
_action_tools = get_tool_names_for_task("action")
_reasoning_tools = get_tool_names_for_task("reasoning")
_planning_tools = get_tool_names_for_task("planning")

_TOOLS_SEARCH = [t for t in _FILTERED_TOOLS if t.name in _search_tools]
_TOOLS_ACTION = [t for t in _FILTERED_TOOLS if t.name in _action_tools]
_TOOLS_REASONING = [t for t in _FILTERED_TOOLS if t.name in _reasoning_tools]
_TOOLS_PLANNING = [t for t in _FILTERED_TOOLS if t.name in _planning_tools]

_TOOLS_BY_MODE = {
    "search": _TOOLS_SEARCH,
    "action": _TOOLS_ACTION,
    "reasoning": _TOOLS_REASONING,
    "planning": _TOOLS_PLANNING,
}

llm_with_tools = llm.bind_tools(_FILTERED_TOOLS)
llm_search = llm.bind_tools(_TOOLS_SEARCH)
llm_action = llm.bind_tools(_TOOLS_ACTION)
llm_reasoning = llm.bind_tools(_TOOLS_REASONING)
llm_planning = llm.bind_tools(_TOOLS_PLANNING)

_READONLY_TOOLS = [t for t in _FILTERED_TOOLS if t.name in ("memory_search", "session_search", "session_list")]
llm_deterministic = llm.bind_tools(_READONLY_TOOLS)

SYSTEM_PROMPT_DEFAULT = """
你是一个友好的对话助手，负责完成用户的任务。

可用工具：read_file / write_file / run_command / web_search / web_fetch / browser_open / browser_click / browser_type / browser_screenshot / browser_inspect / cron_add / plan_task / step_complete / remember / memory_search / list_skills / load_skill

规则：
- 文件/系统操作必须调用工具（写代码用 write_file，不要在对话里贴代码）
- 如果命令被拒绝（不在白名单），直接告知用户并询问是否允许，不要自行假设
- 用户明确允许后，立即用 allow=True 重新执行刚才被拒绝的那条命令，不要仅用文字复述
- 根据当前系统类型选正确命令：Windows用where/dir/find/python；Linux用which/ls/grep/python3
- 检查 Python 用 python --version 或 python -c "import sys;print(sys.version)"，安装包用 python -m pip install
- 如果用户明确要求重试某个操作（如"再试一次"、"换个方式搜"），必须调用工具重新执行，不要仅用文字回复
- 用户要求记住信息时（如"记住XX"），必须调用 remember 工具存储，不要仅用文字回复
- 信息足够就直接总结，不要继续搜索或验证
- 当操作次数接近上限时，直接总结已有信息告知用户，不要继续尝试
- 完成任务后给出简洁总结
"""

def _load_system_prompt() -> str:
    content = _workspace.load_file("SYSTEM_PROMPT.md", profile="dev")
    return content if content else SYSTEM_PROMPT_DEFAULT

_ctx = GraphContext(
    llm=llm_deterministic, llm_search=llm_search, llm_action=llm_action,
    llm_reasoning=llm_reasoning, llm_planning=llm_planning,
    llm_with_tools=llm_with_tools, workspace=_workspace,
    system_prompt=_load_system_prompt(),
)

def build_conversation_graph(checkpointer=None, **_):
    graph = StateGraph(AgentState)

    graph.add_node("analyzer", lambda s: analyzer_node(s, _ctx))
    graph.add_node("router", lambda s: router_node(s, _ctx))
    graph.add_node("memory_retriever", lambda s: memory_retriever_node(s, _ctx))
    graph.add_node("agent", lambda s: agent_node(s, _ctx))
    graph.add_node("tools", ParallelToolNode(_FILTERED_TOOLS))
    graph.add_node("skill_loader", lambda s: skill_loader_node(s, _ctx))
    graph.add_node("verifier", lambda s: verifier_node(s, _ctx))
    graph.add_node("summarizer", lambda s: summarizer_node(s, _ctx))

    graph.add_edge(START, "analyzer")
    graph.add_edge("analyzer", "router")
    graph.add_edge("router", "memory_retriever")
    graph.add_edge("memory_retriever", "agent")

    graph.add_conditional_edges(
        "agent",
        lambda s: should_continue(s, _ctx),
        {"tools": "tools", "summarize": "summarizer", END: END},
    )

    graph.add_edge("tools", "skill_loader")
    graph.add_edge("skill_loader", "verifier")
    graph.add_edge("verifier", "agent")
    graph.add_edge("summarizer", END)

    return graph.compile(checkpointer=checkpointer)


_sub_app_cache = None


def get_sub_app():
    global _sub_app_cache
    if _sub_app_cache is None:
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver
        from config import CONVERSATION_DB
        conn = sqlite3.connect(CONVERSATION_DB, check_same_thread=False)
        saver = SqliteSaver(conn)
        _sub_app_cache = build_conversation_graph(checkpointer=saver)
    return _sub_app_cache


def _spawn_skill_sub(skill_name: str, sm: dict, params: dict) -> dict:
    return spawn_sub_agent(get_sub_app(), sm, params)
