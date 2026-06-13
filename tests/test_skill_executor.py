"""Skill Executor — parse + expand"""
from agent.skills.executor import parse_skill_statemachine, expand_to_taskgraph


def test_parse_skill_statemachine():
    content = """# Test Skill
```skill
{"name":"test-skill","nodes":[{"id":"s1","cmd":"echo hello"}]}
```
"""
    sm = parse_skill_statemachine(content)
    assert sm is not None
    assert sm["name"] == "test-skill"
    # no-definition returns None
    assert parse_skill_statemachine("# just markdown") is None
    # invalid JSON returns None
    assert parse_skill_statemachine("```skill\nnot json\n```") is None


def test_expand_to_taskgraph():
    sm = {"name": "test", "nodes": [
        {"id": "s1", "cmd": "python {file}"},
        {"id": "s2", "cmd": "python verify.py", "depends_on": ["s1"]},
    ]}
    tg = expand_to_taskgraph(sm, {"file": "thesis.md"})
    assert len(tg["nodes"]) == 2
    assert "thesis.md" in tg["nodes"]["s1"]["cmd"]
    assert tg["nodes"]["s2"]["deps"] == ["s1"]
    assert "s1->s2" in tg["edges"]
