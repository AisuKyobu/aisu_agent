"""Skill Executor — 将技能定义展开为可执行的子任务序列"""
import json
from typing import Optional
from agent.logger import NodeLogger

_log = NodeLogger("skill_executor")

# ── 技能状态机 JSON schema（SKILL.md front matter 或 body 中的可选块） ──
# 示例：
# ```skill
# {
#   "name": "aigc-reduce",
#   "nodes": [
#     {"id": "scan", "tool": "run_command",
#      "cmd": "python skills/aigc-reduce/scripts/aigc_scan.py {file}"},
#     {"id": "replace", "tool": "run_command",
#      "cmd": "python skills/aigc-reduce/scripts/do_replace.py {file}",
#      "depends_on": ["scan"]},
#     {"id": "verify", "tool": "run_command",
#      "cmd": "python skills/aigc-reduce/scripts/verify.py {file} --rate 0.4",
#      "depends_on": ["replace"], "retry_on_fail": true, "max_retries": 3}
#   ],
#   "params": {"file": "string"},
#   "on_failure": "report"
# }
# ```


def parse_skill_statemachine(skill_content: str) -> Optional[dict]:
    """从 SKILL.md 正文中提取 ```skill JSON 块。"""
    import re
    m = re.search(r'```skill\s*\n(.*?)\n```', skill_content, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def expand_to_taskgraph(skill_def: dict, params: dict = None) -> dict:
    """将技能状态机定义展开为 task_graph DAG。

    技能定义格式:
    {
      "name": "skill-name",
      "nodes": [{"id": "n1", "tool": "...", "cmd": "...", "depends_on": [...]}, ...],
      "params": {"file": "string"},
      "on_failure": "report" | "retry" | "abort"
    }
    """
    if not skill_def or not skill_def.get("nodes"):
        return {}

    params = params or {}
    nodes = {}
    edges = []
    for node_def in skill_def["nodes"]:
        nid = node_def["id"]
        desc = node_def.get("desc", f"{node_def.get('tool', '?')}: {node_def.get('cmd', '?')}")
        deps = node_def.get("depends_on", [])
        nodes[nid] = {
            "id": nid,
            "desc": desc,
            "status": "pending",
            "deps": deps,
            "tool": node_def.get("tool", "run_command"),
            "cmd": _resolve_params(node_def.get("cmd", ""), params),
            "retry_on_fail": node_def.get("retry_on_fail", False),
            "max_retries": node_def.get("max_retries", 1),
        }
        for dep in deps:
            edges.append(f"{dep}->{nid}")

    return {
        "id": f"skill_{skill_def.get('name', 'unnamed')}",
        "goal": f"执行技能: {skill_def.get('name', '')}",
        "nodes": nodes,
        "edges": edges,
        "on_failure": skill_def.get("on_failure", "report"),
    }


def _resolve_params(cmd: str, params: dict) -> str:
    """替换命令模板中的 {param} 占位符。"""
    for key, val in params.items():
        cmd = cmd.replace(f"{{{key}}}", str(val))
    return cmd


def skill_name_from_markdown(content: str) -> str:
    """从 SKILL.md 中提取技能名（优先 front matter，其次 ```skill 块）。"""
    import re
    m = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    sm = parse_skill_statemachine(content)
    if sm:
        return sm.get("name", "")


# ── Skill Output Cache ──

_skill_cache: dict[str, dict] = {}

def get_cached_skill_result(skill_name: str, params: dict) -> dict | None:
    """同一 skill + 同一参数 180 秒内的缓存结果。"""
    import time
    key = f"{skill_name}:{hash(str(sorted(params.items()))) & 0xFFFFFFFF:08x}"
    entry = _skill_cache.get(key)
    if entry and entry.get("ts", 0) > time.time() - 180:
        return entry.get("result")
    return None

def set_cached_skill_result(skill_name: str, params: dict, result: dict):
    import time
    key = f"{skill_name}:{hash(str(sorted(params.items()))) & 0xFFFFFFFF:08x}"
    _skill_cache[key] = {"result": result, "ts": time.time()}
    return ""
