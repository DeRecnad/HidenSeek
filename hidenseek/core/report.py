"""Отчёт и рекомендации (раздел 8)."""
from __future__ import annotations

from collections import Counter

from ..config import Settings
from .matcher import city_conflicts
from .models import Audit, Finding

WHAT_LABEL = {
    "password": "пароль в утечке",
    "breach": "утечка",
    "phone": "телефон",
    "real_name": "настоящее имя",
    "city": "город",
    "email": "почта",
    "account": "аккаунт на сервисе",
    "username": "занятый ник",
    "subdomain": "поддомен",
}

SEVERITY_LABEL = {4: "критично", 3: "высокая", 2: "средняя", 1: "низкая", 0: "инфо"}


def recommendations(f: Finding, whats: set[str]) -> list[str]:
    r: list[str] = []
    if f.type == "breach":
        if "password" in whats:
            r.append("Смените пароль на этом сервисе и везде, где он повторялся; включите двухфакторную аутентификацию.")
        else:
            r.append("Проверьте, какие данные утекли, и будьте осторожны с фишингом на этот адрес.")
        r.append("Используйте менеджер паролей и уникальный пароль для каждого сервиса.")
    elif f.type == "public_email_in_commits":
        r += [
            "Включите на GitHub «Keep my email addresses private» и «Block command line pushes that expose my email».",
            "Настройте git на noreply-адрес: git config --global user.email <id>+<login>@users.noreply.github.com",
            "Для старых коммитов: перепишите историю (git filter-repo --mailmap) или хотя бы добавьте .mailmap; "
            "учтите, что форки и клоны сохранят старые коммиты.",
        ]
    elif f.type == "profile_fields":
        if "real_name" in whats or "city" in whats:
            r.append("Уберите настоящее имя и/или город из публичного профиля GitHub (Settings → Public profile).")
        if "email" in whats:
            r.append("Скройте публичный email в профиле или замените его отдельным адресом для публикаций.")
    elif f.type == "registered_service":
        r.append("Если аккаунт больше не нужен — удалите его через настройки сервиса; если нужен — смените пароль и включите 2FA.")
    elif f.type == "profile_url":
        if f.status == "review":
            r.append("Проверьте вручную: ваш ли это аккаунт? Отметьте «мой / не мой».")
        r.append("Если аккаунт ваш и заброшен — удалите его или закройте профиль; уберите из него имя и город.")
    elif f.type in ("subdomain", "certificate"):
        r.append("Проверьте, что на поддомене нет забытых тестовых или админских сервисов; лишние DNS-записи удалите.")
    if ("real_name" in whats or "city" in whats) and f.type not in ("profile_fields",):
        r.append("В профиле видно имя или город — закройте профиль или уберите эти поля.")
    return r


def build(audit: Audit, settings: Settings) -> dict:
    ttl = settings.verify_ttl_days
    by_finding: dict[str, list] = {}
    for e in audit.exposures:
        by_finding.setdefault(e.finding_id, []).append(e)

    confirmed_places: Counter = Counter()
    review_places: Counter = Counter()
    items = []
    for f in audit.findings:
        exps = by_finding.get(f.id, [])
        whats = {e.what for e in exps}
        counter = review_places if f.status == "review" else confirmed_places
        if f.status != "not_mine":
            for w in whats:
                counter[w] += 1
        severity = max((e.severity for e in exps), default=0)
        items.append({
            "finding": f.model_dump(mode="json"),
            "exposures": [e.model_dump(mode="json") for e in exps],
            "severity": severity if f.status != "not_mine" else 0,
            "severity_label": SEVERITY_LABEL[severity if f.status != "not_mine" else 0],
            "recommendations": recommendations(f, whats) if f.status != "not_mine" else [],
        })
    items.sort(key=lambda i: (-i["severity"], i["finding"]["status"] != "review", i["finding"]["source"]))

    parts = []
    for what in ("password", "breach", "real_name", "city", "email", "phone", "account", "username", "subdomain"):
        n = confirmed_places.get(what, 0)
        if n:
            parts.append(f"{WHAT_LABEL[what]} — в {n}")
    summary = ("Видно: " + "; ".join(parts) + ".") if parts else "Подтверждённых раскрытий пока нет."
    pending = sum(1 for f in audit.findings if f.status == "review")
    if pending:
        summary += f" Ещё {pending} находок ждут проверки «мой / не мой»."

    return {
        "audit_id": audit.id,
        "summary": summary,
        "counts": {"confirmed": dict(confirmed_places), "review": dict(review_places)},
        "totals": {
            "findings": len(audit.findings),
            "exposures": len([e for e in audit.exposures]),
            "review": pending,
            "identities_verified": sum(1 for i in audit.identities if audit.is_verified(i, ttl)),
            "identities": len(audit.identities),
        },
        "max_severity": max((i["severity"] for i in items), default=0),
        "conflicts": city_conflicts(audit),
        "items": items,
    }
