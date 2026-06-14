import json
import os
import threading

from langchain.tools import tool

from config import DATA_DIR
from tools.tool_registry import registry

PLAN_FILE = os.path.join(DATA_DIR, "plan.json")

_plan_context = threading.local()


def set_plan_thread_id(thread_id: str):
    _plan_context.thread_id = thread_id


def _current_thread_id() -> str:
    return getattr(_plan_context, "thread_id", "")


def _plan_path(thread_id: str = "") -> str:
    return os.path.join(DATA_DIR, f"plan_{thread_id}.json") if thread_id else PLAN_FILE


def load_plan(thread_id: str = "") -> dict:
    path = _plan_path(thread_id)
    if not os.path.exists(path):
        return {"goal": "", "steps": [], "completed": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_plan(plan: dict, thread_id: str = ""):
    path = _plan_path(thread_id)
    data = json.dumps(plan, ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)


def format_plan(plan: dict) -> str:
    if not plan or not plan.get("steps"):
        return ""
    goal = plan["goal"]
    steps = plan["steps"]
    completed = set(plan.get("completed", []))
    lines = [f"任务目标：{goal}", "执行计划："]
    for i, step in enumerate(steps):
        mark = "✅" if i in completed else "⬜"
        lines.append(f"  {mark} {i+1}. {step}")
    return "\n".join(lines)


def format_task_graph(tg: dict) -> str:
    if not tg or not tg.get("nodes"):
        return ""
    lines = [f"DAG 任务: {tg.get('goal', '')}"]
    for nid, node in tg.get("nodes", {}).items():
        deps = node.get("deps", [])
        deps_str = f" ← {', '.join(deps)}" if deps else ""
        lines.append(f"  [{node['status'][:4]}] {node['desc']}{deps_str}")
    return "\n".join(lines)


def load_task_graph(thread_id: str = "") -> dict:
    plan = load_plan(thread_id)
    return plan.get("task_graph", {})


@tool
def plan_task(goal: str, steps: list[str]) -> str:
    """为复杂任务制订执行计划。goal是任务目标，steps是步骤列表（最多10步）。"""
    steps = steps[:10]
    nodes = {}
    for i, s in enumerate(steps):
        deps = [f"n{i-1}"] if i > 0 else []
        nodes[f"n{i}"] = {
            "id": f"n{i}", "desc": s, "status": "pending",
            "deps": deps, "tool": "",
        }
    task_graph = {
        "id": "root", "goal": goal,
        "nodes": nodes,
        "edges": [f"{dep}->n{i}" for i in range(len(steps)) for dep in nodes[f"n{i}"]["deps"]],
    }
    plan = {
        "goal": goal,
        "steps": steps,
        "completed": [],
        "task_graph": task_graph,
    }
    save_plan(plan, thread_id=_current_thread_id())
    return f"计划已创建：\n{format_plan(plan)}"


@tool
def step_complete(step_index: int, result: str) -> str:
    """标记一个步骤已完成。step_index从0开始，result是该步骤的执行结果摘要。"""
    plan = load_plan(thread_id=_current_thread_id())
    if not plan.get("steps"):
        return "当前没有进行中的计划"

    completed = set(plan.get("completed", []))
    completed.add(step_index)
    plan["completed"] = sorted(completed)

    all_done = len(completed) == len(plan["steps"])

    save_plan(plan, thread_id=_current_thread_id())

    msg = f"步骤 {step_index+1} 已完成"
    if all_done:
        msg += "，所有步骤已完成！"
    else:
        next_idx = step_index + 1
        while next_idx < len(plan["steps"]) and next_idx in completed:
            next_idx += 1
        if next_idx < len(plan["steps"]):
            msg += f"\n下一步：{next_idx+1}. {plan['steps'][next_idx]}"

    return msg


registry.register(name="plan_task", toolset="plan", handler=plan_task.func,
                  description="创建多步骤执行计划")
registry.register(name="step_complete", toolset="plan", handler=step_complete.func,
                  description="标记当前步骤完成")
