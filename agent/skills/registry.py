import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_enabled_file = "skills/.enabled.json"


def _load_enabled() -> dict:
    try:
        return json.loads(Path(_enabled_file).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_enabled(data: dict):
    Path(_enabled_file).parent.mkdir(parents=True, exist_ok=True)
    Path(_enabled_file).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@dataclass
class Skill:
    name: str
    description: str
    content: str
    path: str
    metadata: dict = field(default_factory=dict)


_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_skill_file(filepath: str) -> Optional[Skill]:
    try:
        text = Path(filepath).read_text(encoding="utf-8")
    except Exception:
        return None

    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return None

    try:
        import yaml
        meta = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return None

    name = meta.get("name", "")
    description = meta.get("description", "")
    if not name or not description:
        return None

    body = text[m.end():].strip()
    return Skill(
        name=name, description=description,
        content=body, path=filepath,
        metadata=meta.get("metadata", {}),
    )


class SkillRegistry:
    def __init__(self, search_dirs: List[str]):
        self._search_dirs = search_dirs
        self._cache: dict[str, Skill] = {}
        self._enabled: dict[str, bool] = {}

    def discover(self):
        self._cache.clear()
        self._enabled = _load_enabled()
        for sd in self._search_dirs:
            if not os.path.isdir(sd):
                continue
            for entry in os.scandir(sd):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                skill_file = os.path.join(entry.path, "SKILL.md")
                if not os.path.isfile(skill_file):
                    continue
                skill = _parse_skill_file(skill_file)
                if skill:
                    self._cache[skill.name] = skill
            # 新技能默认启用
            for name in self._cache:
                if name not in self._enabled:
                    self._enabled[name] = True

    def is_enabled(self, name: str) -> bool:
        return self._enabled.get(name, True)

    def set_enabled(self, name: str, enabled: bool):
        if name not in self._cache:
            return
        self._enabled[name] = enabled
        _save_enabled(self._enabled)

    def list_all(self) -> List[Skill]:
        return list(self._cache.values())

    def list_available(self) -> List[Skill]:
        return [s for s in self._cache.values() if self._enabled.get(s.name, True)]

    def get(self, name: str) -> Optional[Skill]:
        if not self._enabled.get(name, True):
            return None
        return self._cache.get(name)

    def format_prompt_block(self) -> str:
        skills = self.list_available()
        if not skills:
            return ""
        lines = ["<available_skills>"]
        for s in skills:
            lines.append(f"  <skill name=\"{s.name}\" description=\"{s.description}\" />")
        lines.append("</available_skills>")
        lines.append("使用 load_skill 工具加载需要的技能以获取详细指引。")
        return "\n".join(lines)


_registry: SkillRegistry = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry(search_dirs=[])
    return _registry


def init_skills():
    from config import SKILLS_DIR
    get_registry()._search_dirs = SKILLS_DIR
    get_registry().discover()
