"""Очередь фактов + rate-limit + retry + delay (раздел 2 и 7).

Стоп-условия: факт не обрабатывается дважды, ограничение глубины, лимит фактов на аудит.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from ..modules.base import Fact


@dataclass
class FactQueue:
    max_depth: int
    max_facts: int
    _queue: deque[Fact] = field(default_factory=deque)
    _seen: set[tuple[str, str]] = field(default_factory=set)
    dropped: list[tuple[Fact, str]] = field(default_factory=list)

    @staticmethod
    def key(fact: Fact) -> tuple[str, str]:
        return fact.type, fact.value.strip().lower()

    def push(self, fact: Fact) -> bool:
        k = self.key(fact)
        if k in self._seen:
            return False
        if fact.depth > self.max_depth:
            self.dropped.append((fact, "превышена глубина"))
            return False
        if len(self._seen) >= self.max_facts:
            self.dropped.append((fact, "достигнут лимит фактов на аудит"))
            return False
        self._seen.add(k)
        self._queue.append(fact)
        return True

    def pop(self) -> Optional[Fact]:
        return self._queue.popleft() if self._queue else None

    def __len__(self) -> int:
        return len(self._queue)


class RateLimiter:
    """Минимальный интервал между вызовами одного источника."""

    def __init__(self, delay: float):
        self.delay = delay
        self._last: dict[str, float] = {}

    async def wait(self, key: str) -> None:
        last = self._last.get(key)
        if last is not None:
            pause = self.delay - (time.monotonic() - last)
            if pause > 0:
                await asyncio.sleep(pause)
        self._last[key] = time.monotonic()


async def with_retry(fn: Callable[[], Awaitable], retries: int, base_delay: float,
                     on_retry: Optional[Callable[[int, Exception], None]] = None):
    attempt = 0
    while True:
        try:
            return await fn()
        except Exception as e:  # noqa: BLE001
            if attempt >= retries or getattr(e, "retry", True) is False:
                raise
            attempt += 1
            if on_retry:
                on_retry(attempt, e)
            await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
