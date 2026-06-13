import re
from typing import Tuple, Optional

_DANGEROUS_PATTERNS = [
    (r"rm\s+(-[a-zA-Z]*r[f])", "rm_rf", "recursive_delete"),
    (r"sudo\s", "sudo", "privilege_escalation"),
    (r"chmod\s+[0-7]*7", "chmod_777", "permission_widening"),
    (r">\s*/dev/[a-z]+", "write_dev", "write_to_device"),
    (r"mkfs\.", "mkfs", "format_disk"),
    (r"(wget|curl).*\|.*(sh|bash|python)", "pipe_exec", "pipe_to_shell"),
    (r"dd\s+if=", "dd", "direct_disk_io"),
    (r"(shutdown|reboot|halt|poweroff)\b", "system_power", "shutdown_reboot"),
    (r"git\s+push\s+.*--force", "force_push", "force_push"),
    (r"git\s+reset\s+--hard", "hard_reset", "hard_reset"),
    (r"chown\s+.*:\s*/", "chown_system", "change_system_ownership"),
    (r"mv\s+/", "move_system", "move_system_file"),
    (r"cp\s+/", "copy_system", "copy_system_file"),
]


def detect_dangerous_command(cmd: str) -> Tuple[bool, Optional[str], Optional[str]]:
    if not cmd or not isinstance(cmd, str):
        return False, None, None
    cmd_stripped = cmd.strip()
    for pattern, pat_id, description in _DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_stripped, re.IGNORECASE):
            return True, pat_id, description
    return False, None, None


def format_approval_request(cmd: str, pat_id: str, description: str) -> str:
    return (
        f"\u26a0 检测到危险命令: {description}\n"
        f"命令: {cmd[:200]}\n"
        f"请确认是否允许执行。如果允许，回复'允许'或'同意'。"
    )


def approve_always(cmd: str) -> bool:
    from config import CMD_ALLOW_ALWAYS
    return any(cmd.strip().startswith(p) for p in CMD_ALLOW_ALWAYS)
