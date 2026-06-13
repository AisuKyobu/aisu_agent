"""Reflector — 每 N 步自省，写入 reflective memory"""
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_deepseek import ChatDeepSeek

from agent.logger import NodeLogger
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME

_reflector_llm = ChatDeepSeek(model=MODEL_NAME, temperature=0, api_key=DEEPSEEK_API_KEY, api_base=DEEPSEEK_BASE_URL)
REFLECT_INTERVAL = 8

def should_reflect(step: int, force: bool = False) -> bool:
    return force or (step > 0 and step % REFLECT_INTERVAL == 0)


def reflect(state: dict) -> Optional[dict]:
    """自省：让 LLM 检查当前进度是否偏离目标。

    Returns:
        None 表示无需自省
        {"hint": str, "deviation": bool} 提供自省结果
    """
    if not should_reflect(state.get("current_step", 0)):
        return None

    tg = state.get("task_graph", {})
    goal = tg.get("goal", "")
    if not goal:
        return None

    vlog = state.get("verification_log", [])
    recent_v = vlog[-8:] if len(vlog) > 8 else vlog
    pass_count = sum(1 for v in recent_v if v.get("passed"))
    total = len(recent_v) or 1
    pass_rate = pass_count / total

    fixes = state.get("pending_fixes", [])
    tools_used = [v.get("tool", "?") for v in recent_v]

    prompt = f"""你是一个任务进度检查器。分析 Agent 最近 8 步的执行情况，判断是否偏离目标。

原始目标: {goal}
最近校验: {pass_count}/{total} 通过
使用工具: {', '.join(tools_used)} 
错误数: {len(fixes)}

请用一句话回答: 是否偏离目标？如有偏离，描述应在哪一步纠正。不超过 50 字。"""

    try:
        _log = NodeLogger("reflector")
        _log.step_start(f"checking progress (pass_rate={pass_rate*100:.0f}%)")
        result = _reflector_llm.invoke([HumanMessage(content=prompt)])
        content = result.content if hasattr(result, "content") else ""
        _log.step_done(f"→ {content[:80]}", warn=("偏离" in content or "纠正" in content))
    except Exception:
        _log.warn("reflect skipped: LLM failed")
        return None

    deviation = "偏离" in content or "纠正" in content or "方向不对" in content

    # 写入 reflective memory（在线自省，置信度较低）
    try:
        from agent.memory.manager import get_manager as get_memory_manager
        mgr = get_memory_manager()
        if deviation and pass_rate < 0.6:
            mgr.save_reflection(content, confidence=0.15)
    except Exception:
        pass

    return {"hint": f"[自省] {content}", "deviation": deviation}
