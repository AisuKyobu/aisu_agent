from typing import Annotated, Any, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[List[Any], add_messages]
    summary: str
    plan: List[str]
    task_graph: Optional[dict]
    verification_log: List[dict]
    pending_fixes: List[dict]
    needs_human: bool
    current_step: int
    max_steps: int
    last_result: str
    loaded_skills: List[str]
    thread_id: str
    task_type: str
    task_constraints: str
    missing_params: List[str]
    # ── Analyzer v2 新增 ──
    execution_intent: dict
    execution_mode: str
    verifier_level: str
    retry_per_step: int
    action_history: List[dict]
    retrieved_memory: dict
    profile: str
