"""Учебный режим: синтетические персонажи + мок-источники (раздел 12).

Все данные выдуманы: домены из зарезервированных зон .example / example.com,
названия утечек и сайтов — демонстрационные. Реальных запросов нет.
"""
from __future__ import annotations

import asyncio

from ..core.models import Audit, Identity, IdentityType, OwnerProfile, utcnow
from ..modules.base import Fact, Module, ModuleError, ModuleResult, NewFact, RawFinding, RunContext
from ..modules.maigret_mod import username_confidence

PERSONAS = {
    "alice": {
        "title": "Алиса Тестова",
        "description": "Разработчица: GitHub, свой домен, пара забытых аккаунтов и одна утечка с паролем.",
        "profile": {"full_name": "Алиса Тестова", "city": "Новосибирск", "phones": ["+7 900 000-00-00"]},
        "identities": [
            ("email", "alice.testova@example.com", "demo", None),
            ("github", "alice-testova-demo", "demo", None),
            ("username", "alice-testova-demo", "inherited", "github"),
            ("domain", "alice-testova.example", "demo", None),
            ("username", "persik", "domain_link", "domain"),
            ("email", "a.testova@work.example", None, None),  # не подтверждён — модули его не запускают
        ],
    },
    "boris": {
        "title": "Борис Примеров",
        "description": "Минимальный след: одна почта, всё закрыто. Показывает «чистый» отчёт.",
        "profile": {"full_name": "Борис Примеров", "city": "Казань", "phones": []},
        "identities": [("email", "boris.primerov@example.org", "demo", None)],
    },
}

_GH = "alice-testova-demo"

DATA: dict[tuple[str, str], ModuleResult] = {
    ("github", _GH): ModuleResult(
        findings=[
            RawFinding("profile_fields", f"github.com/{_GH}", f"https://github.example/{_GH}", 1.0, data={"fields": {
                "name": "Alice Testova", "location": "Novosibirsk, Russia",
                "blog": "https://alice-testova.example", "bio": "Backend, Python, котики",
                "email": "alice.testova@example.com"}}),
            RawFinding("public_email_in_commits", "alisa.t@example.net", f"https://github.example/{_GH}/notes/commit/1",
                       1.0, data={"email": "alisa.t@example.net", "commits": 37, "repos": [f"{_GH}/notes", f"{_GH}/dotfiles"],
                                  "author_names": ["Алиса Тестова"]}),
        ],
        new_facts=[NewFact("email", "alisa.t@example.net", inherits=True,
                           reason="адрес привязан к подтверждённому GitHub-аккаунту")],
    ),
    ("crtsh", "alice-testova.example"): ModuleResult(findings=[
        RawFinding("subdomain", "blog.alice-testova.example", None, 1.0, data={"first_seen": "2021-03-02"}),
        RawFinding("subdomain", "dev.alice-testova.example", None, 1.0, data={"first_seen": "2022-07-19"}),
        RawFinding("subdomain", "old-admin.alice-testova.example", None, 1.0, data={"first_seen": "2019-11-05"}),
        RawFinding("certificate", "14 сертификатов для alice-testova.example", None, 1.0, data={"count": 14}),
    ]),
    ("maigret", _GH): ModuleResult(findings=[
        RawFinding("profile_url", f"{site}: {_GH}", f"https://{dom}/{_GH}", username_confidence(_GH), review=True,
                   data={"site": site}) for site, dom in
        [("DemoDev", "demodev.example"), ("CodePen-demo", "codepen.example"), ("Habr-demo", "habr.example")]
    ]),
    ("maigret", "persik"): ModuleResult(findings=[
        RawFinding("profile_url", f"{site}: persik", f"https://{dom}/persik", username_confidence("persik"), review=True,
                   data={"site": site}) for site, dom in
        [("PhotoSite-demo", "photos.example"), ("GameForum-demo", "games.example"), ("Recipes-demo", "recipes.example"),
         ("Music-demo", "music.example"), ("Dating-demo", "dating.example")]
    ]),
    ("holehe", "alice.testova@example.com"): ModuleResult(findings=[
        RawFinding("registered_service", s, f"https://{s}", 0.95, data={"service": s.split(".")[0]})
        for s in ("music-stream.example", "blogs.example", "oldsocial.example", "fitness.example")
    ]),
    ("holehe", "alisa.t@example.net"): ModuleResult(findings=[
        RawFinding("registered_service", "photohost.example", "https://photohost.example", 0.95, data={"service": "photohost"}),
    ]),
    ("hibp", "alice.testova@example.com"): ModuleResult(findings=[
        RawFinding("breach", "DemoShop (2019)", None, 1.0, data={
            "name": "DemoShop", "breach_date": "2019-04-11",
            "data_classes": ["Email addresses", "Passwords", "Names"]}),
        RawFinding("breach", "DemoForum (2021)", None, 1.0, data={
            "name": "DemoForum", "breach_date": "2021-09-30",
            "data_classes": ["Email addresses", "Usernames", "Phone numbers"]}),
    ]),
    ("hibp", "boris.primerov@example.org"): ModuleResult(note="в известных утечках адрес не найден"),
}

