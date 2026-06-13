"""Memory Retriever node — 按 execution_mode 策略检索记忆，通过 MemoryManager 统一入口"""

from agent.logger import NodeLogger
from agent.state import AgentState


def memory_retriever_node(state: AgentState, ctx=None) -> dict:
    _log = NodeLogger("memory_retriever")
    _log.bind(state.get("thread_id", ""), state.get("current_step", 0))
    if state.get("current_step", 0) > 0:
        return {}
    em = state.get("execution_mode", "react")
    profile = state.get("profile", "dev")
    try:
        from agent.memory.manager import get_manager as get_memory_manager
        mgr = get_memory_manager()
        mgr.ensure_builtin(profile=profile)
        refl = mgr.get_reflections()

        if em in ("direct", "monitor"):
            return {"retrieved_memory": {"similar_tasks": [], "reflections": refl}}

        tg = state.get("task_graph", {})
        intent = state.get("execution_intent", {})
        goal = tg.get("goal", "") or intent.get("goal", "")
        if not goal:
            last_msg = state["messages"][-1] if state.get("messages") else None
            goal = last_msg.content if last_msg and hasattr(last_msg, "content") else ""
        if not goal:
            goal = ""
        k = {"react": 2, "dag": 3, "repair-loop": 3, "research-loop": 5}.get(em, 2)
        similar = mgr.search_similar(goal, k=k) if goal else []
        if similar or refl:
            _log.step_done(f"memory: {len(similar)} similar tasks, refl={'yes' if refl else 'no'}")
        else:
            _log.debug("memory: no results")
        return {"retrieved_memory": {"similar_tasks": similar, "reflections": refl}}
    except Exception:
        _log.debug("memory: retrieval skipped")
        return {"retrieved_memory": {"similar_tasks": [], "reflections": ""}}
