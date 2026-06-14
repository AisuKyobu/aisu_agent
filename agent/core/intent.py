"""Intent Classifier — 调用 LLM 分析用户消息，输出完整 ExecutionIntent"""

from langchain_core.messages import HumanMessage
from langchain_deepseek import ChatDeepSeek

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME
from agent.logger import NodeLogger

_log = NodeLogger("classifier")

_llm = ChatDeepSeek(model=MODEL_NAME, temperature=0, api_key=DEEPSEEK_API_KEY, api_base=DEEPSEEK_BASE_URL)


def classify(user_message: str) -> dict:
    """调用 LLM 分析用户消息，返回完整的 ExecutionIntent。"""
    from agent.core.execution_intent import ANALYZER_PROMPT_V2, parse_intent

    try:
        prompt = ANALYZER_PROMPT_V2.replace("{user_message}", user_message)
        response = _llm.invoke([HumanMessage(content=prompt)])
        return parse_intent(response.content.strip())
    except Exception:
        _log.warn(f"classify failed: {user_message[:100]}")
        return {
            "execution_mode": "react",
            "verifier_level": "L1",
            "verifier_frequency": "every_step",
            "autonomy_level": "full_auto",
            "horizon": "medium",
            "risk_level": "low",
            "task_type": "reasoning",
            "goal": "",
            "missing_params": [],
        }
