"""Holehe: на каких сервисах зарегистрирована ваша почта (забытые аккаунты)."""
from __future__ import annotations

from types import SimpleNamespace

from ..config import Settings
from .base import Fact, Module, ModuleError, ModuleResult, RawFinding, RunContext


class HoleheModule(Module):
    name = "holehe"
    title = "Holehe"
    input_type = "email"
    outputs = ("registered_service",)
    description = "Проверяет регистрацию вашего адреса на ~120 сервисах."
    warning = ("Holehe обращается к формам регистрации и входа сервисов — это серая зона их правил. "
               "Модули через восстановление пароля отключены, но отдельные сервисы всё равно могут "
               "прислать вам уведомление о попытке входа.")

    def available(self, settings: Settings) -> tuple[bool, str]:
        try:
            import holehe  # noqa: F401
        except ImportError:
            return False, "не установлен: pip install -r requirements-sources.txt"
        return True, ""

    async def run(self, fact: Fact, ctx: RunContext) -> ModuleResult:
        try:
            from holehe.core import get_functions, import_submodules
        except ImportError as e:
            raise ModuleError(f"holehe недоступен: {e}", retry=False) from e
        import httpx

        modules = import_submodules("holehe.modules")
        # nopasswordrecovery: не трогаем модули, которые идут через «забыли пароль» (шлют письма)
        websites = get_functions(modules, SimpleNamespace(nopasswordrecovery=True))
        out: list[dict] = []
        async with httpx.AsyncClient(timeout=10) as client:
            for site in websites:
                try:
                    await site(fact.value, client, out)
                except Exception:  # noqa: BLE001 — сбой одного сервиса не роняет модуль
                    continue
        res = ModuleResult()
        limited = 0
        for item in out:
            if item.get("rateLimit"):
                limited += 1
                continue
            if item.get("exists") is True:
                extra = {k: item.get(k) for k in ("emailrecovery", "phoneNumber", "others") if item.get(k)}
                res.findings.append(RawFinding(
                    type="registered_service", value=item.get("domain") or item.get("name", "?"),
                    url=f"https://{item['domain']}" if item.get("domain") else None,
                    confidence=0.95, data={"service": item.get("name"), **extra},
                ))
        if limited:
            res.note = f"{limited} сервисов ограничили запросы — повторите позже"
        return res
