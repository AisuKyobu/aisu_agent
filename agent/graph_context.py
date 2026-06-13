"""GraphContext — 共享所有节点可用的 LLM 实例、工具集和配置"""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from agent.workspace import Workspace


@dataclass
class GraphContext:
    llm: BaseChatModel                       # 无工具绑定
    llm_search: BaseChatModel                # web_search/web_fetch
    llm_action: BaseChatModel                # 文件/命令/浏览器/计划
    llm_reasoning: BaseChatModel             # 搜索/文件/命令
    llm_planning: BaseChatModel              # 计划+搜索+文件
    llm_with_tools: BaseChatModel            # 全工具
    workspace: Workspace
    system_prompt: str = ""
