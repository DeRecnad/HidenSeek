"""Модель данных аудита (раздел 3 роадмапа).

Audit
 ├─ owner_profile — ФИО / город / телефоны, только для сверки, поиск не запускают
 ├─ identities    — идентификаторы пользователя + отметка о подтверждении
 ├─ findings      — что найдено (source / url / confidence / found_at / status)
 ├─ exposures     — что именно раскрыто находкой и насколько это серьёзно
 └─ history       — изменения между аудитами (diff — следующий этап)
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = 2


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


class IdentityType(str, Enum):
    EMAIL = "email"
    GITHUB = "github"
    DOMAIN = "domain"
    USERNAME = "username"


# Типы, которые вообще могут запускать модули (раздел 4).
# Телефон, ФИО и город сюда не входят — они живут в owner_profile и служат только эталоном.
SEARCHABLE_TYPES = {t.value for t in IdentityType}


class OwnerProfile(BaseModel):
    full_name: str = ""
    city: str = ""
    phones: list[str] = Field(default_factory=list)


class Identity(BaseModel):
    id: str = Field(default_factory=lambda: new_id("idn"))
    type: IdentityType
    value: str
    verified_by: Optional[str] = None  # email_code | dns_txt | github_oauth | inherited:<idn> | domain_link:<idn> | demo
    verified_at: Optional[datetime] = None
    parent_id: Optional[str] = None  # от какого подтверждённого идентификатора унаследовано
    verify_token: Optional[str] = None  # токен для TXT-записи домена; публичен по своей природе
    added_at: datetime = Field(default_factory=utcnow)

    def is_verified(self, ttl_days: int, now: Optional[datetime] = None) -> bool:
        if not self.verified_by or not self.verified_at:
            return False
        now = now or utcnow()
        return now - self.verified_at <= timedelta(days=ttl_days)

    def verification_state(self, ttl_days: int) -> str:
        if not self.verified_by:
            return "unverified"
        return "verified" if self.is_verified(ttl_days) else "expired"


Exposed = Literal["real_name", "city", "email", "phone", "password", "username", "subdomain"]


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: new_id("fnd"))
    type: str  # profile_url | registered_service | breach | public_email_in_commits | profile_fields | subdomain | certificate
    value: str
    source: str  # имя модуля
    url: Optional[str] = None
    confidence: float = 1.0  # насколько вероятно, что это ВАШ аккаунт
    found_at: datetime = Field(default_factory=utcnow)
    status: Literal["confirmed", "review", "mine", "not_mine"] = "confirmed"
    identity_id: str  # какой подтверждённый идентификатор привёл к находке
    exposes: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    last_seen: Optional[datetime] = None
    gone_at: Optional[datetime] = None  # не найдена при последней успешной проверке источника
    resolved_at: Optional[datetime] = None  # вы отметили «закрыл»: удалил аккаунт, сменил пароль и т.п.

    @property
    def active(self) -> bool:
        return self.gone_at is None and self.status != "not_mine"


class Exposure(BaseModel):
    finding_id: str
    what: str
    severity: int  # 1..4, см. core/report.py
    detail: str = ""


class HistoryEntry(BaseModel):
    finding_id: str
    change: Literal["new", "gone", "changed"]
    run: int = 0
    at: datetime = Field(default_factory=utcnow)


class RunRecord(BaseModel):
    """Один запуск аудита; повторные запуски сравниваются между собой (diff)."""
    n: int
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
    module: Optional[str] = None
    scheduled: bool = False
    new: int = 0
    gone: int = 0
    changed: int = 0


class SourceStatus(BaseModel):
    module: str
    state: Literal["idle", "queued", "running", "done", "failed", "skipped"] = "idle"
    detail: str = ""
    runs: int = 0
    findings: int = 0
    last_run: Optional[datetime] = None


class LogLine(BaseModel):
    at: datetime = Field(default_factory=utcnow)
    level: Literal["OK", "INFO", "WARN", "ERROR"] = "INFO"
    text: str


class Audit(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=lambda: new_id("aud"))
    mode: Literal["real", "demo"] = "real"
    persona: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    save: bool = False
    owner_profile: OwnerProfile = Field(default_factory=OwnerProfile)
    identities: list[Identity] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    exposures: list[Exposure] = Field(default_factory=list)
    history: list[HistoryEntry] = Field(default_factory=list)
    sources: dict[str, SourceStatus] = Field(default_factory=dict)
    disabled_modules: list[str] = Field(default_factory=list)
    suppressed: list[str] = Field(default_factory=list)  # «type:value», удалённые вами унаследованные идентификаторы
    runs: list[RunRecord] = Field(default_factory=list)
    schedule_hours: Optional[int] = None  # периодический повторный аудит
    assistant_consent: bool = False  # разрешено отправлять сводку в Anthropic API
    log: list[LogLine] = Field(default_factory=list)
    running: bool = False

    @staticmethod
    def suppress_key(type_: str, value: str) -> str:
        return f"{type_}:{value.strip().lower()}"

    def identity(self, identity_id: str) -> Optional[Identity]:
        return next((i for i in self.identities if i.id == identity_id), None)

    def is_verified(self, identity: Identity, ttl_days: int) -> bool:
        """Подтверждение действительно, только если не истекло и у всей цепочки родителей тоже."""
        seen: set[str] = set()
        cur: Optional[Identity] = identity
        while cur:
            if cur.id in seen or not cur.is_verified(ttl_days):
                return False
            if cur.verified_by == "demo" and self.mode != "demo":
                return False  # синтетическое подтверждение действует только в учебном режиме
            seen.add(cur.id)
            if not cur.parent_id:
                return True
            cur = self.identity(cur.parent_id)
        return False  # родитель удалён — подтверждение не наследуется

    def finding(self, finding_id: str) -> Optional[Finding]:
        return next((f for f in self.findings if f.id == finding_id), None)

    def add_log(self, level: str, text: str) -> None:
        self.log.append(LogLine(level=level, text=text))
        del self.log[:-500]
        self.updated_at = utcnow()
