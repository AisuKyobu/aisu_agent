"""长期记忆工具 — 仅使用 SQLite 存储，通过 agent/memory/store.py 访问"""
import re

from langchain.tools import tool

from tools.tool_registry import registry


# 不做索引的常见词
_SKIP_WORDS = {"用户的", "网络", "没有", "什么", "一个", "这个", "那个", "可以", "需要",
               "知道", "就是", "不是", "因为", "所以", "如果", "但是", "而且", "或者"}


def _extract_keywords(text: str) -> list[str]:
    """从文本中提取 2 字以上的中文/英文词，去停用词去重。"""
    words = set()
    for m in re.finditer(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text):
        w = m.group().lower()
        if w not in _SKIP_WORDS:
            words.add(w)
    return list(words)


@tool
def remember(key: str, value: str) -> str:
    """主动记住一条重要信息。key是分类标签（如'偏好'、'事实'、'决策'），value是具体内容。"""
    try:
        from agent.memory.manager import get_manager as get_memory_manager
        mgr = get_memory_manager()
        mgr.remember(key, value, source="agent")
        for word in _extract_keywords(value):
            if word != key:
                mgr.remember(word, f"{key}: {value}", source="agent:index")
    except Exception:
        pass
    return f"已记住: [{key}] {value}"


@tool
def memory_search(query: str) -> str:
    """搜索长期记忆中的信息。query是搜索关键词。"""
    try:
        from agent.memory.manager import get_manager as get_memory_manager
        result = get_memory_manager().search_semantic(query)
        if result != "未找到匹配的记忆":
            return result
    except Exception:
        pass
    return "未找到匹配的记忆"


registry.register(name="remember", toolset="memory", handler=remember.func,
                  description="主动记住一条重要信息，key是分类标签，value是具体内容")
registry.register(name="memory_search", toolset="memory", handler=memory_search.func,
                  description="搜索长期记忆中的信息")
