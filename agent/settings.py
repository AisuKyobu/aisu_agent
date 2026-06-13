"""动态配置 — 按 Profile 从 workspace/{profile}/SETTINGS.json 读取，支持热更新。

共享配置: workspace/shared/ 下的文件
Profile配置: workspace/{profile}/SETTINGS.json
每次 agent 调用时读取，修改后无需重启。
"""

import json
import os
from pathlib import Path
from typing import Any

from config import WORKSPACE_DIR

_DEFAULTS = {
    "MAX_STEPS": 20,
    "MAX_SEARCH_COUNT": 7,
    "REASONING_MAX_STEPS": 20,
    "REASONING_MAX_TOOL_CALLS": 15,
    "REASONING_MAX_FILE_READS": 20,
    "REASONING_MAX_SEARCH": 3,
    "MAX_MESSAGES": 120,
    "KEEP_MESSAGES": 80,
    "COMPRESSION_THRESHOLD": 0.75,
    "CONTEXT_LENGTH": 128000,
    "MAX_RETRIES": 3,
    "RETRY_DELAY": 2,
    "TOOL_TIMEOUT": 30,
}

_cache: dict = {}


def _settings_path(profile: str = "dev") -> str:
    return os.path.join(WORKSPACE_DIR, profile, "SETTINGS.json")


def _ensure_defaults(profile: str):
    path = _settings_path(profile)
    if not os.path.isfile(path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(_DEFAULTS, ensure_ascii=False, indent=2), encoding="utf-8")


def get(key: str, profile: str = "dev", default: Any = None) -> Any:
    global _cache
    path = _settings_path(profile)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return _DEFAULTS.get(key, default)
    cache_key = profile
    if cache_key not in _cache or _cache[cache_key].get("_mtime") != mtime:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            merged = dict(_DEFAULTS)
            merged.update(data)
            merged["_mtime"] = mtime
            _cache[cache_key] = merged
        except Exception:
            return _DEFAULTS.get(key, default)
    return _cache[cache_key].get(key, _DEFAULTS.get(key, default))


def get_all(profile: str = "dev") -> dict:
    _ensure_defaults(profile)
    path = _settings_path(profile)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        merged = dict(_DEFAULTS)
        merged.update(data)
        return merged
    except Exception:
        return dict(_DEFAULTS)


def save(data: dict, profile: str = "dev") -> bool:
    try:
        path = _settings_path(profile)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _cache.pop(profile, None)
        return True
    except Exception:
        return False


for _p in ("dev", "qq"):
    _ensure_defaults(_p)
