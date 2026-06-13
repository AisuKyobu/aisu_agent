"""Execution Intent — parse + resolve 核心路径"""
from agent.core.execution_intent import parse_intent, resolve_intent


def test_parse_valid_json():
    raw = '{"execution_mode":"dag","verifier_level":"L1+L2","risk_level":"high"}'
    intent = parse_intent(raw)
    assert intent["execution_mode"] == "dag"
    assert intent["verifier_level"] == "L1+L2"


def test_parse_invalid_falls_back_to_defaults():
    intent = parse_intent("not json at all")
    assert intent["execution_mode"] == "react"
    assert intent["verifier_level"] == "L1"
    assert intent["task_type"] == "reasoning"
    # resolve should work even from fallback
    r = resolve_intent(intent)
    assert "task_constraints" in r
    assert r["max_steps"] > 0
