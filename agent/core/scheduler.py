"""Scheduler 6 modes — 按 execution_mode 分发的调度引擎"""
from typing import Optional, Tuple
from agent.logger import NodeLogger

_log = NodeLogger("scheduler")

# ── DAG 通用工具（保持兼容） ──

def _all_deps_done(task_graph: dict, deps: list[str]) -> bool:
    for dep in deps:
        dep_node = task_graph.get("nodes", {}).get(dep, {})
        if dep_node.get("status") != "completed":
            return False
    return True

def select_next_dag(task_graph: dict) -> Optional[dict]:
    if not task_graph or not task_graph.get("nodes"):
        return None
    candidates = []
    for nid, node in task_graph["nodes"].items():
        if node.get("status") != "pending":
            continue
        if _all_deps_done(task_graph, node.get("deps", [])):
            candidates.append(node)
    if not candidates:
        return None
    candidates.sort(key=lambda n: len(n.get("deps", [])))
    return candidates[0]

def update_node(task_graph: dict, node_id: str, status: str) -> dict:
    if node_id in task_graph.get("nodes", {}):
        task_graph["nodes"][node_id]["status"] = status
    return task_graph

def all_done(task_graph: dict) -> bool:
    if not task_graph or not task_graph.get("nodes"):
        return False
    terminal = {"completed", "failed", "blocked", "skipped"}
    return all(n.get("status") in terminal for n in task_graph["nodes"].values())

def mark_failed(task_graph: dict, node_id: str) -> Tuple[dict, bool]:
    update_node(task_graph, node_id, "failed")
    blocked = False
    for nid, node in task_graph.get("nodes", {}).items():
        if node_id in node.get("deps", []):
            if node.get("status") == "pending":
                node["status"] = "blocked"
                blocked = True
    return task_graph, blocked

# ── 模式感知 format ──

STATUS_ICONS = {"pending":"⬜","completed":"✅","failed":"❌","blocked":"🚫","skipped":"⏭","active":"🔄"}

def format_hint(mode: str, task_graph: dict = None, research_depth: int = 0,
                repair_attempt: int = 0, blocked_nodes: list = None) -> str:
    if not task_graph or not task_graph.get("nodes"):
        if mode == "research-loop":
            return f"[深度研究] 第 {research_depth} 轮"
        if mode == "repair-loop":
            return f"[修复模式] 第 {repair_attempt} 次尝试"
        return ""

    lines = [f"[{mode}]"]
    for nid, node in task_graph["nodes"].items():
        s = node.get("status", "pending")
        icon = STATUS_ICONS.get(s, "⬜")
        deps = node.get("deps", [])
        deps_str = f" ← {', '.join(deps)}" if deps else ""
        lines.append(f"  {icon} [{nid}] {node['desc']}{deps_str}")

    if mode == "dag":
        nxt = select_next_dag(task_graph)
        if nxt:
            lines.append(f"\n下一步: [{nxt['id']}] {nxt['desc']}")
        elif all_done(task_graph):
            lines.append("\n所有节点已完成。")
        else:
            lines.append("\npending 节点被阻塞。")
    elif mode == "react":
        pending = [n for nid,n in task_graph["nodes"].items() if n.get("status")=="pending"]
        if pending:
            lines.append(f"\n剩余 {len(pending)} 步未完成")
    elif mode == "repair-loop":
        lines.append(f"\n修复尝试 {repair_attempt}/5")
        if blocked_nodes:
            lines.append(f"阻塞: {', '.join(blocked_nodes)}")
    elif mode == "research-loop":
        lines.append(f"\n当前深度: {research_depth} 轮")

    return "\n".join(lines)


# ── 分模式调度 ──

def scheduler_dispatch(mode: str, task_graph: dict, state: dict) -> dict:
    """按 execution_mode 返回调度决策。

    Returns: {
        "next_node": Optional[dict],  # DAG 模式下当前节点
        "hint": str,                   # 注入 Agent context 的提示
        "scoped": bool,                # 是否使用精简上下文
    }
    """
    if mode == "direct":
        return {"next_node": None, "hint": "", "scoped": False}

    if mode == "dag":
        nxt = select_next_dag(task_graph)
        if nxt is None:
            return {"next_node": None,
                    "hint": format_hint("dag", task_graph),
                    "scoped": False}
        return {"next_node": nxt,
                "hint": format_hint("dag", task_graph),
                "scoped": True}

    if mode == "react":
        return {"next_node": None,
                "hint": format_hint("react", task_graph),
                "scoped": False}

    if mode == "repair-loop":
        nxt = select_next_dag(task_graph)
        attempts = len([f for f in state.get("pending_fixes", [])])
        blocked = [nid for nid, nd in (task_graph or {}).get("nodes", {}).items()
                   if nd.get("status") == "blocked"]
        hint = format_hint("repair-loop", task_graph, repair_attempt=attempts, blocked_nodes=blocked)
        if attempts >= 5:
            return {"next_node": nxt, "hint": hint, "scoped": False}
        if nxt is None and blocked:
            hint += "\n所有可执行节点已阻塞，建议标记 needs_human。"
            return {"next_node": None, "hint": hint, "scoped": False}
        return {"next_node": nxt, "hint": hint, "scoped": True}

    if mode == "research-loop":
        depth = state.get("current_step", 0)
        hint = format_hint("research-loop", task_graph, research_depth=depth)
        if depth >= 10:
            return {"next_node": None, "hint": hint + "\n达到最大研究深度", "scoped": False}
        return {"next_node": None, "hint": hint, "scoped": False}

    if mode == "monitor":
        nxt = select_next_dag(task_graph)
        if nxt is None:
            return {"next_node": None, "hint": "", "scoped": False}
        return {"next_node": nxt, "hint": format_hint("monitor", task_graph),
                "scoped": True}

    # fallback: react
    return {"next_node": None, "hint": "", "scoped": False}


def build_scoped_context(goal: str, node: dict, recent_msgs: list, handoff: dict = None) -> list:
    """DAG / Repair / Monitor 模式下构建精简上下文。

    Agent 只看到：目标 + 当前节点描述 + 上一步输出信号 + 最近 3 条消息。
    不暴露全局 messages，防止 subtask pollution。
    """
    from langchain_core.messages import SystemMessage
    ctx = [SystemMessage(content=f"[首要目标] {goal}")]
    ctx.append(SystemMessage(content=f"[当前节点] [{node['id']}] {node.get('desc','')}"))
    if node.get("cmd"):
        ctx.append(SystemMessage(content=f"[执行命令] {node['cmd'][:200]}"))
    if handoff:
        ctx.append(SystemMessage(content=f"[上一步输出] {handoff.get('signal','')}"))
    ctx.extend(list(recent_msgs[-3:]))
    return ctx


def extract_handoff_signal(node_output: str, output_key: str = "") -> dict:
    """从节点输出中提取结构化 handoff 信号。

    不是 raw stdout——而是提取 key=value 配对或摘要。
    """
    import re
    signal = {}
    # 尝试 JSON
    try:
        import json
        data = json.loads(node_output)
        if isinstance(data, dict):
            signal = {k: str(v)[:100] for k, v in data.items()}
    except Exception:
        pass
    # 尝试 key=value 模式
    if not signal:
        for m in re.finditer(r'(\w[\w_-]*)\s*[:=]\s*([^\s,;]+)', node_output):
            signal[m.group(1)] = m.group(2)
    # 无结构化输出 → 用前 100 字符
    if not signal:
        signal["output"] = node_output[:100]
    return signal
