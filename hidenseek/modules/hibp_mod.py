"""HaveIBeenPwned: в каких утечках есть ваша почта (официальный API, нужен ключ)."""
from __future__ import annotations

from urllib.parse import quote

from ..config import Settings
from .base import Fact, Module, ModuleError, ModuleResult, RawFinding, RunContext, expect_json


class HibpModule(Module):
    name = "hibp"
    title = "HaveIBeenPwned"
    input_type = "email"
    outputs = ("breach",)
    description = "Утечки, в которых встречается ваш адрес, и какие данные в них были."

    def available(self, settings: Settings) -> tuple[bool, str]:
        if not settings.hibp_api_key:
            return False, "нет HIBP_API_KEY в .env (ключ платный)"
        return True, ""

    async def run(self, fact: Fact, ctx: RunContext) -> ModuleResult:
        resp = await ctx.client.get(
            f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote(fact.value)}",
            params={"truncateResponse": "false"},
            headers={"hibp-api-key": ctx.settings.hibp_api_key, "user-agent": ctx.settings.user_agent},
        )
        if resp.status_code == 404:
            return ModuleResult(note="в известных утечках адрес не найден")
        if resp.status_code == 401:
            raise ModuleError("HIBP отклонил ключ (401)", retry=False)
        breaches = expect_json(resp, list)
        res = ModuleResult()
        for b in breaches:
            if not isinstance(b, dict) or not b.get("Name"):
                raise ModuleError("неожиданный формат записи об утечке")
            res.findings.append(RawFinding(
                type="breach", value=b.get("Title") or b["Name"],
                url=f"https://haveibeenpwned.com/PwnedWebsites#{b['Name']}", confidence=1.0,
                data={"name": b["Name"], "domain": b.get("Domain"), "breach_date": b.get("BreachDate"),
                      "data_classes": b.get("DataClasses") or [], "verified": b.get("IsVerified")},
            ))
        return res
