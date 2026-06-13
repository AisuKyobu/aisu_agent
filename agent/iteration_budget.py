"""线程安全的迭代预算计数器。

每个 Agent（父或子）持有独立的 IterationBudget。
父级上限 90，子级上限 50（可配置）。
execute_code 的编程化工具调用通过 refund() 不计入预算。
"""

import threading


class IterationBudget:
    def __init__(self, max_total: int = 90):
        self.max_total = max_total
        self._used = 0
        self._lock = threading.Lock()

    def consume(self) -> bool:
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        with self._lock:
            if self._used > 0:
                self._used -= 1

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.max_total - self._used)
