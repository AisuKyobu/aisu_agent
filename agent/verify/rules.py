"""Verifier L1/L2/L3 — 三层校验机制"""
import os
import re
from typing import Any

from langchain_deepseek import ChatDeepSeek

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME
from agent.logger import NodeLogger

_log = NodeLogger("verifier_rules")

_verifier_llm = ChatDeepSeek(model=MODEL_NAME, temperature=0, api_key=DEEPSEEK_API_KEY, api_base=DEEPSEEK_BASE_URL)

# ── L1 规则：基于输出文本模式判断工具是否真的执行成功 ──

ERROR_PATTERNS = [
    r"(?i)\b(error|failure|failed|exception|traceback|permission denied|not found)\b",
    r"命令执行失败",
    r"命令退出码: [1-9]",
    r"FileNotFoundError|PermissionError|ModuleNotFoundError|ImportError",
]

OK_PATTERNS = {
    "run_command": [r"命令执行完成", r"已写入", r"已记住", r"截图已保存", r"Successfully"],
    "write_file": [r"已写入"],
    "browser_open": [r"标题:"],
    "browser_screenshot": [r"截图已保存"],
    "web_search": [],
    "web_fetch": [],
    "read_file": [],
    "remember": [r"已记住"],
    "memory_search": [],
    "cron_add": [r"已创建"],
    "cron_remove": [r"已删除"],
    "plan_task": [r"已创建"],
    "step_complete": [r"已完成"],
    "load_skill": [r"技能"],
    "session_search": [],
    "session_list": [],
}


def _matched_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns) if patterns else False


def verify_l1(tool_name: str, output: Any) -> dict:
    """L1 语法校验：扫描 tool_output 中的错误指示符。"""
    text = str(output) if output is not None else ""
    # 去除 untrusted_tool_result XML 包装，避免误判
    text = re.sub(r"</?untrusted_tool_result[^>]*>", "", text)

    if not text.strip():
        return {"level": "L1", "passed": False, "tool": tool_name, "reason": "空输出"}

    has_error = _matched_any(text, ERROR_PATTERNS)
    ok_patterns = OK_PATTERNS.get(tool_name, [])
    has_ok = _matched_any(text, ok_patterns) if ok_patterns else not has_error

    if has_error and not has_ok:
        return {"level": "L1", "passed": False, "tool": tool_name,
                "reason": f"输出含错误指示符: {text[:80]}"}

    return {"level": "L1", "passed": True, "tool": tool_name, "reason": ""}


def verify_l2(tool_name: str, tool_args: dict, tool_output: str) -> dict:
    """L2 副作用验证：检查工具的声称是否真实发生。

    原则：tool success != task success。
    write_file → 读回校验内容一致
    报创建了文件 → 确认文件存在
    """
    text = str(tool_output) if tool_output else ""

    if tool_name == "write_file":
        path = tool_args.get("path", "")
        content = tool_args.get("content", "")
        if path and content:
            try:
                from tools.file_tools import read_file as _rf
                actual = _rf.invoke({"path": path})
                if content == actual:
                    return {"level": "L2", "passed": True, "tool": tool_name, "reason": ""}
                return {"level": "L2", "passed": False, "tool": tool_name,
                        "reason": f"write_file 内容不一致: 期望 {len(content)} chars, 实际 {len(str(actual))} chars"}
            except Exception as e:
                return {"level": "L2", "passed": False, "tool": tool_name,
                        "reason": f"无法读回校验: {e}"}

    if tool_name == "run_command":
        # 抽取出 "已写入 <path>" 的路径，校验是否存在
        import re
        created = re.findall(r'已写入\s+(\S+)', text)
        for p in created:
            if not os.path.exists(p):
                return {"level": "L2", "passed": False, "tool": tool_name,
                        "reason": f"声称写入的 {p} 不存在"}

    if tool_name == "browser_screenshot":
        if not os.path.exists("sandbox/browser_screenshot.png"):
            return {"level": "L2", "passed": False, "tool": tool_name,
                    "reason": "截图文件不存在"}

    return {"level": "L2", "passed": True, "tool": tool_name, "reason": ""}


def verify_l3(goal: str, tool_name: str, output: str) -> dict:
    """L3 语义验证：用 LLM 判断工具输出是否完成了用户目标的一步。

    返回 {"passed": True/False, "reason": str}。
    不独立调用 LLM——由 caller（verifier_node）决定是否触发。
    """
    prompt = (
        f"用户目标: {goal}\n"
        f"上一步工具: {tool_name}\n"
        f"工具输出: {str(output)[:300]}\n\n"
        "请仅用一个词回答: yes (这一步确实推进了目标), no (这一步明显失败), partial (部分完成但需继续)。"
        "不要解释。"
    )
    try:
        _log.debug(f"L3 verify prompt: {prompt[:200]}")
        result = _verifier_llm.invoke(prompt)
        answer = result.content.strip().lower() if hasattr(result, "content") else "partial"
        _log.debug(f"L3 verify: {tool_name} → {answer[:80]}")
        if "yes" in answer:
            return {"level": "L3", "passed": True, "tool": tool_name, "reason": "语义校验通过"}
        if "no" in answer:
            return {"level": "L3", "passed": False, "tool": tool_name, "reason": "语义校验判定失败"}
        return {"level": "L3", "passed": True, "tool": tool_name, "reason": "partial-继续"}
    except Exception as e:
        _log.warn(f"L3 verify skipped: {e}")
        return {"level": "L3", "passed": True, "tool": tool_name, "reason": "L3 skipped (LLM unavailable)"}


def verify(tool_name: str, output: Any) -> dict:
    """向后兼容：默认只跑 L1。"""
    return verify_l1(tool_name, output)

