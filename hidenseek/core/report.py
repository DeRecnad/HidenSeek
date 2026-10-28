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
    last = latest_diff(audit)
    change_of = {}
    if last:
        for kind in ("new", "gone", "changed"):
            for fid in last[kind]:
                change_of[fid] = kind
    items = []
    for f in audit.findings:
        exps = by_finding.get(f.id, [])
        whats = {e.what for e in exps}
        if f.active:
            counter = review_places if f.status == "review" else confirmed_places
            for w in whats:
                counter[w] += 1
        severity = max((e.severity for e in exps), default=0) if f.active else 0
        recs = recommendations(f, whats) if f.active else []
        if f.resolved_at and f.active:
            recs.insert(0, "Вы отметили это как закрытое. Следующий аудит покажет, исчезло ли оно на самом деле.")
        items.append({
            "finding": f.model_dump(mode="json"),
            "exposures": [e.model_dump(mode="json") for e in exps],
            "severity": severity,
            "severity_label": SEVERITY_LABEL[severity],
            "recommendations": recs,
            "change": change_of.get(f.id),
            "gone": f.gone_at is not None,
            "resolved": f.resolved_at is not None,
        })
    items.sort(key=lambda i: (i["gone"], -i["severity"], i["resolved"], i["finding"]["status"] != "review",
                              i["finding"]["source"]))

    parts = []
    for what in ("password", "breach", "real_name", "city", "email", "phone", "account", "username", "subdomain"):
        n = confirmed_places.get(what, 0)
        if n:
            parts.append(f"{WHAT_LABEL[what]} — в {n}")
    summary = ("Видно: " + "; ".join(parts) + ".") if parts else "Подтверждённых раскрытий пока нет."
    pending = sum(1 for f in audit.findings if f.status == "review" and f.active)
    if pending:
        summary += f" Ещё {pending} находок ждут проверки «мой / не мой»."
    actionable = [i for i in items if i["severity"] > 0]
    resolved = sum(1 for i in actionable if i["resolved"])
    if resolved:
        summary += f" Закрыто вами: {resolved} из {len(actionable)}."
    if last:
        summary += (f" С прошлого аудита: новых {len(last['new'])}, исчезло {len(last['gone'])}, "
                    f"изменилось {len(last['changed'])}.")

    return {
        "audit_id": audit.id,
        "summary": summary,
        "counts": {"confirmed": dict(confirmed_places), "review": dict(review_places)},
        "totals": {
            "findings": sum(1 for f in audit.findings if f.gone_at is None),
            "all_findings": len(audit.findings),
            "gone": sum(1 for f in audit.findings if f.gone_at is not None),
            "exposures": len(audit.exposures),
            "review": pending,
            "actionable": len(actionable),
            "resolved": resolved,
            "identities_verified": sum(1 for i in audit.identities if audit.is_verified(i, ttl)),
            "identities": len(audit.identities),
            "runs": len(audit.runs),
        },
        "max_severity": max((i["severity"] for i in items), default=0),
        "conflicts": city_conflicts(audit),
        "diff": last,
        "items": items,
    }


def latest_diff(audit: Audit) -> dict | None:
    """Изменения последнего завершённого запуска относительно предыдущего."""
    done = [r for r in audit.runs if r.finished_at and r.n > 1]
    if not done:
        return None
    r = done[-1]
    out: dict = {"run": r.n, "at": r.finished_at.isoformat(), "new": [], "gone": [], "changed": []}
    for h in audit.history:
        if h.run == r.n and h.finding_id not in out[h.change]:
            out[h.change].append(h.finding_id)
    return out
