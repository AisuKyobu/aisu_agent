"""工具测试 — 每个工具域一条"""
import os
import shutil

import pytest
from tools.sandbox import ensure_sandbox, sandbox_path, in_sandbox
from tools.file_tools import read_file, write_file


def setup_module():
    ensure_sandbox()


def teardown_module():
    shutil.rmtree("sandbox", ignore_errors=True)
    for f in ["plan.json", "hello_test.txt"]:
        if os.path.exists(f):
            os.remove(f)


# ── Sandbox ──
def test_sandbox_path_redirects():
    assert in_sandbox(sandbox_path("C:/Windows/system.ini"))
    assert in_sandbox(sandbox_path("/etc/passwd"))
    result = sandbox_path("sandbox/test.txt")
    assert "sandbox" in result


# ── File ──
def test_file_read_write():
    r = write_file.invoke({"path": "hello_test.txt", "content": "Hello"})
    assert "已写入" in r
    assert read_file.invoke({"path": "hello_test.txt"}) == "Hello"
    assert "不存在" in read_file.invoke({"path": "does_not_exist_123.txt"})


# ── Memory ──
def test_memory_remember_and_search(monkeypatch):
    from agent.memory.store import MemoryStore
    from agent.memory.manager import MemoryManager
    _store = MemoryStore()
    _store.initialize(profile="test")
    _mgr = MemoryManager()
    _mgr.add_provider(_store)
    monkeypatch.setattr("agent.memory.manager._manager", _mgr)
    from tools.memory_tools import remember, memory_search
    r = remember.invoke({"key": "测试", "value": "remember test data"})
    assert "已记住" in r
    r2 = memory_search.invoke({"query": "remember test"})
    assert "remember test data" in r2
    _store.shutdown()


# ── Plan ──
def test_plan_create_and_complete():
    from tools.plan_tools import plan_task, step_complete, load_plan
    if os.path.exists("plan.json"):
        os.remove("plan.json")
    try:
        r = plan_task.invoke({"goal": "测试任务", "steps": ["步骤1", "步骤2"]})
        assert "计划已创建" in r
        plan = load_plan()
        assert plan["goal"] == "测试任务"
        assert len(plan["steps"]) == 2
        r = step_complete.invoke({"step_index": 0, "result": "done"})
        assert "步骤 1 已完成" in r
        r = step_complete.invoke({"step_index": 1, "result": "done"})
        assert "所有步骤已完成" in r
    finally:
        if os.path.exists("plan.json"):
            os.remove("plan.json")


# ── Command + HITL ──
def test_command_whitelist_and_override():
    from tools.command_tools import run_command
    r = run_command.invoke({"cmd": "rm -rf /"})
    assert "检测到危险命令" in r
    r = run_command.invoke({"cmd": "echo test_cmd_123"})
    assert "test_cmd_123" in r
    r = run_command.invoke({"cmd": "rm test.txt", "allow": True})
    assert "检测到危险命令" not in r


# ── Cron ──
def test_cron_lifecycle():
    from agent.cron import CronManager
    mgr = CronManager()
    mgr.start()
    jid = mgr.add(3600, "test cron task", once=True)
    jobs = mgr.list_jobs()
    assert any(j["id"] == jid for j in jobs)
    assert mgr.remove(jid)
    mgr._running = False


# ── Session ──
def test_session_save_search():
    from agent.session import save_session, search_sessions
    sid = "_test_session_tmp"
    try:
        save_session(sid, "test session summary")
        results = search_sessions("test")
        assert any("test" in str(r).lower() for r in results)
    finally:
        sf = os.path.join("sessions", f"{sid}.json")
        if os.path.exists(sf):
            os.remove(sf)


# ── Skill ──
def test_skill_registry():
    from agent.skills.registry import SkillRegistry
    reg = SkillRegistry(search_dirs=["skills"])
    reg.discover()
    all_skills = reg.list_all()
    assert len(all_skills) > 0
    for s in all_skills:
        assert s.name and s.description
        assert reg.is_enabled(s.name) is True
