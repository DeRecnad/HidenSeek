"""crt.sh: поддомены и сертификаты вашего домена из журналов Certificate Transparency."""
from __future__ import annotations

from .base import Fact, Module, ModuleResult, RawFinding, RunContext, expect_json


class CrtShModule(Module):
    name = "crtsh"
    title = "crt.sh"
    input_type = "domain"
    outputs = ("subdomain", "certificate")
    description = "Поддомены вашего домена, видимые в публичных журналах сертификатов."

    async def run(self, fact: Fact, ctx: RunContext) -> ModuleResult:
        domain = fact.value
        rows = expect_json(await ctx.client.get(
            "https://crt.sh/", params={"q": f"%.{domain}", "output": "json"}, timeout=40,
        ), list)
        subs: dict[str, dict] = {}
        certs = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            certs += 1
            for name in str(row.get("name_value", "")).splitlines():
                name = name.strip().lower().lstrip("*.")
                if not name or "@" in name or not (name == domain or name.endswith("." + domain)):
                    continue
                s = subs.setdefault(name, {"first_seen": row.get("not_before"), "issuer": row.get("issuer_name")})
                if row.get("not_before") and (not s["first_seen"] or row["not_before"] < s["first_seen"]):
                    s["first_seen"] = row["not_before"]
        res = ModuleResult()
        for name, s in sorted(subs.items()):
            if name == domain:
                continue
            res.findings.append(RawFinding(
                type="subdomain", value=name, url=f"https://crt.sh/?q={name}", confidence=1.0, data=s,
            ))
        res.findings.append(RawFinding(
            type="certificate", value=f"{certs} сертификатов для {domain}", url=f"https://crt.sh/?q=%25.{domain}",
            confidence=1.0, data={"count": certs},
        ))
        return res
