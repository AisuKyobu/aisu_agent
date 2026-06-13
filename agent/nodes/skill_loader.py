"""Skill Loader node — 追踪技能加载 + 状态机 skill → Sub-Agent"""
from langchain_core.messages import AIMessage

from agent.logger import NodeLogger
from agent.skills.registry import get_registry as get_skill_registry
from agent.skills.executor import (expand_to_taskgraph, get_cached_skill_result,
                                     parse_skill_statemachine, set_cached_skill_result)
from agent.state import AgentState


def skill_loader_node(state: AgentState, ctx=None) -> dict:
    _log = NodeLogger("skill_loader")
    _log.bind(state.get("thread_id", ""), state.get("current_step", 0))
    loaded = set(state.get("loaded_skills", []))
    for msg in state["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name == "load_skill":
                    args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                    skill_name = args.get("skill_name", "")
                    if skill_name:
                        loaded.add(skill_name)
    updates: dict = {"loaded_skills": sorted(loaded)}
    new_skills = loaded - set(state.get("loaded_skills", []))
    if not new_skills:
        return updates

    for name in new_skills:
        skill = get_skill_registry().get(name)
        if not skill: continue
        sm = parse_skill_statemachine(skill.content)
        if not sm: continue

        _log.step_start(f"load skill: {name} (state machine detected)")

        skill_params = {}
        for msg in state["messages"]:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                    if tc_name == "load_skill":
                        tc_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                        if tc_args.get("skill_name") == name:
                            skill_params = {k: v for k, v in tc_args.items() if k != "skill_name"}

        cached = get_cached_skill_result(name, skill_params)
        if cached:
            updates["skill_result"] = cached
            _log.step_done(f"cached: {name}")
            break

        try:
            from agent.conversation_graph import _spawn_skill_sub
            sub_result = _spawn_skill_sub(name, sm, skill_params)
            set_cached_skill_result(name, skill_params, sub_result)
            updates.setdefault("sub_agent_results", {}).update({sub_result["thread_id"]: sub_result})
            if sub_result["status"] == "completed":
                _log.step_done(f"sub-agent: {name} completed")
                summary = f"技能 {name} 执行完成 ({sub_result['output'].get('nodes_completed', '?')})"
                updates["messages"] = [AIMessage(content=summary)]
            else:
                _log.warn(f"sub-agent: {name} FAILED")
        except Exception:
            _log.warn(f"sub-agent spawn failed for skill {name}, falling back to DAG expand")
            tg = expand_to_taskgraph(sm, skill_params)
            if tg:
                updates["task_graph"] = tg
                _log.step_done(f"DAG expanded: {len(tg.get('nodes',{}))} nodes")
                from tools.plan_tools import load_plan, save_plan
                plan_data = load_plan()
                plan_data["task_graph"] = tg
                save_plan(plan_data)
        break

    return updates
