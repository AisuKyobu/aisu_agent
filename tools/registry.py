from tools.browser_tools import browser_click, browser_inspect, browser_open, browser_screenshot, browser_type
from tools.command_tools import run_command
from tools.cron_tools import cron_add, cron_list, cron_remove
from tools.delegate_tool import delegate_task
from tools.file_tools import read_file, write_file
from tools.memory_tools import memory_search, remember
from tools.plan_tools import plan_task, step_complete
from tools.session_tools import session_list, session_search
from tools.skill_tools import list_skills, load_skill
from tools.web_tools import web_fetch, web_search

TOOLS = [
    read_file, write_file, run_command,
    remember, memory_search,
    plan_task, step_complete,
    list_skills, load_skill,
    cron_add, cron_list, cron_remove,
    delegate_task,
    session_search, session_list,
    web_search, web_fetch,
    browser_open, browser_click, browser_type, browser_screenshot, browser_inspect,
]


def get_filtered_tools():
    from config import TOOL_ALLOW, TOOL_DENY
    if TOOL_ALLOW == ["*"]:
        return [t for t in TOOLS if t.name not in TOOL_DENY]
    return [t for t in TOOLS if t.name in TOOL_ALLOW and t.name not in TOOL_DENY]
