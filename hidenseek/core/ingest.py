"""Приём seed-данных. Идентификатор добавляется неподтверждённым — модули он не запускает,
пока не пройдёт подтверждение (core/verify.py)."""
from __future__ import annotations

from .models import Audit, Identity, IdentityType, OwnerProfile
from .normalizer import (DOMAIN_RE, EMAIL_RE, USERNAME_RE, normalize_domain, normalize_email,
                         normalize_username, phone_e164)


class IngestError(ValueError):
    pass


def normalize_identity(type_: str, value: str) -> tuple[IdentityType, str]:
    try:
        t = IdentityType(type_)
    except ValueError as e:
        raise IngestError(
            "Этот тип нельзя подтвердить, поэтому он не запускает поиск. "
            "Телефон, ФИО и город укажите в профиле «это я» — они нужны только для сверки."
        ) from e
    if t == IdentityType.EMAIL:
        v = normalize_email(value)
        if not EMAIL_RE.match(v):
            raise IngestError("Некорректный email")
    elif t == IdentityType.DOMAIN:
        v = normalize_domain(value)
        if not DOMAIN_RE.match(v):
            raise IngestError("Некорректный домен")
    else:
        v = normalize_username(value)
        if not USERNAME_RE.match(v):
            raise IngestError("Ник: 2–64 символа, латиница, цифры, . _ -")
    return t, v


def add_identity(audit: Audit, type_: str, value: str) -> Identity:
    t, v = normalize_identity(type_, value)
    if t == IdentityType.GITHUB:
        raise IngestError("GitHub-аккаунт добавляется только через вход на GitHub (OAuth)")
    if any(i.type == t and i.value.lower() == v.lower() for i in audit.identities):
        raise IngestError("Такой идентификатор уже есть")
    key = Audit.suppress_key(t.value, v)
    if key in audit.suppressed:
        audit.suppressed.remove(key)  # добавили вручную — больше не скрываем
    ident = Identity(type=t, value=v)
    audit.identities.append(ident)
    return ident


def remove_identity(audit: Audit, identity_id: str) -> None:
    """Удаление идентификатора убирает и унаследованные от него, и их находки."""
    doomed = {identity_id}
    changed = True
    while changed:
        changed = False
        for i in audit.identities:
            if i.parent_id in doomed and i.id not in doomed:
                doomed.add(i.id)
                changed = True
    for i in audit.identities:
        # унаследованное само вернётся при следующем аудите — запоминаем, что вы его убрали
        if i.id in doomed and i.parent_id and (key := Audit.suppress_key(i.type.value, i.value)) not in audit.suppressed:
            audit.suppressed.append(key)
    audit.identities = [i for i in audit.identities if i.id not in doomed]
    audit.findings = [f for f in audit.findings if f.identity_id not in doomed]
    kept = {f.id for f in audit.findings}
    audit.exposures = [e for e in audit.exposures if e.finding_id in kept]


def set_profile(audit: Audit, full_name: str, city: str, phones: list[str]) -> OwnerProfile:
    audit.owner_profile = OwnerProfile(
        full_name=(full_name or "").strip()[:200],
        city=(city or "").strip()[:100],
        phones=[p for p in (phone_e164(x) for x in phones or []) if p][:10],
    )
    return audit.owner_profile
