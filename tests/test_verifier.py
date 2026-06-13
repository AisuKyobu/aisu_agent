"""Verifier — L1 + L2 核心路径"""
import os
from agent.verify.rules import verify_l1, verify_l2


def test_l1_detects_error():
    r = verify_l1("run_command", "ERROR: permission denied")
    assert r["passed"] is False
    r2 = verify_l1("run_command", "命令退出码: 1")
    assert r2["passed"] is False


def test_l1_passes_normal_output():
    r = verify_l1("write_file", "已写入 sandbox/test.py")
    assert r["passed"] is True
    r2 = verify_l1("web_search", "")
    assert r2["passed"] is False  # 空输出


def test_l2_write_file_side_effect():
    path = "sandbox/_test_v2.txt"
    os.makedirs("sandbox", exist_ok=True)
    with open(path, "w") as f:
        f.write("hello")
    r = verify_l2("write_file", {"path": path, "content": "hello"}, "已写入")
    os.remove(path)
    assert r["passed"] is True
