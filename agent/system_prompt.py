"""System prompt 3 层组装。

三层设计动机：保持 stable 层字节不变，最大化模型侧 prompt caching 命中率。
- stable:   绝对不变（Agent 身份 + 工具指南 + 环境提示）
- context:  Session 级稳定（AGENTS.md / USER.md / SYSTEM_PROMPT.md / GUIDANCE.md）
- volatile: Turn 级变化（记忆快照 + 时间戳）

STABLE 层的工具指南优先从 workspace/GUIDANCE.md 读取，fallback 到内置默认。
"""

import datetime
from typing import Dict, List, Optional

_GUIDANCE_DEFAULTS = {
    "memory": (
        "[记忆使用指南]\n"
        "使用 remember 工具存储持久事实（用户偏好、重要信息、决策）。\n"
        "使用 memory_search 在需要时检索已存储的信息。\n"
        "将记忆写为声明性事实而非指令——'用户使用 pytest' 而非 '用 pytest 运行测试'。"
    ),
    "search": (
        "[搜索指南]\n"
        "搜索到信息后立即总结回答，不要继续搜索或验证。\n"
        "信息足够就直接给出结论，避免过度迭代。\n"
        "如果 web_search 返回'未找到结果'、'搜索失败'、'CAPTCHA'或连续多次无有效结果，"
        "说明搜索后端暂时不可用，立即停止搜索，直接根据已有知识回答用户，不要继续换词重试。"
    ),
}


def build_system_prompt(
    system_prompt_base: str,
    valid_tool_names: List[str],
    workspace_blocks: List[str],
    retrieved_memory: Optional[dict] = None,
    summary: str = "",
    task_type: str = "",
    task_constraints: str = "",
    loaded_skills: Optional[List[str]] = None,
    thread_id: str = "",
    guidance_text: str = "",
) -> Dict[str, str]:
    now = datetime.datetime.now()
    time_str = now.strftime("%Y年%m月%d日 %A")

    stable_parts = [system_prompt_base]
    stable_parts.append(f"当前日期: {time_str}")

    if guidance_text:
        stable_parts.append(guidance_text)
    else:
        if "memory_search" in valid_tool_names or "remember" in valid_tool_names:
            stable_parts.append(_GUIDANCE_DEFAULTS["memory"])
        if "web_search" in valid_tool_names:
            stable_parts.append(_GUIDANCE_DEFAULTS["search"])

    stable = "\n\n".join(stable_parts)

    context_parts = []
    for block in workspace_blocks:
        context_parts.append(block)
    if thread_id:
        context_parts.append(f"当前会话ID: {thread_id}")
    if task_type:
        context_parts.append(f"任务类型: {task_type}")
    if task_constraints:
        context_parts.append(f"[任务约束]\n{task_constraints}")

    context = "\n\n".join(context_parts) if context_parts else ""

    volatile_parts = []
    if retrieved_memory:
        if retrieved_memory.get("similar_tasks"):
            lines = ["[历史参考 — 相似任务]"]
            for s in retrieved_memory["similar_tasks"]:
                lines.append(f"  · {s.get('goal','')[:60]} → {s.get('outcome','')}")
            volatile_parts.append("\n".join(lines))
        if retrieved_memory.get("reflections"):
            volatile_parts.append(f"[经验反思]\n{retrieved_memory['reflections']}")
        if retrieved_memory.get("prefetch"):
            volatile_parts.append(retrieved_memory["prefetch"])
    if summary:
        volatile_parts.append(f"[对话摘要]\n{summary}")

    volatile = "\n\n".join(volatile_parts) if volatile_parts else ""

    return {"stable": stable, "context": context, "volatile": volatile}


def join_prompt_parts(parts: Dict[str, str]) -> str:
    parts_list = [p for p in (parts.get("stable", ""), parts.get("context", ""), parts.get("volatile", "")) if p]
    return "\n\n".join(parts_list)
