"""工具集系统 — 声明式工具分组与组合。

支持 ``tools``（直接列工具）和 ``includes``（组合其他工具集）的递归解析。
替代原有的硬编码 _TOOLS_SEARCH / _TOOLS_ACTION / _TOOLS_REASONING 等分组。
"""

from typing import List, Set

TOOLSETS = {
    "web": {
        "description": "网页搜索与内容提取",
        "tools": ["web_search", "web_fetch"],
        "includes": [],
    },
    "file": {
        "description": "文件读写操作",
        "tools": ["read_file", "write_file"],
        "includes": [],
    },
    "command": {
        "description": "系统命令执行",
        "tools": ["run_command"],
        "includes": [],
    },
    "browser": {
        "description": "浏览器自动化",
        "tools": ["browser_open", "browser_click", "browser_type",
                   "browser_screenshot", "browser_inspect"],
        "includes": [],
    },
    "memory": {
        "description": "持久记忆存储与检索",
        "tools": ["remember", "memory_search"],
        "includes": [],
    },
    "session": {
        "description": "会话历史检索",
        "tools": ["session_search", "session_list"],
        "includes": [],
    },
    "plan": {
        "description": "任务计划与追踪",
        "tools": ["plan_task", "step_complete"],
        "includes": [],
    },
    "cron": {
        "description": "定时任务管理",
        "tools": ["cron_add", "cron_list", "cron_remove"],
        "includes": [],
    },
    "delegation": {
        "description": "子Agent委派 — LLM可自主拆解复杂任务",
        "tools": ["delegate_task"],
        "includes": [],
    },
    "skill": {
        "description": "技能加载与管理",
        "tools": ["list_skills", "load_skill"],
        "includes": [],
    },

    # ── 组合工具集 ──
    "search": {
        "description": "搜索模式 — 搜索 + 技能 + 会话",
        "tools": [],
        "includes": ["web", "skill", "session"],
    },
    "action": {
        "description": "执行模式 — 文件 + 命令 + 浏览器 + 计划 + 记忆 + 定时 + 委派",
        "tools": [],
        "includes": ["file", "command", "browser", "plan", "memory", "cron", "delegation"],
    },
    "reasoning": {
        "description": "推理模式 — 搜索 + 文件 + 命令 + 截图",
        "tools": ["read_file", "run_command", "browser_screenshot"],
        "includes": ["web"],
    },
    "planning": {
        "description": "规划模式 — 计划 + 文件 + 命令 + 搜索 + 记忆",
        "tools": [],
        "includes": ["plan", "file", "command", "web", "memory"],
    },
}

_CORE_TOOLS = frozenset({
    "web_search", "web_fetch",
    "read_file", "write_file", "run_command",
    "browser_open", "browser_click", "browser_type",
    "browser_screenshot", "browser_inspect",
    "remember", "memory_search",
    "plan_task", "step_complete",
    "cron_add", "cron_list", "cron_remove",
    "delegate_task",
    "session_search", "session_list",
    "list_skills", "load_skill",
})


def validate_toolset(name: str) -> bool:
    return name in TOOLSETS


def resolve_toolset(name: str, visited: Set[str] = None) -> List[str]:
    """递归解析工具集，返回所有工具名的有序列表。"""
    if visited is None:
        visited = set()
    if name in visited:
        return []
    visited.add(name)
    definition = TOOLSETS.get(name)
    if not definition:
        return []
    resolved = set(definition.get("tools", []))
    for included in definition.get("includes", []):
        resolved.update(resolve_toolset(included, visited))
    return sorted(resolved)


def get_tool_names_for_task(task_type: str) -> List[str]:
    """根据任务类型返回对应的工具名列表。"""
    mapping = {
        "search": "search",
        "action": "action",
        "reasoning": "reasoning",
        "planning": "planning",
    }
    toolset_name = mapping.get(task_type, "")
    if toolset_name:
        return resolve_toolset(toolset_name)
    return sorted(_CORE_TOOLS)


def get_all_tool_names() -> List[str]:
    return sorted(_CORE_TOOLS)
