import os
from pathlib import Path


def _scan_file_content(content: str, filename: str) -> str:
    try:
        from tools.threat_patterns import scan_for_threats
        findings = scan_for_threats(content, scope="context")
        if findings:
            import logging
            logging.getLogger("aisu.workspace").warning(
                "Context file %s blocked: %s", filename, ", ".join(findings)
            )
            return f"[BLOCKED: {filename} — 检测到潜在注入风险 ({', '.join(findings)})]"
    except Exception:
        pass
    return content


class Workspace:
    """Workspace 文件管理 — 支持多 Profile。

    目录结构:
      workspace/
      ├── shared/        ← 跨 profile 共享 (AGENTS.md, USER.md)
      ├── dev/           ← 开发助手 profile
      └── qq/            ← QQ 群管家 profile
    """

    FILES = {
        "SYSTEM_PROMPT.md": "",
        "GUIDANCE.md": "",
        "AGENTS.md": "【Agent 自定义指令】",
        "USER.md": "【用户信息】",
    }

    def __init__(self, workspace_dir: str):
        self._dir = workspace_dir
        self._cache: dict[str, list[str]] = {}
        self._mtimes: dict[str, float] = {}

    def _profile_dir(self, profile: str = "dev") -> str:
        return os.path.join(self._dir, profile)

    def _shared_dir(self) -> str:
        return os.path.join(self._dir, "shared")

    def _file_paths(self, filename: str, profile: str) -> list[str]:
        paths = [os.path.join(self._profile_dir(profile), filename)]
        if filename in ("AGENTS.md", "USER.md"):
            paths.insert(0, os.path.join(self._shared_dir(), filename))
        return paths

    def load_file(self, filename: str, profile: str = "dev", scan: bool = False) -> str:
        for filepath in self._file_paths(filename, profile):
            if os.path.isfile(filepath):
                content = Path(filepath).read_text(encoding="utf-8").strip()
                if scan:
                    content = _scan_file_content(content, filename)
                return content
        return ""

    def load_all(self, profile: str = "dev") -> list[str]:
        blocks = []
        for filename, header in self.FILES.items():
            for filepath in self._file_paths(filename, profile):
                if not os.path.isfile(filepath):
                    continue
                mtime = os.path.getmtime(filepath)
                cache_key = f"{profile}:{filename}"
                if self._mtimes.get(cache_key) == mtime and cache_key in self._cache:
                    blocks.extend(self._cache[cache_key])
                    break
                content = Path(filepath).read_text(encoding="utf-8").strip()
                self._mtimes[cache_key] = mtime
                if content:
                    if filename in ("AGENTS.md", "USER.md"):
                        content = _scan_file_content(content, filename)
                    if header and filename in ("AGENTS.md", "USER.md"):
                        result = [f"{header}\n{content}"]
                    else:
                        result = [content]
                    self._cache[cache_key] = result
                    blocks.extend(result)
                else:
                    self._cache.pop(cache_key, None)
                break
        return blocks
