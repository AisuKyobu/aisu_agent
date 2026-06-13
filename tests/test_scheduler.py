"""Scheduler — direct / dag / react / repair-loop / research-loop"""
from agent.core.scheduler import (scheduler_dispatch, select_next_dag,
                                  update_node, all_done, mark_failed)


def _make_dag():
    return {
        "id": "root", "goal": "test",
        "nodes": {
            "n0": {"id": "n0", "desc": "step1", "status": "pending", "deps": [], "cmd": "echo a"},
            "n1": {"id": "n1", "desc": "step2", "status": "pending", "deps": ["n0"], "cmd": "echo b"},
        },
        "edges": ["n0->n1"],
    }


def test_direct_returns_unscoped():
    r = scheduler_dispatch("direct", _make_dag(), {})
    assert r["scoped"] is False
    assert r["next_node"] is None


def test_dag_selects_first_and_returns_none_when_done():
    tg = _make_dag()
    r = scheduler_dispatch("dag", tg, {})
    assert r["scoped"] is True
    assert r["next_node"]["id"] == "n0"
    for nid in tg["nodes"]:
        tg["nodes"][nid]["status"] = "completed"
    r = scheduler_dispatch("dag", tg, {})
    assert r["next_node"] is None


def test_react_not_scoped():
    r = scheduler_dispatch("react", _make_dag(), {})
    assert r["scoped"] is False


def test_repair_loop_after_5_attempts_unscoped():
    tg = _make_dag()
    r = scheduler_dispatch("repair-loop", tg, {"pending_fixes": [{}, {}, {}, {}, {}]})
    assert r["scoped"] is False


def test_research_loop_hints_max_depth():
    r = scheduler_dispatch("research-loop", _make_dag(), {"current_step": 12})
    assert "最大研究深度" in r["hint"]


def test_dag_ops_mark_failed_blocks_deps():
    tg = _make_dag()
    tg, blocked = mark_failed(tg, "n0")
    assert blocked is True
    assert tg["nodes"]["n0"]["status"] == "failed"
    assert tg["nodes"]["n1"]["status"] == "blocked"
    assert all_done(tg) is True
