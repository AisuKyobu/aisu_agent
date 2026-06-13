"""pytest 全局配置 — 会话级自动清理"""
import os
import glob
import shutil

import pytest


@pytest.fixture(autouse=True)
def _cleanup_session_files(request):
    """每个测试前后清理残留的测试会话文件和计划文件"""
    yield
    if request.node.name.startswith("test_"):
        for pattern in ("sessions/_test_*.json", "plan_*.json", "plan.json"):
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except Exception:
                    pass


def pytest_sessionfinish(session, exitstatus):
    """测试全部结束后清理残留"""
    for d in ("sandbox",):
        shutil.rmtree(d, ignore_errors=True)
    for f in glob.glob("hello_test.txt"):
        try:
            os.remove(f)
        except Exception:
            pass
    sf = "sessions/_index.json"
    if os.path.exists(sf):
        import json
        try:
            data = json.load(open(sf, "r", encoding="utf-8"))
            cleaned = [s for s in data if not s.get("id", "").startswith("_test_")]
            if len(cleaned) != len(data):
                json.dump(cleaned, open(sf, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
