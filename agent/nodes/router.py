"""Router node — Intent Resolver: 将 ExecutionIntent 展开为运行时配置"""
from agent.core.execution_intent import resolve_intent
from agent.logger import NodeLogger
from agent.state import AgentState
from agent.types import TASK_CONSTRAINTS, TaskType
from config import REASONING_MAX_STEPS, MAX_STEPS

# execution_mode → 不允许的 task_type（冲突时修正）
_MODE_TASK_FIX = {
    "dag":           {"deterministic": "action",   "search": "action"},
    "repair-loop":   {"deterministic": "action",   "search": "action"},
    "research-loop": {"deterministic": "search",   "action": "search"},
    "direct":        {},
}

def _normalize(em: str, tt: str) -> str:
    """修正冲突的 execution_mode × task_type 组合。"""
    fixes = _MODE_TASK_FIX.get(em, {})
    if tt in fixes:
        return fixes[tt]
    return tt


def router_node(state: AgentState, ctx=None) -> dict:
    _log = NodeLogger("router")
    _log.bind(state.get("thread_id", ""), 0)
    intent = state.get("execution_intent", {})
    tt = state.get("task_type", "reasoning")

    if not intent:
        missing = state.get("missing_params", [])
        max_val = (REASONING_MAX_STEPS if tt == "reasoning" else 15 if tt == "planning" else MAX_STEPS)
        _log.step_done(f"fallback → react(max_steps={max_val}, L1)")
        return {
            "task_constraints": TASK_CONSTRAINTS.get(tt, TASK_CONSTRAINTS[TaskType.REASONING]),
            "max_steps": max_val, "execution_mode": "react", "verifier_level": "L1",
            "autonomy_level": "full_auto", "retry_max_total": 3, "retry_per_step": 2,
            "task_type": tt, "missing_params": missing,
        }

    resolved = resolve_intent(intent)
    em = resolved.get("execution_mode", "react")
    original_tt = resolved.get("task_type", "reasoning")
    fixed_tt = _normalize(em, original_tt)
    if fixed_tt != original_tt:
        _log.warn(f"task_type 冲突修正: {original_tt} → {fixed_tt} (mode={em})")
        resolved["task_type"] = fixed_tt
    _log.step_done(f"→ {em}(v:{resolved['verifier_level']} "
                   f"steps:{resolved['max_steps']} auto:{resolved.get('autonomy_level','?')})")
    return resolved
