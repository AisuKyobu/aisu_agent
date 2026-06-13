"""设置系统 — 热更新 + Profile 隔离"""

import json
import os


def test_settings_defaults():
    """所有默认值可用且合理"""
    from agent.settings import get_all, _DEFAULTS
    for profile in ("dev", "qq"):
        settings = get_all(profile=profile)
        assert "MAX_STEPS" in settings
        assert "MAX_SEARCH_COUNT" in settings
        assert "CONTEXT_LENGTH" in settings
        assert settings.get("MAX_STEPS", 0) > 0
        assert settings.get("CONTEXT_LENGTH", 0) > 1000


def test_settings_read_write():
    """设置读写一致性"""
    from agent.settings import get_all, save, get

    original = get_all(profile="dev")
    original["MAX_STEPS"] = 25
    save(original, profile="dev")

    restored = get("MAX_STEPS", profile="dev", default=20)
    assert restored == 25

    # 恢复
    original["MAX_STEPS"] = 20
    save(original, profile="dev")


def test_settings_profile_isolation():
    """dev 和 qq 设置独立"""
    from agent.settings import get_all, save, get

    dev_orig = get_all(profile="dev")
    qq_orig = get_all(profile="qq")

    dev_orig["MAX_STEPS"] = 30
    save(dev_orig, profile="dev")

    qq = get("MAX_STEPS", profile="qq", default=20)
    assert qq != 30, "qq profile 不应被 dev 的修改影响"

    # 恢复
    dev_orig["MAX_STEPS"] = 20
    save(dev_orig, profile="dev")


def test_settings_json_files_exist():
    """dev 和 qq 的 SETTINGS.json 文件存在且格式正确"""
    ws = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    for profile in ("dev", "qq"):
        path = os.path.join(ws, profile, "SETTINGS.json")
        assert os.path.isfile(path)
        data = json.load(open(path, encoding="utf-8"))
        assert isinstance(data, dict)
        assert "MAX_STEPS" in data


def test_settings_hot_reload():
    """mtime 变化后重新加载"""
    import time
    from agent.settings import get_all, save, get

    original = get_all(profile="dev")
    original["MAX_SEARCH_COUNT"] = 99
    save(original, profile="dev")

    restored = get("MAX_SEARCH_COUNT", profile="dev", default=7)
    assert restored == 99

    original["MAX_SEARCH_COUNT"] = 7
    save(original, profile="dev")
