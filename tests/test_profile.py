"""Profile 切换 + 记忆隔离 — 单元测试"""

import os
import sqlite3


def test_workspace_has_profiles():
    """workspace 目录结构正确：dev/ qq/ shared/ 都存在"""
    ws = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    for d in ("dev", "qq", "shared"):
        assert os.path.isdir(os.path.join(ws, d)), f"缺少目录: workspace/{d}"


def test_dev_profile_files_exist():
    """dev profile 有 SYSTEM_PROMPT.md 和 SETTINGS.json"""
    ws = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    for f in ("SYSTEM_PROMPT.md", "GUIDANCE.md", "SETTINGS.json"):
        path = os.path.join(ws, "dev", f)
        assert os.path.isfile(path), f"缺少: workspace/dev/{f}"


def test_qq_profile_files_exist():
    """qq profile 有独立的 SYSTEM_PROMPT.md 和 SETTINGS.json"""
    ws = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    for f in ("SYSTEM_PROMPT.md", "GUIDANCE.md", "SETTINGS.json"):
        path = os.path.join(ws, "qq", f)
        assert os.path.isfile(path), f"缺少: workspace/qq/{f}"


def test_dev_qq_prompts_different():
    """dev 和 qq 的 SYSTEM_PROMPT.md 内容不同"""
    ws = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    dev_prompt = open(os.path.join(ws, "dev", "SYSTEM_PROMPT.md"), encoding="utf-8").read()
    qq_prompt = open(os.path.join(ws, "qq", "SYSTEM_PROMPT.md"), encoding="utf-8").read()
    assert dev_prompt != qq_prompt, "两个 profile 的 prompt 应该不同"


def test_dev_qq_settings_different():
    """dev 和 qq 的 SETTINGS.json 值不同（qq 更保守）"""
    import json
    ws = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    dev_s = json.load(open(os.path.join(ws, "dev", "SETTINGS.json"), encoding="utf-8"))
    qq_s = json.load(open(os.path.join(ws, "qq", "SETTINGS.json"), encoding="utf-8"))
    assert dev_s.get("MAX_STEPS", 0) >= qq_s.get("MAX_STEPS", 0), "qq 的 MAX_STEPS 不应大于 dev"


def test_memory_store_profile_isolation():
    """不同 profile 使用不同 db 文件"""
    from agent.memory.store import MemoryStore
    s1 = MemoryStore()
    s1.initialize(profile="dev")
    s2 = MemoryStore()
    s2.initialize(profile="qq")
    assert s1.db_path != s2.db_path, "不同 profile 应该用不同 db"
    assert "dev" in s1.db_path
    assert "qq" in s2.db_path
    s1.shutdown()
    s2.shutdown()


def test_settings_by_profile():
    """agent/settings.py 按 profile 读写"""
    from agent.settings import get, save, get_all

    # 读 dev
    dev_max = get("MAX_STEPS", profile="dev", default=20)
    assert isinstance(dev_max, int) and dev_max > 0

    # 读 qq
    qq_max = get("MAX_STEPS", profile="qq", default=20)
    assert isinstance(qq_max, int) and qq_max > 0

    # 保存后读回
    original = get_all(profile="dev")
    save(original, profile="dev")
    restored = get("MAX_STEPS", profile="dev", default=20)
    assert restored == dev_max


def test_workspace_load_by_profile():
    """workspace.load_file 按 profile 加载不同文件"""
    from agent.workspace import Workspace
    ws = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    w = Workspace(ws)

    dev_p = w.load_file("SYSTEM_PROMPT.md", profile="dev")
    qq_p = w.load_file("SYSTEM_PROMPT.md", profile="qq")
    assert "助手" in dev_p or "agent" in dev_p.lower()
    assert "群" in qq_p or "管家" in qq_p or "aisu" in qq_p.lower()


def test_workspace_shared_files():
    """shared/ 目录的 AGENTS.md 和 USER.md 可被两个 profile 加载"""
    from agent.workspace import Workspace
    ws = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    w = Workspace(ws)

    agents_dev = w.load_file("AGENTS.md", profile="dev")
    agents_qq = w.load_file("AGENTS.md", profile="qq")
    assert agents_dev == agents_qq, "shared 文件在两个 profile 中应相同"
