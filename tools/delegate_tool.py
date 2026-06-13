"""delegate_task — LLM 自主委派子 Agent 执行复杂任务。

支持两种模式:
  1. 单个任务:   delegate_task(goal="分析项目A的代码质量")
  2. 并行批量:   delegate_task(tasks=[{"goal":"分析A"},{"goal":"分析B"}])

子 Agent 在独立 thread_id 中运行，不污染主 Agent 上下文。
受 SUBAGENT_BLOCKED_TOOLS 约束，无法委派/cron/澄清。
"""

import json
from langchain.tools import tool

from tools.tool_registry import registry


def _app():
    from agent.conversation_graph import get_sub_app
    return get_sub_app()


@tool
def delegate_task(goal: str = "", tasks: list = None,
                   toolsets: list = None, max_iterations: int = 50) -> str:
    """委派子Agent独立执行复杂任务。

    适用场景:
    - 需要多步推理、多工具配合的复杂分析
    - 需要同时处理多个独立子任务（使用 tasks 参数并行）
    - 计算密集或需要大量搜索的任务

    参数:
    - goal: 单个任务目标（如"分析项目A的代码质量并生成报告"）
    - tasks: 并行任务列表 [{"goal":"...","toolsets":["web"]},...]
      如果指定 tasks，goal 将被忽略
    - toolsets: 限制子Agent可用的工具集，如 ["web","file"]
      不指定则继承完整工具集
    - max_iterations: 子Agent最大迭代次数，默认50

    注意: 子Agent看不到你的对话历史，只有独立上下文。
    """
    from agent.sub_agent import spawn_sub_agent, spawn_sub_agents_parallel

    # ── 并行批处理模式 ──
    if tasks and isinstance(tasks, list) and len(tasks) > 0:
        task_defs = []
        for t in tasks:
            if isinstance(t, str):
                task_defs.append({"goal": t, "max_steps": max_iterations})
            else:
                td = {"goal": t.get("goal", t.get("task", "")),
                       "max_steps": t.get("max_iterations", max_iterations)}
                if t.get("toolsets"):
                    td["allowed_toolsets"] = t["toolsets"]
                task_defs.append(td)

        results = spawn_sub_agents_parallel(_app(), task_defs, child_depth=0)
        summaries = []
        for r in results:
            status = r.get("status", "failed")
            goal_text = r.get("goal", "")[:40]
            if r.get("output", {}).get("final_response"):
                text = r["output"]["final_response"][:200]
                summaries.append(f"[{status}] {goal_text}: {text}")
            else:
                summaries.append(f"[{status}] {goal_text}")
        return "子Agent并行执行结果:\n" + "\n".join(summaries)

    # ── 单任务模式 ──
    if not goal:
        return json.dumps({"error": "必须提供 goal 或 tasks 参数"})

    task_def = {
        "goal": goal,
        "execution_mode": "react",
        "verifier_level": "L1+L2",
        "max_steps": max_iterations,
    }
    if toolsets:
        task_def["allowed_toolsets"] = toolsets

    result = spawn_sub_agent(_app(), task_def, child_depth=0)

    return json.dumps({
        "goal": goal,
        "status": result.get("status", "failed"),
        "output": result.get("output", {}),
        "error": result.get("error", ""),
    }, ensure_ascii=False)


registry.register(name="delegate_task", toolset="delegation",
                  handler=delegate_task.func,
                  description="委派子Agent独立执行复杂任务，支持并行批量")
