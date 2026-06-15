"""MemoryManager — 编排记忆 Provider。

管理内置 MemoryStore + 至多一个外部 Provider。
每轮执行完整的 prefetch → sync 循环。
后台写入使用 ThreadPoolExecutor，防止外部 Provider 的延迟阻塞主循环。
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from agent.memory.memory_provider import MemoryProvider

logger = logging.getLogger("aisu.memory.manager")


class MemoryManager:
    def __init__(self):
        self._providers: List[MemoryProvider] = []
        self._has_external = False
        self._executor: Optional[ThreadPoolExecutor] = None
        self._executor_lock = threading.Lock()

    @property
    def builtin(self) -> Optional[MemoryProvider]:
        for p in self._providers:
            if p.name == "builtin":
                return p
        return None

    def ensure_builtin(self, profile: str = "dev") -> MemoryProvider:
        existing = self.builtin
        if existing and getattr(existing, "_profile", None) == profile:
            return existing
        if existing and getattr(existing, "_profile", None) != profile:
            existing.shutdown()
            self._providers = [p for p in self._providers if p is not existing]
            logger.info("Switched memory profile: %s → %s", getattr(existing, "_profile", "?"), profile)
        from agent.memory.store import MemoryStore
        store = MemoryStore()
        store.initialize(profile=profile)
        self.add_provider(store)
        return store

    def add_provider(self, provider: MemoryProvider) -> None:
        if provider.name != "builtin":
            if self._has_external:
                logger.warning("Rejected external memory provider '%s': only one allowed", provider.name)
                return
            self._has_external = True
        self._providers.append(provider)
        logger.info("Memory provider '%s' registered", provider.name)

    def initialize_all(self, profile: str = "dev", **kwargs) -> None:
        self.ensure_builtin(profile=profile)
        for p in self._providers:
            try:
                if not getattr(p, "_initialized", False):
                    p.initialize(profile=profile, **kwargs)
            except Exception as e:
                logger.warning("Memory provider '%s' init failed: %s", p.name, e)

    def prefetch_all(self, query: str, **kwargs) -> str:
        parts = []
        for p in self._providers:
            try:
                result = p.prefetch(query, **kwargs)
                if result and result.strip():
                    parts.append(result)
            except Exception as e:
                logger.debug("Memory provider '%s' prefetch failed: %s", p.name, e)
        return "\n\n".join(parts)

    def sync_all(self, user_content: str, assistant_content: str) -> None:
        def _run():
            for p in self._providers:
                try:
                    p.sync_turn(user_content, assistant_content)
                except Exception as e:
                    logger.debug("Memory provider '%s' sync failed: %s", p.name, e)
        self._submit_background(_run)

    def save_episode(self, goal: str, steps: list, errors: list,
                     outcome: str, summary: str = "") -> None:
        for p in self._providers:
            try:
                p.save_episode(goal, steps, errors, outcome, summary)
            except Exception as e:
                logger.warning("Memory provider '%s' save_episode failed: %s", p.name, e)

    def search_similar(self, goal: str, k: int = 3) -> list:
        if self.builtin:
            return self.builtin.search_similar(goal, k)
        return []

    def remember(self, key: str, value: str, source: str = "", user_id: str = "guest") -> None:
        if self.builtin:
            self.builtin.remember_value(key, value, source, user_id)

    def search_semantic(self, query: str, user_id: str = "guest") -> str:
        if self.builtin:
            return self.builtin.search_semantic(query, user_id)
        return ""

    def get_reflections(self) -> str:
        if self.builtin:
            return self.builtin.get_reflections()
        return ""

    def maybe_reflect(self, force: bool = False) -> None:
        if self.builtin:
            self.builtin.maybe_reflect(force)

    def save_reflection(self, pattern: str, confidence: float = 0.15) -> None:
        if self.builtin:
            self.builtin.save_reflection(pattern, confidence)

    def _submit_background(self, fn):
        with self._executor_lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1)
        try:
            self._executor.submit(fn)
        except Exception:
            pass

    def shutdown(self):
        with self._executor_lock:
            if self._executor:
                self._executor.shutdown(wait=False)
                self._executor = None
        for p in self._providers:
            try:
                p.shutdown()
            except Exception:
                pass


_manager: Optional[MemoryManager] = None


def get_manager() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager()
    return _manager
