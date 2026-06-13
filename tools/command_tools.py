from langchain.tools import tool

from config import CMD_ALLOW, TOOL_TIMEOUT
from tools.sandbox import execute
from tools.tool_registry import registry


def _is_safe(cmd: str) -> bool:
    from tools.approval import approve_always, detect_dangerous_command
    if approve_always(cmd):
        return True
    is_dangerous, _, _ = detect_dangerous_command(cmd)
    if is_dangerous:
        return False
    return any(cmd.strip().lower().startswith(p) for p in CMD_ALLOW)


@tool
def run_command(cmd: str, allow: bool = False) -> str:
    """执行系统命令。只允许白名单内的命令。如果是白名单外的命令且 allow=False，会提示询问用户是否允许。"""
    from tools.approval import detect_dangerous_command, format_approval_request
    if not allow:
        is_dangerous, pat_id, desc = detect_dangerous_command(cmd)
        if is_dangerous:
            return format_approval_request(cmd, pat_id, desc or "未知风险")
        if not _is_safe(cmd):
            return (
                f"⚠ 该命令不在白名单内: {cmd[:100]}\n"
                "请询问用户是否允许执行该命令。如果用户允许，使用 allow=True 参数重新执行。"
            )
    try:
        return execute(cmd, TOOL_TIMEOUT)
    except Exception as e:
        from tools.error_sanitizer import sanitize_tool_error
        return sanitize_tool_error(str(e))


registry.register(name="run_command", toolset="command", handler=run_command.func,
                  description="执行系统命令，受白名单和危险命令审批保护")
