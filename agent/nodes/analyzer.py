"""Analyzer node — 从 AgentState 提取消息，调用 classify 分类，写回 state"""
from agent.core.intent import classify
from agent.logger import NodeLogger
from agent.state import AgentState


def analyzer_node(state: AgentState, ctx=None) -> dict:
    _log = NodeLogger("analyzer")
    tid = state.get("thread_id", "")
    _log.bind(tid, 0)
    last = state["messages"][-1]
    is_human = hasattr(last, "type") and last.type == "human"
    if not is_human:
        return {}

    text = last.content if hasattr(last, "content") else str(last)
    _log.step_start(f"classify: {text[:50]}")

    intent = classify(text)
    _log.step_done(f"→ {intent.get('execution_mode','?')}/{intent.get('task_type','?')} "
                   f"(verifier:{intent.get('verifier_level','?')} risk:{intent.get('risk_level','?')})")

    return {
        "execution_intent": intent,
        "task_type": intent.get("task_type", "reasoning"),
        "missing_params": intent.get("missing_params", []),
        "current_step": 0,
    }
