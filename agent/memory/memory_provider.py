"""MemoryProvider — 可插拔记忆后端的抽象基类。

内置实现: MemoryStore（SQLite episodic + semantic + reflective）。
外部扩展: 通过实现此 ABC 接入向量数据库等外部记忆系统。
"""

from abc import ABC, abstractmethod
from typing import Any, List


class MemoryProvider(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def initialize(self, **kwargs) -> None:
        pass

    @abstractmethod
    def prefetch(self, query: str, **kwargs) -> str:
        pass

    @abstractmethod
    def sync_turn(self, user_content: str, assistant_content: str, **kwargs) -> None:
        pass

    def save_episode(self, goal: str, steps: list, errors: list, outcome: str, summary: str = "") -> None:
        pass

    def search_similar(self, goal: str, k: int = 3) -> list:
        return []

    def remember_value(self, key: str, value: str, source: str = "") -> None:
        pass

    def search_semantic(self, query: str) -> str:
        return ""

    def get_reflections(self) -> str:
        return ""

    def shutdown(self) -> None:
        pass
