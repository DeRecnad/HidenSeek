"""Сверка находок с профилем «это я» (раздел 5) → exposures.

ФИО, город и телефоны — не стартовая точка, а эталон: если в профиле, найденном по
подтверждённому идентификатору, видно ваше настоящее имя или город — это exposure.
Confidence = «насколько вероятно, что это ваш аккаунт», а не «тот ли это человек».
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from ..config import Settings
from .models import Audit, Exposure, Finding
from .normalizer import latin_key, name_tokens, phone_e164

# Severity: утечка с паролем > телефон / утечка > настоящее имя + город > имя / город / почта > занятый ник
SEVERITY = {
    "password": 4,
    "breach": 3,
    "phone": 3,
    "real_name": 2,
    "city": 2,
    "email": 2,
    "account": 1,
    "username": 1,
    "subdomain": 1,
}
NAME_AND_CITY_BUMP = 3

PHONE_RE = re.compile(r"\+?\d[\d\s()\-]{8,}\d")


def _texts(data: Any) -> Iterable[str]:
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for v in data.values():
            yield from _texts(v)
    elif isinstance(data, (list, tuple, set)):
        for v in data:
            yield from _texts(v)


def name_matches(owner_name: str, candidate: str) -> bool:
    owner = [t for t in name_tokens(owner_name) if len(t) > 1]
    cand = set(name_tokens(candidate))
    if not owner or not cand:
        return False
    hits = sum(1 for t in owner if t in cand)
    return hits >= min(2, len(owner))


def city_matches(owner_city: str, text: str) -> bool:
    c = latin_key(owner_city)
    return bool(c) and c in latin_key(text)


def _profile_fields(f: Finding) -> dict[str, str]:
    fields = f.data.get("fields") or {}
    return {k: str(v) for k, v in fields.items() if v}


def exposures_for(f: Finding, audit: Audit) -> list[Exposure]:
    prof = audit.owner_profile
    out: dict[str, Exposure] = {}

    def add(what: str, detail: str) -> None:
        out.setdefault(what, Exposure(finding_id=f.id, what=what, severity=SEVERITY[what], detail=detail))

    if f.type == "breach":
        classes = [c.lower() for c in f.data.get("data_classes", [])]
        if "passwords" in classes:
            add("password", "в утечке были пароли")
        else:
            add("breach", "адрес есть в утечке: " + ", ".join(f.data.get("data_classes", [])[:6]))
        if "phone numbers" in classes:
            add("phone", "в утечке были телефоны")
    elif f.type == "public_email_in_commits":
        add("email", f"адрес виден в {f.data.get('commits', '?')} публичных коммитах")
        for n in f.data.get("author_names", []):
            if prof.full_name and name_matches(prof.full_name, n):
                add("real_name", f"имя автора коммитов: {n}")
    elif f.type == "registered_service":
        add("account", "аккаунт на сервисе зарегистрирован на вашу почту")
    elif f.type == "profile_url":
        add("username", "ник занят на сайте")
    elif f.type == "subdomain":
        add("subdomain", "поддомен виден в журналах сертификатов")

    fields = _profile_fields(f)
    name = fields.get("name", "")
    if name:
        if prof.full_name and name_matches(prof.full_name, name):
            add("real_name", f"в профиле указано имя: {name}")
        elif not prof.full_name:
            add("real_name", f"в профиле указано имя «{name}» — задайте эталон ФИО, чтобы сверить")
    location = fields.get("location", "")
    if location and prof.city and city_matches(prof.city, location):
        add("city", f"в профиле указан город: {location}")
    elif location and not prof.city:
        add("city", f"в профиле указано местоположение «{location}» — задайте эталон города")
    if fields.get("email"):
        add("email", f"публичный email в профиле: {fields['email']}")

    owner_phones = {phone_e164(p) for p in prof.phones if phone_e164(p)}
    if owner_phones:
        for text in _texts(f.data):
            for m in PHONE_RE.findall(text):
                if phone_e164(m) in owner_phones:
                    add("phone", "ваш номер телефона виден в источнике")

    exps = list(out.values())
    if "real_name" in out and "city" in out:
        for e in exps:
            if e.what in ("real_name", "city"):
                e.severity = max(e.severity, NAME_AND_CITY_BUMP)
    return exps


def city_conflicts(audit: Audit) -> list[dict]:
    """«В 3 источниках один город, в 1 — другой» → оба значения с источником, без схлопывания."""
    seen: dict[str, list[dict]] = {}
    for f in audit.findings:
        if f.status == "not_mine":
            continue
        loc = _profile_fields(f).get("location")
        if loc:
            seen.setdefault(latin_key(loc), []).append({"value": loc, "source": f.source, "finding_id": f.id})
    if len(seen) < 2:
        return []
    return [{"field": "city", "values": [v for vals in seen.values() for v in vals]}]


def apply(audit: Audit, settings: Settings | None = None) -> None:
    audit.exposures = []
    for f in audit.findings:
        if f.status == "not_mine":
            continue  # вы отметили «не мой» — не считаем это раскрытием
        audit.exposures.extend(exposures_for(f, audit))
