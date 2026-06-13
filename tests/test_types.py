"""Types — TaskType 约束覆盖"""
from agent.types import TaskType, TASK_CONSTRAINTS


def test_all_task_types_have_constraints():
    for tt in TaskType:
        assert tt in TASK_CONSTRAINTS, f"{tt} missing"
        assert len(TASK_CONSTRAINTS[tt]) > 10
