"""Диспетчер: факт → модули с подходящим input_type → запуск.

1. Подтверждённый факт (type, value) → в очередь
2. Цикл: факт → модули с подходящим input_type → запуск
3. Найденное → в отчёт; новый факт идёт в очередь, только если он наследует подтверждение
4. Сбой модуля не роняет процесс: «недоступен» + причина
5. Каждый запуск сравнивается с предыдущим: новое / исчезнувшее / изменившееся (diff)
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Optional

import httpx

from ..config import Settings
from ..modules.base import Fact, Module, ModuleResult, RunContext
from ..modules.own_profile import eligible
from . import matcher
from .models import SEARCHABLE_TYPES, Audit, Finding, HistoryEntry, IdentityType, RunRecord, SourceStatus, utcnow
from .queue import FactQueue, RateLimiter, with_retry
from .verify import add_inherited

MODULE_TIMEOUT = 600


@asynccontextmanager
async def default_client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": settings.user_agent},
                                 follow_redirects=True) as client:
        yield client


class _Run:
    """Что произошло за один запуск — для сравнения с предыдущим."""

    def __init__(self, audit: Audit, record: RunRecord):
        self.audit, self.record = audit, record
        self.seen: set[str] = set()
        self.checked: set[tuple[str, str]] = set()  # (модуль, идентификатор), проверенные успешно
        self.compare = record.n > 1  # первый запуск не с чем сравнивать

    def note(self, f: Finding, change: str) -> None:
        if not self.compare:
            return
        self.audit.history.append(HistoryEntry(finding_id=f.id, change=change, run=self.record.n))
        setattr(self.record, change, getattr(self.record, change) + 1)


def _comparable(f: Finding) -> dict:
    """Данные находки без полей, которые добавил разбор ваших страниц (их нет в ответе источника)."""
    if f.type == "profile_url":
        return {k: v for k, v in f.data.items() if k != "fields"}
    return f.data


def _merge(run: _Run, mod: Module, fact: Fact, result: ModuleResult) -> int:
    """Добавить находки; повторный запуск обновляет существующие, сохраняя вашу отметку «мой / не мой»."""
    audit, now = run.audit, utcnow()
    index = {(f.source, f.type, f.value.lower()): f for f in audit.findings}
    added = 0
    for raw in result.findings:
        key = (mod.name, raw.type, raw.value.lower())
        existing = index.get(key)
        if existing:
            run.seen.add(existing.id)
            if existing.gone_at is not None:
                existing.gone_at = None
                run.note(existing, "new")  # снова появилась
            elif _comparable(existing) != raw.data and raw.type != "certificate":
                run.note(existing, "changed")
            existing.url, existing.confidence, existing.last_seen = raw.url, raw.confidence, now
            fields = existing.data.get("fields") if existing.type == "profile_url" else None
            existing.data = dict(raw.data, **({"fields": fields} if fields else {}))
            continue
        f = Finding(type=raw.type, value=raw.value, source=mod.name, url=raw.url, confidence=raw.confidence,
                    status="review" if raw.review else "confirmed", identity_id=fact.identity_id, data=dict(raw.data),
                    last_seen=now)
        audit.findings.append(f)
        index[key] = f
        run.seen.add(f.id)
        run.note(f, "new")
        added += 1
    return added


async def run_audit(
    audit: Audit,
    registry: dict[str, Module],
    settings: Settings,
    only_module: Optional[str] = None,
    client_factory: Callable = default_client,
    on_progress: Optional[Callable[[Audit], None]] = None,
    enricher=None,
    scheduled: bool = False,
) -> Audit:
    ttl = settings.verify_ttl_days
    queue = FactQueue(max_depth=settings.max_depth, max_facts=settings.max_facts)
    limiter = RateLimiter(settings.module_delay)
    progress = on_progress or (lambda a: None)
    record = RunRecord(n=len(audit.runs) + 1, module=only_module, scheduled=scheduled)
    audit.runs.append(record)
    run = _Run(audit, record)
    audit.running = True
    audit.add_log("INFO", f"AUDIT START #{record.n}" + (f" / ONLY {only_module.upper()}" if only_module else "")
                  + (" / ПО РАСПИСАНИЮ" if scheduled else ""))

    for ident in audit.identities:
        if audit.is_verified(ident, ttl):
            queue.push(Fact(ident.type.value, ident.value, ident.id, 0))
        else:
            state = ident.verification_state(ttl)
            audit.add_log("WARN", f"SKIP {ident.type.value}:{ident.value} — {'истёк срок подтверждения' if state == 'expired' else 'не подтверждён'}, модули не запускаются")

    active = [m for m in registry.values() if m.name not in audit.disabled_modules
              and (only_module is None or m.name == only_module)]
    for m in active:
        ok, reason = m.available(settings)
        st = audit.sources.setdefault(m.name, SourceStatus(module=m.name))
        st.state, st.detail = ("queued", "") if ok else ("skipped", reason)
    progress(audit)

    try:
        async with client_factory(settings) as client:
            ctx = RunContext(settings=settings, client=client)
            while (fact := queue.pop()) is not None:
                for mod in active:
                    if mod.input_type != fact.type or not mod.available(settings)[0]:
                        continue
                    await _run_one(run, mod, fact, ctx, limiter, queue, settings)
                    progress(audit)
            if enricher is not None and only_module is None:
                await enrich_own_profiles(audit, enricher, client)
    finally:
        _mark_gone(run)
        for fact, why in queue.dropped:
            audit.add_log("WARN", f"FACT DROPPED {fact.type}:{fact.value} — {why}")
        for st in audit.sources.values():
            if st.state in ("queued", "running"):
                st.state = "done" if st.runs else "idle"
                if not st.runs:
                    st.detail = "нет подтверждённых идентификаторов подходящего типа"
        matcher.apply(audit, settings)
        record.finished_at = utcnow()
        audit.running = False
        diff = f" / DIFF +{record.new} −{record.gone} ~{record.changed}" if run.compare else ""
        audit.add_log("OK", f"AUDIT DONE ....... {len(audit.findings)} FINDINGS / {len(audit.exposures)} EXPOSURES{diff}")
        progress(audit)
    return audit


def _mark_gone(run: _Run) -> None:
    """Источник успешно проверил идентификатор, а находки больше нет → «исчезло»."""
    now = utcnow()
    for f in run.audit.findings:
        if f.gone_at is None and f.id not in run.seen and (f.source, f.identity_id) in run.checked:
            f.gone_at = now
            run.note(f, "gone")


async def enrich_own_profiles(audit: Audit, enricher, client, only: Optional[Finding] = None) -> int:
    ok, reason = enricher.available()
    targets = [only] if only else [f for f in audit.findings if eligible(f)]
    if not targets:
        return 0
    if not ok:
        audit.add_log("INFO", f"OWN PROFILES SKIPPED — {reason}")
        return 0
    n = 0
    for f in targets:
        try:
            fields = await enricher.enrich(f, client)
        except Exception as e:  # noqa: BLE001
            audit.add_log("WARN", f"OWN PROFILE {f.value} — не удалось прочитать: {e}")
            continue
        if fields:
            f.data["fields"] = fields
            n += 1
            audit.add_log("OK", f"OWN PROFILE ....... {f.value}: поля {', '.join(sorted(fields))}")
    return n


async def _run_one(run: _Run, mod: Module, fact: Fact, ctx: RunContext, limiter: RateLimiter,
                   queue: FactQueue, settings: Settings) -> None:
    audit = run.audit
    st = audit.sources.setdefault(mod.name, SourceStatus(module=mod.name))
    st.state, st.detail = "running", f"{fact.type}:{fact.value}"
    audit.add_log("INFO", f"RUN {mod.name.upper()} ....... {fact.type}:{fact.value}")

    async def call():
        await limiter.wait(mod.name)
        return await asyncio.wait_for(mod.run(fact, ctx), timeout=MODULE_TIMEOUT)

    def on_retry(n: int, e: Exception) -> None:
        audit.add_log("WARN", f"RETRY {mod.name.upper()} #{n} — {e}")

    try:
        result = await with_retry(call, settings.module_retries, max(settings.module_delay, 0.5), on_retry)
    except Exception as e:  # noqa: BLE001 — сбой модуля не роняет аудит
        st.state, st.detail = "failed", f"недоступен: {e or type(e).__name__}"
        st.runs += 1
        st.last_run = utcnow()
        audit.add_log("ERROR", f"{mod.name.upper()} FAILED — {e or type(e).__name__}")
        return

    run.checked.add((mod.name, fact.identity_id))
    added = _merge(run, mod, fact, result)
    st.runs += 1
    st.findings += added
    st.last_run = utcnow()
    st.state, st.detail = "done", result.note or f"{len(result.findings)} находок"
    audit.add_log("OK", f"{mod.name.upper()} DONE ....... {len(result.findings)} FOUND / {added} NEW")

    parent = audit.identity(fact.identity_id)
    for nf in result.new_facts:
        if not nf.inherits or nf.type not in SEARCHABLE_TYPES or parent is None:
            audit.add_log("INFO", f"NOT QUEUED {nf.type}:{nf.value} — не наследует подтверждение")
            continue
        child = add_inherited(audit, IdentityType(nf.type), nf.value, parent, f"inherited:{parent.id}")
        if child is None:
            audit.add_log("INFO", f"NOT QUEUED {nf.type}:{nf.value} — вы удалили этот идентификатор")
            continue
        if queue.push(Fact(nf.type, nf.value, child.id, fact.depth + 1)):
            audit.add_log("OK", f"QUEUED {nf.type}:{nf.value} — {nf.reason or 'наследует подтверждение'}")
