"""Reflector — 每 N 步自省，写入 reflective memory"""
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_deepseek import ChatDeepSeek

from agent.logger import NodeLogger
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME

_reflector_llm = ChatDeepSeek(model=MODEL_NAME, temperature=0, api_key=DEEPSEEK_API_KEY, api_base=DEEPSEEK_BASE_URL)
REFLECT_INTERVAL = 8

_log = NodeLogger("reflector")


def should_reflect(step: int, force: bool = False) -> bool:
    return force or (step > 0 and step % REFLECT_INTERVAL == 0)


def _extract_goal(state: dict) -> str:
    """提取当前任务目标：优先 task_graph.goal，否则取最近一条用户消息。"""
    tg = state.get("task_graph", {})
    goal = tg.get("goal", "")
    if goal:
        return str(goal)[:200]
    for m in reversed(state.get("messages", [])):
        if hasattr(m, "type") and m.type == "human":
            content = getattr(m, "content", "")
            if content:
                return str(content)[:200]
    return ""


def _recent_progress_summary(state: dict) -> str:
    """把最近几条消息压缩成反思用的上下文摘要。"""
    msgs = state.get("messages", [])
    lines = []
    for m in msgs[-8:]:
        t = getattr(m, "type", "")
        if t == "human":
            lines.append(f"[用户] {str(getattr(m, 'content', ''))[:80]}")
        elif t == "ai":
            content = str(getattr(m, "content", ""))[:80]
            tool_calls = getattr(m, "tool_calls", None)
            if tool_calls:
                names = [tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "?") for tc in tool_calls]
                lines.append(f"[AI] 计划调用: {', '.join(names)}")
            elif content:
                lines.append(f"[AI] {content}")
        elif t == "tool":
            name = getattr(m, "name", "?")
            content = str(getattr(m, "content", ""))[:80]
            lines.append(f"[工具-{name}] {content}")
    return "\n".join(lines) or "（无最近执行记录）"


def reflect(state: dict) -> Optional[dict]:
    """自省：让 LLM 检查当前进度是否偏离目标。

    Returns:
        None 表示无需自省
        {"hint": str, "deviation": bool} 提供自省结果
    """
    step = state.get("current_step", 0)
    if not should_reflect(step):
        return None

    goal = _extract_goal(state)
    if not goal:
        _log.debug(f"step {step}: no goal, skip reflection")
        return None

    vlog = state.get("verification_log", [])
    recent_v = vlog[-8:] if len(vlog) > 8 else vlog
    pass_count = sum(1 for v in recent_v if v.get("passed"))
    total = len(recent_v) or 1
    pass_rate = pass_count / total
    fixes = state.get("pending_fixes", [])
    progress = _recent_progress_summary(state)

    prompt = f"""你是一个 Agent 执行进度检查器。请判断当前执行是否仍然围绕用户目标推进，是否偏离、重复或陷入无效循环。

原始目标: {goal}

最近执行摘要:
{progress}

最近校验记录: {pass_count}/{total} 通过
待修复错误数: {len(fixes)}

请用一句话回答：
1. 是否仍在正确推进目标？
2. 如果偏离，简要说明应在下一步如何纠正。
不超过 60 字。"""

    try:
        _log.step_start(f"reflect at step {step} (pass_rate={pass_rate*100:.0f}%)")
        result = _reflector_llm.invoke([HumanMessage(content=prompt)])
        content = result.content if hasattr(result, "content") else ""
        content = content.strip().replace("\n", " ")
        deviation = any(k in content for k in ("偏离", "纠正", "方向不对", "无效", "重复", "没有推进"))
        _log.step_done(f"→ {content[:80]}", warn=deviation)
    except Exception as e:
        _log.warn(f"reflect skipped at step {step}: {e}")
        return None

    # 写入 reflective memory（在线自省，置信度较低）
    try:
        from agent.memory.manager import get_manager as get_memory_manager
        mgr = get_memory_manager()
        if deviation:
            mgr.save_reflection(content, confidence=0.15)
    except Exception:
        pass

    return {"hint": f"[自省] {content}", "deviation": deviation}
