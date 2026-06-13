from langchain.tools import tool

from agent.cron import get_manager
from tools.tool_registry import registry


@tool
def cron_add(interval: int, task: str, once: bool = False, session_id: str = "") -> str:
    """添加一个定时任务。interval是间隔秒数（最小5秒），task是任务描述，
    once=True则只执行一次（默认False），
    session_id指定到期后回复到的会话ID（为空则只广播通知）。"""
    mgr = get_manager()
    job_id = mgr.add(interval, task, once=once, session_id=session_id)
    mode = "一次" if once else f"每{interval}秒"
    info = f"定时任务已创建，ID: {job_id}，{mode}执行"
    if session_id:
        info += f"，到期后回复到当前会话"
    return info


@tool
def cron_list() -> str:
    """列出所有定时任务。"""
    mgr = get_manager()
    jobs = mgr.list_jobs()
    if not jobs:
        return "没有定时任务"
    lines = ["定时任务列表："]
    for j in jobs:
        mode = "单次" if j.get("once") else f"每{j['interval']}秒"
        tag = " [回复到会话]" if j.get("session_id") else " [广播]"
        lines.append(f"  {j['id']}: {mode}{tag} — {j['task'][:40]}")
    return "\n".join(lines)


@tool
def cron_remove(job_id: str) -> str:
    """删除一个定时任务。job_id是 cron_add 返回的任务ID。"""
    mgr = get_manager()
    ok = mgr.remove(job_id)
    return f"已删除任务 {job_id}" if ok else f"任务不存在: {job_id}"


registry.register(name="cron_add", toolset="cron", handler=cron_add.func,
                  description="添加定时任务")
registry.register(name="cron_list", toolset="cron", handler=cron_list.func,
                  description="列出所有定时任务")
registry.register(name="cron_remove", toolset="cron", handler=cron_remove.func,
                  description="删除定时任务")
