"""Интерфейс модуля: что принимает (input_type) + что отдаёт (outputs)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ..config import Settings


class ModuleError(Exception):
    """Ошибка источника. retry=False — повторять бессмысленно (нет ключа, 404 и т.п.)."""

    def __init__(self, message: str, retry: bool = True):
        super().__init__(message)
        self.retry = retry


@dataclass
class Fact:
    type: str
    value: str
    identity_id: str
    depth: int = 0


@dataclass
class RawFinding:
    type: str
    value: str
    url: Optional[str] = None
    confidence: float = 1.0
    review: bool = False  # «проверьте вручную: ваш ли это аккаунт?»
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class NewFact:
    """Новый факт для очереди. Попадает туда, только если наследует подтверждение."""
    type: str
    value: str
    inherits: bool = False
    reason: str = ""


@dataclass
class ModuleResult:
    findings: list[RawFinding] = field(default_factory=list)
    new_facts: list[NewFact] = field(default_factory=list)
    note: str = ""


@dataclass
class RunContext:
    settings: Settings
    client: httpx.AsyncClient


class Module:
    name: str = ""
    title: str = ""
    input_type: str = ""
    outputs: tuple[str, ...] = ()
    description: str = ""
    warning: str = ""

    def available(self, settings: Settings) -> tuple[bool, str]:
        return True, ""

    async def run(self, fact: Fact, ctx: RunContext) -> ModuleResult:  # pragma: no cover - интерфейс
        raise NotImplementedError

    def info(self, settings: Settings) -> dict[str, Any]:
        ok, reason = self.available(settings)
        return {
            "name": self.name, "title": self.title, "input_type": self.input_type,
            "outputs": list(self.outputs), "description": self.description,
            "warning": self.warning, "available": ok, "unavailable_reason": reason,
        }


def expect_json(resp: httpx.Response, kind: type) -> Any:
    """Проверка формата ответа, а не только кода 200."""
    if resp.status_code == 429 or resp.status_code >= 500:
        raise ModuleError(f"HTTP {resp.status_code}: источник временно недоступен")
    if resp.status_code != 200:
        raise ModuleError(f"HTTP {resp.status_code}", retry=False)
    try:
        data = resp.json()
    except ValueError as e:
        raise ModuleError("ответ не JSON — формат источника изменился?") from e
    if not isinstance(data, kind):
        raise ModuleError(f"неожиданный формат ответа: ожидался {kind.__name__}")
    return data
