"""Verifier node — 三层校验: L1语法 / L2副作用 / L3语义 + handoff + 三维 guardrail"""
import hashlib
import json

from langchain_core.messages import AIMessage

from agent.logger import NodeLogger
from agent.core.scheduler import extract_handoff_signal
from agent.state import AgentState
from agent.verify.rules import verify as verify_tool_output
from agent.verify.rules import verify_l2, verify_l3


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


_GUARD_EXACT_FAILURE_WARN = 2
_GUARD_EXACT_FAILURE_BLOCK = 5
_GUARD_SAME_TOOL_FAILURE_WARN = 3
_GUARD_SAME_TOOL_FAILURE_HALT = 8
_GUARD_NO_PROGRESS_WARN = 2
_GUARD_NO_PROGRESS_BLOCK = 5

_IDEMPOTENT_TOOLS = frozenset({
    "read_file", "web_search", "web_fetch",
    "browser_screenshot", "session_search", "session_list",
    "memory_search", "list_skills",
})


def _canonical_args(args: dict) -> str:
    return json.dumps(args or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _analyze_guardrail(action_history: list, tool_name: str, tool_args: dict, tool_output: str, pending_fixes: list) -> dict:
    """三维 guardrail 分析: 精确重复 / 同类失败 / 幂等无进展。

    Returns: {"level": "WARN"|"BLOCK"|"HALT", "reason": str} 或 None 表示放行。
    """
    sig = _sha256(f"{tool_name}:{_canonical_args(tool_args)}")
    action_history.append({"sig": sig, "tool": tool_name, "args": _canonical_args(tool_args)})

    # ① 精确重复: 同一 tool + 完全相同参数连续失败
    recent = action_history[-_GUARD_EXACT_FAILURE_BLOCK:]
    exact_count = sum(1 for a in recent[-_GUARD_EXACT_FAILURE_BLOCK:] if a["sig"] == sig)
    if exact_count >= _GUARD_EXACT_FAILURE_BLOCK:
        return {"level": "BLOCK", "reason": f"{tool_name} 相同参数已连续失败 {exact_count} 次——请切换策略，不要重复相同调用"}

    if exact_count >= _GUARD_EXACT_FAILURE_WARN:
        pending_failures = sum(1 for f in pending_fixes[-_GUARD_EXACT_FAILURE_BLOCK:] if f.get("tool") == tool_name)
        if pending_failures >= _GUARD_EXACT_FAILURE_WARN:
            return {"level": "WARN", "reason": f"{tool_name} 相同参数已失败 {exact_count} 次——检查错误信息，尝试不同方式"}

    # ② 同类失败: 同一 tool 不同参数连续失败
    same_tool_recent = [a for a in action_history[-_GUARD_SAME_TOOL_FAILURE_HALT:] if a["tool"] == tool_name]
    fail_count = sum(1 for f in pending_fixes[-_GUARD_SAME_TOOL_FAILURE_HALT:] if f.get("tool") == tool_name)
    if len(same_tool_recent) >= _GUARD_SAME_TOOL_FAILURE_HALT and fail_count >= _GUARD_SAME_TOOL_FAILURE_HALT:
        return {"level": "HALT", "reason": f"{tool_name} 已连续失败 {fail_count} 次——完全停止重试，改用其他方法或求助用户"}

    if len(same_tool_recent) >= _GUARD_SAME_TOOL_FAILURE_WARN and fail_count >= _GUARD_SAME_TOOL_FAILURE_WARN:
        return {"level": "WARN", "reason": f"{tool_name} 已多次失败——考虑更换工具或策略"}

    # ③ 幂等无进展: 只读工具反复返回相同结果
    if tool_name in _IDEMPOTENT_TOOLS:
        output_hash = _sha256(str(tool_output)[:200])
        idem_recent = [a for a in action_history[-_GUARD_NO_PROGRESS_BLOCK:] if a["tool"] == tool_name]
        if len(idem_recent) >= _GUARD_NO_PROGRESS_BLOCK and all(
            a.get("output_hash") == output_hash for a in idem_recent[-_GUARD_NO_PROGRESS_BLOCK:]
        ):
            return {"level": "BLOCK", "reason": f"{tool_name} 连续返回相同结果——该查询无更多信息，使用已有结果"}

        if len(idem_recent) >= _GUARD_NO_PROGRESS_WARN and all(
            a.get("output_hash") == output_hash for a in idem_recent[-_GUARD_NO_PROGRESS_WARN:]
        ):
            return {"level": "WARN", "reason": f"{tool_name} 可能返回重复结果——确认是否需要继续查询"}

        if action_history:
            action_history[-1]["output_hash"] = output_hash

    return None


def verifier_node(state: AgentState, ctx=None) -> dict:
    _log = NodeLogger("verifier")
    _log.bind(state.get("thread_id", ""), state.get("current_step", 0))
    msgs = state["messages"]
    tool_msgs = [m for m in msgs if hasattr(m, "type") and m.type == "tool"]
    if not tool_msgs:
        return {}
    last_tool = tool_msgs[-1]
    tool_name = getattr(last_tool, "name", "")
    vl = state.get("verifier_level", "L1")
    tool_output = getattr(last_tool, "content", "")
    if not tool_name:
        return {}

    tool_args = {}
    for m in reversed(msgs):
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                if tc_name == tool_name:
                    tool_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                    break
            if tool_args:
                break

    vlog = list(state.get("verification_log", []))
    updates = {"verification_log": vlog, "last_result": str(tool_output)[:500]}

    history = list(state.get("action_history", []))
    fixes = list(state.get("pending_fixes", []))

    # ── 三维 Guardrail 分析 ──
    guard_result = _analyze_guardrail(history, tool_name, tool_args, tool_output, fixes)
    updates["action_history"] = history

    if guard_result:
        level = guard_result["level"]
        reason = guard_result["reason"]
        _log.warn(f"Guardrail {level}: {reason}")
        if level == "HALT":
            hint = AIMessage(content=f"[Guardrail HALT] {reason}")
            updates["messages"] = [hint]
            updates["needs_human"] = True
            updates["pending_fixes"] = fixes
            return updates
        elif level == "BLOCK":
            fix_entry = {"tool": tool_name, "reason": reason}
            fixes.append(fix_entry)
            if len(fixes) >= 3 and state.get("execution_mode") not in ("repair-loop", "dag"):
                _log.warn(f"自动切换 → repair-loop ({len(fixes)} 次连续失败)")
                updates["execution_mode"] = "repair-loop"
                updates["task_constraints"] = "当前处于修复模式。目标是消除错误，而不是完成原始任务。最多尝试 5 次修复。"
            hint = AIMessage(content=f"[Guardrail BLOCK] {reason}。用不同方式重试。")
            updates["messages"] = [hint]
            updates["pending_fixes"] = fixes
            return updates
        elif level == "WARN":
            hint = AIMessage(content=f"[Guardrail WARN] {reason}")
            updates["messages"] = [hint]
            updates["pending_fixes"] = fixes

    # ── HITL 检测：工具返回了"需要用户授权"的文字而非真正的执行结果 ──
    _hitl_markers = ["不在白名单内", "请询问用户是否允许", "检测到危险命令"]
    if any(m in str(tool_output) for m in _hitl_markers):
        _log.warn(f"HITL triggered: {tool_name} needs user approval")
        hint = AIMessage(content=(
            f"[安全提示] 命令 `{tool_name}` 需要用户确认。"
            "请将安全提示原样展示给用户，询问用户是否允许执行。"
            "在用户明确回复“允许”或“同意”之前，不能自行使用 allow=True 参数。不要自行假设。"
        ))
        updates["messages"] = [hint]
        updates["needs_human"] = True
        vlog.append({"step": state.get("current_step", 0), "tool": tool_name,
                     "level": "HITL", "passed": True, "reason": "需要用户授权"})
        updates["verification_log"] = vlog
        return updates

    if vl == "none":
        updates["pending_fixes"] = []
        return updates

    def _fail(r):
        fixes = list(state.get("pending_fixes", []))
        fixes.append({"tool": tool_name, "reason": r["reason"]})
        vlog.append({"step": state.get("current_step", 0), "tool": tool_name,
                     "level": r.get("level", ""), "passed": False, "reason": r["reason"]})
        updates["verification_log"] = vlog
        max_retries = state.get("retry_per_step", 2)

        if len(fixes) >= 3 and state.get("execution_mode") not in ("repair-loop", "dag"):
            _log.warn(f"自动切换 → repair-loop ({len(fixes)} 次连续失败)")
            updates["execution_mode"] = "repair-loop"
            updates["task_constraints"] = "当前处于修复模式。目标是消除错误，而不是完成原始任务。最多尝试 5 次修复。"

        if len(fixes) > max_retries:
            updates["needs_human"] = True; updates["pending_fixes"] = fixes
            hint = AIMessage(content=f"[Verifier] {tool_name} 连续失败 {len(fixes)} 次: {r['reason']}。请告知用户发生了什么，并询问是否允许继续尝试或用其他方式执行。")
            updates["messages"] = [hint]
            _log.warn(f"{tool_name} 失败(×{len(fixes)}): {r['reason'][:60]} → needs_human")
        else:
            _log.warn(f"{tool_name} {r.get('level','')}失败 (重试{len(fixes)}/{max_retries}): {r['reason'][:60]}")
            hint = AIMessage(content=f"[Verifier {r.get('level','L1')}] {tool_name} 未成功: {r['reason']}。用不同方式重试。")
            updates["messages"] = [hint]; updates["pending_fixes"] = fixes
        return updates

    def _pass(r):
        vlog.append({"step": state.get("current_step", 0), "tool": tool_name,
                     "level": r.get("level", ""), "passed": True, "reason": r["reason"]})
        updates["verification_log"] = vlog

    r1 = verify_tool_output(tool_name, tool_output)
    if not r1["passed"]: return _fail(r1)
    _pass(r1)

    if vl in ("L1+L2", "L1+L2+L3") and tool_name in ("write_file", "run_command", "browser_screenshot"):
        r2 = verify_l2(tool_name, tool_args, str(tool_output))
        if not r2["passed"]: return _fail(r2)
        _pass(r2)

    if vl == "L1+L2+L3":
        tg = state.get("task_graph", {})
        goal = tg.get("goal", "") if tg else ""
        if goal:
            r3 = verify_l3(goal, tool_name, str(tool_output))
            if not r3["passed"]: return _fail(r3)
            _pass(r3)

    em = state.get("execution_mode", "react")
    if em == "dag":
        tg = state.get("task_graph", {})
        tg_nodes = tg.get("nodes", {})
        for node_id, node in tg_nodes.items():
            if node.get("status") == "active":
                signal = extract_handoff_signal(str(tool_output))
                outputs = dict(state.get("node_outputs", {}))
                outputs[node_id] = signal
                updates["node_outputs"] = outputs
                break

    updates["pending_fixes"] = []
    _log.debug(f"✅ {tool_name} L1 pass")
    return updates
