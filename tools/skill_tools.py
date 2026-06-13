import os

from langchain.tools import tool

from agent.skills.registry import get_registry
from tools.sandbox import copy_to_sandbox
from tools.tool_registry import registry


@tool
def list_skills() -> str:
    """列出所有可用的技能及其描述。"""
    skills = get_registry().list_available()
    if not skills:
        return "当前没有可用的技能。在 skills/ 目录下创建 <name>/SKILL.md 文件来添加技能。"
    lines = ["可用技能："]
    for s in skills:
        lines.append(f"  - {s.name}: {s.description}")
    return "\n".join(lines)


@tool
def load_skill(skill_name: str) -> str:
    """加载指定技能的详细指引。skill_name 是技能名称。"""
    skill = get_registry().get(skill_name)
    if not skill:
        available = ", ".join(s.name for s in get_registry().list_available())
        return f"技能 '{skill_name}' 不存在。可用技能：{available}"

    scripts_dir = os.path.join("skills", skill_name, "scripts")
    if os.path.isdir(scripts_dir):
        copy_to_sandbox(scripts_dir, os.path.join("skills", skill_name, "scripts"))
        return f"技能：{skill_name}\n\n（技能脚本已就绪）\n\n{skill.content}"

    return f"技能：{skill_name}\n\n{skill.content}"


registry.register(name="list_skills", toolset="skill", handler=list_skills.func,
                  description="列出所有可用技能")
registry.register(name="load_skill", toolset="skill", handler=load_skill.func,
                  description="加载指定技能，获取详细指引")