# Один источник «падает» на первой попытке — чтобы показать retry.
FLAKY_ONCE = {("crtsh", "alice-testova.example")}

# Повторный запуск возвращает немного другое — чтобы показать сравнение аудитов (diff):
# старый аккаунт удалён (исчез), появился новый сервис, один сайт с ником закрылся.
RERUN: dict[tuple[str, str], ModuleResult] = {
    ("holehe", "alice.testova@example.com"): ModuleResult(findings=[
        RawFinding("registered_service", s, f"https://{s}", 0.95, data={"service": s.split(".")[0]})
        for s in ("music-stream.example", "blogs.example", "fitness.example", "newsletter.example")
    ]),
    ("maigret", "persik"): ModuleResult(findings=[
        f for f in DATA[("maigret", "persik")].findings if not f.value.startswith("Dating-demo")
    ]),
}

# Что видно на страницах, если вы отметите аккаунт «мой» (разбор только ваших страниц).
OWN_PAGES = {
    f"https://demodev.example/{_GH}": {"name": "Alice Testova", "location": "Novosibirsk", "bio": "Python, котики"},
    f"https://habr.example/{_GH}": {"name": "Алиса Т.", "bio": "Пишу про бэкенд"},
    "https://photos.example/persik": {"location": "Москва"},
}


class MockModule(Module):
    def __init__(self, real: Module, delay: float = 0.35):
        self.real = real
        self.name, self.title, self.input_type = real.name, real.title + " (мок)", real.input_type
        self.outputs, self.description, self.warning = real.outputs, real.description, ""
        self.delay = delay
        self._failed: set[tuple[str, str]] = set()
        self._calls: dict[tuple[str, str], int] = {}

    def available(self, settings) -> tuple[bool, str]:
        return True, ""

    async def run(self, fact: Fact, ctx: RunContext) -> ModuleResult:
        await asyncio.sleep(self.delay)
        key = (self.name, fact.value)
        if key in FLAKY_ONCE and key not in self._failed:
            self._failed.add(key)
            raise ModuleError("HTTP 503: источник временно недоступен (демо-сбой)")
        n = self._calls[(fact.identity_id, fact.value)] = self._calls.get((fact.identity_id, fact.value), 0) + 1
        res = RERUN.get(key) if n > 1 and key in RERUN else DATA.get(key)
        if res is None:
            return ModuleResult(note="ничего не найдено (демо)")
        return ModuleResult(findings=list(res.findings), new_facts=list(res.new_facts), note=res.note)


def demo_enricher():
    from ..modules.own_profile import DemoEnricher

    return DemoEnricher(OWN_PAGES)


def mock_registry(real: dict[str, Module], delay: float = 0.35) -> dict[str, Module]:
    return {name: MockModule(m, delay) for name, m in real.items()}


def build_demo_audit(persona: str) -> Audit:
    p = PERSONAS.get(persona)
    if not p:
        raise KeyError(persona)
    audit = Audit(mode="demo", persona=persona, owner_profile=OwnerProfile(**p["profile"]))
    by_type: dict[str, Identity] = {}
    for type_, value, how, parent_type in p["identities"]:
        ident = Identity(type=IdentityType(type_), value=value)
        if how:
            parent = by_type.get(parent_type) if parent_type else None
            ident.verified_at = utcnow()
            ident.parent_id = parent.id if parent else None
            ident.verified_by = {"inherited": f"inherited:{parent.id}" if parent else "demo",
                                 "domain_link": f"domain_link:{parent.id}" if parent else "demo"}.get(how, "demo")
        audit.identities.append(ident)
        by_type.setdefault(type_, ident)
    audit.add_log("INFO", f"DEMO AUDIT ....... {p['title']} — синтетические данные, сеть не используется")
    return audit
