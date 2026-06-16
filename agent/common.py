"""Shared utilities for agent graphs."""
import re

from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage


_RAW_TOOL_MARKERS = [
    r"<｜｜DSML｜｜tool_calls",
    r"<｜｜DSML｜｜invoke",
    r"<tool_calls",
    r"<invoke",
]
_RAW_TOOL_MARKER_RE = re.compile("|".join(_RAW_TOOL_MARKERS))


def sanitize_raw_tool_calls(content: str) -> str:
    """清理 LLM 在 content 里幻觉出的原始工具调用标记。"""
    if not isinstance(content, str) or not content:
        return content
    patterns = [
        (r"<｜｜DSML｜｜tool_calls>.*?</｜｜DSML｜｜tool_calls>", re.DOTALL),
        (r"<｜｜DSML｜｜invoke[^>]*>.*?</｜｜DSML｜｜invoke>", re.DOTALL),
        (r"<tool_calls>.*?</tool_calls>", re.DOTALL),
        (r"<invoke[^>]*>.*?</invoke>", re.DOTALL),
    ]
    for pat, flags in patterns:
        content = re.sub(pat, "", content, flags=flags)
    return content.strip()


def invoke_with_retry(llm_instance, msgs, max_retries=3, label="LLM"):
    import time
    from config import RETRY_DELAY
    from agent.logger import NodeLogger
    from tools.error_sanitizer import sanitize_tool_error
    _log = NodeLogger("common")
    total_chars = sum(len(str(getattr(m, "content", ""))) for m in msgs if hasattr(m, "content"))
    _log.llm_start(label, total_chars)
    t0 = time.time()
    last_result = None
    for attempt in range(max_retries):
        try:
            result = llm_instance.invoke(msgs)
            tools = []
            if hasattr(result, "tool_calls") and result.tool_calls:
                tools = [tc.get("name","") if isinstance(tc, dict) else getattr(tc,"name","") for tc in result.tool_calls]
            content = str(getattr(result, "content", "")) if result else ""

            # 检测 raw XML/DSML tool call 泄漏
            _has_raw = bool(_RAW_TOOL_MARKER_RE.search(content)) and not tools
            if _has_raw and attempt < max_retries - 1:
                _log.warn(f"LLM raw XML/DSML tool call detected, retry {attempt + 1}")
                # 标记以便调用方升级 task_type
                if result and hasattr(result, "content"):
                    setattr(result, "_raw_tool_call", True)
                last_result = result
                continue

            _log.llm_done(label, tools, chars=len(content), duration=time.time()-t0)
            return result
        except Exception as e:
            sanitized = sanitize_tool_error(str(e))
            _log.warn(f"LLM invoke failed (attempt {attempt + 1}/{max_retries}): {sanitized}")
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                return None
    return last_result


def count_tool_calls(msgs: list, tool_names: tuple, per_turn: bool = True) -> int:
    """统计工具调用次数。per_turn=True 时只统计最近一轮（最后一条 HumanMessage 之后）。"""
    if per_turn:
        start = 0
        for i in range(len(msgs) - 1, -1, -1):
            if hasattr(msgs[i], "type") and msgs[i].type == "human":
                start = i
                break
        msgs = msgs[start:]
    cnt = 0
    for m in msgs:
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                if name in tool_names:
                    cnt += 1
    return cnt


def context_refresh(goal: str, recent_msgs: list, summary: str, verification_log: list) -> list:
    """深层上下文重建：超过 120 条消息时，用 LLM 重构精简上下文。

    不依赖增量压缩，而是从零构建：
    - 原始目标（不压缩）
    - 最近 5 条对话
    - 校验日志摘要
    - 已有 summary
    """
    from langchain_deepseek import ChatDeepSeek
    from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME

    # 提取关键信息
    last5 = recent_msgs[-5:]
    steps_log = "\n".join(
        f"- [{v.get('level','?')}] {v.get('tool','?')}: {'pass' if v.get('passed') else 'FAIL'}"
        for v in verification_log[-10:])
    recent_text = "\n".join(
        f"[{m.type}]\n{str(m.content)[:200]}" for m in last5)

    prompt = f"""你是一个上下文重建器。请将以下长对话压缩为一段 150 字内的连贯中文摘要。

原始目标（不可丢失）: {goal}

最近 5 条对话:
{recent_text}

校验日志:
{steps_log if steps_log else '无'}

已有摘要: {summary}

输出一段摘要："""
    try:
        llm = ChatDeepSeek(model=MODEL_NAME, temperature=0, api_key=DEEPSEEK_API_KEY, api_base=DEEPSEEK_BASE_URL)
        result = invoke_with_retry(llm, [HumanMessage(content=prompt)], label="context_refresh")
        new_summary = result.content if result and hasattr(result, "content") else summary
        # 构建精简上下文
        return [
            SystemMessage(content=f"[首要目标] {goal}"),
            SystemMessage(content=f"[上下文重建摘要] {new_summary}"),
            *last5,
        ]
    except Exception:
        # 降级：直接返回最近消息
        return [SystemMessage(content=f"[首要目标] {goal}")] + list(last5)
